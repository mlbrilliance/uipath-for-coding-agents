using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
using UiPath.CodedWorkflows;

namespace AuroraSupplyChainDefender.Notify;

/// <summary>
/// Posts a structured finding to a Slack channel via the
/// <c>chat.postMessage</c> Web API.
/// </summary>
/// <remarks>
/// <para>
/// Implements the "Notify.SendDigest" service task from the BPMN
/// (<c>process.bpmn</c>). Called after <see cref="AppendToDigest"/> so the
/// operator sees the finding in real time.
/// </para>
/// <para>
/// The Slack bot token is read from <c>SLACK_BOT_TOKEN</c> per R.X.01-R.X.04.
/// The token is never logged or serialised. Every HTTP POST is wrapped in a
/// retry loop (≥ 3 retries, ≥ 5 s interval) per R.E.02. 4xx failures are not
/// retried per R.E.03.
/// </para>
/// </remarks>
public class SendDigest : CodedWorkflowBase
{
    private const string SlackApiBase = "https://slack.com/api/chat.postMessage";
    private const int MaxRetries = 3;
    private static readonly TimeSpan RetryInterval = TimeSpan.FromSeconds(5);

    private readonly HttpClient _httpClient;

    /// <summary>
    /// Default constructor used by the UiPath runtime. Creates a fresh
    /// <see cref="HttpClient"/> with a 30-second timeout.
    /// </summary>
    public SendDigest()
        : this(new HttpClient { Timeout = TimeSpan.FromSeconds(30) })
    {
    }

    /// <summary>
    /// Test-only constructor that accepts an <see cref="HttpClient"/> with a
    /// mocked <see cref="HttpMessageHandler"/> so unit tests can control HTTP
    /// responses without hitting the real Slack API.
    /// </summary>
    /// <param name="httpClient">Pre-configured HttpClient (typically with
    /// a mock handler).</param>
    public SendDigest(HttpClient httpClient)
    {
        _httpClient = httpClient ?? throw new ArgumentNullException(nameof(httpClient));
    }

    /// <summary>
    /// Workflow entry point.
    /// </summary>
    /// <param name="in_strChannel">Slack channel ID or name (e.g.
    /// <c>"#supply-chain-alerts"</c>).</param>
    /// <param name="in_objPayload">The finding to post.</param>
    /// <returns>
    /// The Slack message timestamp (<c>ts</c>) on success, e.g.
    /// <c>"1503435956.000247"</c>.
    /// </returns>
    /// <exception cref="ArgumentException">
    /// Thrown if <paramref name="in_strChannel"/> is null/empty or
    /// <paramref name="in_objPayload"/> is null.
    /// </exception>
    /// <exception cref="HttpRequestException">
    /// Thrown on 4xx responses or after retries are exhausted.
    /// </exception>
    [Workflow]
    public async Task<string> Execute(string in_strChannel, DigestEntry in_objPayload)
    {
        if (string.IsNullOrWhiteSpace(in_strChannel))
            throw new ArgumentException("Channel is required.", nameof(in_strChannel));
        if (in_objPayload is null)
            throw new ArgumentNullException(nameof(in_objPayload));

        SafeLog(
            "Starting Notify.SendDigest",
            LogLevel.Info,
            new Dictionary<string, object>
            {
                ["channel"] = in_strChannel,
                ["ecosystem"] = in_objPayload.Ecosystem,
                ["severity"] = in_objPayload.Severity,
            });

        string token = ResolveToken();
        SlackPayload payload = BuildSlackPayload(in_strChannel, in_objPayload);
        string json = JsonSerializer.Serialize(payload);

        using var request = new HttpRequestMessage(HttpMethod.Post, SlackApiBase)
        {
            Content = new StringContent(json, Encoding.UTF8, "application/json"),
        };
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token);

        HttpResponseMessage response = await PostWithRetryAsync(request);

        string responseBody = await response.Content.ReadAsStringAsync();
        string out_strMessageId = ParseSlackResponse(responseBody);

        SafeLog(
            "Completed Notify.SendDigest",
            LogLevel.Info,
            new Dictionary<string, object> { ["messageId"] = out_strMessageId });

        return out_strMessageId;
    }

    // ── pure helpers (R.K.01) ──────────────────────────────────────────

    /// <summary>
    /// Builds the outbound Slack payload from the channel and digest entry.
    /// Extracted as a pure helper per R.K.01 so Tester can unit-test the
    /// payload shape without hitting the Slack API.
    /// </summary>
    public static SlackPayload BuildSlackPayload(string channel, DigestEntry entry)
    {
        string text = $":warning: *{entry.Severity}* finding in *{entry.Ecosystem}*\n>{entry.Finding}";
        return new SlackPayload
        {
            Channel = channel,
            Text = text,
        };
    }

    /// <summary>
    /// Parses the Slack <c>chat.postMessage</c> JSON response and returns
    /// the message <c>ts</c> (timestamp/id). Throws on <c>"ok": false</c>
    /// or missing <c>ts</c>.
    /// </summary>
    public static string ParseSlackResponse(string responseBody)
    {
        using JsonDocument doc = JsonDocument.Parse(responseBody);
        JsonElement root = doc.RootElement;

        if (root.TryGetProperty("ok", out JsonElement okEl) && okEl.ValueKind == JsonValueKind.False)
        {
            string error = root.TryGetProperty("error", out JsonElement err)
                ? err.GetString() ?? "unknown"
                : "unknown";
            throw new HttpRequestException($"Slack API returned ok=false: {error}");
        }

        if (root.TryGetProperty("ts", out JsonElement tsEl))
        {
            return tsEl.GetString() ?? throw new HttpRequestException("Slack response ts is null.");
        }

        throw new HttpRequestException("Slack response missing 'ts' field.");
    }

    // ── retry + token ──────────────────────────────────────────────────

    /// <summary>
    /// POSTs the request with a retry loop. Retries on 5xx and transient
    /// network errors. Does NOT retry on 4xx (R.E.03).
    /// </summary>
    private async Task<HttpResponseMessage> PostWithRetryAsync(HttpRequestMessage request)
    {
        for (int attempt = 0; attempt <= MaxRetries; attempt++)
        {
            try
            {
                // Clone the request content because SendAsync disposes it.
                using var cloned = await CloneRequestAsync(request);
                HttpResponseMessage response = await _httpClient.SendAsync(cloned);
                int status = (int)response.StatusCode;

                if (status < 500)
                {
                    return response; // 2xx or 4xx → don't retry
                }

                SafeLog(
                    $"Slack POST returned {status}, retry {attempt + 1}/{MaxRetries}",
                    LogLevel.Warn,
                    new Dictionary<string, object> { ["status"] = status, ["attempt"] = attempt + 1 });
            }
            catch (HttpRequestException ex) when (attempt < MaxRetries)
            {
                SafeLog(
                    $"Slack POST transient error: {ex.Message}, retry {attempt + 1}/{MaxRetries}",
                    LogLevel.Warn,
                    new Dictionary<string, object> { ["error"] = ex.GetType().Name, ["attempt"] = attempt + 1 });
            }

            if (attempt < MaxRetries)
            {
                await Task.Delay(RetryInterval);
            }
        }

        throw new HttpRequestException(
            $"Slack chat.postMessage failed after {MaxRetries + 1} attempts.");
    }

    private static async Task<HttpRequestMessage> CloneRequestAsync(HttpRequestMessage request)
    {
        var clone = new HttpRequestMessage(request.Method, request.RequestUri);
        if (request.Content != null)
        {
            byte[] contentBytes = await request.Content.ReadAsByteArrayAsync();
            clone.Content = new ByteArrayContent(contentBytes);
            if (request.Content.Headers.ContentType != null)
            {
                clone.Content.Headers.ContentType = request.Content.Headers.ContentType;
            }
        }
        foreach (var header in request.Headers)
        {
            clone.Headers.TryAddWithoutValidation(header.Key, header.Value);
        }
        return clone;
    }

    /// <summary>
    /// Reads the Slack bot token from <c>SLACK_BOT_TOKEN</c> per R.X.01.
    /// </summary>
    private static string ResolveToken()
    {
        string? token = Environment.GetEnvironmentVariable("SLACK_BOT_TOKEN");
        if (string.IsNullOrWhiteSpace(token))
        {
            throw new InvalidOperationException(
                "SLACK_BOT_TOKEN environment variable is not set.");
        }
        return token;
    }

    // ── SafeLog ────────────────────────────────────────────────────────

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
