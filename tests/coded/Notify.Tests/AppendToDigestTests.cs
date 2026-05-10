using System;
using AuroraSupplyChainDefender.Notify;
using Xunit;

namespace AuroraSupplyChainDefender.Notify.Tests;

/// <summary>
/// Hermetic tests for <see cref="AppendToDigest"/>. Uses
/// <see cref="MemoryDigestStore"/> for in-memory state so no external
/// dependencies are required.
/// </summary>
public class AppendToDigestTests
{
    private static DigestEntry Entry(
        string finding = "Typosquat: lodaash → lodash",
        string severity = "Warning",
        string ecosystem = "npm") => new()
        {
            Finding = finding,
            Severity = severity,
            Ecosystem = ecosystem,
        };

    private static AppendToDigest NewWorkflow() =>
        new AppendToDigest(new MemoryDigestStore());

    [Fact]
    public void Empty_Digest_Gets_First_Entry()
    {
        var workflow = NewWorkflow();
        int size = workflow.Execute(Entry());

        Assert.Equal(1, size);
    }

    [Fact]
    public void Additional_Entries_Append()
    {
        var workflow = NewWorkflow();

        workflow.Execute(Entry("Finding A"));
        int size = workflow.Execute(Entry("Finding B"));

        Assert.Equal(2, size);
    }

    [Fact]
    public void Dedup_On_Identical_Finding_Ecosystem_Severity()
    {
        var workflow = NewWorkflow();

        workflow.Execute(Entry("Same Finding", "Warning", "npm"));
        int size = workflow.Execute(Entry("Same Finding", "Warning", "npm"));

        Assert.Equal(1, size); // duplicate suppressed
    }

    [Fact]
    public void Dedup_Is_Case_Insensitive()
    {
        var workflow = NewWorkflow();

        workflow.Execute(Entry("LODAASH", "WARNING", "NPM"));
        int size = workflow.Execute(Entry("lodaash", "warning", "npm"));

        Assert.Equal(1, size);
    }

    [Fact]
    public void Different_Severity_Is_Not_Deduplicated()
    {
        var workflow = NewWorkflow();

        workflow.Execute(Entry("lodaash", "Info", "npm"));
        int size = workflow.Execute(Entry("lodaash", "Critical", "npm"));

        Assert.Equal(2, size);
    }

    [Fact]
    public void Different_Ecosystem_Is_Not_Deduplicated()
    {
        var workflow = NewWorkflow();

        workflow.Execute(Entry("requests", "Warning", "npm"));
        int size = workflow.Execute(Entry("requests", "Warning", "pypi"));

        Assert.Equal(2, size);
    }

    [Fact]
    public void Returns_Size_After_Multiple_Appends()
    {
        var workflow = NewWorkflow();

        workflow.Execute(Entry("A", "Info", "npm"));
        workflow.Execute(Entry("B", "Warning", "npm"));
        workflow.Execute(Entry("C", "Critical", "pypi"));
        workflow.Execute(Entry("B", "Warning", "npm")); // duplicate
        int size = workflow.Execute(Entry("D", "Info", "pypi"));

        Assert.Equal(4, size); // A, B, C, D (B duplicate suppressed)
    }

    [Fact]
    public void Throws_On_Null_Entry()
    {
        var workflow = NewWorkflow();

        var ex = Assert.Throws<ArgumentNullException>(
            () => workflow.Execute(null!));

        Assert.Equal("in_objEntry", ex.ParamName);
    }

    [Fact]
    public void IsDuplicate_Static_Helper_Matches_Exactly()
    {
        var existing = new System.Collections.Generic.List<DigestEntry>
        {
            Entry("foo", "Info", "npm"),
            Entry("bar", "Warning", "pypi"),
        };

        Assert.True(AppendToDigest.IsDuplicate(existing, Entry("foo", "Info", "npm")));
        Assert.False(AppendToDigest.IsDuplicate(existing, Entry("baz", "Info", "npm")));
    }
}
