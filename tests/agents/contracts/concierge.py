"""Concierge Form-Task contract + offline validator.

Concierge is the swarm's only path to humans (R.SW.05 — HITL gates are
absolute). The contract is a ``FormTask`` carrying the catalog name, folder
context, and form fields. The validator below talks to a *mocked* uipath SDK
client so the test never reaches Orchestrator.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

FOLDER_HEADER = "X-UIPATH-OrganizationUnitId"
UIPATH_CATALOG_MISSING_CODE = 2451


class FormTaskValidationError(ValueError):
    """Raised when a Form Task payload would be rejected by Action Center."""

    def __init__(self, message: str, *, uipath_error_code: int | None = None) -> None:
        super().__init__(message)
        self.uipath_error_code = uipath_error_code


class TaskStatus(StrEnum):
    UNASSIGNED = "Unassigned"
    PENDING = "Pending"
    COMPLETED = "Completed"


_ALLOWED_FIELD_TYPES = {"text", "textfield", "textarea", "select", "url", "checkbox"}


class FormField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1)
    type: str
    label: str | None = None
    options: list[str] | None = None


class FormTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    catalog: str = Field(min_length=1)
    folder_id: int = Field(gt=0)
    title: str = Field(min_length=1)
    fields: list[FormField] = Field(min_length=1)
    status: TaskStatus = TaskStatus.PENDING


def submit_form_task(payload: dict[str, Any], sdk_client: Any) -> FormTask:
    """Validate and submit a Form Task through a (mocked) uipath SDK client.

    Per UiPath docs, the action catalog must already exist (error 2451 is
    raised otherwise); we surface that as a typed ``FormTaskValidationError``
    *before* calling the SDK so the boundary is preserved (R.T.03).
    """
    catalog = (payload.get("catalog") or "").strip()
    if not catalog:
        raise FormTaskValidationError(
            "catalog must be non-empty (UiPath error 2451: catalog must pre-exist)",
            uipath_error_code=UIPATH_CATALOG_MISSING_CODE,
        )

    headers = getattr(sdk_client.api_client, "headers", {}) or {}
    folder_header = headers.get(FOLDER_HEADER)
    if not folder_header:
        raise FormTaskValidationError(
            f"missing folder context header {FOLDER_HEADER!r}"
        )

    raw_fields = payload.get("fields") or []
    if not raw_fields:
        raise FormTaskValidationError("form must declare at least one field")
    fields: list[FormField] = []
    for raw in raw_fields:
        if raw.get("type") not in _ALLOWED_FIELD_TYPES:
            raise FormTaskValidationError(
                f"unsupported field type: {raw.get('type')!r}"
            )
        fields.append(FormField(**raw))

    task = FormTask(
        catalog=catalog,
        folder_id=int(folder_header),
        title=payload["title"],
        fields=fields,
        status=TaskStatus.PENDING,
    )

    sdk_client.tasks.create(
        folder=payload.get("folder_name"),
        catalog=task.catalog,
        title=task.title,
        priority=payload.get("priority", "Medium"),
        form=task.model_dump(mode="json"),
        data=payload.get("data", {}),
    )
    return task
