using System.IO;
using System.Linq;
using AuroraSupplyChainDefender.GitHub.Parsers;
using Xunit;

namespace AuroraSupplyChainDefender.GitHub.Tests
{
    public class NpmParserTests
    {
        private static string ReadFixture(string name)
        {
            var path = Path.Combine(
                Path.GetDirectoryName(typeof(NpmParserTests).Assembly.Location)!,
                "Fixtures", name);
            return File.ReadAllText(path);
        }

        [Fact]
        public void ParsePackageLockJson_HandlesV3Layout()
        {
            var json = ReadFixture("package-lock.v3.json");
            var entries = NpmParser.ParsePackageLockJson(json);

            // The empty "" key (root project) is skipped; 4 deps remain.
            Assert.Equal(4, entries.Count);

            var lodash = entries.Single(e => e.Name == "lodash");
            Assert.Equal("npm", lodash.Ecosystem);
            Assert.Equal("4.17.21", lodash.Version);
            Assert.Equal(1, lodash.Depth);

            var express = entries.Single(e => e.Name == "express");
            Assert.Equal("4.18.2", express.Version);
            Assert.Equal(1, express.Depth);

            // Nested transitive: depth = 2 (two `node_modules/` segments).
            var qs = entries.Single(e => e.Name == "qs");
            Assert.Equal(2, qs.Depth);

            // Scoped name preserved with the leading @scope/.
            var scoped = entries.Single(e => e.Name == "@scope/util");
            Assert.Equal("1.2.3", scoped.Version);
        }

        [Fact]
        public void ParsePackageLockJson_HandlesV1Layout()
        {
            var json = ReadFixture("package-lock.v1.json");
            var entries = NpmParser.ParsePackageLockJson(json);

            // 3 packages: lodash (depth 1), request (depth 1), qs (depth 2).
            Assert.Equal(3, entries.Count);
            var lodash = entries.Single(e => e.Name == "lodash");
            Assert.Equal("4.17.20", lodash.Version);
            Assert.Equal(1, lodash.Depth);
            var qs = entries.Single(e => e.Name == "qs");
            Assert.Equal(2, qs.Depth);
        }

        [Fact]
        public void ParseYarnLock_HandlesV1Format()
        {
            var text = ReadFixture("yarn.lock");
            var entries = NpmParser.ParseYarnLock(text);

            Assert.Equal(3, entries.Count);
            Assert.Contains(entries, e => e.Name == "lodash" && e.Version == "4.17.21");
            Assert.Contains(entries, e => e.Name == "@types/node" && e.Version == "14.18.63");
            Assert.Contains(entries, e => e.Name == "express" && e.Version == "4.18.2");
            Assert.All(entries, e => Assert.Equal("npm", e.Ecosystem));
        }

        [Fact]
        public void Parser_HandlesEmpty()
        {
            // Empty input never throws; returns an empty list.
            Assert.Empty(NpmParser.ParseYarnLock(string.Empty));
            Assert.Empty(NpmParser.ParseYarnLock("   \n  \n"));
            Assert.Empty(NpmParser.ParsePackageLockJson(string.Empty));
            Assert.Empty(NpmParser.ParsePackageLockJson("{}"));
        }
    }
}
