using AuroraSupplyChainDefender.GitHub;
using Xunit;

namespace AuroraSupplyChainDefender.GitHub.Tests;

/// <summary>
/// Pure-function tests for <see cref="SemverBumpHelper"/>. No I/O, no
/// network — these exercise the rule that an OpenAutoPR auto-merge
/// candidate must stay within the current major version line.
/// </summary>
public class SemverBumpHelperTests
{
    [Fact]
    public void AdjacentMinor_ReturnsUpstream()
    {
        // 4.17.20 + 4.18.0 → 4.18.0  (canonical case from the spec)
        Assert.Equal("4.18.0", SemverBumpHelper.GetMinorBump("4.17.20", "4.18.0"));
    }

    [Fact]
    public void HighestMinorWithinSameMajor_ReturnsUpstream()
    {
        // 4.17.20 + 4.20.5 → 4.20.5  (caller passes the latest same-major)
        Assert.Equal("4.20.5", SemverBumpHelper.GetMinorBump("4.17.20", "4.20.5"));
    }

    [Fact]
    public void MajorBump_ReturnsCurrentUnchanged()
    {
        // 4.17.20 + 5.0.0 → 4.17.20  (no minor bump available; never major)
        Assert.Equal("4.17.20", SemverBumpHelper.GetMinorBump("4.17.20", "5.0.0"));
    }

    [Fact]
    public void MajorTwoVersionsAhead_ReturnsCurrentUnchanged()
    {
        // 1.0.0 + 3.4.5 → 1.0.0  (still no minor bump within major 1)
        Assert.Equal("1.0.0", SemverBumpHelper.GetMinorBump("1.0.0", "3.4.5"));
    }

    [Fact]
    public void Prerelease_LosesToRelease_ReturnsUpstream()
    {
        // 4.17.0-rc1 + 4.17.0 → 4.17.0  (SemVer §11.3: pre-release < release)
        Assert.Equal("4.17.0", SemverBumpHelper.GetMinorBump("4.17.0-rc1", "4.17.0"));
    }

    [Fact]
    public void UpstreamPrerelease_DoesNotDowngradeRelease()
    {
        // 4.17.0 + 4.17.0-rc2 → 4.17.0  (release > pre-release; never downgrade)
        Assert.Equal("4.17.0", SemverBumpHelper.GetMinorBump("4.17.0", "4.17.0-rc2"));
    }

    [Fact]
    public void EqualCurrentAndUpstream_ReturnsCurrent()
    {
        Assert.Equal("4.17.20", SemverBumpHelper.GetMinorBump("4.17.20", "4.17.20"));
    }

    [Fact]
    public void EmptyCurrent_ReturnsEmpty()
    {
        Assert.Equal(string.Empty, SemverBumpHelper.GetMinorBump(string.Empty, "4.17.0"));
    }

    [Fact]
    public void EmptyUpstream_ReturnsCurrentUnchanged()
    {
        Assert.Equal("4.17.20", SemverBumpHelper.GetMinorBump("4.17.20", string.Empty));
    }

    [Fact]
    public void MalformedCurrent_ReturnsCurrentUnchanged()
    {
        // We never invent a bump from an unparseable input.
        Assert.Equal("not-a-semver", SemverBumpHelper.GetMinorBump("not-a-semver", "4.17.0"));
    }

    [Fact]
    public void MalformedUpstream_ReturnsCurrentUnchanged()
    {
        Assert.Equal("4.17.20", SemverBumpHelper.GetMinorBump("4.17.20", "not-a-semver"));
    }

    [Fact]
    public void LeadingV_IsAccepted()
    {
        // Tag-style "v4.17.20" should parse and be treated identically.
        Assert.Equal("v4.18.0", SemverBumpHelper.GetMinorBump("v4.17.20", "v4.18.0"));
    }

    [Fact]
    public void DowngradeWithinSameMajor_ReturnsCurrent()
    {
        // 4.17.20 + 4.16.0 → 4.17.20  (upstream older; never regress)
        Assert.Equal("4.17.20", SemverBumpHelper.GetMinorBump("4.17.20", "4.16.0"));
    }

    [Fact]
    public void PatchBumpOnly_StillReturnsUpstream()
    {
        // 4.17.20 + 4.17.21 → 4.17.21  (within-minor patches still take)
        Assert.Equal("4.17.21", SemverBumpHelper.GetMinorBump("4.17.20", "4.17.21"));
    }

    [Fact]
    public void PrereleaseOrdering_NumericIdentifiersSortAsNumbers()
    {
        // 1.0.0-alpha.2 < 1.0.0-alpha.10 (numeric, not lexical).
        // We exercise this through the bump rule: same major → take upstream.
        Assert.Equal("1.0.0-alpha.10", SemverBumpHelper.GetMinorBump("1.0.0-alpha.2", "1.0.0-alpha.10"));
    }
}
