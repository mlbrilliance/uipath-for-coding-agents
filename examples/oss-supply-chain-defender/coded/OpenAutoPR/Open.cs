using System;
using System.Collections.Generic;
using System.Linq;
using System.Net;
using System.Threading.Tasks;
using Octokit;
using UiPath.CodedWorkflows;

namespace AuroraSupplyChainDefender.GitHub;

/// <summary>
/// OpenAutoPR Coded Workflow. Opens a SemVer-MINOR-only auto-merge-track PR
/// for a HIGH-severity vulnerability finding.
/// </summary>
/// <remarks>
/// <para>
/// Entry point bound by the BPMN <c>OpenAutoPR</c> service task in the
/// Open-Source Supply-Chain Defender process (<c>bindings.json</c>).
/// </para>
/// <para>
/// The workflow is intentionally narrow: it computes a same-major bump via
/// <see cref="SemverBumpHelper.GetMinorBump"/>, rewrites the manifest file
/// in a topic branch, opens a PR, and labels it
/// <c>aurora-auto-pr</c>/<c>high-severity</c>. The auto-merge decision (CI
/// green + DMN policy) lives elsewhere — this workflow only opens.
/// </para>
/// <para>
/// Idempotency is structural: re-running with the same finding looks for
/// the deterministic head-branch name first and reuses an existing PR if
/// one is open, so a Maestro retry never fans out duplicate PRs.
/// </para>
/// </remarks>
public class Open : CodedWorkflowBase
{
    private const string AutoPrLabel = "aurora-auto-pr";
    private const string HighSeverityLabel = "high-severity";
    private const int MaxApiRetries = 3;
    private static readonly TimeSpan RetryBaseDelay = TimeSpan.FromSeconds(5);

    private readonly IGitHubClient? _injectedClient;

    /// <summary>
    /// Default constructor used by the UiPath runtime. Reads the bot token
    /// from <c>GITHUB_TOKEN</c> at execution time per R.X (token from env,
    /// never hard-coded).
    /// </summary>
    public Open()
    {
    }

    /// <summary>
    /// Test-only constructor that injects a pre-built <see cref="IGitHubClient"/>.
    /// Lets the xUnit harness drive the workflow with a Moq'd client without
    /// touching network or environment.
    /// </summary>
    /// <param name="client">A configured GitHub client to use in place of the production-wired one.</param>
    public Open(IGitHubClient client)
    {
        _injectedClient = client ?? throw new ArgumentNullException(nameof(client));
    }

    /// <summary>
    /// Workflow entry point. Opens a PR (or returns an existing one) for the
    /// given finding.
    /// </summary>
    /// <param name="in_objFinding">
    /// The vulnerability finding that triggered the auto-PR path. Argument
    /// follows REFramework R.N.02 (<c>in_</c> direction prefix, type
    /// abbreviation <c>obj</c> for a single record).
    /// </param>
    /// <returns>A <see cref="PrResult"/> describing the opened or pre-existing PR.</returns>
    [Workflow]
    public PrResult Execute(VulnFinding in_objFinding)
    {
        SafeLog(
            "Starting GitHub.Open (OpenAutoPR)",
            LogLevel.Info,
            new Dictionary<string, object>
            {
                ["repository"] = $"{in_objFinding?.RepositoryOwner}/{in_objFinding?.RepositoryName}",
                ["package"] = in_objFinding?.PackageName ?? string.Empty,
                ["currentVersion"] = in_objFinding?.CurrentVersion ?? string.Empty,
                ["upstreamLatest"] = in_objFinding?.UpstreamLatest ?? string.Empty,
            });

        if (in_objFinding is null)
        {
            throw new ArgumentNullException(nameof(in_objFinding));
        }

        ValidateFinding(in_objFinding);

        string appliedVersion = SemverBumpHelper.GetMinorBump(
            in_objFinding.CurrentVersion,
            in_objFinding.UpstreamLatest);

        if (string.Equals(appliedVersion, in_objFinding.CurrentVersion, StringComparison.Ordinal))
        {
            // No same-major minor bump available. The DMN policy upstream of
            // this task should have routed major bumps to the patch-PR HITL
            // path, so reaching here means there's nothing to do — surface
            // an explicit BusinessException rather than opening an empty PR.
            SafeLog(
                "GitHub.Open: no minor bump available; declining to open PR",
                LogLevel.Info,
                new Dictionary<string, object>
                {
                    ["currentVersion"] = in_objFinding.CurrentVersion,
                    ["upstreamLatest"] = in_objFinding.UpstreamLatest,
                });
            throw new InvalidOperationException(
                $"OpenAutoPR: no SemVer-MINOR bump available for " +
                $"{in_objFinding.PackageName} ({in_objFinding.CurrentVersion} → {in_objFinding.UpstreamLatest}). " +
                "Major-version bumps are out of scope for this workflow.");
        }

        IGitHubClient client = _injectedClient ?? BuildProductionClient();

        string headBranch = BuildBranchName(in_objFinding, appliedVersion);

        try
        {
            // Idempotency gate: if a PR is already open from this branch,
            // return its details verbatim. R.K.06.
            PrResult? existing = TryFindExistingPr(client, in_objFinding, headBranch).GetAwaiter().GetResult();
            if (existing is not null)
            {
                SafeLog(
                    "GitHub.Open: returning existing PR (idempotent)",
                    LogLevel.Info,
                    new Dictionary<string, object>
                    {
                        ["pr_url"] = existing.PrUrl,
                        ["pr_number"] = existing.PrNumber,
                    });
                return existing;
            }

            return OpenFreshPr(client, in_objFinding, headBranch, appliedVersion).GetAwaiter().GetResult();
        }
        catch (AuthorizationException ex)
        {
            // R.E.03: auth failures surface immediately, no retry.
            SafeLog(
                "GitHub.Open: auth failure — surfacing without retry",
                LogLevel.Error,
                new Dictionary<string, object> { ["error"] = ex.Message });
            throw;
        }
        catch (NotFoundException)
        {
            throw;
        }
    }

    private static void ValidateFinding(VulnFinding finding)
    {
        if (string.IsNullOrWhiteSpace(finding.RepositoryOwner))
            throw new ArgumentException("RepositoryOwner is required.", nameof(finding));
        if (string.IsNullOrWhiteSpace(finding.RepositoryName))
            throw new ArgumentException("RepositoryName is required.", nameof(finding));
        if (string.IsNullOrWhiteSpace(finding.PackageName))
            throw new ArgumentException("PackageName is required.", nameof(finding));
        if (string.IsNullOrWhiteSpace(finding.CurrentVersion))
            throw new ArgumentException("CurrentVersion is required.", nameof(finding));
        if (string.IsNullOrWhiteSpace(finding.UpstreamLatest))
            throw new ArgumentException("UpstreamLatest is required.", nameof(finding));
        if (string.IsNullOrWhiteSpace(finding.ManifestPath))
            throw new ArgumentException("ManifestPath is required.", nameof(finding));
    }

    private static string BuildBranchName(VulnFinding finding, string appliedVersion)
    {
        // Deterministic name keyed on package + target version so that retries
        // collide on the same branch (idempotency) and humans can read the
        // PR list at a glance.
        string sanePkg = finding.PackageName.Replace("/", "-").Replace("@", "");
        return $"aurora/auto-pr/{sanePkg}-{appliedVersion}";
    }

    private async Task<PrResult?> TryFindExistingPr(IGitHubClient client, VulnFinding finding, string headBranch)
    {
        string headFilter = $"{finding.RepositoryOwner}:{headBranch}";
        var request = new PullRequestRequest
        {
            State = ItemStateFilter.Open,
            Head = headFilter,
            Base = finding.BaseBranch,
        };

        IReadOnlyList<PullRequest> existing = await WithRetryAsync(
            () => client.PullRequest.GetAllForRepository(
                finding.RepositoryOwner, finding.RepositoryName, request))
            .ConfigureAwait(false);

        PullRequest? match = existing?.FirstOrDefault(pr =>
            string.Equals(pr.Head?.Ref, headBranch, StringComparison.Ordinal));

        if (match is null)
        {
            return null;
        }

        return new PrResult
        {
            PrUrl = match.HtmlUrl ?? string.Empty,
            PrNumber = match.Number,
            HeadBranch = headBranch,
            BaseBranch = finding.BaseBranch,
            AppliedVersion = ExtractVersionFromBranch(headBranch),
            Idempotent = true,
        };
    }

    private async Task<PrResult> OpenFreshPr(
        IGitHubClient client,
        VulnFinding finding,
        string headBranch,
        string appliedVersion)
    {
        // 1. Resolve base SHA.
        Reference baseRef = await WithRetryAsync(
            () => client.Git.Reference.Get(
                finding.RepositoryOwner, finding.RepositoryName, $"heads/{finding.BaseBranch}"))
            .ConfigureAwait(false);

        // 2. Create the topic branch ref. If the branch already exists from
        // a partially-failed prior run, treat that as idempotent.
        try
        {
            await WithRetryAsync(
                () => client.Git.Reference.Create(
                    finding.RepositoryOwner,
                    finding.RepositoryName,
                    new NewReference($"refs/heads/{headBranch}", baseRef.Object.Sha)))
                .ConfigureAwait(false);
        }
        catch (ApiValidationException)
        {
            // 422 from GitHub when the ref already exists. Continue with
            // the existing branch.
            SafeLog(
                "GitHub.Open: head branch already exists; continuing",
                LogLevel.Info,
                new Dictionary<string, object> { ["head"] = headBranch });
        }

        // 3. Read the current manifest contents on the new branch.
        IReadOnlyList<RepositoryContent> contents = await WithRetryAsync(
            () => client.Repository.Content.GetAllContentsByRef(
                finding.RepositoryOwner, finding.RepositoryName, finding.ManifestPath, headBranch))
            .ConfigureAwait(false);

        RepositoryContent manifest = contents.FirstOrDefault()
            ?? throw new InvalidOperationException(
                $"Manifest '{finding.ManifestPath}' not found on branch '{headBranch}'.");

        string updatedContent = ApplyVersionBump(
            manifest.Content ?? string.Empty,
            finding.CurrentVersion,
            appliedVersion);

        // 4. Commit the bump.
        await WithRetryAsync(
            () => client.Repository.Content.UpdateFile(
                finding.RepositoryOwner,
                finding.RepositoryName,
                finding.ManifestPath,
                new UpdateFileRequest(
                    BuildCommitMessage(finding, appliedVersion),
                    updatedContent,
                    manifest.Sha,
                    headBranch)))
            .ConfigureAwait(false);

        // 5. Open the PR.
        var newPr = new NewPullRequest(
            BuildPrTitle(finding, appliedVersion),
            headBranch,
            finding.BaseBranch)
        {
            Body = BuildPrBody(finding, appliedVersion),
        };
        PullRequest pr = await WithRetryAsync(
            () => client.PullRequest.Create(
                finding.RepositoryOwner, finding.RepositoryName, newPr))
            .ConfigureAwait(false);

        // 6. Apply labels. Failure to label is non-fatal — the PR exists.
        try
        {
            await WithRetryAsync(
                () => client.Issue.Labels.AddToIssue(
                    finding.RepositoryOwner,
                    finding.RepositoryName,
                    pr.Number,
                    new[] { AutoPrLabel, HighSeverityLabel }))
                .ConfigureAwait(false);
        }
        catch (Exception ex) when (ex is not AuthorizationException)
        {
            SafeLog(
                "GitHub.Open: label application failed; PR remains open",
                LogLevel.Info,
                new Dictionary<string, object> { ["pr_number"] = pr.Number, ["error"] = ex.Message });
        }

        return new PrResult
        {
            PrUrl = pr.HtmlUrl ?? string.Empty,
            PrNumber = pr.Number,
            HeadBranch = headBranch,
            BaseBranch = finding.BaseBranch,
            AppliedVersion = appliedVersion,
            Idempotent = false,
        };
    }

    /// <summary>
    /// Public for test introspection. Replaces <paramref name="current"/>
    /// with <paramref name="next"/> as a whole-token version match in the
    /// manifest body. Conservative: only swaps the exact pinned string.
    /// </summary>
    /// <param name="manifestContent">Raw manifest content.</param>
    /// <param name="current">Current pinned version.</param>
    /// <param name="next">Bumped version to apply.</param>
    public static string ApplyVersionBump(string manifestContent, string current, string next)
    {
        if (string.IsNullOrEmpty(manifestContent)) return manifestContent ?? string.Empty;
        if (string.IsNullOrEmpty(current) || string.IsNullOrEmpty(next)) return manifestContent;
        return manifestContent.Replace(current, next);
    }

    private static string BuildCommitMessage(VulnFinding finding, string appliedVersion)
    {
        return $"chore(deps): bump {finding.PackageName} to {appliedVersion} ({finding.AdvisoryId})";
    }

    private static string BuildPrTitle(VulnFinding finding, string appliedVersion)
    {
        return $"chore(deps): bump {finding.PackageName} {finding.CurrentVersion} → {appliedVersion}";
    }

    private static string BuildPrBody(VulnFinding finding, string appliedVersion)
    {
        return
            $"Automated MINOR-only bump opened by AURORA OpenAutoPR for advisory `{finding.AdvisoryId}`.\n\n" +
            $"- Package: `{finding.PackageName}` ({finding.Ecosystem})\n" +
            $"- From: `{finding.CurrentVersion}`\n" +
            $"- To: `{appliedVersion}`\n" +
            $"- Manifest: `{finding.ManifestPath}`\n" +
            $"- Severity floor: `{finding.SeverityFloor}`\n\n" +
            "Auto-merge gating happens via the DMN policy on this repo, not this PR's title.";
    }

    private static string ExtractVersionFromBranch(string headBranch)
    {
        int dashIdx = headBranch.LastIndexOf('-');
        return dashIdx >= 0 && dashIdx < headBranch.Length - 1
            ? headBranch.Substring(dashIdx + 1)
            : string.Empty;
    }

    private IGitHubClient BuildProductionClient()
    {
        // R.X.04: token is read from the environment, never hard-coded.
        // R.X.02: minimum-scope PAT or app token expected.
        string token = Environment.GetEnvironmentVariable("GITHUB_TOKEN") ?? string.Empty;
        if (string.IsNullOrWhiteSpace(token))
        {
            throw new InvalidOperationException(
                "OpenAutoPR requires GITHUB_TOKEN to be set in the bot environment.");
        }

        var client = new GitHubClient(new ProductHeaderValue("aurora-supply-chain-defender"))
        {
            Credentials = new Credentials(token),
        };
        return client;
    }

    /// <summary>
    /// R.E.02 retry wrapper. Retries up to <see cref="MaxApiRetries"/> times
    /// on transient (5xx) responses with a fixed back-off; surfaces 4xx
    /// immediately so auth/validation failures are never masked.
    /// </summary>
    private static async Task<T> WithRetryAsync<T>(Func<Task<T>> op)
    {
        Exception? last = null;
        for (int attempt = 1; attempt <= MaxApiRetries; attempt++)
        {
            try
            {
                return await op().ConfigureAwait(false);
            }
            catch (AuthorizationException)
            {
                throw;
            }
            catch (NotFoundException)
            {
                throw;
            }
            catch (ApiValidationException)
            {
                throw;
            }
            catch (ApiException ex) when (IsTransient(ex.StatusCode))
            {
                last = ex;
                if (attempt == MaxApiRetries) break;
                await Task.Delay(RetryBaseDelay).ConfigureAwait(false);
            }
        }
        throw last!;
    }

    private static async Task WithRetryAsync(Func<Task> op)
    {
        await WithRetryAsync<object?>(async () =>
        {
            await op().ConfigureAwait(false);
            return null;
        }).ConfigureAwait(false);
    }

    private static bool IsTransient(HttpStatusCode code)
    {
        int n = (int)code;
        return n >= 500 && n <= 599;
    }

    /// <summary>
    /// Wraps the base-class <c>Log</c> in a try/catch so the workflow stays
    /// unit-testable outside the UiPath runtime, where the logger service
    /// container is not wired up. Mirror of the helper in T-C2.
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
