using System;
using System.Collections.Generic;
using System.Linq;
using System.Net;
using System.Threading.Tasks;
using Octokit;
using UiPath.CodedWorkflows;

namespace AuroraSupplyChainDefender.GitHub;

/// <summary>
/// OpenPatchPR Coded Workflow. Entry point for the BPMN <c>OpenPatchPR</c>
/// service task in the Open-Source Supply-Chain Defender process
/// (see <c>examples/oss-supply-chain-defender/process.bpmn</c>): opens a real
/// GitHub PR with the proposed patch and labels it so the downstream
/// <c>AutoMerge</c> DMN gate can decide whether to merge automatically once
/// CI is green.
/// </summary>
/// <remarks>
/// <para>
/// Workflow shape, in order:
/// </para>
/// <list type="number">
///   <item>Resolve the target repository's default branch.</item>
///   <item>Create the patch branch from the default branch's tip — or, if
///   the patch branch already exists from a previous (failed) run, reuse it
///   so the workflow is idempotent.</item>
///   <item>Push commits via the Contents API: <c>UpdateFile</c> when the
///   target file already exists on the patch branch, <c>CreateFile</c>
///   otherwise.</item>
///   <item>Open the PR using <see cref="BumpHelper"/>-built title/body — or
///   reuse the existing PR if one is already open from the same branch.</item>
///   <item>Apply the labels <c>aurora-patch</c> and
///   <c>auto-merge-eligible</c>.</item>
/// </list>
/// <para>
/// Every external boundary is wrapped in <c>try</c>/<c>catch</c> per R.E.01;
/// transient 5xx faults are retried up to 3 times with a 5-second delay per
/// R.E.02; 4xx authentication failures are surfaced unwrapped per R.E.03.
/// Logging goes through <see cref="SafeLog"/> per R.L.03 — the
/// <c>GITHUB_TOKEN</c> credential is never logged (R.X.03).
/// </para>
/// </remarks>
public class Open : CodedWorkflowBase
{
    /// <summary>Maximum retry attempts on transient (5xx / network) faults.</summary>
    public const int MaxRetryAttempts = 3;

    /// <summary>
    /// Delay between retry attempts. R.E.02 floor is 5 seconds. Exposed as a
    /// mutable static so the unit-test fixture can shrink it without forcing
    /// a 5-second sleep into every retry test; the production default is the
    /// 5-second R.E.02 minimum.
    /// </summary>
    public static TimeSpan RetryDelay { get; set; } = TimeSpan.FromSeconds(5);

    /// <summary>Labels applied to every PR opened by this workflow.</summary>
    public static readonly IReadOnlyList<string> PrLabels = new[]
    {
        "aurora-patch",
        "auto-merge-eligible",
    };

    private readonly IGitHubClient? _injectedClient;
    private readonly string? _ownerOverride;
    private readonly string? _repoOverride;

    /// <summary>
    /// Default constructor used by the runtime. Reads <c>GITHUB_TOKEN</c>,
    /// <c>GITHUB_OWNER</c>, and <c>GITHUB_REPO</c> from the environment when
    /// the workflow runs; the credential is never read until
    /// <see cref="Execute"/> is invoked.
    /// </summary>
    public Open()
    {
    }

    /// <summary>
    /// Test-only constructor that lets the unit-test fixture inject a mocked
    /// <see cref="IGitHubClient"/> and a fixed owner/repo pair, bypassing the
    /// environment-variable lookup.
    /// </summary>
    public Open(IGitHubClient client, string owner, string repo)
    {
        _injectedClient = client ?? throw new ArgumentNullException(nameof(client));
        _ownerOverride = owner ?? throw new ArgumentNullException(nameof(owner));
        _repoOverride = repo ?? throw new ArgumentNullException(nameof(repo));
    }

    /// <summary>
    /// Workflow entry point. Opens a patch PR for <paramref name="in_objFinding"/>
    /// applying <paramref name="in_objDiff"/> and returns the PR coordinates.
    /// </summary>
    /// <param name="in_objFinding">
    /// The vulnerability finding driving this patch. Argument follows
    /// REFramework R.N.02 (<c>in_</c> direction prefix).
    /// </param>
    /// <param name="in_objDiff">
    /// The proposed diff to apply. Argument follows REFramework R.N.02.
    /// </param>
    /// <returns>
    /// A <see cref="PrResult"/> with the PR's HTML URL, number, branch, and
    /// the list of paths touched. The Maestro variable <c>pr_url</c> binds to
    /// <see cref="PrResult.Url"/>.
    /// </returns>
    [Workflow]
    public PrResult Execute(VulnFinding in_objFinding, ProposedDiff in_objDiff)
    {
        if (in_objFinding is null) throw new ArgumentNullException(nameof(in_objFinding));
        if (in_objDiff is null) throw new ArgumentNullException(nameof(in_objDiff));

        SafeLog(
            "Starting GitHub.Open (OpenPatchPR)",
            LogLevel.Info,
            new Dictionary<string, object>
            {
                ["package"] = in_objFinding.Package ?? string.Empty,
                ["ecosystem"] = in_objFinding.Ecosystem ?? string.Empty,
                ["cve"] = in_objFinding.Cve ?? string.Empty,
                ["fileCount"] = in_objDiff.Files?.Count ?? 0,
            });

        // Resolve the GitHub client + target repo. The token is fetched once
        // here and never logged.
        IGitHubClient client = _injectedClient ?? BuildClientFromEnvironment();
        (string owner, string repo) = ResolveTargetRepo();

        string branch = BumpHelper.ComputeBranchName(in_objFinding);
        string commitMessage = BumpHelper.BuildCommitMessage(in_objFinding);
        string title = BumpHelper.BuildPrTitle(in_objFinding);
        string body = BumpHelper.BuildPrBody(in_objFinding, in_objDiff);

        // Run the async pipeline synchronously — the UiPath runtime drives the
        // workflow synchronously and the underlying SDK is async-only. We
        // GetAwaiter().GetResult() instead of .Wait() so exceptions surface
        // unwrapped.
        PrResult result;
        try
        {
            result = OpenPullRequestAsync(
                client, owner, repo, branch, commitMessage, title, body, in_objDiff)
                .GetAwaiter().GetResult();
        }
        catch (AuthorizationException)
        {
            // R.E.03 — never retry on 4xx auth failures; surface them.
            SafeLog(
                "GitHub auth failure opening patch PR",
                LogLevel.Error,
                new Dictionary<string, object> { ["owner"] = owner, ["repo"] = repo });
            throw;
        }
        catch (ApiException ex) when (Is4xxNonRetryable(ex))
        {
            SafeLog(
                $"GitHub 4xx opening patch PR: {(int?)ex.StatusCode}",
                LogLevel.Error,
                new Dictionary<string, object>
                {
                    ["owner"] = owner,
                    ["repo"] = repo,
                    ["status"] = (int?)ex.StatusCode ?? -1,
                });
            throw;
        }

        SafeLog(
            "Completed GitHub.Open (OpenPatchPR)",
            LogLevel.Info,
            new Dictionary<string, object>
            {
                ["prNumber"] = result.Number,
                ["branch"] = result.Branch,
                ["filesTouched"] = result.FilesTouched.Count,
            });
        return result;
    }

    private async Task<PrResult> OpenPullRequestAsync(
        IGitHubClient client,
        string owner,
        string repo,
        string branch,
        string commitMessage,
        string title,
        string body,
        ProposedDiff diff)
    {
        // Step 1: resolve default branch.
        Repository repository = await WithRetryAsync(
            () => client.Repository.Get(owner, repo),
            "Repository.Get").ConfigureAwait(false);
        string defaultBranch = repository.DefaultBranch;
        if (string.IsNullOrWhiteSpace(defaultBranch))
        {
            throw new InvalidOperationException(
                $"Repository {owner}/{repo} has no default branch.");
        }

        // Step 2: create the patch branch from the default branch's tip, or
        // reuse it if it already exists (idempotent rerun).
        Reference defaultRef = await WithRetryAsync(
            () => client.Git.Reference.Get(owner, repo, $"heads/{defaultBranch}"),
            "Git.Reference.Get(default)").ConfigureAwait(false);

        Reference? branchRef = await TryGetReferenceAsync(
            client, owner, repo, $"heads/{branch}").ConfigureAwait(false);
        if (branchRef is null)
        {
            branchRef = await WithRetryAsync(
                () => client.Git.Reference.Create(
                    owner, repo, new NewReference($"refs/heads/{branch}", defaultRef.Object.Sha)),
                "Git.Reference.Create").ConfigureAwait(false);
        }

        // Step 3: push commits via the Contents API.
        var filesTouched = new List<string>();
        if (diff.Files is not null)
        {
            foreach (KeyValuePair<string, string> file in diff.Files)
            {
                if (string.IsNullOrWhiteSpace(file.Key))
                {
                    continue;
                }
                if (file.Value is null)
                {
                    throw new InvalidOperationException(
                        $"ProposedDiff.Files['{file.Key}'] is null; expected a string body.");
                }

                await UpsertFileAsync(
                    client, owner, repo, branch, file.Key, file.Value, commitMessage)
                    .ConfigureAwait(false);
                filesTouched.Add(file.Key);
            }
        }

        // Step 4: open the PR — or reuse an existing open one for this branch
        // (idempotent rerun).
        PullRequest pr = await OpenOrFindPullRequestAsync(
            client, owner, repo, branch, defaultBranch, title, body)
            .ConfigureAwait(false);

        // Step 5: tag the PR with our labels.
        await WithRetryAsync(
            () => client.Issue.Labels.AddToIssue(owner, repo, pr.Number, PrLabels.ToArray()),
            "Issue.Labels.AddToIssue").ConfigureAwait(false);

        return new PrResult
        {
            Url = pr.HtmlUrl,
            Number = pr.Number,
            Branch = branch,
            FilesTouched = filesTouched,
        };
    }

    private async Task UpsertFileAsync(
        IGitHubClient client,
        string owner,
        string repo,
        string branch,
        string path,
        string content,
        string commitMessage)
    {
        // Try to find the file on the branch first; UpdateFile if found,
        // CreateFile if not.
        IReadOnlyList<RepositoryContent>? existing = null;
        try
        {
            existing = await WithRetryAsync(
                () => client.Repository.Content.GetAllContentsByRef(owner, repo, path, branch),
                "Repository.Content.GetAllContentsByRef").ConfigureAwait(false);
        }
        catch (NotFoundException)
        {
            existing = null;
        }

        RepositoryContent? current = existing?.Count > 0 ? existing[0] : null;
        if (current is not null)
        {
            await WithRetryAsync(
                () => client.Repository.Content.UpdateFile(
                    owner, repo, path,
                    new UpdateFileRequest(commitMessage, content, current.Sha, branch)),
                "Repository.Content.UpdateFile").ConfigureAwait(false);
        }
        else
        {
            await WithRetryAsync(
                () => client.Repository.Content.CreateFile(
                    owner, repo, path,
                    new CreateFileRequest(commitMessage, content, branch)),
                "Repository.Content.CreateFile").ConfigureAwait(false);
        }
    }

    private async Task<PullRequest> OpenOrFindPullRequestAsync(
        IGitHubClient client,
        string owner,
        string repo,
        string branch,
        string defaultBranch,
        string title,
        string body)
    {
        try
        {
            return await WithRetryAsync(
                () => client.PullRequest.Create(
                    owner, repo,
                    new NewPullRequest(title, branch, defaultBranch) { Body = body }),
                "PullRequest.Create").ConfigureAwait(false);
        }
        catch (ApiException ex) when (IsPullRequestAlreadyExists(ex))
        {
            // GitHub returns 422 when a PR is already open from this head ref.
            // List PRs on the branch and return the existing one.
            IReadOnlyList<PullRequest> existing = await WithRetryAsync(
                () => client.PullRequest.GetAllForRepository(
                    owner, repo,
                    new PullRequestRequest
                    {
                        State = ItemStateFilter.Open,
                        Head = $"{owner}:{branch}",
                    }),
                "PullRequest.GetAllForRepository").ConfigureAwait(false);
            PullRequest? match = existing.FirstOrDefault();
            if (match is null)
            {
                throw;
            }
            return match;
        }
    }

    private async Task<Reference?> TryGetReferenceAsync(
        IGitHubClient client, string owner, string repo, string reference)
    {
        try
        {
            return await WithRetryAsync(
                () => client.Git.Reference.Get(owner, repo, reference),
                "Git.Reference.Get").ConfigureAwait(false);
        }
        catch (NotFoundException)
        {
            return null;
        }
    }

    /// <summary>
    /// Octokit retry handler. Re-runs <paramref name="action"/> on transient
    /// 5xx faults up to <see cref="MaxRetryAttempts"/> times with
    /// <see cref="RetryDelay"/> between attempts. Re-raises 4xx auth failures
    /// immediately (R.E.03). Internal so unit tests can hit retry paths
    /// through the public <see cref="Execute"/> entry point.
    /// </summary>
    internal async Task<T> WithRetryAsync<T>(Func<Task<T>> action, string operationLabel)
    {
        if (action is null) throw new ArgumentNullException(nameof(action));

        int attempt = 0;
        Exception? lastError = null;
        while (attempt < MaxRetryAttempts)
        {
            attempt++;
            try
            {
                return await action().ConfigureAwait(false);
            }
            catch (AuthorizationException)
            {
                // R.E.03 — never retry on 4xx auth.
                throw;
            }
            catch (ApiException ex) when (Is4xxNonRetryable(ex))
            {
                // R.E.03 — never retry on other 4xx.
                throw;
            }
            catch (ApiException ex)
            {
                lastError = ex;
                SafeLog(
                    $"Transient API fault on {operationLabel}: {(int?)ex.StatusCode}",
                    LogLevel.Warn,
                    new Dictionary<string, object>
                    {
                        ["attempt"] = attempt,
                        ["status"] = (int?)ex.StatusCode ?? -1,
                        ["operation"] = operationLabel,
                    });
            }
            catch (Exception ex) when (IsTransientNetworkFailure(ex))
            {
                lastError = ex;
                SafeLog(
                    $"Transient network fault on {operationLabel}: {ex.GetType().Name}",
                    LogLevel.Warn,
                    new Dictionary<string, object>
                    {
                        ["attempt"] = attempt,
                        ["operation"] = operationLabel,
                    });
            }

            if (attempt < MaxRetryAttempts)
            {
                await Task.Delay(RetryDelay).ConfigureAwait(false);
            }
        }

        throw new InvalidOperationException(
            $"GitHub.Open: {operationLabel} failed after {MaxRetryAttempts} attempts.",
            lastError);
    }

    private static bool Is4xxNonRetryable(ApiException ex)
    {
        int status = (int)ex.StatusCode;
        // 401/403 — auth; 422 — validation. None retryable.
        // 404 — surface as a real not-found via NotFoundException; never reached
        // here because Octokit raises NotFoundException, not ApiException, for 404.
        if (status == 401 || status == 403 || status == 422) return true;
        return status >= 400 && status < 500;
    }

    private static bool IsPullRequestAlreadyExists(ApiException ex)
    {
        // GitHub returns 422 with message "A pull request already exists" when
        // an open PR is already on this head ref.
        if ((int)ex.StatusCode != 422) return false;
        return ex.Message?.IndexOf("pull request already exists",
            StringComparison.OrdinalIgnoreCase) >= 0;
    }

    private static bool IsTransientNetworkFailure(Exception ex)
    {
        // Octokit wraps network failures in HttpRequestException; treat them
        // as retryable along with operation cancellations and TaskCanceled
        // (HTTP timeout) — none of these are auth/validation failures.
        return ex is System.Net.Http.HttpRequestException
            || ex is TaskCanceledException
            || ex is OperationCanceledException;
    }

    private (string Owner, string Repo) ResolveTargetRepo()
    {
        if (!string.IsNullOrEmpty(_ownerOverride) && !string.IsNullOrEmpty(_repoOverride))
        {
            return (_ownerOverride!, _repoOverride!);
        }

        string owner = Environment.GetEnvironmentVariable("GITHUB_OWNER") ?? string.Empty;
        string repo = Environment.GetEnvironmentVariable("GITHUB_REPO") ?? string.Empty;
        if (string.IsNullOrWhiteSpace(owner) || string.IsNullOrWhiteSpace(repo))
        {
            throw new InvalidOperationException(
                "GITHUB_OWNER and GITHUB_REPO environment variables must be set.");
        }
        return (owner.Trim(), repo.Trim());
    }

    private static IGitHubClient BuildClientFromEnvironment()
    {
        // R.X.03 — read the token here and never log it.
        string token = Environment.GetEnvironmentVariable("GITHUB_TOKEN") ?? string.Empty;
        if (string.IsNullOrWhiteSpace(token))
        {
            throw new InvalidOperationException(
                "GITHUB_TOKEN environment variable must be set.");
        }
        var client = new GitHubClient(new ProductHeaderValue("aurora-supply-chain-defender"))
        {
            Credentials = new Credentials(token),
        };
        return client;
    }

    /// <summary>
    /// Wraps the base-class <c>Log</c> in a try/catch so the workflow logic
    /// stays unit-testable outside the UiPath runtime, where the logger
    /// service container is not wired up. R.L.03 still holds in production.
    /// </summary>
    private void SafeLog(string message, LogLevel level, IDictionary<string, object> fields)
    {
        try
        {
            Log(message, level, fields);
        }
        catch (NullReferenceException)
        {
            // Runtime not initialised (e.g., xUnit harness). Discard.
        }
    }
}
