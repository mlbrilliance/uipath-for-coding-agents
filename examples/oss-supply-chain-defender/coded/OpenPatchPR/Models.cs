using System.Collections.Generic;

namespace AuroraSupplyChainDefender.GitHub;

/// <summary>
/// One vulnerability finding produced by the upstream Vuln-Lookup branch of
/// the supply-chain-defender process. Drives the version-bump computed by
/// <see cref="BumpHelper"/> and the citation block in the PR body.
/// </summary>
/// <remarks>
/// Produced by Vuln-Lookup (NVD / OSV / GitHub Advisory union) and consumed by
/// the Critical sub-process step that opens a patch PR. Severity is the value
/// from the DMN severity-matrix decision; <see cref="Open"/> opens a PR
/// only for Critical findings — the High path goes through OpenAutoPR (T-C6).
/// </remarks>
public sealed class VulnFinding
{
    /// <summary>Package ecosystem: <c>"npm"</c> or <c>"pypi"</c>.</summary>
    public string Ecosystem { get; set; } = string.Empty;

    /// <summary>Package name (lockfile-shaped, e.g., <c>"lodash"</c>).</summary>
    public string Package { get; set; } = string.Empty;

    /// <summary>Currently installed version string, e.g., <c>"4.17.20"</c>.</summary>
    public string CurrentVersion { get; set; } = string.Empty;

    /// <summary>SemVer-aware fixed version recommended by the advisory.</summary>
    public string FixedVersion { get; set; } = string.Empty;

    /// <summary>CVE identifier, e.g., <c>"CVE-2021-23337"</c>. Optional.</summary>
    public string Cve { get; set; } = string.Empty;

    /// <summary>Severity bucket from the DMN matrix: Critical, High, Medium, Low.</summary>
    public string Severity { get; set; } = string.Empty;
}

/// <summary>
/// The proposed patch diff for a finding. <see cref="Files"/> is a map of
/// repository-relative file path → new full file content; the workflow either
/// creates each file (if it does not yet exist on the patch branch) or updates
/// it in place.
/// </summary>
public sealed class ProposedDiff
{
    /// <summary>
    /// Map of repository-relative path → new file content (UTF-8 string).
    /// Empty values are allowed and mean "create empty file"; null values are
    /// rejected as ill-formed.
    /// </summary>
    public Dictionary<string, string> Files { get; set; } = new();

    /// <summary>
    /// Optional human-readable URL pointing at the upstream diff (e.g., the
    /// release-notes anchor). Cited in the PR body when non-empty.
    /// </summary>
    public string Url { get; set; } = string.Empty;

    /// <summary>One-line summary of the change. Used as the PR title suffix.</summary>
    public string Summary { get; set; } = string.Empty;
}

/// <summary>
/// Result of opening a patch PR. Bound to the Maestro variable
/// <c>pr_url</c> (see <c>bindings.json::tasks.OpenPatchPR.io.outputs</c>) so
/// the AutoMerge DMN decision can correlate the WaitForCI receive event back
/// to the same PR.
/// </summary>
public sealed class PrResult
{
    /// <summary>Full HTML URL of the opened PR.</summary>
    public string Url { get; set; } = string.Empty;

    /// <summary>PR number assigned by GitHub.</summary>
    public int Number { get; set; }

    /// <summary>Branch the PR was opened from (the patch branch).</summary>
    public string Branch { get; set; } = string.Empty;

    /// <summary>Files changed by the patch — repository-relative paths.</summary>
    public List<string> FilesTouched { get; set; } = new();
}
