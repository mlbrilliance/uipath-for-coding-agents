"""GitHub default-branch commit-recency lookup.

Asks the GitHub REST API for the latest commit on a repo's default branch
and returns days since that commit.

Auth via `GITHUB_TOKEN`. The full Orchestrator-Asset integration (R.X.02)
lands in a later task — this PR keeps the env-var path so the agent can be
exercised end-to-end before the credential resource is wired.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

import httpx
import structlog
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential

logger = structlog.get_logger(__name__)

GITHUB_API = "https://api.github.com"


class CommitRecencyResult(BaseModel):
    """Result of a default-branch commit-recency probe."""
    repo_url: str
    days_since: Optional[int] = None
    found: bool = False


def _parse_repo(repo_url: str) -> Optional[tuple[str, str]]:
    """Extract (org, repo) from a GitHub URL. None for non-GitHub hosts."""
    if not repo_url:
        return None
    parsed = urlparse(repo_url if "://" in repo_url else f"https://{repo_url}")
    if (parsed.hostname or "").lower() != "github.com":
        return None
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        return None
    org, repo = parts[0], parts[1]
    if repo.endswith(".git"):
        repo = repo[:-4]
    return (org, repo)


def _days_since(iso_ts: str) -> Optional[int]:
    """Convert an ISO-8601 commit timestamp into days since now (UTC)."""
    try:
        # Normalize trailing Z → +00:00 for fromisoformat.
        if iso_ts.endswith("Z"):
            iso_ts = iso_ts[:-1] + "+00:00"
        committed = datetime.fromisoformat(iso_ts)
    except ValueError:
        return None
    if committed.tzinfo is None:
        committed = committed.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - committed
    return max(0, delta.days)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
async def get_commit_recency(repo_url: str) -> CommitRecencyResult:
    """Return days since the most recent commit on the default branch.

    Returns `found=False` and `days_since=None` when the repo can't be
    located or the API returns no commits. Never raises on API errors.
    """
    parsed = _parse_repo(repo_url)
    if parsed is None:
        logger.info("commit_recency.skip_unparseable_url", repo_url=repo_url)
        return CommitRecencyResult(repo_url=repo_url, found=False)

    org, repo = parsed
    headers = {"Accept": "application/vnd.github+json"}
    if token := os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"

    url = f"{GITHUB_API}/repos/{org}/{repo}/commits"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(url, headers=headers, params={"per_page": 1})
    except httpx.HTTPError as exc:
        logger.warning("commit_recency.http_error", repo_url=repo_url, error=str(exc))
        return CommitRecencyResult(repo_url=repo_url, found=False)

    if response.status_code == 404:
        logger.info("commit_recency.repo_not_found", repo_url=repo_url)
        return CommitRecencyResult(repo_url=repo_url, found=False)
    if response.status_code != 200:
        logger.warning(
            "commit_recency.unexpected_status",
            repo_url=repo_url,
            status=response.status_code,
        )
        return CommitRecencyResult(repo_url=repo_url, found=False)

    try:
        commits = response.json()
    except ValueError:
        return CommitRecencyResult(repo_url=repo_url, found=False)

    if not isinstance(commits, list) or not commits:
        return CommitRecencyResult(repo_url=repo_url, found=False)

    commit_info = commits[0].get("commit", {}).get("committer", {}) or {}
    iso_ts = commit_info.get("date")
    if not iso_ts:
        return CommitRecencyResult(repo_url=repo_url, found=True, days_since=None)

    days = _days_since(iso_ts)
    return CommitRecencyResult(repo_url=repo_url, found=True, days_since=days)
