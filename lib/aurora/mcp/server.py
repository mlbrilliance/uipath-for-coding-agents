"""AURORA MCP server.

Tools exposed to any MCP-aware client:
    aurora_recall          — scoped memory retrieval
    aurora_fingerprint     — classify a fault event
    aurora_list_clusters   — list known fingerprint clusters
    aurora_append_resolution — record Surgeon's fix against a cluster
    aurora_replay_instance — kick off a sandbox-folder twin replay
    aurora_compost_dry_run — preview what compost would propose
    aurora_policy_dry_run  — preview Conductor's next N hours

Launched via the plugin manifest:
    "command": "uv",
    "args": ["run", "--directory", "${PLUGIN_DIR}", "python", "-m", "aurora.mcp.server"]

This module imports `mcp` lazily so the package itself stays import-safe
even when the MCP runtime isn't installed.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import timedelta
from typing import Any

from aurora.fingerprint import classify_event, append_resolution, list_clusters
from aurora.policy import dry_run as policy_dry_run, load_policy
from aurora.recall import recall as recall_fn
from aurora import replay as replay_mod

logger = logging.getLogger(__name__)


def _build_server() -> Any:
    """Construct the MCP server with all tools registered.

    Imports the MCP SDK lazily.
    """
    try:
        from mcp.server import Server
        from mcp.types import Tool, TextContent
    except ImportError as e:
        raise RuntimeError(
            "mcp package not installed; AURORA MCP server cannot run. "
            "Install with `uv sync` or `pip install mcp>=0.9`."
        ) from e

    server = Server("aurora")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="aurora_recall",
                description=(
                    "Scoped memory retrieval. Returns ranked excerpts from project / org / skill "
                    "tiers based on the requesting agent's role. Use before reasoning over historical "
                    "context — never `cat` memory directly."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "agent": {"type": "string"},
                        "candidate": {"type": "string"},
                        "tier": {"type": "string", "enum": ["project", "org", "skill", "any"]},
                        "fleet": {"type": "string", "enum": ["discovery", "build", "operate"]},
                        "limit": {"type": "integer", "default": 10},
                        "since_days": {"type": "integer"},
                    },
                },
            ),
            Tool(
                name="aurora_fingerprint",
                description=(
                    "Classify a fault event by structural fingerprint and update the cluster index. "
                    "Used by Diagnostician right after Sentry emits a fault."
                ),
                inputSchema={
                    "type": "object",
                    "required": ["event"],
                    "properties": {
                        "event": {"type": "object"},
                    },
                },
            ),
            Tool(
                name="aurora_list_clusters",
                description="List known fingerprint clusters (debug / human-facing).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "kind": {"type": "string"},
                        "limit": {"type": "integer", "default": 20},
                    },
                },
            ),
            Tool(
                name="aurora_append_resolution",
                description=(
                    "Attach a Surgeon resolution (PR url + summary) to a fingerprint cluster. "
                    "Used after a successful self-heal."
                ),
                inputSchema={
                    "type": "object",
                    "required": ["cluster_id", "pr", "summary"],
                    "properties": {
                        "cluster_id": {"type": "string"},
                        "pr": {"type": "string"},
                        "summary": {"type": "string"},
                    },
                },
            ),
            Tool(
                name="aurora_replay_instance",
                description=(
                    "Kick off a sandbox-folder twin replay of a faulted Maestro instance or job. "
                    "Used by Diagnostician for ambiguous faults (cluster confidence < 0.6)."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "instance_id": {"type": "string"},
                        "job_id": {"type": "integer"},
                    },
                },
            ),
            Tool(
                name="aurora_compost_dry_run",
                description=(
                    "Preview the PRs the compost step would propose, without opening them. "
                    "Useful before flipping an aurora-compost cron on for real."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "since_days": {"type": "integer", "default": 1},
                    },
                },
            ),
            Tool(
                name="aurora_policy_dry_run",
                description=(
                    "Forecast Conductor's next N hours given the current backlog and Operate-fleet "
                    "state. Returns dispatches, gates that would fire, and budget projection."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "since_hours": {"type": "integer", "default": 24},
                    },
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict | None) -> list[TextContent]:
        arguments = arguments or {}
        result = await _dispatch(name, arguments)
        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

    return server


async def _dispatch(name: str, args: dict) -> Any:
    """Route the MCP tool call to the in-process implementation."""
    if name == "aurora_recall":
        since = timedelta(days=args["since_days"]) if "since_days" in args else None
        return recall_fn(
            query=args.get("query"),
            agent=args.get("agent"),
            candidate=args.get("candidate"),
            tier=args.get("tier"),
            fleet=args.get("fleet"),
            limit=args.get("limit", 10),
            since=since,
        )

    if name == "aurora_fingerprint":
        cluster = classify_event(args["event"])
        return cluster.__dict__

    if name == "aurora_list_clusters":
        return list_clusters(kind=args.get("kind"), limit=args.get("limit", 20))

    if name == "aurora_append_resolution":
        append_resolution(
            cluster_id=args["cluster_id"],
            pr=args["pr"],
            summary=args["summary"],
        )
        return {"ok": True, "cluster_id": args["cluster_id"]}

    if name == "aurora_replay_instance":
        instance_id = args.get("instance_id")
        if not instance_id:
            raise ValueError("aurora_replay_instance requires `instance_id`")
        result = replay_mod.replay_instance(
            instance_id=instance_id,
            sandbox_folder=args.get("sandbox_folder"),
        )
        return result.model_dump()

    if name == "aurora_compost_dry_run":
        from datetime import datetime, timezone
        from pathlib import Path as _Path
        import os as _os

        from aurora.compost import propose_skill_pr

        home = _Path(_os.environ.get("AURORA_HOME", "/opt/aurora"))
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        learnings_path = home / "learnings" / f"{date}.jsonl"
        results = propose_skill_pr(learnings_path, dry_run=True)
        return {
            "since_days": args.get("since_days", 1),
            "candidates": [r.model_dump() for r in results],
        }

    if name == "aurora_policy_dry_run":
        policy, _ = load_policy()
        return policy_dry_run(policy, since_hours=args.get("since_hours", 24))

    raise ValueError(f"unknown tool: {name!r}")


async def _serve() -> None:
    """Run the MCP server on stdio."""
    try:
        from mcp.server.stdio import stdio_server  # type: ignore[import-not-found]
    except ImportError as e:
        raise RuntimeError(
            "mcp.server.stdio not available; install mcp>=0.9 with stdio support"
        ) from e

    server = _build_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> int:
    logging.basicConfig(level="INFO", stream=sys.stderr)
    asyncio.run(_serve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
