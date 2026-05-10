using System.Collections.Generic;
using AuroraSupplyChainDefender.GitHub;
using Xunit;

namespace AuroraSupplyChainDefender.GitHub.Tests;

/// <summary>
/// Pure-helper tests for <see cref="BumpHelper"/>. Verify the deterministic
/// shape of branch names, commit messages, PR titles, and PR bodies — and
/// the graceful degradation when fields are missing.
/// </summary>
public class BumpHelperTests
{
    private static VulnFinding NewFinding(
        string ecosystem = "npm",
        string package = "lodash",
        string current = "4.17.20",
        string fixedVer = "4.17.21",
        string cve = "CVE-2021-23337",
        string severity = "Critical")
        => new VulnFinding
        {
            Ecosystem = ecosystem,
            Package = package,
            CurrentVersion = current,
            FixedVersion = fixedVer,
            Cve = cve,
            Severity = severity,
        };

    [Fact]
    public void ComputeBranchName_Has_Aurora_Patch_Shape()
    {
        // Acceptance: branch name is `aurora-patch/{eco}/{pkg}/{cve}`.
        VulnFinding finding = NewFinding();

        string branch = BumpHelper.ComputeBranchName(finding);

        Assert.Equal("aurora-patch/npm/lodash/cve-2021-23337", branch);
    }

    [Fact]
    public void ComputeBranchName_Replaces_Slash_In_Scoped_Npm_Package()
    {
        // npm scoped packages embed a `/` in the name; the branch name must
        // remain a fixed 4-segment ref.
        VulnFinding finding = NewFinding(package: "@scope/inner", cve: "CVE-2024-0001");

        string branch = BumpHelper.ComputeBranchName(finding);

        Assert.Equal("aurora-patch/npm/scope-inner/cve-2024-0001", branch);
    }

    [Fact]
    public void ComputeBranchName_Falls_Back_When_Cve_Is_Missing()
    {
        // R.E.04 implication: graceful degrade when an upstream field is
        // empty rather than throw — the workflow has to keep moving.
        VulnFinding finding = NewFinding(cve: "");

        string branch = BumpHelper.ComputeBranchName(finding);

        Assert.Equal("aurora-patch/npm/lodash/no-cve-lodash", branch);
    }

    [Fact]
    public void BuildCommitMessage_Has_Conventional_Commit_Shape()
    {
        VulnFinding finding = NewFinding();

        string message = BumpHelper.BuildCommitMessage(finding);

        Assert.Equal(
            "fix(npm): bump lodash 4.17.20 -> 4.17.21 (CVE-2021-23337)",
            message);
    }

    [Fact]
    public void BuildCommitMessage_Omits_Cve_When_Absent()
    {
        VulnFinding finding = NewFinding(cve: "   ");

        string message = BumpHelper.BuildCommitMessage(finding);

        Assert.Equal("fix(npm): bump lodash 4.17.20 -> 4.17.21", message);
    }

    [Fact]
    public void BuildPrTitle_Matches_CommitMessage()
    {
        // PR title and commit message intentionally share their shape so the
        // GitHub UI and the Git log show consistent text.
        VulnFinding finding = NewFinding();

        string title = BumpHelper.BuildPrTitle(finding);
        string message = BumpHelper.BuildCommitMessage(finding);

        Assert.Equal(message, title);
    }

    [Fact]
    public void BuildPrBody_Cites_The_Cve()
    {
        VulnFinding finding = NewFinding();
        var diff = new ProposedDiff
        {
            Files = new Dictionary<string, string> { ["package.json"] = "{}" },
            Url = "https://example.com/diff",
            Summary = "Bump lodash from 4.17.20 to 4.17.21",
        };

        string body = BumpHelper.BuildPrBody(finding, diff);

        Assert.Contains("CVE-2021-23337", body);
        Assert.Contains("https://nvd.nist.gov/vuln/detail/CVE-2021-23337", body);
        Assert.Contains("Bump lodash from 4.17.20 to 4.17.21", body);
        Assert.Contains("https://example.com/diff", body);
        Assert.Contains("Files touched: **1**", body);
    }

    [Fact]
    public void BuildPrBody_Notes_Missing_Cve_Without_Throwing()
    {
        VulnFinding finding = NewFinding(cve: "");
        var diff = new ProposedDiff();

        string body = BumpHelper.BuildPrBody(finding, diff);

        Assert.Contains("_none assigned_", body);
        Assert.DoesNotContain("nvd.nist.gov", body);
    }

    [Fact]
    public void BuildPrBody_Mentions_Both_Labels()
    {
        // Operators read the body to confirm the auto-merge tag landed.
        VulnFinding finding = NewFinding();
        var diff = new ProposedDiff();

        string body = BumpHelper.BuildPrBody(finding, diff);

        Assert.Contains("aurora-patch", body);
        Assert.Contains("auto-merge-eligible", body);
    }
}
