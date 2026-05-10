// AURORA — Supply-Chain Defender
// Pure parser for Python `requirements.txt`.
//
// R.K.01: pure function over text; no I/O.
//
// Handles:
//   pkg==1.2.3            → pinned (version "1.2.3")
//   pkg>=1.0,<2.0         → range (version captured verbatim minus the name)
//   pkg                   → unpinned (version "")
//   pkg ; python_version >= "3.7"   → strip env marker
//   # comment             → skip
//   <blank line>          → skip
//   -r other.txt          → record once with name "-r:other.txt", ecosystem
//                           "pypi-include" so downstream sees it but does not
//                           treat it as a package.
using System.Collections.Generic;
using System.Text.RegularExpressions;

namespace AuroraSupplyChainDefender.GitHub.Parsers
{
    public static class PyPiParser
    {
        private const string Ecosystem = "pypi";

        // PEP 508 name: letters, digits, "-", "_", ".", scoped form not allowed.
        private static readonly Regex NameRe = new(
            @"^([A-Za-z0-9][A-Za-z0-9._-]*)\s*(.*)$",
            RegexOptions.Compiled);

        public static List<LockfileEntry> ParseRequirementsTxt(string text)
        {
            var entries = new List<LockfileEntry>();
            if (string.IsNullOrWhiteSpace(text))
            {
                return entries;
            }

            var lines = text.Replace("\r\n", "\n").Split('\n');
            foreach (var raw in lines)
            {
                var line = raw.Trim();
                if (line.Length == 0 || line.StartsWith('#'))
                {
                    continue;
                }
                // Strip inline comments.
                var hashIdx = line.IndexOf(" #", System.StringComparison.Ordinal);
                if (hashIdx >= 0)
                {
                    line = line.Substring(0, hashIdx).TrimEnd();
                    if (line.Length == 0) continue;
                }

                // Recursive include: `-r other.txt` or `--requirement other.txt`.
                // Also `-c constraints.txt`. Record as referenced-not-resolved so
                // the operator can see it, but do not treat as a real package.
                if (line.StartsWith("-r ") ||
                    line.StartsWith("--requirement ") ||
                    line.StartsWith("-c ") ||
                    line.StartsWith("--constraint "))
                {
                    var pathPart = line.IndexOf(' ') >= 0
                        ? line.Substring(line.IndexOf(' ') + 1).Trim()
                        : string.Empty;
                    entries.Add(new LockfileEntry
                    {
                        Ecosystem = "pypi-include",
                        Name = pathPart,
                        Version = string.Empty,
                        Depth = 1,
                    });
                    continue;
                }

                // Strip env markers: `pkg ; python_version >= "3.7"`.
                var semi = line.IndexOf(';');
                if (semi >= 0)
                {
                    line = line.Substring(0, semi).TrimEnd();
                    if (line.Length == 0) continue;
                }

                // VCS / URL installs: `git+https://...#egg=name` — best-effort.
                if (line.StartsWith("git+") || line.StartsWith("http://") ||
                    line.StartsWith("https://") || line.StartsWith("file://"))
                {
                    var egg = line.IndexOf("#egg=", System.StringComparison.Ordinal);
                    if (egg > 0)
                    {
                        var eggName = line.Substring(egg + 5).TrimEnd();
                        entries.Add(new LockfileEntry
                        {
                            Ecosystem = Ecosystem,
                            Name = eggName,
                            Version = string.Empty,
                            Depth = 1,
                        });
                    }
                    continue;
                }

                var m = NameRe.Match(line);
                if (!m.Success)
                {
                    continue;
                }
                var name = m.Groups[1].Value;
                var rest = m.Groups[2].Value.Trim();

                string version = string.Empty;
                if (rest.StartsWith("=="))
                {
                    // Pinned. Capture version up to next operator/space.
                    var rv = rest.Substring(2).Trim();
                    var stop = rv.IndexOfAny(new[] { ',', ' ' });
                    version = stop >= 0 ? rv.Substring(0, stop) : rv;
                }
                else if (rest.Length > 0)
                {
                    // Range / inequality / extras like `[crypto]>=1.0`.
                    version = rest;
                }

                entries.Add(new LockfileEntry
                {
                    Ecosystem = Ecosystem,
                    Name = name,
                    Version = version,
                    Depth = 1,
                });
            }
            return entries;
        }
    }
}
