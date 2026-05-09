// AURORA — Supply-Chain Defender
// Pure parsers for npm `package-lock.json` (v2/v3 layout) and `yarn.lock` (v1).
//
// R.K.01: pure functions over file content; no I/O. Tester unit-tests these
// outside the runtime by passing fixture text directly.
//
// PDD: US-34. The parser output drives the parallel-gateway branches
// (VulnLookup, MaintainerHealth, TyposquatCheck) so the LockfileEntry shape
// must match the Pydantic contract exactly.
using System.Collections.Generic;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace AuroraSupplyChainDefender.GitHub.Parsers
{
    public static class NpmParser
    {
        private const string Ecosystem = "npm";

        /// <summary>
        /// Parse npm `package-lock.json`. Handles lockfileVersion 2 and 3
        /// (the `packages` map; key is `"node_modules/<name>"` or `""` for the
        /// root project). Lockfile v1 (`dependencies` only) is supported as a
        /// fallback when `packages` is absent.
        /// </summary>
        public static List<LockfileEntry> ParsePackageLockJson(string json)
        {
            var entries = new List<LockfileEntry>();
            if (string.IsNullOrWhiteSpace(json))
            {
                return entries;
            }

            using var doc = JsonDocument.Parse(json);
            var root = doc.RootElement;

            if (root.TryGetProperty("packages", out var packages) &&
                packages.ValueKind == JsonValueKind.Object)
            {
                foreach (var prop in packages.EnumerateObject())
                {
                    // The empty-key entry describes the root project itself; skip it.
                    if (string.IsNullOrEmpty(prop.Name))
                    {
                        continue;
                    }

                    // Key shape: "node_modules/<name>" for top-level deps,
                    // "node_modules/<a>/node_modules/<b>" for nested ones.
                    var name = ExtractNpmNameFromPackagesKey(prop.Name);
                    if (string.IsNullOrEmpty(name))
                    {
                        continue;
                    }

                    var version = prop.Value.TryGetProperty("version", out var v)
                        ? v.GetString() ?? string.Empty
                        : string.Empty;

                    // depth = number of "node_modules/" segments in the key.
                    var depth = CountOccurrences(prop.Name, "node_modules/");

                    entries.Add(new LockfileEntry
                    {
                        Ecosystem = Ecosystem,
                        Name = name,
                        Version = version,
                        Depth = depth < 1 ? 1 : depth,
                    });
                }

                return entries;
            }

            // v1 fallback: walk the recursive `dependencies` tree.
            if (root.TryGetProperty("dependencies", out var deps) &&
                deps.ValueKind == JsonValueKind.Object)
            {
                WalkV1Dependencies(deps, depth: 1, entries);
            }

            return entries;
        }

        private static void WalkV1Dependencies(
            JsonElement deps,
            int depth,
            List<LockfileEntry> entries)
        {
            foreach (var prop in deps.EnumerateObject())
            {
                var version = prop.Value.TryGetProperty("version", out var v)
                    ? v.GetString() ?? string.Empty
                    : string.Empty;
                entries.Add(new LockfileEntry
                {
                    Ecosystem = Ecosystem,
                    Name = prop.Name,
                    Version = version,
                    Depth = depth,
                });
                if (prop.Value.TryGetProperty("dependencies", out var nested) &&
                    nested.ValueKind == JsonValueKind.Object)
                {
                    WalkV1Dependencies(nested, depth + 1, entries);
                }
            }
        }

        // The package-lock packages key is "node_modules/<a>" or
        // "node_modules/<a>/node_modules/<b>", possibly with scope:
        // "node_modules/@scope/pkg" or
        // "node_modules/@scope/pkg/node_modules/inner".
        private static string ExtractNpmNameFromPackagesKey(string key)
        {
            const string sep = "node_modules/";
            var lastIdx = key.LastIndexOf(sep, System.StringComparison.Ordinal);
            if (lastIdx < 0)
            {
                return string.Empty;
            }
            var tail = key.Substring(lastIdx + sep.Length);
            // Scoped: "@scope/name" — keep it whole.
            if (tail.StartsWith('@'))
            {
                var slash = tail.IndexOf('/');
                if (slash < 0)
                {
                    return tail;
                }
                // Stop at any further "/node_modules/..." (shouldn't happen
                // here, but defensive).
                return tail.Substring(0, FindNameEnd(tail, slash + 1));
            }
            return tail.Substring(0, FindNameEnd(tail, 0));
        }

        private static int FindNameEnd(string tail, int from)
        {
            var idx = tail.IndexOf('/', from);
            return idx < 0 ? tail.Length : idx;
        }

        private static int CountOccurrences(string haystack, string needle)
        {
            if (string.IsNullOrEmpty(needle)) return 0;
            int count = 0, idx = 0;
            while ((idx = haystack.IndexOf(needle, idx, System.StringComparison.Ordinal)) != -1)
            {
                count++;
                idx += needle.Length;
            }
            return count;
        }

        /// <summary>
        /// Parse a v1 `yarn.lock`. The format is a custom DSL: a header line
        /// like `lodash@^4.17.0:` (or several comma-separated specifiers)
        /// followed by indented `version "X.Y.Z"` and other keys, terminated
        /// by a blank line.
        /// </summary>
        public static List<LockfileEntry> ParseYarnLock(string text)
        {
            var entries = new List<LockfileEntry>();
            if (string.IsNullOrWhiteSpace(text))
            {
                return entries;
            }

            string? currentName = null;
            string? currentVersion = null;

            void Flush()
            {
                if (!string.IsNullOrEmpty(currentName) &&
                    !string.IsNullOrEmpty(currentVersion))
                {
                    entries.Add(new LockfileEntry
                    {
                        Ecosystem = Ecosystem,
                        Name = currentName!,
                        Version = currentVersion!,
                        Depth = 1,
                    });
                }
                currentName = null;
                currentVersion = null;
            }

            var lines = text.Replace("\r\n", "\n").Split('\n');
            foreach (var raw in lines)
            {
                if (string.IsNullOrWhiteSpace(raw))
                {
                    Flush();
                    continue;
                }
                if (raw.StartsWith('#'))
                {
                    continue;
                }
                if (!raw.StartsWith(' ') && !raw.StartsWith('\t'))
                {
                    // New block header: e.g. `lodash@^4.17.0:` or
                    // `"@types/node@*", "@types/node@^14":`
                    Flush();
                    currentName = ExtractYarnName(raw.TrimEnd(':', ' ', '\t'));
                }
                else
                {
                    var trimmed = raw.Trim();
                    if (trimmed.StartsWith("version ", System.StringComparison.Ordinal))
                    {
                        currentVersion = trimmed.Substring("version ".Length)
                            .Trim().Trim('"');
                    }
                }
            }
            Flush();
            return entries;
        }

        // Yarn header may look like:
        //   lodash@^4.17.0
        //   "lodash@^4.17.0", "lodash@^4.17.21"
        //   "@types/node@*"
        //   "@scope/pkg@npm:@scope/pkg@^1.0"
        // We pick the first specifier and lift the package name (everything
        // before the @ that follows the optional leading @scope/).
        private static string ExtractYarnName(string header)
        {
            // Take first comma-separated specifier.
            var first = header.Split(',')[0].Trim().Trim('"');
            // Scoped: "@scope/name@version-spec"
            if (first.StartsWith('@'))
            {
                var slash = first.IndexOf('/');
                if (slash > 0)
                {
                    var atAfter = first.IndexOf('@', slash);
                    return atAfter > 0 ? first.Substring(0, atAfter) : first;
                }
            }
            var at = first.IndexOf('@');
            return at > 0 ? first.Substring(0, at) : first;
        }
    }
}
