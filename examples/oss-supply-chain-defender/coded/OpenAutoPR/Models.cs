namespace AuroraSupplyChainDefender.GitHub;

/// <summary>
/// One vulnerability finding produced by the upstream branches of the
/// Open-Source Supply-Chain Defender process (vulnerability lookup,
/// maintainer health, etc.).
/// </summary>
/// <remarks>
/// Consumed by <see cref="Open"/> to open a SemVer-MINOR auto-PR when the
/// finding's severity meets <see cref="SeverityFloor"/>. Field shape mirrors
/// the sibling <c>OpenPatchPR</c> input so the two coded workflows can be
/// driven from the same Maestro variable (<c>vuln_findings</c>) without
/// per-task adapters.
/// </remarks>
public sealed class VulnFinding
{
    /// <summary>Owner of the GitHub repository (organisation or user login).</summary>
    public string RepositoryOwner { get; set; } = string.Empty;

    /// <summary>Repository name (without the owner prefix).</summary>
    public string RepositoryName { get; set; } = string.Empty;

    /// <summary>Default branch the PR targets (e.g., <c>main</c>).</summary>
    public string BaseBranch { get; set; } = "main";

    /// <summary>Package ecosystem: <c>"npm"</c>, <c>"pypi"</c>, etc.</summary>
    public string Ecosystem { get; set; } = string.Empty;

    /// <summary>Package name being bumped.</summary>
    public string PackageName { get; set; } = string.Empty;

    /// <summary>Currently-pinned version in the lockfile.</summary>
    public string CurrentVersion { get; set; } = string.Empty;

    /// <summary>Latest upstream version available on the registry.</summary>
    public string UpstreamLatest { get; set; } = string.Empty;

    /// <summary>
    /// Path of the manifest file the bump rewrites — e.g.,
    /// <c>package.json</c>, <c>requirements.txt</c>. The workflow does a
    /// straight string replace of <see cref="CurrentVersion"/> with the
    /// computed minor bump inside this file's contents.
    /// </summary>
    public string ManifestPath { get; set; } = string.Empty;

    /// <summary>CVE or advisory identifier surfaced for context in the PR body.</summary>
    public string AdvisoryId { get; set; } = string.Empty;

    /// <summary>
    /// Severity floor that gates this workflow. <see cref="Open"/> only opens
    /// PRs for findings whose severity meets or exceeds this floor; default is
    /// <c>"high"</c>. Field is on the input (rather than baked into the
    /// workflow) so the same coded entry point can be reused with a lower
    /// floor for dry-run dashboards.
    /// </summary>
    public string SeverityFloor { get; set; } = "high";
}

/// <summary>
/// Result emitted by <see cref="Open"/>. The Maestro variable
/// <c>pr_url</c> (see <c>bindings.json::tasks.OpenAutoPR</c>) binds to
/// <see cref="PrUrl"/>.
/// </summary>
public sealed class PrResult
{
    /// <summary>HTTPS URL of the opened (or pre-existing idempotent) PR.</summary>
    public string PrUrl { get; set; } = string.Empty;

    /// <summary>PR number on the repository.</summary>
    public int PrNumber { get; set; }

    /// <summary>Branch the PR was opened from.</summary>
    public string HeadBranch { get; set; } = string.Empty;

    /// <summary>Base branch the PR targets.</summary>
    public string BaseBranch { get; set; } = string.Empty;

    /// <summary>The version the bump moved <see cref="VulnFinding.CurrentVersion"/> to.</summary>
    public string AppliedVersion { get; set; } = string.Empty;

    /// <summary>
    /// True when the workflow re-discovered a PR from a previous run instead
    /// of opening a new one. Idempotency signal: re-running OpenAutoPR with
    /// the same finding never opens a duplicate PR.
    /// </summary>
    public bool Idempotent { get; set; }
}
