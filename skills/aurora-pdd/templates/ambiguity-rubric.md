# Ambiguity rubric — used by `aurora-pdd`

Score in [0.0, 1.0]. Sum weighted signals; cap at 1.0.

| ID | Signal | Weight | Detection |
|---|---|---|---|
| AMB.01 | Trigger is `unknown` OR has multiple types | 0.25 | regex on `## Trigger` block |
| AMB.02 | Any input source is `unknown` | 0.15 per occurrence | grep `## Inputs` table |
| AMB.03 | Any output destination is `unknown` | 0.15 per occurrence | grep `## Outputs` table |
| AMB.04 | Acceptance criteria count < 3 | 0.20 | structural |
| AMB.05 | Vague language in acceptance criteria | 0.10 per occurrence | regex against forbidden tokens |
| AMB.06 | Actor row has `unknown` or empty | 0.20 per row | structural |
| AMB.07 | `## Out of scope` is empty | 0.10 | structural |

## Forbidden tokens (AMB.05)

These phrases are treated as evidence of vagueness:

- "as expected"
- "works correctly"
- "etc."
- "and so on"
- "appropriately"
- "if needed"
- "when necessary"
- "or similar"

## Threshold

- ≤ 0.4 → backlog status `ready-for-architect`
- > 0.4 → backlog status `needs-interviewer`; populate `## Open questions`

## Re-scoring after Interviewer

When Interviewer's responses come back, Analyst re-runs this rubric. If the score doesn't drop below 0.4 after one round of questions, escalate to Conductor with status `needs-second-interview` — the PDD is structurally wrong, not just ambiguous.
