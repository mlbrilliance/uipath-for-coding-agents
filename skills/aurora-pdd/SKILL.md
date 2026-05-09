---
name: aurora-pdd
description: Author a Process Definition Document with calibrated ambiguity scoring. Used by `analyst` after a candidate is promoted from Curator's backlog. Templates and the ambiguity rubric live in `templates/`. Output is a structured PDD that Architect, Forgers, and Tester all consume verbatim. Includes a Given/When/Then acceptance-criteria pattern that maps 1:1 to test cases. Sets ambiguity_score in [0,1]; values above 0.4 trigger Interviewer.
---

# aurora-pdd

The PDD is the single most important document in any AURORA project. Architect picks a pattern from it. Forger sub-fleet builds against it. Tester writes acceptance tests from it. Surgeon, months later, reads it to understand what was supposed to happen.

If the PDD is bad, every downstream artifact is also bad. So the discipline is: structure first, content second, ambiguity scored last.

## When to invoke

- After Curator promotes a candidate to `pending-analyst`
- When Interviewer's responses come back and Analyst needs to refresh ambiguity

## How to author

Start from `templates/pdd.md` (template ships in this skill). Fill every section. Use Markdown headings — no XML, no JSON in the body. Each section has a purpose:

- **`## Summary`** — one paragraph. What is the process and why does it exist?
- **`## Trigger`** — exactly one of: schedule (cron), event (webhook), on-demand. With the trigger metadata.
- **`## Inputs`** — bulleted list with source + format for each. Source must be a named system (GitHub, NVD, Slack channel, Action Center catalog).
- **`## Outputs`** — bulleted list with destination + format for each.
- **`## Actors`** — table: column 1 = actor type (RPA / AI Agent / Human / External System), column 2 = name, column 3 = role.
- **`## Acceptance criteria`** — Given/When/Then triples, minimum 3, maximum 12. Each becomes ≥ 1 test case.
- **`## Out of scope`** — bullet list of what this process explicitly does NOT do.
- **`## Open questions`** — bullets, only present when ambiguity > 0.4.

Format the file with anchors so Interviewer can reference specific sections (`#trigger`, `#acceptance-criteria-2`, etc.).

## Ambiguity rubric (templates/ambiguity-rubric.md ships with this skill)

Score from 0.0 (perfectly clear) to 1.0 (totally vague) by summing weighted signals:

| Signal | Weight | Detection |
|---|---|---|
| Trigger is `unknown` or has multiple types | 0.25 | regex on `## Trigger` block |
| Any input source is `unknown` | 0.15 per occurrence | grep `## Inputs` |
| Any output destination is `unknown` | 0.15 per occurrence | grep `## Outputs` |
| Acceptance criteria count < 3 | 0.20 | structural check |
| Acceptance criteria use vague language ("works correctly", "as expected", "etc.") | 0.10 per occurrence | regex |
| Actor column has `unknown` or empty | 0.20 per row | structural check |
| Out-of-scope is empty | 0.10 | structural check (forces explicit boundary) |

Cap at 1.0. Round to two decimals.

A score above 0.4 means Analyst sets backlog status to `needs-interviewer`. Below 0.4 means `ready-for-architect`.

## Acceptance-criteria style guide

Bad: "the process should pull invoices correctly"

Good: "Given a SharePoint folder with new invoice PDFs, When the timer fires at 02:00 UTC, Then all PDFs younger than 24 hours are extracted and posted to queue `vendor-invoices` with `Specific Reference == invoice-number`."

The Given/When/Then format is strict because Tester writes test cases against the literal text. Hand-wavy criteria produce hand-wavy tests, which produce production failures.

## Anti-patterns

- Don't pick a pattern. Architect does.
- Don't write activity sequences or pseudocode. PDD is what + why, not how.
- Don't omit `## Out of scope`. Boundaries are part of the contract.
- Don't write more than 12 acceptance criteria. If you can't capture the contract in 12, the process is too large; bounce to Strategist for decomposition.
- Don't smooth over `unknown` values to keep the score down. The score's job is to surface gaps, not to look good.
