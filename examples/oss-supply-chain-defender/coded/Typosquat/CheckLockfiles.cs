using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using UiPath.CodedWorkflows;

namespace AuroraSupplyChainDefender.Typosquat;

/// <summary>
/// TyposquatCheck Coded Workflow. Entry point for the BPMN
/// <c>TyposquatCheck</c> service task in the Open-Source Supply-Chain Defender
/// process (see <c>examples/oss-supply-chain-defender/process.bpmn</c> and
/// <c>bindings.json::tasks.TyposquatCheck</c>: package
/// <c>AuroraSupplyChainDefender</c>, entry <c>Typosquat.CheckLockfiles</c>).
/// </summary>
/// <remarks>
/// <para>
/// For each <see cref="LockfileEntry"/>, computes the Levenshtein distance to
/// every package on the allow-list for that entry's ecosystem. If the minimum
/// distance is &gt; 0 (i.e., not an exact match) and ≤
/// <see cref="MaxDistanceThreshold"/>, the entry is flagged as a typosquat
/// suspect, paired with the closest legitimate package name.
/// </para>
/// <para>
/// Allow-list lookups are case-insensitive (lower-cased before comparison) so
/// that <c>Lodash</c> still matches <c>lodash</c> exactly. The allow-list
/// itself is loaded once per workflow instance from <c>AllowList.json</c>;
/// subsequent calls reuse the cached value.
/// </para>
/// </remarks>
public class CheckLockfiles : CodedWorkflowBase
{
    /// <summary>
    /// Levenshtein-distance ceiling for "near miss". 1 catches single typos
    /// (<c>reqests</c> → <c>requests</c>); 2 catches double-letter mistakes
    /// (<c>lodaash</c> → <c>lodash</c>) — the canonical typosquat patterns.
    /// </summary>
    public const int MaxDistanceThreshold = 2;

    private const string DefaultAllowListFileName = "AllowList.json";

    private AllowList? _cachedAllowList;
    private readonly string? _allowListPathOverride;

    /// <summary>
    /// Default constructor used by the UiPath runtime.
    /// </summary>
    public CheckLockfiles()
    {
    }

    /// <summary>
    /// Test-only constructor that lets the test fixture inject a path to a
    /// hermetic <c>AllowList.json</c> instead of relying on the file copied
    /// next to the assembly at runtime.
    /// </summary>
    /// <param name="allowListPath">Absolute path to a JSON allow-list file.</param>
    public CheckLockfiles(string allowListPath)
    {
        _allowListPathOverride = allowListPath;
    }

    /// <summary>
    /// Workflow entry point. Returns the typosquat suspects for the given
    /// lockfile entries.
    /// </summary>
    /// <param name="in_dt_Lockfiles">
    /// Structured lockfile rows produced by <c>ResolveLockfiles</c>. Argument
    /// name follows REFramework R.N.02 (<c>in_</c> direction prefix).
    /// </param>
    /// <returns>
    /// Zero or more <see cref="TyposquatSuspect"/> records — one per flagged
    /// entry. The Maestro variable <c>typosquat_suspects</c>
    /// (see <c>bindings.json</c>) is bound to this return value.
    /// </returns>
    [Workflow]
    public List<TyposquatSuspect> Execute(List<LockfileEntry> in_dt_Lockfiles)
    {
        SafeLog(
            "Starting Typosquat.CheckLockfiles",
            LogLevel.Info,
            new Dictionary<string, object> { ["entryCount"] = in_dt_Lockfiles?.Count ?? 0 });

        var out_dt_Suspects = new List<TyposquatSuspect>();
        if (in_dt_Lockfiles is null || in_dt_Lockfiles.Count == 0)
        {
            SafeLog(
                "Completed Typosquat.CheckLockfiles (no entries)",
                LogLevel.Info,
                new Dictionary<string, object> { ["suspectCount"] = 0 });
            return out_dt_Suspects;
        }

        AllowList allowList = LoadAllowList();

        foreach (LockfileEntry entry in in_dt_Lockfiles)
        {
            if (entry is null || string.IsNullOrWhiteSpace(entry.Name) || string.IsNullOrWhiteSpace(entry.Ecosystem))
            {
                continue;
            }

            IReadOnlyList<string>? allowed = allowList.ForEcosystem(entry.Ecosystem);
            if (allowed is null || allowed.Count == 0)
            {
                // Unknown ecosystem: not in scope for this checker.
                continue;
            }

            string suspectName = entry.Name.Trim();
            string suspectKey = suspectName.ToLowerInvariant();
            int bestDistance = int.MaxValue;
            string bestMatch = string.Empty;

            foreach (string legitName in allowed)
            {
                int distance = Levenshtein.Distance(suspectKey, legitName.ToLowerInvariant());
                if (distance < bestDistance)
                {
                    bestDistance = distance;
                    bestMatch = legitName;
                    if (bestDistance == 0)
                    {
                        break; // exact match; cannot improve
                    }
                }
            }

            if (bestDistance == 0)
            {
                // Exact match → legitimate, not a typosquat.
                continue;
            }

            if (bestDistance <= MaxDistanceThreshold)
            {
                out_dt_Suspects.Add(new TyposquatSuspect
                {
                    Ecosystem = entry.Ecosystem,
                    SuspectName = suspectName,
                    NearestLegitimate = bestMatch,
                    Distance = bestDistance,
                });
            }
        }

        SafeLog(
            "Completed Typosquat.CheckLockfiles",
            LogLevel.Info,
            new Dictionary<string, object> { ["suspectCount"] = out_dt_Suspects.Count });

        return out_dt_Suspects;
    }

    /// <summary>
    /// Wraps the base-class <c>Log</c> in a try/catch so the workflow logic
    /// stays unit-testable outside the UiPath runtime, where the logger
    /// service container is not wired up. R.L.03 still holds in production:
    /// when the runtime supplies a logger, this calls it; under unit tests it
    /// silently no-ops instead of throwing a <see cref="NullReferenceException"/>.
    /// </summary>
    private void SafeLog(string message, LogLevel level, IDictionary<string, object> fields)
    {
        try
        {
            Log(message, level, fields);
        }
        catch (NullReferenceException)
        {
            // Runtime not initialised (e.g., xUnit harness). Discard.
        }
    }

    /// <summary>
    /// Lazily loads the allow-list from disk. The read is wrapped in a
    /// try/catch per R.E.01 — file I/O is an external boundary — and a
    /// failure surfaces as an explicit <see cref="InvalidOperationException"/>
    /// rather than a swallowed default that would silently mask every
    /// suspect.
    /// </summary>
    private AllowList LoadAllowList()
    {
        if (_cachedAllowList is not null)
        {
            return _cachedAllowList;
        }

        string path = ResolveAllowListPath();
        try
        {
            string json = File.ReadAllText(path);
            AllowList? parsed = JsonSerializer.Deserialize<AllowList>(
                json,
                new JsonSerializerOptions { PropertyNameCaseInsensitive = true });
            if (parsed is null)
            {
                throw new InvalidOperationException(
                    $"AllowList.json at '{path}' deserialised to null.");
            }
            _cachedAllowList = parsed;
            return parsed;
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or JsonException)
        {
            SafeLog(
                $"Failed to load AllowList.json from '{path}': {ex.Message}",
                LogLevel.Error,
                new Dictionary<string, object> { ["path"] = path, ["error"] = ex.GetType().Name });
            throw new InvalidOperationException(
                $"TyposquatCheck could not load allow-list from '{path}'.", ex);
        }
    }

    private string ResolveAllowListPath()
    {
        if (!string.IsNullOrEmpty(_allowListPathOverride))
        {
            return _allowListPathOverride!;
        }

        // The csproj copies AllowList.json next to the workflow assembly via
        // <None Update="AllowList.json" CopyToOutputDirectory="PreserveNewest" />.
        string assemblyDir = Path.GetDirectoryName(typeof(CheckLockfiles).Assembly.Location)
                             ?? AppContext.BaseDirectory;
        return Path.Combine(assemblyDir, DefaultAllowListFileName);
    }

    /// <summary>
    /// JSON-shaped allow-list. Public for test injection.
    /// </summary>
    public sealed class AllowList
    {
        public List<string> Npm { get; set; } = new();
        public List<string> Pypi { get; set; } = new();

        public IReadOnlyList<string>? ForEcosystem(string ecosystem)
        {
            return ecosystem?.Trim().ToLowerInvariant() switch
            {
                "npm" => Npm,
                "pypi" => Pypi,
                _ => null,
            };
        }
    }
}
