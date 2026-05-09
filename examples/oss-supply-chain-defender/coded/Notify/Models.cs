using System;
using System.Text.Json.Serialization;

namespace AuroraSupplyChainDefender.Notify;

/// <summary>
/// One finding entry for the weekly digest — produced by the upstream
/// fan-out checks (Typosquat, Vulner, MaintainerHealth) and consumed by both
/// <see cref="AppendToDigest"/> and <see cref="SendDigest"/>.
/// </summary>
public sealed class DigestEntry
{
    /// <summary>Human-readable description of the finding.</summary>
    [JsonPropertyName("finding")]
    public string Finding { get; set; } = string.Empty;

    /// <summary>Severity level: Info, Warning, Critical.</summary>
    [JsonPropertyName("severity")]
    public string Severity { get; set; } = string.Empty;

    /// <summary>Package ecosystem: npm, pypi, etc.</summary>
    [JsonPropertyName("ecosystem")]
    public string Ecosystem { get; set; } = string.Empty;

    /// <summary>UTC timestamp when the finding was recorded.</summary>
    [JsonPropertyName("timestamp")]
    public DateTime Timestamp { get; set; } = DateTime.UtcNow;
}

/// <summary>
/// Outbound Slack chat.postMessage payload.
/// </summary>
/// <remarks>
/// Serialised to JSON and POSTed to <c>https://slack.com/api/chat.postMessage</c>
/// with a Bearer token from the <c>SLACK_BOT_TOKEN</c> environment variable.
/// </remarks>
public sealed class SlackPayload
{
    /// <summary>Slack channel ID or name (e.g. <c>#supply-chain-alerts</c>).</summary>
    [JsonPropertyName("channel")]
    public string Channel { get; set; } = string.Empty;

    /// <summary>Message text. Supports Slack mrkdwn.</summary>
    [JsonPropertyName("text")]
    public string Text { get; set; } = string.Empty;
}
