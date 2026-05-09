using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using UiPath.CodedWorkflows;

namespace AuroraSupplyChainDefender.Notify;

/// <summary>
/// Abstraction over weekly-digest persistence so <see cref="AppendToDigest"/>
/// is testable outside the UiPath runtime and can swap between in-memory
/// storage (unit tests) and a Storage Bucket (production).
/// </summary>
public interface IDigestStore
{
    /// <summary>
    /// Loads the digest entries for the given date. Returns an empty list
    /// if no digest exists yet.
    /// </summary>
    List<DigestEntry> Load(DateTime date);

    /// <summary>
    /// Persists the digest entries for the given date.
    /// </summary>
    void Save(DateTime date, List<DigestEntry> entries);
}

/// <summary>
/// In-memory digest store for offline unit tests.
/// </summary>
public sealed class MemoryDigestStore : IDigestStore
{
    private readonly Dictionary<string, List<DigestEntry>> _store = new();

    public List<DigestEntry> Load(DateTime date)
    {
        string key = DateKey(date);
        return _store.TryGetValue(key, out List<DigestEntry>? entries)
            ? new List<DigestEntry>(entries)
            : new List<DigestEntry>();
    }

    public void Save(DateTime date, List<DigestEntry> entries)
    {
        _store[DateKey(date)] = new List<DigestEntry>(entries);
    }

    private static string DateKey(DateTime date) => date.ToString("yyyy-MM-dd");
}

/// <summary>
/// Appends a finding to the running weekly digest so <see cref="SendDigest"/>
/// can batch-post at the end of the scan window.
/// </summary>
/// <remarks>
/// <para>
/// Implements the "Notify.AppendToDigest" service task from the BPMN
/// (<c>process.bpmn</c>). Called once per fan-out finding before
/// <see cref="SendDigest"/> fires.
/// </para>
/// <para>
/// The digest key is <c>digest-{yyyy-MM-dd}.json</c> (UTC date). Identical
/// entries — same <see cref="DigestEntry.Finding"/>, <see cref="DigestEntry.Ecosystem"/>,
/// and <see cref="DigestEntry.Severity"/> — are deduplicated.
/// </para>
/// </remarks>
public class AppendToDigest : CodedWorkflowBase
{
    private readonly IDigestStore _store;

    /// <summary>
    /// Default constructor used by the UiPath runtime. Uses the in-memory
    /// store; in production this would be replaced by a Storage Bucket-backed
    /// implementation via Orchestrator Assets.
    /// </summary>
    public AppendToDigest()
        : this(new MemoryDigestStore())
    {
    }

    /// <summary>
    /// Test-only constructor that accepts an <see cref="IDigestStore"/>
    /// so unit tests can inject a hermetic in-memory store.
    /// </summary>
    /// <param name="store">Digest persistence backend.</param>
    public AppendToDigest(IDigestStore store)
    {
        _store = store ?? throw new ArgumentNullException(nameof(store));
    }

    /// <summary>
    /// Workflow entry point. Appends <paramref name="in_objEntry"/> to
    /// today's digest (deduplicating) and returns the new digest size.
    /// </summary>
    /// <param name="in_objEntry">The finding to append.</param>
    /// <returns>The number of entries in the digest after appending.</returns>
    /// <exception cref="ArgumentNullException">
    /// Thrown if <paramref name="in_objEntry"/> is null.
    /// </exception>
    [Workflow]
    public int Execute(DigestEntry in_objEntry)
    {
        if (in_objEntry is null)
            throw new ArgumentNullException(nameof(in_objEntry));

        SafeLog(
            "Starting Notify.AppendToDigest",
            LogLevel.Info,
            new Dictionary<string, object>
            {
                ["ecosystem"] = in_objEntry.Ecosystem,
                ["severity"] = in_objEntry.Severity,
            });

        DateTime today = DateTime.UtcNow.Date;
        List<DigestEntry> entries = _store.Load(today);

        // Dedup: same Finding + Ecosystem + Severity = duplicate.
        if (!IsDuplicate(entries, in_objEntry))
        {
            entries.Add(in_objEntry);
        }

        _store.Save(DateTime.UtcNow.Date, entries);
        int out_intDigestSize = entries.Count;

        SafeLog(
            "Completed Notify.AppendToDigest",
            LogLevel.Info,
            new Dictionary<string, object> { ["digestSize"] = out_intDigestSize });

        return out_intDigestSize;
    }

    // ── pure helper (R.K.01) ───────────────────────────────────────────

    /// <summary>
    /// Returns true if <paramref name="entry"/> is already present in
    /// <paramref name="existing"/> based on Finding + Ecosystem + Severity
    /// equality (case-insensitive).
    /// </summary>
    public static bool IsDuplicate(List<DigestEntry> existing, DigestEntry entry)
    {
        return existing.Any(e =>
            string.Equals(e.Finding, entry.Finding, StringComparison.OrdinalIgnoreCase) &&
            string.Equals(e.Ecosystem, entry.Ecosystem, StringComparison.OrdinalIgnoreCase) &&
            string.Equals(e.Severity, entry.Severity, StringComparison.OrdinalIgnoreCase));
    }

    // ── SafeLog ────────────────────────────────────────────────────────

    /// <summary>
    /// Wraps the base-class <c>Log</c> in a try/catch so the workflow logic
    /// stays unit-testable outside the UiPath runtime, where the logger
    /// service container is not wired up. R.L.03 still holds in production.
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
}
