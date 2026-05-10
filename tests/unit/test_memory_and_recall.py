"""Unit tests for aurora.memory and aurora.recall."""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from aurora import memory as memory_mod
from aurora.recall import recall as _recall


class _RecallMod:
    recall = staticmethod(_recall)
recall_mod = _RecallMod()


def test_append_and_iter_learnings(tmp_aurora_home: Path) -> None:
    store = memory_mod.MemoryStore()
    store.append_learning(
        agent="surgeon",
        project_id="CAND-test-1",
        kind="fingerprint-resolution",
        summary="rotated GITHUB_TOKEN to fallback after 401",
    )
    store.append_learning(
        agent="surgeon",
        project_id="CAND-test-2",
        kind="fingerprint-resolution",
        summary="re-walked aaname after SharePoint folder rename",
    )

    learnings = list(store.iter_learnings())
    assert len(learnings) == 2
    assert all(learning.agent == "surgeon" for learning in learnings)


def test_iter_learnings_filters_by_since(tmp_aurora_home: Path) -> None:
    store = memory_mod.MemoryStore()
    store.append_learning(
        agent="scout", project_id="CAND-old",
        kind="signal", summary="older",
        ts="2020-01-01T00:00:00+00:00",
    )
    store.append_learning(
        agent="scout", project_id="CAND-new",
        kind="signal", summary="recent",
    )

    recent = list(store.iter_learnings(since=timedelta(days=30)))
    assert len(recent) == 1
    assert recent[0].project_id == "CAND-new"


def test_search_org_finds_keywords(tmp_aurora_home: Path) -> None:
    store = memory_mod.MemoryStore()
    (store.home / "org" / "vendor-quirks.md").write_text(
        "## SharePoint\n\nFolder renames change `aaname` but parent role stays stable.\n"
        "Always include parent walk in the selector fallback.\n",
        encoding="utf-8",
    )
    results = store.search_org("SharePoint folder rename")
    assert len(results) == 1
    assert "SharePoint" in results[0].snippet


def test_search_org_returns_empty_when_no_match(tmp_aurora_home: Path) -> None:
    store = memory_mod.MemoryStore()
    (store.home / "org" / "noise.md").write_text("# heading\nUnrelated content.\n", encoding="utf-8")
    results = store.search_org("magenta unicorn")
    assert results == []


def test_recall_picks_default_tiers_for_known_agent(tmp_aurora_home: Path) -> None:
    # Prime org memory
    store = memory_mod.MemoryStore()
    (store.home / "org" / "patterns-that-worked.md").write_text(
        "Maestro is the right pattern when actor_count >= 2.\n", encoding="utf-8"
    )
    results = recall_mod.recall(query="Maestro pattern actor_count", agent="architect", limit=5)
    assert any(r["tier"] == "org" for r in results)


def test_recall_unknown_agent_uses_default_tiers(tmp_aurora_home: Path) -> None:
    store = memory_mod.MemoryStore()
    (store.home / "org" / "test.md").write_text("token rotation works for github\n", encoding="utf-8")
    results = recall_mod.recall(query="token rotation github", agent="not-a-real-agent", limit=5)
    assert isinstance(results, list)


def test_recall_skill_tier_includes_learnings(tmp_aurora_home: Path) -> None:
    store = memory_mod.MemoryStore()
    store.append_learning(
        agent="diagnostician",
        project_id="CAND-1",
        kind="fingerprint",
        summary="auth-failed clusters distinct between GitHub and UiPath identity",
    )
    results = recall_mod.recall(query="auth failed cluster", tier="skill", limit=5)
    # At least the appended learning should match
    assert any("auth-failed" in r.get("snippet", "") for r in results)
