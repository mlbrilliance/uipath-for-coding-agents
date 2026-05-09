using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using AuroraSupplyChainDefender.Typosquat;
using Xunit;

namespace AuroraSupplyChainDefender.Typosquat.Tests;

/// <summary>
/// Hermetic tests for <see cref="CheckLockfiles"/>. Each test writes a tiny
/// JSON allow-list to a temp directory and injects the path via the test
/// constructor — no network, no dependency on bin-output file copy.
/// </summary>
public class CheckLockfilesTests : IDisposable
{
    private readonly string _allowListPath;

    public CheckLockfilesTests()
    {
        _allowListPath = Path.Combine(
            Path.GetTempPath(),
            $"aurora-typosquat-allowlist-{Guid.NewGuid():N}.json");
        File.WriteAllText(_allowListPath, """
            {
              "npm": ["lodash", "react", "express", "axios"],
              "pypi": ["requests", "numpy", "flask", "django"]
            }
            """);
    }

    public void Dispose()
    {
        if (File.Exists(_allowListPath))
        {
            File.Delete(_allowListPath);
        }
    }

    private CheckLockfiles NewWorkflow() => new CheckLockfiles(_allowListPath);

    private static LockfileEntry Entry(string ecosystem, string name)
        => new LockfileEntry { Ecosystem = ecosystem, Name = name, Version = "1.0.0", Depth = 0 };

    [Fact]
    public void Returns_Empty_When_All_Match_AllowList()
    {
        var workflow = NewWorkflow();
        var input = new List<LockfileEntry>
        {
            Entry("npm", "lodash"),
            Entry("npm", "react"),
            Entry("pypi", "numpy"),
        };

        List<TyposquatSuspect> suspects = workflow.Execute(input);

        Assert.Empty(suspects);
    }

    [Fact]
    public void Returns_Suspect_When_Near_AllowList_Entry()
    {
        var workflow = NewWorkflow();
        var input = new List<LockfileEntry> { Entry("npm", "lodaash") };

        List<TyposquatSuspect> suspects = workflow.Execute(input);

        var suspect = Assert.Single(suspects);
        Assert.Equal("npm", suspect.Ecosystem);
        Assert.Equal("lodaash", suspect.SuspectName);
        Assert.Equal("lodash", suspect.NearestLegitimate);
        Assert.Equal(1, suspect.Distance);
    }

    [Fact]
    public void Returns_Suspect_For_Lodaash_With_Distance_At_Most_Two()
    {
        // Acceptance criterion T-C2 spec: lodaash vs lodash flagged with d <= 2.
        var workflow = NewWorkflow();
        var input = new List<LockfileEntry> { Entry("npm", "lodaash") };

        var suspect = Assert.Single(workflow.Execute(input));
        Assert.Equal("lodash", suspect.NearestLegitimate);
        Assert.True(suspect.Distance <= 2);
    }

    [Fact]
    public void Distinguishes_Ecosystems()
    {
        // 'requests' is legit on PyPI but NOT on npm. An npm entry called
        // 'requests' should be checked only against the npm allow-list and
        // — being far from any npm name (closest is 'react' / 'express') —
        // should NOT flag merely because PyPI has 'requests'.
        // It WILL flag against 'react' (distance 4) or 'express' (distance 5)
        // — both > 2 → no suspect emitted.
        var workflow = NewWorkflow();
        var input = new List<LockfileEntry> { Entry("npm", "requests") };

        List<TyposquatSuspect> suspects = workflow.Execute(input);

        Assert.Empty(suspects);
    }

    [Fact]
    public void Skips_Exact_Match()
    {
        var workflow = NewWorkflow();
        var input = new List<LockfileEntry>
        {
            Entry("npm", "lodash"),
            Entry("npm", "lodash"), // duplicate exact match — still skipped
        };

        Assert.Empty(workflow.Execute(input));
    }

    [Fact]
    public void Skips_Exact_Match_Case_Insensitive()
    {
        // Lodash on npm should be treated as exact-match against lodash.
        var workflow = NewWorkflow();
        var input = new List<LockfileEntry> { Entry("npm", "Lodash") };

        Assert.Empty(workflow.Execute(input));
    }

    [Fact]
    public void Returns_Empty_When_Input_Is_Null()
    {
        var workflow = NewWorkflow();
        Assert.Empty(workflow.Execute(null!));
    }

    [Fact]
    public void Skips_Unknown_Ecosystem()
    {
        var workflow = NewWorkflow();
        var input = new List<LockfileEntry> { Entry("cargo", "lodaash") };

        Assert.Empty(workflow.Execute(input));
    }

    [Fact]
    public void Returns_Expected_Suspects_For_Mixed_Lockfile()
    {
        // T-C2 acceptance: ReturnsExpectedSuspects.
        var workflow = NewWorkflow();
        var input = new List<LockfileEntry>
        {
            Entry("npm", "lodash"),       // legit
            Entry("npm", "lodaash"),      // suspect → lodash, d=1
            Entry("npm", "expres"),       // suspect → express, d=1
            Entry("pypi", "reqests"),     // suspect → requests, d=1
            Entry("pypi", "numpy"),       // legit
            Entry("pypi", "totally-unrelated-package"), // far → no suspect
        };

        List<TyposquatSuspect> suspects = workflow.Execute(input);

        Assert.Equal(3, suspects.Count);

        TyposquatSuspect lodaash = suspects.Single(s => s.SuspectName == "lodaash");
        Assert.Equal("npm", lodaash.Ecosystem);
        Assert.Equal("lodash", lodaash.NearestLegitimate);
        Assert.Equal(1, lodaash.Distance);

        TyposquatSuspect expres = suspects.Single(s => s.SuspectName == "expres");
        Assert.Equal("npm", expres.Ecosystem);
        Assert.Equal("express", expres.NearestLegitimate);
        Assert.Equal(1, expres.Distance);

        TyposquatSuspect reqests = suspects.Single(s => s.SuspectName == "reqests");
        Assert.Equal("pypi", reqests.Ecosystem);
        Assert.Equal("requests", reqests.NearestLegitimate);
        Assert.Equal(1, reqests.Distance);
    }
}
