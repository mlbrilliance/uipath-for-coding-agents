# `Config.xlsx::LicenseCompat` — sheet shape (follow-up)

T-C8 wires the runtime calls into `CheckLicenseDrift.xaml` (ClearlyDefined.io
primary, GitHub Licenses fallback). The `Config.xlsx::LicenseCompat` sheet
referenced in `tasks.md::T-C8` and `docs/grill-2026-05-09.md::D6` is the
SPDX-compatibility matrix the workflow consults to classify a `(declared,
transitive)` pair as **compatible**, **conflict**, or **review**.

`Config.xlsx` is a binary artefact and isn't editable in this environment.
Document the sheet shape here so a follow-up commit can author it manually
(or via `openpyxl`) without re-deriving the columns from scratch.

## `Settings` sheet — additions

The workflow already calls `GetAsset` for these two URL bases. Add them as
rows in the existing `Settings` sheet (Name / Value / Description columns):

| Name                    | Value                          | Description                                              |
|-------------------------|--------------------------------|----------------------------------------------------------|
| `ClearlyDefinedApiBase` | `https://api.clearlydefined.io`| Primary license-data source. No auth.                    |
| `GitHubApiBase`         | `https://api.github.com`       | Fallback when ClearlyDefined returns no SPDX `declared`. |

## `LicenseCompat` sheet — schema

Hit policy: `FIRST` (first matching row wins; reflects DMN R.M.03).

| Column                | Type    | Notes                                                          |
|-----------------------|---------|----------------------------------------------------------------|
| `DeclaredSpdx`        | string  | SPDX id or wildcard `*` (e.g. `MIT`, `Apache-2.0`, `GPL-*`).   |
| `TransitiveSpdx`      | string  | SPDX id or wildcard `*`.                                       |
| `ConflictType`        | enum    | `compatible` \| `conflict` \| `review`.                        |
| `Severity`            | enum    | `low` \| `medium` \| `high` \| `critical`.                     |
| `Rationale`           | string  | One-line human explanation surfaced in the conflict row.       |
| `RequiresHITL`        | bool    | `true` routes through `concierge` Action Center gate.          |

## Seed rows

The minimum the demo needs:

| DeclaredSpdx  | TransitiveSpdx | ConflictType | Severity | Rationale                                       | RequiresHITL |
|---------------|----------------|--------------|----------|-------------------------------------------------|--------------|
| `MIT`         | `MIT`          | compatible   | low      | identical permissive                            | false        |
| `MIT`         | `Apache-2.0`   | compatible   | low      | both permissive; Apache notice required         | false        |
| `MIT`         | `GPL-*`        | conflict     | high     | copyleft contamination of permissive declared   | true         |
| `Apache-2.0`  | `GPL-*`        | conflict     | high     | copyleft contamination of permissive declared   | true         |
| `*`           | `AGPL-*`       | conflict     | critical | network-copyleft; almost always blocks SaaS use | true         |
| `*`           | `*`            | review       | medium   | unknown pair — Concierge requests human read    | true         |

## Wiring (next task)

`workflows/License/CheckLicenseDrift.xaml` currently emits a row whenever
declared and resolved disagree (column `ConflictType = SPDX_MISMATCH`). The
follow-up should:

1. After the per-package fallback chain, look up `(declared, resolved)` in
   the `LicenseCompat` sheet.
2. Replace the placeholder `SPDX_MISMATCH` with the matched
   `ConflictType` and stamp `Severity` into a fifth column on
   `out_dt_Conflicts`.
3. If `RequiresHITL = true`, raise an Orchestrator queue item the
   `concierge` agent picks up (it owns Action Center bridging).

This split keeps T-C8 focused on the HTTP wiring; the matrix shape lives
here as a reproducible spec for the next commit.
