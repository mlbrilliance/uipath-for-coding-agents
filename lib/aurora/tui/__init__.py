"""AURORA Textual TUI for `aurora status`.

Widgets:
    - EventTail   — tails events.jsonl with kind-coloured lines
    - AgentGrid   — 19-cell grid (4 cols x 5 rows minus 1) of agent states
    - GatesPane   — pending HITL gates with deadline countdowns
    - BudgetMeter — daily Claude-tier token spend vs policy.yaml ceilings

The widgets read their data via `aurora.tui.state.load_state`. State is read-only
operational data (events.jsonl, gate metadata) — *not* the AURORA memory tier
guarded by R.SW.04, which remains exclusive to `aurora-recall` / `aurora-fingerprint`.
"""
