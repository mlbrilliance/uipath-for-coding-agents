---
name: aurora-promote
description: HITL gate via UiPath Action Center. Creates a Form Task in the configured catalog (`aurora_supply_chain_approvals`), assigns approvers from a configured list, polls for completion, applies the policy.yaml gate's timeout behavior, and returns the approver's response to the calling agent. Used for prod publishes, emergency patches, deprecations, large fixes, and skill-compost PR reviews. The implementation of every gate in `policy.yaml::gates`.
---

# aurora-promote

This is the only path AURORA takes when it needs human input. Every HITL gate goes through this skill, in `concierge`'s hands. The audit trail is the catalog itself — `aurora_supply_chain_approvals` — visible in Action Center, queryable via the Orchestrator API, and survives session boundaries.

## When to invoke

- Conductor before any publish into a folder matching `^Production`
- Surgeon when a fix touches > 3 workflows
- Strategist when proposing a deprecation
- Diagnostician when a fault is novel and Conductor needs human triage
- Conductor at the end of the nightly compost step (skill-update PR review)

## Inputs

A JSON request matching `templates/<kind>.json`. The shipped templates are:

- `templates/interview.json` — multi-question Q&A (used by Interviewer via Concierge)
- `templates/prod-publish.json` — package version + diff + approve/reject
- `templates/emergency-patch.json` — triage summary + proposed fix diff + approve/reject/escalate
- `templates/deprecation.json` — process name, last-run, dependents, approve/keep
- `templates/large-fix.json` — affected workflow list + regression results + approve/reject
- `templates/skill-compost-pr.json` — PR link, learnings cluster, approve-merge/reject

Each template defines a Form (UiPath Form Designer JSON) plus AURORA-side metadata (timeout, approvers env var, on-timeout behavior).

## How to invoke

```python
from aurora.promote import open_gate

response = open_gate(
    kind="emergency_patch",
    candidate="CAND-2026-05-09-aabbccdd",
    context={
        "triage_path": ".aurora/triage/2026-05-09T03:42-supply-chain.md",
        "diff_url": "https://github.com/aurora-demo-org/.../pull/42",
        "fingerprint": "selector-broken/wnd-aaname-mismatch",
        "cluster_size": 12,
    },
    approvers_env="AURORA_EMERGENCY_APPROVERS",
    timeout_hours=4,
    on_timeout="escalate",
)

if response.approved:
    # proceed
else:
    # log + escalate or abandon per gate definition
```

The implementation lives in `lib/aurora/promote.py`. It uses the `uipath-python` SDK's `sdk.tasks.create(...)` and `sdk.tasks.get(...)` for create + poll. For Maestro user tasks, it uses the Maestro Tasks API to bind to the in-flight instance.

## Form templates ship as JSON

Each template under `templates/` is a Form Designer JSON, plus AURORA front-matter. Example skeleton (`templates/emergency-patch.json`):

```json
{
  "aurora": {
    "kind": "emergency_patch",
    "default_timeout_hours": 4,
    "default_on_timeout": "escalate",
    "default_approvers_env": "AURORA_EMERGENCY_APPROVERS",
    "priority": "High"
  },
  "form": {
    "components": [
      { "type": "panel", "title": "AURORA emergency patch approval",
        "components": [
          { "type": "htmlelement", "key": "summary", "tag": "p", "content": "{{ triage_summary }}" },
          { "type": "textfield", "key": "fingerprint", "label": "Fingerprint", "disabled": true },
          { "type": "url", "key": "diff_url", "label": "Proposed fix (PR)", "disabled": true },
          { "type": "select", "key": "decision", "label": "Decision",
            "data": { "values": [
              { "label": "Approve and merge", "value": "approve" },
              { "label": "Reject", "value": "reject" },
              { "label": "Escalate", "value": "escalate" }
            ]}, "validate": { "required": true } },
          { "type": "textarea", "key": "notes", "label": "Notes (optional)" },
          { "type": "button", "label": "Submit", "action": "submit" }
        ]
      }
    ]
  }
}
```

The `{{ triage_summary }}` token is replaced server-side from the request `context` map.

## Output (returned to caller)

```json
{
  "task_id": "abc-123",
  "approved": true,
  "decision": "approve",
  "approver": "puneet@example.com",
  "responded_at": "2026-05-09T04:11:30Z",
  "form_data": { "decision": "approve", "notes": "ship it" },
  "elapsed_seconds": 1734,
  "escalated_to": null
}
```

## Anti-patterns

- Don't render the form in chat. The audit trail is Action Center.
- Don't approve on the human's behalf. Even when "obvious."
- Don't bypass the catalog. All tasks go through `${UIPATH_ACTION_CATALOG}`.
- Don't log the full form payload to swarm memory — payloads can carry sensitive context. Log only `{kind, candidate, approver, decision, elapsed_seconds}`.
- Don't poll faster than 30s. Action Center is not a real-time channel; respect it.
