namespace AuroraSupplyChainDefender.Typosquat;

/// <summary>
/// One row of a resolved lockfile: an ecosystem-qualified dependency entry.
/// </summary>
/// <remarks>
/// Produced by <c>ResolveLockfiles</c> (T-C3) and consumed by every
/// fan-out branch of the supply-chain-defender process, including
/// <see cref="CheckLockfiles"/>.
/// </remarks>
public sealed class LockfileEntry
{
    /// <summary>Package ecosystem: <c>"npm"</c> or <c>"pypi"</c>.</summary>
    public string Ecosystem { get; set; } = string.Empty;

    /// <summary>Package name as it appears in the lockfile.</summary>
    public string Name { get; set; } = string.Empty;

    /// <summary>Resolved version string. Optional for typosquat checking.</summary>
    public string Version { get; set; } = string.Empty;

    /// <summary>Dependency depth (0 = direct, 1+ = transitive).</summary>
    public int Depth { get; set; }
}

/// <summary>
/// A typosquat suspect: a lockfile entry whose name is suspiciously close
/// to a legitimate package on the same ecosystem's allow-list.
/// </summary>
public sealed class TyposquatSuspect
{
    /// <summary>Ecosystem of the suspect entry: <c>"npm"</c> or <c>"pypi"</c>.</summary>
    public string Ecosystem { get; set; } = string.Empty;

    /// <summary>The dependency name flagged as a possible typosquat.</summary>
    public string SuspectName { get; set; } = string.Empty;

    /// <summary>The closest matching legitimate package name from the allow-list.</summary>
    public string NearestLegitimate { get; set; } = string.Empty;

    /// <summary>Levenshtein distance between <see cref="SuspectName"/> and <see cref="NearestLegitimate"/>.</summary>
    public int Distance { get; set; }
}
