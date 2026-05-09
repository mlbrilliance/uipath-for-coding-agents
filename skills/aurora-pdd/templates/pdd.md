# <ProcessName> — PDD

> Authored by `analyst` for CAND-<id>. Do not edit by hand once the project is in flight; mutations go through `interviewer` only.

## Summary

<one paragraph: what the process does and why it exists>

## Trigger

- Type: `<schedule | event | on-demand>`
- Detail: `<cron expression OR event source + filter OR caller>`

## Inputs

| Source | Format | Notes |
|---|---|---|
| <e.g., GitHub API> | <e.g., REST JSON> | <e.g., per-repo lockfile> |

## Outputs

| Destination | Format | Notes |
|---|---|---|
| <e.g., Action Center> | <e.g., Form Task> | <e.g., emergency patch approval> |

## Actors

| Type | Name | Role |
|---|---|---|
| RPA | <e.g., Workflows/GitHub/FetchLockfile.xaml> | <reads lockfiles> |
| AI Agent | <e.g., agents/vuln-lookup> | <classifies vulns> |
| Human | <e.g., security-lead@acme> | <approves emergency patches> |
| External System | <e.g., NVD API> | <CVE source> |

## Acceptance criteria

- AC-1: Given <state>, When <event>, Then <observable outcome>
- AC-2: Given <state>, When <event>, Then <observable outcome>
- AC-3: Given <state>, When <event>, Then <observable outcome>

(minimum 3, maximum 12)

## Out of scope

- <explicit boundary 1>
- <explicit boundary 2>

## Open questions

(populate only when ambiguity_score > 0.4)

- Q-1: <gap>
- Q-2: <gap>

## Metadata

- ambiguity_score: <0.00>
- score: <0-100>
- score_rationale: <one line>
- author: analyst
- last_modified: <iso-8601>
