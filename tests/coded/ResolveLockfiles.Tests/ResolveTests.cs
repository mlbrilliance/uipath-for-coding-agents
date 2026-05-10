using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using Moq;
using Octokit;
using Xunit;

namespace AuroraSupplyChainDefender.GitHub.Tests
{
    public class ResolveTests
    {
        private static string ReadFixture(string name)
        {
            var path = Path.Combine(
                Path.GetDirectoryName(typeof(ResolveTests).Assembly.Location)!,
                "Fixtures", name);
            return File.ReadAllText(path);
        }

        private static (Mock<IGitHubClient>, Mock<IRepositoriesClient>, Mock<IRepositoryContentsClient>)
            BuildMocks(IReadOnlyList<Repository> repos)
        {
            var contents = new Mock<IRepositoryContentsClient>(MockBehavior.Strict);
            // Default: every path returns NotFound. Tests override for the
            // specific (owner, repo, path) tuples they care about.
            contents
                .Setup(c => c.GetRawContent(It.IsAny<string>(), It.IsAny<string>(), It.IsAny<string>()))
                .ThrowsAsync(new NotFoundException("not found", System.Net.HttpStatusCode.NotFound));

            var repoClient = new Mock<IRepositoriesClient>(MockBehavior.Strict);
            repoClient.SetupGet(r => r.Content).Returns(contents.Object);
            repoClient
                .Setup(r => r.GetAllForOrg(It.IsAny<string>()))
                .ReturnsAsync(repos);

            var client = new Mock<IGitHubClient>(MockBehavior.Strict);
            client.SetupGet(c => c.Repository).Returns(repoClient.Object);

            return (client, repoClient, contents);
        }

        [Fact]
        public async Task Filters_Repos_By_ScanScope_Glob()
        {
            var repos = new[]
            {
                RepoBuilder.Make("acme", "alpha"),
                RepoBuilder.Make("acme", "beta"),
                RepoBuilder.Make("acme", "node-app"),
                RepoBuilder.Make("acme", "py-app"),
                RepoBuilder.Make("acme", "go-app"),
            };
            var (client, _, contents) = BuildMocks(repos);

            // node-app ships package-lock.json, py-app ships requirements.txt.
            contents
                .Setup(c => c.GetRawContent("acme", "node-app", "package-lock.json"))
                .ReturnsAsync(Encoding.UTF8.GetBytes(ReadFixture("package-lock.v3.json")));
            contents
                .Setup(c => c.GetRawContent("acme", "py-app", "requirements.txt"))
                .ReturnsAsync(Encoding.UTF8.GetBytes(ReadFixture("requirements.txt")));

            var resolver = new LockfileResolver(client.Object);
            var result = await resolver.ResolveAsync(
                "acme",
                new List<string> { "node-app", "py-app" });

            // Only the two scope-matched repos should have produced lockfiles.
            Assert.Equal(2, result.Count);
            Assert.Contains(result, l => l.Repo == "acme/node-app" && l.Ecosystem == "npm");
            Assert.Contains(result, l => l.Repo == "acme/py-app" && l.Ecosystem == "pypi");
            Assert.DoesNotContain(result, l => l.Repo.Contains("alpha"));
            Assert.DoesNotContain(result, l => l.Repo.Contains("beta"));
            Assert.DoesNotContain(result, l => l.Repo.Contains("go-app"));

            // Non-matching repos must NOT be probed for lockfile content.
            contents.Verify(
                c => c.GetRawContent("acme", "alpha", It.IsAny<string>()),
                Times.Never);
            contents.Verify(
                c => c.GetRawContent("acme", "beta", It.IsAny<string>()),
                Times.Never);
        }

        [Fact]
        public async Task Returns_Empty_For_Repos_Without_Lockfiles()
        {
            var repos = new[] { RepoBuilder.Make("acme", "empty-repo") };
            var (client, _, _) = BuildMocks(repos);

            var resolver = new LockfileResolver(client.Object);
            var result = await resolver.ResolveAsync(
                "acme",
                new List<string> { "*" });

            Assert.Empty(result);
        }

        [Fact]
        public async Task Continues_On_Per_Repo_Failure()
        {
            // Three repos. First and third have a package-lock.json. Middle
            // one throws an unexpected exception during fetch — the resolver
            // must skip it and still emit the other two (R.E.01).
            var repos = new[]
            {
                RepoBuilder.Make("acme", "first"),
                RepoBuilder.Make("acme", "boom"),
                RepoBuilder.Make("acme", "third"),
            };
            var (client, _, contents) = BuildMocks(repos);

            var pkgLock = Encoding.UTF8.GetBytes(ReadFixture("package-lock.v3.json"));
            contents
                .Setup(c => c.GetRawContent("acme", "first", "package-lock.json"))
                .ReturnsAsync(pkgLock);
            contents
                .Setup(c => c.GetRawContent("acme", "third", "package-lock.json"))
                .ReturnsAsync(pkgLock);
            // Boom: a non-NotFound exception escapes the per-path try/catch
            // path inside FetchRepoLockfilesAsync as a re-throw … so to exercise
            // R.E.01 we need the exception to bubble out of the per-repo try/catch.
            // GetAllForOrg succeeds; GetRawContent for "boom" throws AggregateException
            // for *every* path including ones that would normally NotFound.
            contents
                .Setup(c => c.GetRawContent("acme", "boom", It.IsAny<string>()))
                .ThrowsAsync(new InvalidOperationException("simulated repo-level fault"));

            var resolver = new LockfileResolver(client.Object);
            var result = await resolver.ResolveAsync(
                "acme",
                new List<string> { "*" });

            // first + third resolved despite boom failing.
            Assert.Equal(2, result.Count);
            Assert.Contains(result, l => l.Repo == "acme/first");
            Assert.Contains(result, l => l.Repo == "acme/third");
            Assert.DoesNotContain(result, l => l.Repo == "acme/boom");
        }

        [Fact]
        public async Task ScanScope_Star_Matches_Everything()
        {
            var repos = new[]
            {
                RepoBuilder.Make("acme", "one"),
                RepoBuilder.Make("acme", "two"),
            };
            var (client, _, contents) = BuildMocks(repos);
            contents
                .Setup(c => c.GetRawContent("acme", "one", "go.sum"))
                .ReturnsAsync(Encoding.UTF8.GetBytes(ReadFixture("go.sum")));
            contents
                .Setup(c => c.GetRawContent("acme", "two", "go.sum"))
                .ReturnsAsync(Encoding.UTF8.GetBytes(ReadFixture("go.sum")));

            var resolver = new LockfileResolver(client.Object);
            var result = await resolver.ResolveAsync("acme", new List<string> { "*" });
            Assert.Equal(2, result.Count);
            Assert.All(result, l => Assert.Equal("go", l.Ecosystem));
        }
    }
}
