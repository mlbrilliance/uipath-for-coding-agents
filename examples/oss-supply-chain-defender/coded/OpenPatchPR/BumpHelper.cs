using System;
using System.Globalization;
using System.Text;

namespace AuroraSupplyChainDefender.GitHub;

/// <summary>
/// Pure-function helpers that compute the deterministic shape of the patch
/// PR — branch name, commit message, PR title, and PR body. Extracted out of
/// <see cref="Open"/> so that R.K.01 (pure helpers, primitive inputs) holds
/// and so the unit-test fixture can verify the artifact shape without
/// touching <see cref="Octokit.IGitHubClient"/>.
/// </summary>
/// <remarks>
/// All inputs are normalised so that a malformed <see cref="VulnFinding"/>
/// (missing CVE, weird ecosystem casing, embedded slashes) still produces a
/// branch name that GitHub accepts and a PR body that renders as Markdown.
/// </remarks>
public static class BumpHelper
{
    /// <summary>
    /// Branch-name template. Format:
    /// <c>aurora-patch/{ecosystem}/{package}/{cve-or-fallback}</c>.
    /// </summary>
    /// <remarks>
    /// Slashes inside <see cref="VulnFinding.Package"/> (npm scoped packages
    /// such as <c>@scope/name</c>) are replaced with <c>-</c> so the
    /// resulting ref-name has a fixed segment count. Missing CVEs fall back
    /// to <c>no-cve-{package}</c> to keep the branch unique per package
    /// while remaining valid as a Git ref.
    /// </remarks>
    public static string ComputeBranchName(VulnFinding finding)
    {
        if (finding is null) throw new ArgumentNullException(nameof(finding));

        string ecosystem = NormaliseSegment(finding.Ecosystem, "unknown-ecosystem");
        string package = NormaliseSegment(finding.Package, "unknown-package");
        string cveSegment = string.IsNullOrWhiteSpace(finding.Cve)
            ? $"no-cve-{package}"
            : NormaliseSegment(finding.Cve, "no-cve");

        return $"aurora-patch/{ecosystem}/{package}/{cveSegment}";
    }

    /// <summary>
    /// Commit-message template. Format:
    /// <c>fix({ecosystem}): bump {package} {current} → {fixed} ({cve})</c>.
    /// Trailing parenthetical is omitted when the CVE is absent.
    /// </summary>
    public static string BuildCommitMessage(VulnFinding finding)
    {
        if (finding is null) throw new ArgumentNullException(nameof(finding));

        string ecosystem = NormaliseDisplay(finding.Ecosystem, "unknown");
        string package = NormaliseDisplay(finding.Package, "unknown-package");
        string current = NormaliseDisplay(finding.CurrentVersion, "?");
        string fixedVersion = NormaliseDisplay(finding.FixedVersion, "?");

        string head = $"fix({ecosystem}): bump {package} {current} -> {fixedVersion}";
        return string.IsNullOrWhiteSpace(finding.Cve)
            ? head
            : $"{head} ({finding.Cve.Trim()})";
    }

    /// <summary>
    /// PR-title template. Same shape as the commit message; the redundancy is
    /// deliberate — GitHub's UI shows the title prominently while the commit
    /// log shows the message, and matching them simplifies operator review.
    /// </summary>
    public static string BuildPrTitle(VulnFinding finding) => BuildCommitMessage(finding);

    /// <summary>
    /// Markdown PR body. Cites the CVE (or notes its absence), names the
    /// ecosystem and package, summarises the bump, and tags the patch as
    /// <c>auto-merge-eligible</c> via a footer that human reviewers and the
    /// AutoMerge DMN gate both read.
    /// </summary>
    /// <param name="finding">The advisory record driving the patch.</param>
    /// <param name="diff">
    /// The proposed diff. <see cref="ProposedDiff.Summary"/> and
    /// <see cref="ProposedDiff.Url"/>, when non-empty, are quoted into the
    /// "Change details" section.
    /// </param>
    public static string BuildPrBody(VulnFinding finding, ProposedDiff diff)
    {
        if (finding is null) throw new ArgumentNullException(nameof(finding));
        if (diff is null) throw new ArgumentNullException(nameof(diff));

        string ecosystem = NormaliseDisplay(finding.Ecosystem, "unknown");
        string package = NormaliseDisplay(finding.Package, "unknown-package");
        string current = NormaliseDisplay(finding.CurrentVersion, "?");
        string fixedVersion = NormaliseDisplay(finding.FixedVersion, "?");
        string severity = NormaliseDisplay(finding.Severity, "Unknown");

        var sb = new StringBuilder();
        sb.AppendLine("## AURORA patch PR");
        sb.AppendLine();
        sb.AppendLine("This PR was opened automatically by the AURORA Open-Source Supply-Chain Defender after a Critical-severity finding was approved through Action Center.");
        sb.AppendLine();
        sb.AppendLine("### Vulnerability");
        sb.AppendLine();
        sb.AppendLine($"- **Ecosystem:** `{ecosystem}`");
        sb.AppendLine($"- **Package:** `{package}`");
        sb.AppendLine($"- **Current version:** `{current}`");
        sb.AppendLine($"- **Fixed version:** `{fixedVersion}`");
        sb.AppendLine($"- **Severity:** {severity}");

        if (!string.IsNullOrWhiteSpace(finding.Cve))
        {
            string cve = finding.Cve.Trim();
            sb.AppendLine($"- **CVE:** [{cve}](https://nvd.nist.gov/vuln/detail/{cve})");
        }
        else
        {
            sb.AppendLine("- **CVE:** _none assigned_");
        }

        sb.AppendLine();
        sb.AppendLine("### Change details");
        sb.AppendLine();
        if (!string.IsNullOrWhiteSpace(diff.Summary))
        {
            sb.AppendLine(diff.Summary.Trim());
            sb.AppendLine();
        }
        if (!string.IsNullOrWhiteSpace(diff.Url))
        {
            sb.AppendLine($"Upstream diff: <{diff.Url.Trim()}>");
            sb.AppendLine();
        }

        int fileCount = diff.Files?.Count ?? 0;
        sb.AppendLine($"Files touched: **{fileCount.ToString(CultureInfo.InvariantCulture)}**.");
        sb.AppendLine();
        sb.AppendLine("---");
        sb.AppendLine();
        sb.AppendLine("Tagged `aurora-patch` and `auto-merge-eligible`. The AutoMerge DMN gate at `process.bpmn::AutoMerge` decides whether to auto-merge once CI is green.");
        return sb.ToString();
    }

    /// <summary>
    /// Strip slashes, whitespace, and characters that would break a Git ref
    /// or PR display field. Lower-cased for branch segments, returns
    /// <paramref name="fallback"/> when the input is empty.
    /// </summary>
    private static string NormaliseSegment(string? value, string fallback)
    {
        if (string.IsNullOrWhiteSpace(value)) return fallback;

        var sb = new StringBuilder(value.Length);
        foreach (char c in value.Trim())
        {
            if (char.IsLetterOrDigit(c))
            {
                sb.Append(char.ToLowerInvariant(c));
            }
            else if (c == '-' || c == '.' || c == '_')
            {
                sb.Append(c);
            }
            else
            {
                sb.Append('-');
            }
        }
        string normalised = sb.ToString().Trim('-', '.');
        return string.IsNullOrEmpty(normalised) ? fallback : normalised;
    }

    /// <summary>
    /// Trim and replace empty input with <paramref name="fallback"/> while
    /// otherwise preserving the original casing — used for human-readable
    /// fields (commit message, PR title, PR body).
    /// </summary>
    private static string NormaliseDisplay(string? value, string fallback)
    {
        if (string.IsNullOrWhiteSpace(value)) return fallback;
        return value.Trim();
    }
}
