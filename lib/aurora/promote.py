"""Action Center HITL gates — runtime implementation of `aurora-promote` skill.

Used by Concierge (and any agent that needs human sign-off). Loads the
matching form template from skills/aurora-promote/templates/<kind>.json,
fills in `{{ ... }}` placeholders from the request `context`, creates
the Form Task via the UiPath SDK, polls for completion, applies the
configured timeout behavior.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from aurora.uipath_client import UiPathClient

logger = logging.getLogger(__name__)

PLACEHOLDER = re.compile(r"\{\{\s*(\w+)\s*\}\}")
POLL_INTERVAL_SECONDS = 30
TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent / "skills" / "aurora-promote" / "templates"


@dataclass
class GateResponse:
    task_id: int
    approved: bool
    decision: str
    approver: str | None
    responded_at: str
    form_data: dict[str, Any]
    elapsed_seconds: int
    escalated_to: str | None = None
    timed_out: bool = False


class GateError(RuntimeError):
    """Raised on unrecoverable gate failure (timeout=='deny' counts as success)."""


def open_gate(
    *,
    kind: str,
    candidate: str | None = None,
    context: dict[str, Any] | None = None,
    approvers_env: str = "AURORA_EMERGENCY_APPROVERS",
    timeout_hours: int | None = None,
    on_timeout: str | None = None,
    catalog: str | None = None,
    poll_interval: int = POLL_INTERVAL_SECONDS,
    template_dir: Path | None = None,
) -> GateResponse:
    """Create an Action Center Form Task and wait for completion."""
    context = context or {}
    template = _load_template(kind, template_dir or TEMPLATE_DIR)
    aurora_meta = template.get("aurora", {})
    form_def = template.get("form", {})

    timeout_hours = timeout_hours or aurora_meta.get("default_timeout_hours", 8)
    on_timeout = on_timeout or aurora_meta.get("default_on_timeout", "deny")
    priority = aurora_meta.get("priority", "Medium")
    catalog = catalog or os.environ.get("UIPATH_ACTION_CATALOG", "aurora_supply_chain_approvals")

    rendered = _render_placeholders(form_def, context | {"candidate": candidate or ""})
    title = rendered.get("title", f"AURORA: {kind}")

    client = UiPathClient()
    approver_emails = [e.strip() for e in os.environ.get(approvers_env, "").split(",") if e.strip()]
    approver_user_ids = [uid for uid in (client.find_user_id(e) for e in approver_emails) if uid]

    if not approver_user_ids:
        raise GateError(
            f"no approvers resolved from {approvers_env}={approver_emails!r}; "
            f"check that the emails exist as Automation Cloud users"
        )

    task = client.create_form_task(
        catalog=catalog,
        title=title,
        priority=priority,
        form_definition=rendered,
        data={"context": context, "candidate": candidate, "kind": kind},
        approver_user_ids=approver_user_ids,
    )
    task_id_raw = task.get("Id") or task.get("id")
    if task_id_raw is None:
        raise GateError(f"FormTask response missing Id/id: {task!r}")
    task_id = int(task_id_raw)
    started_at = time.time()
    timeout_at = started_at + (timeout_hours * 3600)
    logger.info("opened gate kind=%s task=%s timeout=%dh", kind, task_id, timeout_hours)

    while True:
        time.sleep(poll_interval)
        current = client.get_task(task_id)
        status = current.get("Status")
        if status == "Completed":
            data = current.get("Data") or {}
            decision = (data.get("decision") or data.get("approve") or "").lower()
            approved = decision in ("approve", "yes", "true")
            return GateResponse(
                task_id=task_id,
                approved=approved,
                decision=decision,
                approver=current.get("LastModifiedBy", {}).get("EmailAddress")
                         if isinstance(current.get("LastModifiedBy"), dict)
                         else None,
                responded_at=datetime.now(UTC).isoformat(),
                form_data=data,
                elapsed_seconds=int(time.time() - started_at),
            )

        if time.time() > timeout_at:
            return _handle_timeout(
                kind=kind,
                task_id=task_id,
                on_timeout=on_timeout,
                started_at=started_at,
            )


def _handle_timeout(
    *, kind: str, task_id: int, on_timeout: str, started_at: float
) -> GateResponse:
    elapsed = int(time.time() - started_at)
    if on_timeout == "auto-approve":
        logger.warning("gate %s timed out — policy says auto-approve", kind)
        return GateResponse(
            task_id=task_id, approved=True, decision="auto-approve",
            approver=None, responded_at=datetime.now(UTC).isoformat(),
            form_data={}, elapsed_seconds=elapsed, timed_out=True,
        )
    if on_timeout == "deny":
        logger.warning("gate %s timed out — policy says deny", kind)
        return GateResponse(
            task_id=task_id, approved=False, decision="timeout-deny",
            approver=None, responded_at=datetime.now(UTC).isoformat(),
            form_data={}, elapsed_seconds=elapsed, timed_out=True,
        )
    # escalate (default)
    logger.warning("gate %s timed out — escalating to backup approvers", kind)
    return GateResponse(
        task_id=task_id, approved=False, decision="escalated",
        approver=None, responded_at=datetime.now(UTC).isoformat(),
        form_data={}, elapsed_seconds=elapsed, timed_out=True,
        escalated_to="<backup-approver-pool>",
    )


def _load_template(kind: str, template_dir: Path) -> dict[str, Any]:
    candidates = [
        template_dir / f"{kind}.json",
        template_dir / f"{kind.replace('_', '-')}.json",
    ]
    for path in candidates:
        if path.exists():
            return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
    raise GateError(f"no template for kind={kind!r}; looked in {[str(p) for p in candidates]}")


def _render_placeholders(obj: Any, context: dict[str, Any]) -> Any:
    if isinstance(obj, str):
        def repl(m: re.Match[str]) -> str:
            key = m.group(1)
            val = context.get(key, "")
            return str(val) if val is not None else ""
        return PLACEHOLDER.sub(repl, obj)
    if isinstance(obj, list):
        return [_render_placeholders(x, context) for x in obj]
    if isinstance(obj, dict):
        return {k: _render_placeholders(v, context) for k, v in obj.items()}
    return obj
