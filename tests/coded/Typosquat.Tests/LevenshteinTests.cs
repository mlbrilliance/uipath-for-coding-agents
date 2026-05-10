using AuroraSupplyChainDefender.Typosquat;
using Xunit;

namespace AuroraSupplyChainDefender.Typosquat.Tests;

public class LevenshteinTests
{
    [Fact]
    public void Distance_IdenticalStrings_ReturnsZero()
    {
        Assert.Equal(0, Levenshtein.Distance("lodash", "lodash"));
        Assert.Equal(0, Levenshtein.Distance("", ""));
        Assert.Equal(0, Levenshtein.Distance("a", "a"));
    }

    [Fact]
    public void Distance_TypicalSquats_ReturnsTwoOrLess()
    {
        // lodaash → lodash: one extra 'a'
        Assert.True(Levenshtein.Distance("lodaash", "lodash") <= 2);
        // reqests → requests: missing 'u'
        Assert.True(Levenshtein.Distance("reqests", "requests") <= 1);
        // flassk → flask: one extra 's'
        Assert.True(Levenshtein.Distance("flassk", "flask") <= 1);
    }

    [Fact]
    public void Distance_CompletelyDifferent_ReturnsLength()
    {
        Assert.Equal(3, Levenshtein.Distance("abc", "xyz"));
    }

    [Fact]
    public void Distance_EmptyA_ReturnsLengthOfB()
    {
        Assert.Equal(6, Levenshtein.Distance("", "lodash"));
    }

    [Fact]
    public void Distance_EmptyB_ReturnsLengthOfA()
    {
        Assert.Equal(6, Levenshtein.Distance("lodash", ""));
    }

    [Fact]
    public void Distance_IsSymmetric()
    {
        Assert.Equal(
            Levenshtein.Distance("lodash", "lodaash"),
            Levenshtein.Distance("lodaash", "lodash"));
    }

    [Fact]
    public void Distance_SingleSubstitution_ReturnsOne()
    {
        // numpy vs nympy: one substitution
        Assert.Equal(1, Levenshtein.Distance("numpy", "nympy"));
    }
}
