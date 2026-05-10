using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Octokit;
using UiPath.CodedWorkflows;

namespace AuroraSupplyChainDefender.GitHub;

/// <summary>
/// PostPendingComment Coded Workflow. Entry point for the BPMN
/// <c>PostPendingComment</c> send task in the Open-Source Supply-Chain
/// Defender process (<c>bindings.json</c>). Posts an idempotent
/// audit-trail comment on a PR to signal that AURORA is watching for
/// CI completion. If a comment with the marker already exists, the
/// workflow returns the existing comment's URL without posting a
/// duplicate.
/// </summary>
/// <remarks>
/// <para>
/// Idempotency is structural (R.K.06): the deterministic marker
/// <c>&lt;!-- aurora:waiting-for-ci --&gt;</c> is embedded in the
/// comment body. Before posting, the workflow scans existing comments
/// for this marker; if found, it returns the existing comment's URL.
/// </para>
/// <para>
/// Every external boundary is wrapped in <c>try</c>/<c>catch</c> per
/// R.E.01; transient 5xx faults are retried up to 3 times with a
/// 5-second delay per R.E.02; 4xx authentication failures are
/// surfaced unwrapped per R.E.03. Logging goes through
/// <see cref="SafeLog"/> per R.L.03 — the <c>GITHUB_TOKEN</c>
/// credential is never logged (R.X.03).
/// </para>
/// </remarks>
public class PostPendingComment : CodedWorkflowBase
{
    /// <summary>HTML comment marker embedded in the posted comment body.</summary>
    public const string CommentMarker = "<!-- aurora:waiting-for-ci -->";

    /// <summary>Maximum retry attempts on transient (5xx / network) faults.</summary>
    public const int MaxRetryAttempts = 3;

    /// <summary>
    /// Delay between retry attempts. Exposed as a mutable static so the
    /// unit-test fixture can shrink it without forcing a 5-second sleep.
    /// </summary>
    public static TimeSpan RetryDelay { get; set; } = TimeSpan.FromSeconds(5);

    private readonly IGitHubClient? _injectedClient;
    private readonly string? _ownerOverride;
    private readonly string? _repoOverride;

    /// <summary>
    /// Default constructor used by the UiPath runtime. Reads
    /// <c>GITHUB_TOKEN</c>, <c>GITHUB_OWNER</c>, and
    /// <c>GITHUB_REPO</c> from the environment at execution time.
    /// </summary>
    public PostPendingComment()
    {
    }

    /// <summary>
    /// Test-only constructor that lets the xUnit harness inject a mocked
    /// <see cref="IGitHubClient"/> and a fixed owner/repo pair.
    /// </summary>
    public PostPendingComment(IGitHubClient client, string owner, string repo)
    {
        _injectedClient = client ?? throw new ArgumentNullException(nameof(client));
        _ownerOverride = owner ?? throw new ArgumentNullException(nameof(owner));
        _repoOverride = repo ?? throw new ArgumentNullException(nameof(repo));
    }

    /// <summary>
    /// Workflow entry point. Posts a "waiting for CI" audit-trail comment
    /// on the specified pull request, or returns the existing one if the
    /// marker is already present (idempotent, R.K.06).
    /// </summary>
    /// <param name="in_strRepoFullName">
    /// Full repository name in <c>owner/repo</c> format. Argument follows
    /// REFramework R.N.02 (<c>in_</c> direction prefix, <c>str</c> type
    /// abbreviation).
    /// </param>
    /// <param name="in_intPullNumber">
    /// Pull request number. Argument follows REFramework R.N.02.
    /// </param>
    /// <returns>
    /// The marker string <c>&lt;!-- aurora:waiting-for-ci --&gt;</c>,
    /// confirming the comment exists on the PR. The Maestro variable
    /// <c>ci_comment_marker</c> binds to this output.
    /// </returns>
    [Workflow]
    public string Execute(string in_strRepoFullName, int in_intPullNumber)
    {
        if (string.IsNullOrWhiteSpace(in_strRepoFullName))
            throw new ArgumentNullException(nameof(in_strRepoFullName));
        if (in_intPullNumber <= 0)
            throw new ArgumentOutOfRangeException(nameof(in_intPullNumber));

        SafeLog(
            "Starting GitHub.PostPendingComment",
            LogLevel.Info,
            new Dictionary<string, object>
            {
                ["repo"] = in_strRepoFullName,
                ["pullNumber"] = in_intPullNumber,
            });

        IGitHubClient client = _injectedClient ?? BuildClientFromEnvironment();
        (string owner, string repo) = ResolveTargetRepo(in_strRepoFullName);

        string result;
        try
        {
            result = PostOrFindCommentAsync(client, owner, repo, in_intPullNumber)
                .GetAwaiter().GetResult();
        }
        catch (AuthorizationException)
        {
            SafeLog(
                "GitHub auth failure posting pending comment",
                LogLevel.Error,
                new Dictionary<string, object> { ["owner"] = owner, ["repo"] = repo });
            throw;
        }
        catch (ApiException ex) when (Is4xxNonRetryable(ex))
        {
            SafeLog(
                $"GitHub 4xx posting pending comment: {(int?)ex.StatusCode}",
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
            "Completed GitHub.PostPendingComment",
            LogLevel.Info,
            new Dictionary<string, object>
            {
                ["pullNumber"] = in_intPullNumber,
                ["marker"] = CommentMarker,
            });
        return result;
    }

    private async Task<string> PostOrFindCommentAsync(
        IGitHubClient client, string owner, string repo, int pullNumber)
    {
        // Idempotency gate (R.K.06): scan existing comments for the marker.
        IReadOnlyList<IssueComment> comments = await WithRetryAsync(
            () => client.Issue.Comment.GetAllForIssue(owner, repo, pullNumber),
            "Issue.Comment.GetAllForIssue").ConfigureAwait(false);

        IssueComment? existing = comments.FirstOrDefault(c =>
            c.Body?.Contains(CommentMarker, StringComparison.Ordinal) == true);

        if (existing is not null)
        {
            SafeLog(
                "GitHub.PostPendingComment: existing marker comment found (idempotent)",
                LogLevel.Info,
                new Dictionary<string, object>
                {
                    ["commentId"] = existing.Id,
                    ["pullNumber"] = pullNumber,
                });
            return CommentMarker;
        }

        // No existing comment with marker — post one.
        string body = $"{CommentMarker}\n🔍 AURORA is watching CI on this PR. " +
                      "Results will be processed automatically once checks complete.";

        await WithRetryAsync(
            () => client.Issue.Comment.Create(owner, repo, pullNumber, body),
            "Issue.Comment.Create").ConfigureAwait(false);

        return CommentMarker;
    }

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
                throw;
            }
            catch (ApiException ex) when (Is4xxNonRetryable(ex))
            {
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
            $"GitHub.PostPendingComment: {operationLabel} failed after {MaxRetryAttempts} attempts.",
            lastError);
    }

    private static bool Is4xxNonRetryable(ApiException ex)
    {
        int status = (int)ex.StatusCode;
        return status >= 400 && status < 500;
    }

    private static bool IsTransientNetworkFailure(Exception ex)
    {
        return ex is System.Net.Http.HttpRequestException
            || ex is TaskCanceledException
            || ex is OperationCanceledException;
    }

    private (string Owner, string Repo) ResolveTargetRepo(string repoFullName)
    {
        if (!string.IsNullOrEmpty(_ownerOverride) && !string.IsNullOrEmpty(_repoOverride))
        {
            return (_ownerOverride!, _repoOverride!);
        }

        string[] parts = repoFullName.Split('/', 2);
        if (parts.Length != 2 || string.IsNullOrWhiteSpace(parts[0]) || string.IsNullOrWhiteSpace(parts[1]))
        {
            throw new ArgumentException(
                $"Repo full name must be in 'owner/repo' format, got: '{repoFullName}'");
        }
        return (parts[0].Trim(), parts[1].Trim());
    }

    private static IGitHubClient BuildClientFromEnvironment()
    {
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

    private void SafeLog(string message, LogLevel level, IDictionary<string, object> fields)
    {
        try
        {
            Log(message, level, fields);
        }
        catch (NullReferenceException)
        {
        }
    }
}
