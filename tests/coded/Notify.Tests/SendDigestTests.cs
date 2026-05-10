using System;
using System.Net;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using AuroraSupplyChainDefender.Notify;
using Moq;
using Moq.Protected;
using Xunit;

namespace AuroraSupplyChainDefender.Notify.Tests;

/// <summary>
/// Hermetic tests for <see cref="SendDigest"/>. Uses Moq to mock
/// <see cref="HttpMessageHandler"/> so no real HTTP calls are made.
/// </summary>
public class SendDigestTests
{
    private const string TestToken = "xoxb-test-token";
    private static readonly DigestEntry SampleEntry = new()
    {
        Finding = "Typosquat: lodaash → lodash",
        Severity = "Warning",
        Ecosystem = "npm",
        Timestamp = new DateTime(2026, 5, 9, 12, 0, 0, DateTimeKind.Utc),
    };

    /// <summary>
    /// Creates an <see cref="HttpClient"/> backed by a mock handler that
    /// returns the given response.
    /// </summary>
    private static HttpClient CreateMockClient(
        HttpStatusCode status,
        string responseBody,
        int callCount = 1)
    {
        var handler = new Mock<HttpMessageHandler>(MockBehavior.Strict);
        var setup = handler
            .Protected()
            .SetupSequence<Task<HttpResponseMessage>>(
                "SendAsync",
                ItExpr.IsAny<HttpRequestMessage>(),
                ItExpr.IsAny<CancellationToken>());

        for (int i = 0; i < callCount; i++)
        {
            setup = setup.ReturnsAsync(new HttpResponseMessage
            {
                StatusCode = status,
                Content = new StringContent(responseBody),
            });
        }

        return new HttpClient(handler.Object) { Timeout = TimeSpan.FromSeconds(5) };
    }

    /// <summary>
    /// Creates a SendDigest with a mock HttpClient that intercepts the
    /// request for verification.
    /// </summary>
    private static (SendDigest, Mock<HttpMessageHandler>) CreateWorkflowWithHandler(
        HttpStatusCode status,
        string responseBody)
    {
        var handler = new Mock<HttpMessageHandler>(MockBehavior.Strict);
        handler
            .Protected()
            .Setup<Task<HttpResponseMessage>>(
                "SendAsync",
                ItExpr.IsAny<HttpRequestMessage>(),
                ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(new HttpResponseMessage
            {
                StatusCode = status,
                Content = new StringContent(responseBody),
            });

        var client = new HttpClient(handler.Object) { Timeout = TimeSpan.FromSeconds(5) };
        // Set the token via env so ResolveToken finds it.
        Environment.SetEnvironmentVariable("SLACK_BOT_TOKEN", TestToken);
        var workflow = new SendDigest(client);
        return (workflow, handler);
    }

    [Fact]
    public async Task Posts_With_Bearer_Token()
    {
        // Arrange
        HttpResponseMessage? capturedResponse = null;
        var handler = new Mock<HttpMessageHandler>(MockBehavior.Strict);
        handler
            .Protected()
            .Setup<Task<HttpResponseMessage>>(
                "SendAsync",
                ItExpr.IsAny<HttpRequestMessage>(),
                ItExpr.IsAny<CancellationToken>())
            .Callback<HttpRequestMessage, CancellationToken>((req, _) =>
            {
                // Capture the Authorization header
                capturedResponse = new HttpResponseMessage
                {
                    StatusCode = HttpStatusCode.OK,
                    Content = new StringContent(
                        """{"ok":true,"ts":"12345.6789","channel":"C01"}"""),
                };
            })
            .ReturnsAsync(() => capturedResponse!);

        var client = new HttpClient(handler.Object);
        Environment.SetEnvironmentVariable("SLACK_BOT_TOKEN", TestToken);
        var workflow = new SendDigest(client);

        // Act
        string messageId = await workflow.Execute("#test", SampleEntry);

        // Assert
        Assert.Equal("12345.6789", messageId);
        handler.Protected().Verify(
            "SendAsync",
            Times.Once(),
            ItExpr.Is<HttpRequestMessage>(req =>
                req.Method == HttpMethod.Post &&
                req.RequestUri!.ToString() == "https://slack.com/api/chat.postMessage" &&
                req.Headers.Authorization!.Scheme == "Bearer" &&
                req.Headers.Authorization.Parameter == TestToken),
            ItExpr.IsAny<CancellationToken>());
    }

    [Fact]
    public async Task Retries_On_5xx()
    {
        // Arrange — first response is 503, second is 200
        var handler = new Mock<HttpMessageHandler>(MockBehavior.Strict);
        handler
            .Protected()
            .SetupSequence<Task<HttpResponseMessage>>(
                "SendAsync",
                ItExpr.IsAny<HttpRequestMessage>(),
                ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(new HttpResponseMessage
            {
                StatusCode = HttpStatusCode.ServiceUnavailable,
                Content = new StringContent("Service Unavailable"),
            })
            .ReturnsAsync(new HttpResponseMessage
            {
                StatusCode = HttpStatusCode.OK,
                Content = new StringContent(
                    """{"ok":true,"ts":"retry-ts"}"""),
            });

        var client = new HttpClient(handler.Object);
        Environment.SetEnvironmentVariable("SLACK_BOT_TOKEN", TestToken);
        var workflow = new SendDigest(client);

        // Act
        string messageId = await workflow.Execute("#alerts", SampleEntry);

        // Assert — second attempt succeeded
        Assert.Equal("retry-ts", messageId);
        handler.Protected().Verify(
            "SendAsync",
            Times.Exactly(2),
            ItExpr.IsAny<HttpRequestMessage>(),
            ItExpr.IsAny<CancellationToken>());
    }

    [Fact]
    public async Task Returns_Ts_On_200()
    {
        // Arrange
        var (workflow, _) = CreateWorkflowWithHandler(
            HttpStatusCode.OK,
            """{"ok":true,"ts":"1503435956.000247"}""");

        // Act
        string messageId = await workflow.Execute("#general", SampleEntry);

        // Assert
        Assert.Equal("1503435956.000247", messageId);
    }

    [Fact]
    public async Task Throws_On_4xx()
    {
        // Arrange — 400 response should NOT be retried (R.E.03)
        var handler = new Mock<HttpMessageHandler>(MockBehavior.Strict);
        handler
            .Protected()
            .Setup<Task<HttpResponseMessage>>(
                "SendAsync",
                ItExpr.IsAny<HttpRequestMessage>(),
                ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(new HttpResponseMessage
            {
                StatusCode = HttpStatusCode.BadRequest,
                Content = new StringContent(
                    """{"ok":false,"error":"invalid_channel"}"""),
            });

        var client = new HttpClient(handler.Object);
        Environment.SetEnvironmentVariable("SLACK_BOT_TOKEN", TestToken);
        var workflow = new SendDigest(client);

        // Act & Assert — should throw immediately, not retry
        var ex = await Assert.ThrowsAsync<HttpRequestException>(
            () => workflow.Execute("#bad-channel", SampleEntry));

        Assert.Contains("invalid_channel", ex.Message);
        handler.Protected().Verify(
            "SendAsync",
            Times.Once(), // only one call, no retry
            ItExpr.IsAny<HttpRequestMessage>(),
            ItExpr.IsAny<CancellationToken>());
    }

    [Fact]
    public void BuildSlackPayload_Produces_Correct_Shape()
    {
        // Pure helper test (R.K.01)
        SlackPayload payload = SendDigest.BuildSlackPayload("#ops", SampleEntry);

        Assert.Equal("#ops", payload.Channel);
        Assert.Contains("Warning", payload.Text);
        Assert.Contains("npm", payload.Text);
        Assert.Contains("Typosquat: lodaash", payload.Text);
    }

    [Fact]
    public void ParseSlackResponse_Throws_On_OkFalse()
    {
        var ex = Assert.Throws<HttpRequestException>(() =>
            SendDigest.ParseSlackResponse(
                """{"ok":false,"error":"not_authed"}"""));

        Assert.Contains("not_authed", ex.Message);
    }

    [Fact]
    public void ParseSlackResponse_Extracts_Ts()
    {
        string ts = SendDigest.ParseSlackResponse(
            """{"ok":true,"channel":"C01","ts":"9999.0001"}""");

        Assert.Equal("9999.0001", ts);
    }
}
