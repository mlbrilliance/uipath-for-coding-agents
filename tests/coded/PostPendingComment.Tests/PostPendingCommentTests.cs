using System;
using System.Collections.Generic;
using System.Net;
using System.Threading.Tasks;
using AuroraSupplyChainDefender.GitHub;
using Moq;
using Octokit;
using Xunit;

namespace AuroraSupplyChainDefender.GitHub.Tests;

/// <summary>
/// Hermetic tests for <see cref="PostPendingComment"/>. The underlying
/// <see cref="IGitHubClient"/> is mocked so the workflow's idempotency,
/// retry, and auth-failure behaviour are exercised without hitting the
/// real API.
/// </summary>
public class PostPendingCommentTests
{
    private const string Owner = "demo-org";
    private const string Repo = "demo-repo";
    private const int PullNumber = 42;

    /// <summary>
    /// Wires every IGitHubClient sub-client used by the workflow with a
    /// happy-path response. Returns the <see cref="Mocks"/> bundle so
    /// individual tests can override one call to model a fault.
    /// </summary>
    private static Mocks BuildHappyPathMocks()
    {
        var mocks = new Mocks();

        // No existing comments with marker by default.
        mocks.IssueComments
            .Setup(c => c.GetAllForIssue(Owner, Repo, PullNumber))
            .ReturnsAsync(Array.Empty<IssueComment>());

        // Comment creation succeeds.
        mocks.IssueComments
            .Setup(c => c.Create(Owner, Repo, PullNumber, It.IsAny<string>()))
            .ReturnsAsync((string o, string r, int n, string body) =>
            {
                var comment = new IssueComment();
                OctokitTestFactory.SetProp(comment, nameof(IssueComment.Id), 1234);
                OctokitTestFactory.SetProp(comment, nameof(IssueComment.Body), body);
                OctokitTestFactory.SetProp(comment, nameof(IssueComment.HtmlUrl),
                    $"https://github.com/{Owner}/{Repo}/issues/{n}#issuecomment-1234");
                return comment;
            });

        return mocks;
    }

    [Fact]
    public async Task Execute_Posts_Comment_When_No_Existing_Marker()
    {
        Mocks mocks = BuildHappyPathMocks();
        var workflow = new PostPendingComment(mocks.Client.Object, Owner, Repo);

        string result = await Task.Run(() =>
            workflow.Execute($"{Owner}/{Repo}", PullNumber));

        Assert.Equal(PostPendingComment.CommentMarker, result);
        mocks.IssueComments.Verify(
            c => c.Create(Owner, Repo, PullNumber,
                It.Is<string>(body =>
                    body.Contains(PostPendingComment.CommentMarker, StringComparison.Ordinal))),
            Times.Once);
    }

    [Fact]
    public async Task Execute_Skips_Posting_When_Marker_Already_Exists()
    {
        // R.K.06 — idempotent: if a comment with the marker already exists,
        // do not post another one.
        Mocks mocks = BuildHappyPathMocks();

        var existingComment = new IssueComment();
        OctokitTestFactory.SetProp(existingComment, nameof(IssueComment.Id), 999);
        OctokitTestFactory.SetProp(existingComment, nameof(IssueComment.Body),
            $"{PostPendingComment.CommentMarker}\nOlder message from a prior run.");

        mocks.IssueComments
            .Setup(c => c.GetAllForIssue(Owner, Repo, PullNumber))
            .ReturnsAsync(new[] { existingComment });

        var workflow = new PostPendingComment(mocks.Client.Object, Owner, Repo);

        string result = await Task.Run(() =>
            workflow.Execute($"{Owner}/{Repo}", PullNumber));

        Assert.Equal(PostPendingComment.CommentMarker, result);
        // Create must NOT have been called — idempotent.
        mocks.IssueComments.Verify(
            c => c.Create(Owner, Repo, PullNumber, It.IsAny<string>()),
            Times.Never);
    }

    [Fact]
    public async Task Execute_Throws_On_Null_RepoFullName()
    {
        Mocks mocks = BuildHappyPathMocks();
        var workflow = new PostPendingComment(mocks.Client.Object, Owner, Repo);

        await Assert.ThrowsAsync<ArgumentNullException>(
            () => Task.Run(() => workflow.Execute(null!, PullNumber)));
    }

    [Fact]
    public async Task Execute_Throws_On_Zero_PullNumber()
    {
        Mocks mocks = BuildHappyPathMocks();
        var workflow = new PostPendingComment(mocks.Client.Object, Owner, Repo);

        await Assert.ThrowsAsync<ArgumentOutOfRangeException>(
            () => Task.Run(() => workflow.Execute($"{Owner}/{Repo}", 0)));
    }

    [Fact]
    public async Task Execute_Retries_On_Transient_5xx_Then_Succeeds()
    {
        Mocks mocks = BuildHappyPathMocks();

        int call = 0;
        mocks.IssueComments
            .Setup(c => c.GetAllForIssue(Owner, Repo, PullNumber))
            .Returns(() =>
            {
                call++;
                if (call == 1) throw ApiError(HttpStatusCode.ServiceUnavailable);
                return Task.FromResult<IReadOnlyList<IssueComment>>(Array.Empty<IssueComment>());
            });

        var workflow = new PostPendingCommentWithFastRetry(
            mocks.Client.Object, Owner, Repo);

        string result = await Task.Run(() =>
            workflow.Execute($"{Owner}/{Repo}", PullNumber));

        Assert.Equal(2, call);
        Assert.Equal(PostPendingComment.CommentMarker, result);
    }

    [Fact]
    public async Task Execute_Does_Not_Retry_On_401_Auth_Failure()
    {
        // R.E.03 — never retry on 4xx auth.
        Mocks mocks = BuildHappyPathMocks();

        int call = 0;
        mocks.IssueComments
            .Setup(c => c.GetAllForIssue(Owner, Repo, PullNumber))
            .Returns(() =>
            {
                call++;
                throw new AuthorizationException(
                    HttpStatusCode.Unauthorized, new Exception("auth failed"));
            });

        var workflow = new PostPendingCommentWithFastRetry(
            mocks.Client.Object, Owner, Repo);

        await Assert.ThrowsAsync<AuthorizationException>(
            () => Task.Run(() => workflow.Execute($"{Owner}/{Repo}", PullNumber)));

        Assert.Equal(1, call);
    }

    [Fact]
    public async Task Execute_Parses_RepoFullName_Correctly()
    {
        Mocks mocks = BuildHappyPathMocks();
        var workflow = new PostPendingComment(mocks.Client.Object, Owner, Repo);

        await Task.Run(() => workflow.Execute($"{Owner}/{Repo}", PullNumber));

        mocks.IssueComments.Verify(
            c => c.GetAllForIssue(Owner, Repo, PullNumber),
            Times.Once);
    }

    [Fact]
    public async Task Execute_Throws_On_Malformed_RepoFullName_Without_Override()
    {
        // When no owner/repo override is injected, ResolveTargetRepo parses
        // the repoFullName. A name without '/' should throw.
        var workflow = new PostPendingComment();

        await Assert.ThrowsAsync<ArgumentException>(
            () => Task.Run(() => workflow.Execute("no-slash-here", PullNumber)));
    }

    /// <summary>
    /// Test subclass that shrinks <see cref="PostPendingComment.RetryDelay"/>
    /// so retry tests don't sleep for 5 seconds.
    /// </summary>
    private sealed class PostPendingCommentWithFastRetry : PostPendingComment
    {
        public PostPendingCommentWithFastRetry(IGitHubClient client, string owner, string repo)
            : base(client, owner, repo)
        {
            PostPendingComment.RetryDelay = TimeSpan.FromMilliseconds(1);
        }
    }

    /// <summary>Bundle of Moq objects used by every test.</summary>
    private sealed class Mocks
    {
        public Mock<IGitHubClient> Client { get; } = new(MockBehavior.Strict);
        public Mock<IIssuesClient> Issues { get; } = new(MockBehavior.Strict);
        public Mock<IIssueCommentsClient> IssueComments { get; } = new(MockBehavior.Strict);

        public Mocks()
        {
            Client.SetupGet(c => c.Issue).Returns(Issues.Object);
            Issues.SetupGet(c => c.Comment).Returns(IssueComments.Object);
        }
    }

    private static ApiException ApiError(HttpStatusCode status)
    {
        return new ApiException($"GitHub returned {status}", status);
    }
}
