"""Concierge contract tests — offline.

R.SW.05: HITL gates from policy.yaml are absolute. Concierge is the swarm's
only path to humans, so the ``FormTask`` contract must reject malformed
payloads *before* dialling Action Center.

The uipath-python SDK client is replaced with a ``MagicMock`` (R.T.03 — mock
dependencies, never the SUT). We assert the dispatcher still hits the
expected SDK surface so the wiring is exercised.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tests.agents.conftest import load_fixture_json  # noqa: E402
from tests.agents.contracts.concierge import (  # noqa: E402
    FOLDER_HEADER,
    UIPATH_CATALOG_MISSING_CODE,
    FormTask,
    FormTaskValidationError,
    TaskStatus,
    submit_form_task,
)


@pytest.fixture
def form_task_payload() -> dict[str, Any]:
    return load_fixture_json("concierge", "form_task_payload.json")


@pytest.fixture
def mocked_sdk_with_folder() -> MagicMock:
    """SDK stub with the required X-UIPATH-OrganizationUnitId header set."""
    sdk = MagicMock(name="uipath_sdk")
    sdk.api_client.headers = {FOLDER_HEADER: "73"}
    sdk.tasks.create.return_value = {"Id": 9001, "Status": "Pending"}
    return sdk


def test_valid_payload_produces_form_task(
    form_task_payload: dict[str, Any],
    mocked_sdk_with_folder: MagicMock,
    action_catalog: str,
) -> None:
    task = submit_form_task(form_task_payload, mocked_sdk_with_folder)
    assert isinstance(task, FormTask)
    assert task.catalog == action_catalog
    assert task.catalog == form_task_payload["catalog"]
    assert task.folder_id == 73
    assert task.status == TaskStatus.PENDING
    assert {f.key for f in task.fields} == {"approve", "diff_url", "notes"}
    mocked_sdk_with_folder.tasks.create.assert_called_once()
    call_kwargs = mocked_sdk_with_folder.tasks.create.call_args.kwargs
    assert call_kwargs["catalog"] == action_catalog


def test_missing_catalog_raises_with_uipath_code(
    form_task_payload: dict[str, Any],
    mocked_sdk_with_folder: MagicMock,
) -> None:
    """UiPath error 2451: action catalog must pre-exist."""
    payload = dict(form_task_payload)
    payload["catalog"] = ""
    with pytest.raises(FormTaskValidationError) as info:
        submit_form_task(payload, mocked_sdk_with_folder)
    assert info.value.uipath_error_code == UIPATH_CATALOG_MISSING_CODE
    mocked_sdk_with_folder.tasks.create.assert_not_called()


def test_missing_folder_header_blocks_submission(
    form_task_payload: dict[str, Any],
) -> None:
    sdk = MagicMock(name="uipath_sdk")
    sdk.api_client.headers = {}
    with pytest.raises(FormTaskValidationError, match=FOLDER_HEADER):
        submit_form_task(form_task_payload, sdk)
    sdk.tasks.create.assert_not_called()


def test_unsupported_field_type_is_rejected(
    form_task_payload: dict[str, Any],
    mocked_sdk_with_folder: MagicMock,
) -> None:
    payload = dict(form_task_payload)
    payload["fields"] = [{"key": "bogus", "type": "datepicker"}]
    with pytest.raises(FormTaskValidationError, match="unsupported field type"):
        submit_form_task(payload, mocked_sdk_with_folder)
    mocked_sdk_with_folder.tasks.create.assert_not_called()


def test_empty_fields_list_is_rejected(
    form_task_payload: dict[str, Any],
    mocked_sdk_with_folder: MagicMock,
) -> None:
    payload = dict(form_task_payload)
    payload["fields"] = []
    with pytest.raises(FormTaskValidationError):
        submit_form_task(payload, mocked_sdk_with_folder)


def test_sdk_is_mocked_at_boundary(
    form_task_payload: dict[str, Any],
    mocked_sdk_with_folder: MagicMock,
) -> None:
    """R.T.03 — never let the SUT reach Orchestrator."""
    submit_form_task(form_task_payload, mocked_sdk_with_folder)
    assert mocked_sdk_with_folder.tasks.create.called
    assert isinstance(mocked_sdk_with_folder, MagicMock)
