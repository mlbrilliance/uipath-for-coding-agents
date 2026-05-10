"""OpenSSF Scorecard lookup.

Public REST API: https://api.securityscorecards.dev/projects/<platform>/<org>/<repo>
No auth required. Anonymous works at a generous rate.

The Scorecard service returns aggregate `score` (0-10) plus per-check
breakdown. We surface the aggregate; downstream policy may extend to
per-check thresholds later.
"""
from __future__ import annotations

from urllib.parse import urlparse

import httpx
import structlog
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential

logger = structlog.get_logger(__name__)

SCORECARD_BASE = "https://api.securityscorecards.dev/projects"


class ScorecardResult(BaseModel):
    """Subset of the Scorecard API response we care about."""
    repo_url: str
    score: float | None = None
    found: bool = False


def _parse_repo(repo_url: str) -> tuple[str, str, str] | None:
    """Extract (platform, org, repo) from a GitHub-style URL.

    Returns None for URLs we can't shape into Scorecard's API path.
    """
    if not repo_url:
        return None
    parsed = urlparse(repo_url if "://" in repo_url else f"https://{repo_url}")
    host = (parsed.hostname or "").lower()
    parts = [p for p in parsed.path.split("/") if p]
    if host != "github.com" or len(parts) < 2:
        return None
    org, repo = parts[0], parts[1]
    # Strip a trailing .git if present.
    if repo.endswith(".git"):
        repo = repo[:-4]
    return ("github.com", org, repo)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
async def get_scorecard(repo_url: str) -> ScorecardResult:
    """Query OpenSSF Scorecard for the given repo URL.

    Returns a ScorecardResult with `found=False` and `score=None`
    when the API has no data for the repo. Never raises on API
    errors — callers want a sentinel, not an exception.
    """
    parsed = _parse_repo(repo_url)
    if parsed is None:
        logger.info("scorecard.skip_unparseable_url", repo_url=repo_url)
        return ScorecardResult(repo_url=repo_url, found=False)

    platform, org, repo = parsed
    url = f"{SCORECARD_BASE}/{platform}/{org}/{repo}"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(url)
    except httpx.HTTPError as exc:
        logger.warning("scorecard.http_error", repo_url=repo_url, error=str(exc))
        return ScorecardResult(repo_url=repo_url, found=False)

    if response.status_code == 404:
        logger.info("scorecard.no_data", repo_url=repo_url)
        return ScorecardResult(repo_url=repo_url, found=False)
    if response.status_code != 200:
        logger.warning(
            "scorecard.unexpected_status",
            repo_url=repo_url,
            status=response.status_code,
        )
        return ScorecardResult(repo_url=repo_url, found=False)

    try:
        data = response.json()
    except ValueError:
        logger.warning("scorecard.invalid_json", repo_url=repo_url)
        return ScorecardResult(repo_url=repo_url, found=False)

    score = data.get("score")
    if not isinstance(score, (int, float)):
        return ScorecardResult(repo_url=repo_url, found=True, score=None)
    return ScorecardResult(repo_url=repo_url, found=True, score=float(score))
