// AURORA — Supply-Chain Defender
// POCOs for the ResolveLockfiles Coded Workflow output.
//
// The JSON shape (PascalCase property names serialise to lowercase via
// JsonPropertyName attributes) matches the Pydantic Lockfile / LockfileEntry
// shape consumed by the MaintainerHealth and VulnLookup Coded Agents
// (examples/oss-supply-chain-defender/agents/maintainer-health/models.py).
//
// Downstream contract:
//   {
//     "repo": "...", "ecosystem": "...", "path": "...",
//     "deps": [ { "ecosystem": "...", "name": "...", "version": "...", "depth": 1 } ]
//   }
//
// PDD: US-33, US-34. Conventions: R.K.01 (POCOs are pure data), R.N.01.
using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace AuroraSupplyChainDefender.GitHub
{
    /// <summary>A single dependency line lifted from a lockfile.</summary>
    public sealed class LockfileEntry
    {
        [JsonPropertyName("ecosystem")]
        public string Ecosystem { get; set; } = string.Empty;

        [JsonPropertyName("name")]
        public string Name { get; set; } = string.Empty;

        [JsonPropertyName("version")]
        public string Version { get; set; } = string.Empty;

        /// <summary>1 = direct, 2+ = transitive. Lockfile parsers default to 1
        /// when depth cannot be inferred from the file format.</summary>
        [JsonPropertyName("depth")]
        public int Depth { get; set; } = 1;
    }

    /// <summary>One lockfile harvested from one repo.</summary>
    public sealed class Lockfile
    {
        [JsonPropertyName("repo")]
        public string Repo { get; set; } = string.Empty;

        [JsonPropertyName("path")]
        public string Path { get; set; } = string.Empty;

        [JsonPropertyName("ecosystem")]
        public string Ecosystem { get; set; } = string.Empty;

        /// <summary>Field is named `deps` (not `entries`) on the wire to match
        /// the Pydantic contract in maintainer-health/models.py.</summary>
        [JsonPropertyName("deps")]
        public List<LockfileEntry> Entries { get; set; } = new();
    }
}
