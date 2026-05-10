// AURORA — Supply-Chain Defender
// Pure parser for Go's `go.sum`.
//
// R.K.01: pure function over text; no I/O.
//
// `go.sum` lines are of the form:
//   <module> <version> h1:<hash>
//   <module> <version>/go.mod h1:<hash>
// We dedupe on (module, version) since each module appears at least twice
// (the module-content hash and the module/go.mod hash). The depth is
// indeterminate from go.sum alone, so we record everything as 1 (direct);
// transitive resolution would require go.mod traversal which is out of scope.
using System.Collections.Generic;

namespace AuroraSupplyChainDefender.GitHub.Parsers
{
    public static class GoParser
    {
        private const string Ecosystem = "go";

        public static List<LockfileEntry> ParseGoSum(string text)
        {
            var entries = new List<LockfileEntry>();
            if (string.IsNullOrWhiteSpace(text))
            {
                return entries;
            }

            // (module, version) → already-emitted? — preserve insertion order via the list.
            var seen = new HashSet<string>(System.StringComparer.Ordinal);

            var lines = text.Replace("\r\n", "\n").Split('\n');
            foreach (var raw in lines)
            {
                var line = raw.Trim();
                if (line.Length == 0 || line.StartsWith('#'))
                {
                    continue;
                }

                // <module> <version-and-maybe-/go.mod> h1:<hash>
                var firstSp = line.IndexOf(' ');
                if (firstSp <= 0) continue;
                var secondSp = line.IndexOf(' ', firstSp + 1);
                if (secondSp <= firstSp) continue;

                var module = line.Substring(0, firstSp);
                var versionToken = line.Substring(firstSp + 1, secondSp - firstSp - 1);

                // Strip "/go.mod" suffix to dedupe.
                const string goModSuffix = "/go.mod";
                if (versionToken.EndsWith(goModSuffix, System.StringComparison.Ordinal))
                {
                    versionToken = versionToken.Substring(0, versionToken.Length - goModSuffix.Length);
                }

                var dedupeKey = module + "@" + versionToken;
                if (!seen.Add(dedupeKey))
                {
                    continue;
                }

                entries.Add(new LockfileEntry
                {
                    Ecosystem = Ecosystem,
                    Name = module,
                    Version = versionToken,
                    Depth = 1,
                });
            }
            return entries;
        }
    }
}
