using System.IO;
using System.Linq;
using AuroraSupplyChainDefender.GitHub.Parsers;
using Xunit;

namespace AuroraSupplyChainDefender.GitHub.Tests
{
    public class PyPiParserTests
    {
        private static string ReadFixture(string name)
        {
            var path = Path.Combine(
                Path.GetDirectoryName(typeof(PyPiParserTests).Assembly.Location)!,
                "Fixtures", name);
            return File.ReadAllText(path);
        }

        [Fact]
        public void ParseRequirementsTxt_HandlesPinnedAndRange()
        {
            var entries = PyPiParser.ParseRequirementsTxt(ReadFixture("requirements.txt"));

            // Real packages: requests, flask, django, pyyaml, numpy = 5.
            // Plus one referenced-not-resolved include (-r dev-requirements.txt).
            var pkgs = entries.Where(e => e.Ecosystem == "pypi").ToList();
            Assert.Equal(5, pkgs.Count);

            var requests = pkgs.Single(e => e.Name == "requests");
            Assert.Equal("2.31.0", requests.Version);

            var flask = pkgs.Single(e => e.Name == "flask");
            Assert.Equal(">=2.2,<3.0", flask.Version);

            // django==4.2.7 with a trailing comment must still parse to 4.2.7.
            var django = pkgs.Single(e => e.Name == "django");
            Assert.Equal("4.2.7", django.Version);

            // pyyaml ; python_version >= "3.7" — env marker stripped, no version.
            var pyyaml = pkgs.Single(e => e.Name == "pyyaml");
            Assert.Equal(string.Empty, pyyaml.Version);

            // Unpinned numpy.
            var numpy = pkgs.Single(e => e.Name == "numpy");
            Assert.Equal(string.Empty, numpy.Version);
        }

        [Fact]
        public void ParseRequirementsTxt_SkipsRecursiveIncludes()
        {
            var entries = PyPiParser.ParseRequirementsTxt(ReadFixture("requirements.txt"));

            // The -r line is recorded as a non-package marker, ecosystem
            // "pypi-include", so MaintainerHealth/VulnLookup skip it but
            // operators still see it in the output.
            var includes = entries.Where(e => e.Ecosystem == "pypi-include").ToList();
            Assert.Single(includes);
            Assert.Equal("dev-requirements.txt", includes[0].Name);

            // It must NOT appear as a real package.
            var pkgs = entries.Where(e => e.Ecosystem == "pypi").ToList();
            Assert.DoesNotContain(pkgs, e => e.Name.Contains("dev-requirements"));
        }

        [Fact]
        public void ParseRequirementsTxt_IgnoresBlankAndCommentLines()
        {
            var text = "# nothing here\n\n  # indented comment\n";
            Assert.Empty(PyPiParser.ParseRequirementsTxt(text));
        }
    }
}
