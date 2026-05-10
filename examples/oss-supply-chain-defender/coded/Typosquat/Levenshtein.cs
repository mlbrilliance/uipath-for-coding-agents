using System;

namespace AuroraSupplyChainDefender.Typosquat;

/// <summary>
/// Pure-function Levenshtein edit-distance helper.
/// </summary>
/// <remarks>
/// <para>
/// Computes the minimum number of single-character insertions, deletions, or
/// substitutions required to transform one string into another. This is the
/// canonical "edit distance" metric, and it is the typosquat detector's core
/// signal: package names that are within distance 1 or 2 of a popular package
/// are likely candidates for confusion attacks (<c>lodaash</c> vs
/// <c>lodash</c>, <c>reqests</c> vs <c>requests</c>).
/// </para>
/// <para>
/// The implementation uses the standard Wagner-Fischer dynamic programming
/// algorithm with a rolling-buffer optimisation: only the previous and current
/// rows of the cost matrix are retained, so memory is O(min(|a|,|b|)) instead
/// of O(|a|·|b|). Time complexity remains O(|a|·|b|), which is acceptable for
/// the typosquat use case (allow-lists ~100 entries, package names ~30 chars).
/// </para>
/// <para>
/// Comparison is ordinal (byte-by-byte). Callers that want case-insensitive
/// comparison must normalise inputs (e.g., <c>ToLowerInvariant</c>) before
/// calling.
/// </para>
/// </remarks>
public static class Levenshtein
{
    /// <summary>
    /// Returns the Levenshtein distance between <paramref name="a"/> and
    /// <paramref name="b"/>.
    /// </summary>
    /// <param name="a">First string. Non-null; may be empty.</param>
    /// <param name="b">Second string. Non-null; may be empty.</param>
    /// <returns>
    /// The minimum number of insertions, deletions, or substitutions to
    /// transform <paramref name="a"/> into <paramref name="b"/>. Always
    /// non-negative. Equals <c>b.Length</c> when <paramref name="a"/> is empty,
    /// and <c>a.Length</c> when <paramref name="b"/> is empty.
    /// </returns>
    /// <exception cref="ArgumentNullException">
    /// Thrown if either input is <c>null</c>.
    /// </exception>
    public static int Distance(string a, string b)
    {
        if (a is null) throw new ArgumentNullException(nameof(a));
        if (b is null) throw new ArgumentNullException(nameof(b));

        if (a.Length == 0) return b.Length;
        if (b.Length == 0) return a.Length;

        // Always iterate the shorter string in the inner loop so the rolling
        // buffer is min(|a|,|b|) wide.
        if (a.Length < b.Length)
        {
            (a, b) = (b, a);
        }

        // previous[j] = distance between a[..i-1] and b[..j]
        // current[j]  = distance between a[..i]   and b[..j]
        int[] previous = new int[b.Length + 1];
        int[] current = new int[b.Length + 1];

        for (int j = 0; j <= b.Length; j++)
        {
            previous[j] = j;
        }

        for (int i = 1; i <= a.Length; i++)
        {
            current[0] = i;
            char aChar = a[i - 1];
            for (int j = 1; j <= b.Length; j++)
            {
                int substitutionCost = aChar == b[j - 1] ? 0 : 1;
                int deletion = previous[j] + 1;
                int insertion = current[j - 1] + 1;
                int substitution = previous[j - 1] + substitutionCost;
                current[j] = Math.Min(Math.Min(deletion, insertion), substitution);
            }

            // Rotate buffers: current becomes previous for the next row.
            (previous, current) = (current, previous);
        }

        return previous[b.Length];
    }
}
