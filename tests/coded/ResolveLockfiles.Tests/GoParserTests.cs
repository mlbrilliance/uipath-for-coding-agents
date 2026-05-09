using System.IO;
using System.Linq;
using AuroraSupplyChainDefender.GitHub.Parsers;
using Xunit;

namespace AuroraSupplyChainDefender.GitHub.Tests
{
    public class GoParserTests
    {
        private static string ReadFixture(string name)
        {
            var path = Path.Combine(
                Path.GetDirectoryName(typeof(GoParserTests).Assembly.Location)!,
                "Fixtures", name);
            return File.ReadAllText(path);
        }

        [Fact]
        public void ParseGoSum_DedupesGoModLines()
        {
            var entries = GoParser.ParseGoSum(ReadFixture("go.sum"));

            // 3 distinct modules (each appears twice in go.sum: content + go.mod).
            Assert.Equal(3, entries.Count);
            Assert.Contains(entries, e =>
                e.Name == "github.com/davecgh/go-spew" && e.Version == "v1.1.1");
            Assert.Contains(entries, e =>
                e.Name == "github.com/google/go-cmp" && e.Version == "v0.5.9");
            Assert.Contains(entries, e =>
                e.Name == "golang.org/x/mod" && e.Version == "v0.5.1");
            Assert.All(entries, e => Assert.Equal("go", e.Ecosystem));
        }

        [Fact]
        public void ParseGoSum_HandlesEmpty()
        {
            Assert.Empty(GoParser.ParseGoSum(string.Empty));
            Assert.Empty(GoParser.ParseGoSum("\n  \n"));
        }
    }
}
