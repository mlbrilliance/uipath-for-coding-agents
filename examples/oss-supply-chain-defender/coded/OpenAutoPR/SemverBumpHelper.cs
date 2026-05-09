using System;

namespace AuroraSupplyChainDefender.GitHub;

/// <summary>
/// Pure-function helper for the "MINOR-only" SemVer bump rule.
/// </summary>
/// <remarks>
/// <para>
/// The OpenAutoPR workflow only ever proposes a bump that stays within the
/// current major version line. Major-version jumps are policy-gated through a
/// different DMN branch (HIGH-severity findings that cross a major are routed
/// to the HITL-gated patch-PR path), and a dependency-bot must never silently
/// upgrade across <c>vN → v(N+1)</c> because that's where breaking changes
/// live by SemVer contract.
/// </para>
/// <para>
/// The bump rule, given a <c>current</c> pin and an <c>upstreamLatest</c>:
/// </para>
/// <list type="bullet">
///   <item>
///     If both parse and share the same major, and upstream is strictly
///     greater than current under SemVer ordering, take upstream.
///     <para>e.g., <c>4.17.20 + 4.18.0 → 4.18.0</c>;
///     <c>4.17.20 + 4.20.5 → 4.20.5</c>.</para>
///   </item>
///   <item>
///     If majors differ — including the upstream-major-bumped case
///     <c>4.17.20 + 5.0.0</c> — return the current version unchanged. The
///     calling workflow interprets a "no-op" return as "no minor bump
///     available within this major; defer to the patch-PR path or skip."
///   </item>
///   <item>
///     If current is a pre-release of the same target version
///     (<c>4.17.0-rc1</c>) and upstream is its release (<c>4.17.0</c>), take
///     upstream — pre-release &lt; release in SemVer.
///   </item>
///   <item>
///     If either input is empty, malformed, or not parseable as a SemVer
///     <c>MAJOR.MINOR.PATCH[-prerelease]</c>, return current unchanged. We
///     never invent a bump from an unparseable input.
///   </item>
///   <item>
///     If current and upstream compare as equal, return current.
///   </item>
/// </list>
/// </remarks>
public static class SemverBumpHelper
{
    /// <summary>
    /// Returns the SemVer-MINOR-only bumped version for <paramref name="current"/>
    /// given <paramref name="upstreamLatest"/>.
    /// </summary>
    /// <param name="current">
    /// The currently-pinned version in the manifest (e.g., <c>"4.17.20"</c>).
    /// </param>
    /// <param name="upstreamLatest">
    /// The latest version available upstream (e.g., <c>"4.18.0"</c>).
    /// </param>
    /// <returns>
    /// <paramref name="upstreamLatest"/> if it is a valid same-major bump and
    /// strictly greater than <paramref name="current"/>; otherwise
    /// <paramref name="current"/> unchanged. Never returns null.
    /// </returns>
    public static string GetMinorBump(string current, string upstreamLatest)
    {
        if (string.IsNullOrWhiteSpace(current))
        {
            // No basis to compute a bump against. Return what the caller gave
            // us (an empty string) rather than synthesizing one.
            return current ?? string.Empty;
        }

        if (string.IsNullOrWhiteSpace(upstreamLatest))
        {
            return current;
        }

        if (!SemVer.TryParse(current, out SemVer currentVer) ||
            !SemVer.TryParse(upstreamLatest, out SemVer upstreamVer))
        {
            // Malformed input — refuse to invent a bump.
            return current;
        }

        if (currentVer.Major != upstreamVer.Major)
        {
            // Major bump required. OpenAutoPR is MINOR-only by contract.
            return current;
        }

        if (SemVer.Compare(upstreamVer, currentVer) > 0)
        {
            // Same major, upstream strictly greater — take it. This covers
            // the highest-minor-within-same-major case, since the caller
            // passes the latest upstream for that major.
            return upstreamLatest;
        }

        return current;
    }

    /// <summary>
    /// Minimal SemVer 2.0.0 parser sufficient for the bump-decision use
    /// case. Public for unit-test introspection — the workflow itself only
    /// calls <see cref="GetMinorBump"/>.
    /// </summary>
    public readonly struct SemVer
    {
        public int Major { get; }
        public int Minor { get; }
        public int Patch { get; }
        public string PreRelease { get; }

        private SemVer(int major, int minor, int patch, string preRelease)
        {
            Major = major;
            Minor = minor;
            Patch = patch;
            PreRelease = preRelease ?? string.Empty;
        }

        /// <summary>
        /// True if this SemVer carries a pre-release identifier.
        /// Pre-releases sort below their corresponding release per SemVer §11.
        /// </summary>
        public bool IsPreRelease => !string.IsNullOrEmpty(PreRelease);

        /// <summary>
        /// Tries to parse <paramref name="raw"/> as a SemVer 2.0.0 version.
        /// Accepts an optional leading <c>v</c> (e.g., <c>v4.17.20</c>).
        /// Build-metadata suffixes (<c>+build.1</c>) are ignored per spec.
        /// </summary>
        public static bool TryParse(string raw, out SemVer value)
        {
            value = default;
            if (string.IsNullOrWhiteSpace(raw))
            {
                return false;
            }

            string trimmed = raw.Trim();
            if (trimmed.Length > 0 && (trimmed[0] == 'v' || trimmed[0] == 'V'))
            {
                trimmed = trimmed.Substring(1);
            }

            // Split off build metadata (everything after '+'); ignored.
            int plusIdx = trimmed.IndexOf('+');
            if (plusIdx >= 0)
            {
                trimmed = trimmed.Substring(0, plusIdx);
            }

            string preRelease = string.Empty;
            int hyphenIdx = trimmed.IndexOf('-');
            if (hyphenIdx >= 0)
            {
                preRelease = trimmed.Substring(hyphenIdx + 1);
                trimmed = trimmed.Substring(0, hyphenIdx);
                if (string.IsNullOrEmpty(preRelease))
                {
                    return false;
                }
            }

            string[] parts = trimmed.Split('.');
            if (parts.Length != 3)
            {
                return false;
            }

            if (!int.TryParse(parts[0], out int major) ||
                !int.TryParse(parts[1], out int minor) ||
                !int.TryParse(parts[2], out int patch))
            {
                return false;
            }

            if (major < 0 || minor < 0 || patch < 0)
            {
                return false;
            }

            value = new SemVer(major, minor, patch, preRelease);
            return true;
        }

        /// <summary>
        /// Compares two SemVer values per SemVer 2.0.0 §11. Returns &lt; 0 if
        /// <paramref name="a"/> &lt; <paramref name="b"/>, 0 if equal, &gt; 0 otherwise.
        /// </summary>
        public static int Compare(SemVer a, SemVer b)
        {
            int cmp = a.Major.CompareTo(b.Major);
            if (cmp != 0) return cmp;
            cmp = a.Minor.CompareTo(b.Minor);
            if (cmp != 0) return cmp;
            cmp = a.Patch.CompareTo(b.Patch);
            if (cmp != 0) return cmp;

            // SemVer §11.3: a version with a pre-release is lower than the
            // same numeric version without one. Two pre-releases compare
            // lexically over their dot-separated identifiers.
            if (a.IsPreRelease && !b.IsPreRelease) return -1;
            if (!a.IsPreRelease && b.IsPreRelease) return 1;
            if (!a.IsPreRelease && !b.IsPreRelease) return 0;

            return ComparePreRelease(a.PreRelease, b.PreRelease);
        }

        private static int ComparePreRelease(string a, string b)
        {
            string[] partsA = a.Split('.');
            string[] partsB = b.Split('.');
            int len = Math.Min(partsA.Length, partsB.Length);
            for (int i = 0; i < len; i++)
            {
                bool aNum = int.TryParse(partsA[i], out int an);
                bool bNum = int.TryParse(partsB[i], out int bn);
                if (aNum && bNum)
                {
                    int cmp = an.CompareTo(bn);
                    if (cmp != 0) return cmp;
                }
                else if (aNum)
                {
                    // Numeric identifiers always have lower precedence than
                    // alphanumeric ones (SemVer §11.4.3).
                    return -1;
                }
                else if (bNum)
                {
                    return 1;
                }
                else
                {
                    int cmp = string.CompareOrdinal(partsA[i], partsB[i]);
                    if (cmp != 0) return cmp;
                }
            }
            return partsA.Length.CompareTo(partsB.Length);
        }
    }
}
