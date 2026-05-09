// AURORA — Supply-Chain Defender
// ResolveLockfiles Coded Workflow.
//
// Bound to BPMN serviceTask "ResolveLockfiles" (entry: GitHub.ResolveLockfiles)
// in examples/oss-supply-chain-defender/process.bpmn.
//
// Contract (PDD US-33, US-34):
//   in_strOrg          GitHub org slug
//   in_arrScanScope    list of repo-name globs ("*" → all)
//   out_dt_Lockfiles   list of Lockfile (one per file found across repos)
//
// The implementation is split:
//   - LockfileResolver (testable, takes any IGitHubClient, no env reads)
//   - Resolve.Execute  (the [Workflow] entry; constructs the client from
//                       GITHUB_TOKEN env and delegates).
//
// Conventions:
//   R.E.01 — every external boundary (per-repo fetch) wrapped in try/catch;
//            one failed repo does not kill the batch.
//   R.E.02 — Octokit retries 3× with 5s delay (RetryScope-equivalent).
//   R.L.03 — UiPath logger via _logger; no Console.WriteLine.
//   R.X.03 — GITHUB_TOKEN read from env only; never written to memory.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using AuroraSupplyChainDefender.GitHub.Parsers;
using Octokit;
using Octokit.Internal;
using UiPath.CodedWorkflows;

namespace AuroraSupplyChainDefender.GitHub
{
    /// <summary>
    /// UiPath Coded Workflow entry. The Maestro engine calls
    /// <see cref="Execute"/> with the bindings declared in bindings.json.
    /// </summary>
    public class Resolve : CodedWorkflowBase
    {
        [Workflow]
        public List<Lockfile> Execute(string in_strOrg, List<string> in_arrScanScope)
        {
            if (string.IsNullOrWhiteSpace(in_strOrg))
            {
                throw new ArgumentException(
                    "in_strOrg is required (R.N.02 arg-prefixed input).",
                    nameof(in_strOrg));
            }
            in_arrScanScope ??= new List<string> { "*" };

            // R.X.03: read GITHUB_TOKEN from env only — never from Config or
            // memory. If absent, fall back to anonymous (lower rate limit).
            var token = Environment.GetEnvironmentVariable("GITHUB_TOKEN");
            var client = BuildGitHubClient(token);

            var resolver = new LockfileResolver(client, MakeLogAdapter());
            return resolver.ResolveAsync(in_strOrg, in_arrScanScope)
                .GetAwaiter().GetResult();
        }

        // The UiPath base class exposes a logger; expose it as a thin Action<string>
        // so LockfileResolver stays free of UiPath types and is unit-testable.
        private Action<string, Exception?> MakeLogAdapter()
        {
            return (msg, ex) =>
            {
                // R.L.03: route through the UiPath logger surface. The base
                // class exposes Log() — call it on every external-boundary
                // event so Orchestrator's job log captures the trace.
                var line = ex is null
                    ? msg
                    : $"{msg} | {ex.GetType().Name}: {ex.Message}";
                try { Log(line); }
                catch { /* logger not yet wired during unit tests */ }
            };
        }

        private static IGitHubClient BuildGitHubClient(string? token)
        {
            // R.E.02: 3 attempts with 5 s delay implemented via a DelegatingHandler.
            var retryHandler = new RetryHandler(maxAttempts: 3, delaySeconds: 5)
            {
                InnerHandler = new HttpClientHandler(),
            };
            var connection = new Connection(
                new ProductHeaderValue("AURORA-SupplyChainDefender"),
                new HttpClientAdapter(() => retryHandler));

            if (!string.IsNullOrWhiteSpace(token))
            {
                connection.Credentials = new Credentials(token);
            }
            return new GitHubClient(connection);
        }
    }

    /// <summary>
    /// Pure orchestrator: enumerate repos, filter by ScanScope glob, fetch
    /// the four supported lockfiles from each repo's default-branch tip,
    /// hand off to the parser. Constructed with any IGitHubClient (Octokit
    /// production client in production; Moq mock in unit tests).
    /// </summary>
    public sealed class LockfileResolver
    {
        public const string PackageLockJson = "package-lock.json";
        public const string YarnLock = "yarn.lock";
        public const string RequirementsTxt = "requirements.txt";
        public const string GoSum = "go.sum";

        private readonly IGitHubClient _client;
        private readonly Action<string, Exception?> _log;

        public LockfileResolver(IGitHubClient client, Action<string, Exception?>? log = null)
        {
            _client = client ?? throw new ArgumentNullException(nameof(client));
            _log = log ?? ((_, __) => { });
        }

        public async Task<List<Lockfile>> ResolveAsync(string org, List<string> scanScope)
        {
            var output = new List<Lockfile>();
            IReadOnlyList<Repository> repos;
            try
            {
                repos = await _client.Repository.GetAllForOrg(org).ConfigureAwait(false);
            }
            catch (Exception ex)
            {
                _log($"Failed to enumerate repos for org '{org}'", ex);
                throw;
            }

            var matchers = (scanScope ?? new List<string> { "*" })
                .Select(GlobToRegex)
                .ToList();

            foreach (var repo in repos)
            {
                if (!matchers.Any(re => re.IsMatch(repo.Name)))
                {
                    continue;
                }

                // R.E.01: per-repo failures never kill the batch.
                try
                {
                    var found = await FetchRepoLockfilesAsync(repo).ConfigureAwait(false);
                    output.AddRange(found);
                }
                catch (Exception ex)
                {
                    _log($"Skipping repo '{repo.FullName}' after error", ex);
                    continue;
                }
            }
            return output;
        }

        private async Task<List<Lockfile>> FetchRepoLockfilesAsync(Repository repo)
        {
            var found = new List<Lockfile>();
            // Look for each lockfile name in the repo root. We try each in
            // turn rather than walking the whole tree — root-level lockfiles
            // are the contract.
            var paths = new[] { PackageLockJson, YarnLock, RequirementsTxt, GoSum };
            foreach (var path in paths)
            {
                string content;
                try
                {
                    var rawBytes = await _client.Repository.Content
                        .GetRawContent(repo.Owner.Login, repo.Name, path)
                        .ConfigureAwait(false);
                    content = Encoding.UTF8.GetString(rawBytes);
                }
                catch (NotFoundException)
                {
                    // Common case: this repo doesn't ship that lockfile.
                    continue;
                }
                catch (Exception ex)
                {
                    _log($"Failed to fetch '{path}' from {repo.FullName}", ex);
                    continue;
                }

                var lockfile = ParseByPath(repo.FullName, path, content);
                if (lockfile is not null)
                {
                    found.Add(lockfile);
                }
            }
            return found;
        }

        /// <summary>
        /// Static parse-dispatch — exposed for unit testing parsing-without-IO.
        /// </summary>
        public static Lockfile? ParseByPath(string repoFullName, string path, string content)
        {
            List<LockfileEntry> entries;
            string ecosystem;
            switch (path)
            {
                case PackageLockJson:
                    entries = NpmParser.ParsePackageLockJson(content);
                    ecosystem = "npm";
                    break;
                case YarnLock:
                    entries = NpmParser.ParseYarnLock(content);
                    ecosystem = "npm";
                    break;
                case RequirementsTxt:
                    entries = PyPiParser.ParseRequirementsTxt(content);
                    ecosystem = "pypi";
                    break;
                case GoSum:
                    entries = GoParser.ParseGoSum(content);
                    ecosystem = "go";
                    break;
                default:
                    return null;
            }
            return new Lockfile
            {
                Repo = repoFullName,
                Path = path,
                Ecosystem = ecosystem,
                Entries = entries,
            };
        }

        // Glob → regex with `*` and `?` wildcards. `*` alone matches anything.
        // Anchored ^...$ to avoid partial-name matches.
        internal static Regex GlobToRegex(string glob)
        {
            if (string.IsNullOrEmpty(glob) || glob == "*")
            {
                return new Regex(".*", RegexOptions.Compiled);
            }
            var sb = new StringBuilder("^");
            foreach (var c in glob)
            {
                switch (c)
                {
                    case '*': sb.Append(".*"); break;
                    case '?': sb.Append('.'); break;
                    default:  sb.Append(Regex.Escape(c.ToString())); break;
                }
            }
            sb.Append('$');
            return new Regex(sb.ToString(), RegexOptions.Compiled);
        }
    }

    /// <summary>
    /// Tiny retry DelegatingHandler honouring R.E.02. 3 attempts, 5 s delay,
    /// retries on transient HTTP failures (5xx, network, 429). 4xx auth
    /// failures (R.E.03) are surfaced immediately.
    /// </summary>
    internal sealed class RetryHandler : DelegatingHandler
    {
        private readonly int _maxAttempts;
        private readonly TimeSpan _delay;

        public RetryHandler(int maxAttempts, int delaySeconds)
        {
            _maxAttempts = maxAttempts < 1 ? 1 : maxAttempts;
            _delay = TimeSpan.FromSeconds(delaySeconds);
        }

        protected override async Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            System.Threading.CancellationToken cancellationToken)
        {
            HttpResponseMessage? response = null;
            Exception? lastEx = null;
            for (var attempt = 1; attempt <= _maxAttempts; attempt++)
            {
                try
                {
                    response = await base.SendAsync(request, cancellationToken)
                        .ConfigureAwait(false);
                    var status = (int)response.StatusCode;
                    // R.E.03: don't retry on 4xx auth (401/403).
                    if (status == 401 || status == 403)
                    {
                        return response;
                    }
                    if (status < 500 && status != 429)
                    {
                        return response;
                    }
                    if (attempt == _maxAttempts) return response;
                }
                catch (HttpRequestException ex)
                {
                    lastEx = ex;
                    if (attempt == _maxAttempts) throw;
                }
                await Task.Delay(_delay, cancellationToken).ConfigureAwait(false);
            }
            // Unreachable — the loop either returns or throws — but keep the
            // compiler happy.
            if (response is not null) return response;
            throw lastEx ?? new HttpRequestException("RetryHandler exhausted with no response.");
        }
    }
}
