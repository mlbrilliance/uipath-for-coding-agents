# PDD — AURORA: Final Mile to a Live UiPath Demo

UiPath calls this kind of document a Process Definition Document. We use the UiPath term here, not "PRD."

Status: drafted 2026-05-09 from the conversation context, the resolved-decisions block in `/home/claude/.claude/plans/mission-ship-aurora-smooth-meerkat.md`, and the doc-grilling artifact at `.aurora/grill-2026-05-09.md`. Once approved, `triage` will decompose this into `tasks.md`.

## Problem Statement

A previous design pass produced 109 files defining AURORA — a 19-agent coding-agent swarm that builds, tests, deploys, monitors, and self-heals UiPath automations. The package imports cleanly and every BPMN/DMN/JSON parses. But the swarm cannot actually run a UiPath process end-to-end yet: nine pieces are explicitly stubbed, four UiPath integration assumptions were just shown to be wrong against the official docs, and several agent definitions describe APIs that do not exist (`uip publish` for Maestro projects, direct Test Manager API publish). The submission deadline for the UiPath for Coding Agents challenge is 2026-05-15. Without the final-mile work, the 12-minute demo in `docs/demo-script.md` cannot be executed live, and the claims in `docs/submission-post.md` are contradicted by the running system.

## Solution

Take AURORA from "imports cleanly with documented stubs" to "executes the 12-minute demo script live, end-to-end, with real Orchestrator round-trips, real GitHub PRs, real Action Center HITL, real Sentry-detected fault injection and Surgeon self-heal — no mocks." Concretely: promote nine stubs to real implementations, correct four contradicted assumptions against UiPath docs, ship one new FastAPI webhook service and one Maestro publish bridge, and update `submission-post.md` so the marketing claims and the running system agree.

## User Stories

### UiPath challenge judges (the primary audience)

1. As a UiPath challenge judge, I want to see AURORA boot from a single `aurora start` command, so that I can evaluate the operational discipline without wading through manual setup steps.
2. As a UiPath challenge judge, I want every UiPath integration in AURORA to use UiPath's real documented APIs (Orchestrator OData, Maestro engine, Action Center Form Tasks, Test Manager link, Coded-Agent SDK), so that the submission demonstrates real platform fluency rather than aspirational shims.
3. As a UiPath challenge judge, I want the 12-minute demo to run live (not recorded), so that I can trust the artifacts I'm shown.
4. As a UiPath challenge judge, I want the submission post (`docs/submission-post.md`) to claim only what actually ships, so that no executive review uncovers a gap between marketing and reality.
5. As a UiPath challenge judge, I want every `<uipath:*>` extension in `process.bpmn` to be a documented Studio Web schema (or absent), so that the file would import into Studio Web without errors.
6. As a UiPath challenge judge, I want the Coded Agents to follow the official `uipath init`-generated manifest shape, so that I can run `uipath pack` / `uipath publish` against the project unmodified.

### Demo audience (run-of-show during the 12-minute demo)

7. As a demo viewer, I want to see Scout pick up a Slack signal, Curator dedupe it, and Analyst score it, so that I see the Discovery fleet working concurrently.
8. As a demo viewer, I want to see four Forgers running in parallel worktrees while Cartographer populates the Object Repository, so that I see the Build fleet's concurrency.
9. As a demo viewer, I want to see the BPMN model rendered in Studio Web after `forger-maestro` emits it, so that the "model becomes implementation" story is visible.
10. As a demo viewer, I want to see exactly two HITL approvals (prod-publish and emergency-patch) routed through Action Center, so that the policy-driven gating is concrete.
11. As a demo viewer, I want to see a real GitHub PR opened in the demo org by AURORA, with CI green, auto-merged per DMN policy, so that the Critical sub-process flow is visible end-to-end.
12. As a demo viewer, I want `break.sh` to trigger an actual auth fault that Sentry catches in < 60 s, Diagnostician fingerprints, and Surgeon self-heals — visible in `aurora status`, so that the self-healing claim is demonstrated, not described.
13. As a demo viewer, I want the compost-step PR against `skills/<name>/SKILL.md` to appear at the end of the demo, so that the "self-evolving skills" claim is concrete.

### AURORA operator (the human running the swarm)

14. As an AURORA operator, I want `aurora policy validate --strict --live` to actually probe Orchestrator and GitHub, so that policy validation surfaces config drift before a swarm boot wastes my time.
15. As an AURORA operator, I want `aurora status` to show a Textual TUI with live event tail, agent grid, gates pane, and budget meter, so that I can see the swarm's state at a glance without grepping log files.
16. As an AURORA operator, I want a single CLI binary name (`uipath`, not the fictional `uip`), so that I can copy/paste docs and have them work.
17. As an AURORA operator, I want every agent's claimed UiPath API to actually exist, so that I am not surprised at runtime by a missing endpoint.
18. As an AURORA operator, I want `make ci` to enforce the merge gate, so that no half-finished work lands on `main`.
19. As an AURORA operator, I want my `.env` credentials never written to memory or learnings, so that the swarm honours R.X.03 even on hot paths.

### AURORA agents (the runtime contract)

20. As Concierge, I want to ensure the `aurora_supply_chain_approvals` task catalog exists on first call, so that subsequent Form Task creates don't fail with error 2451.
21. As Concierge, I want every Orchestrator OData call to set `X-UIPATH-OrganizationUnitId`, so that folder context is correct.
22. As Sentry, I want to detect a `kind: auth_failed` event from Orchestrator within 60 s of injection, so that Diagnostician's fingerprinting can begin promptly.
23. As Diagnostician, I want a fingerprint cluster with confidence ≥ 0.7 on the auth-failed cluster after `break.sh`, so that I dispatch Surgeon with `auto_fix: true`.
24. As Surgeon, I want a fresh worktree spun up under `${AURORA_WORKTREE_DIR}/<job-id>/` for the auth-rotation fix, so that the main checkout is untouched.
25. As Surgeon, I want to rotate the `GITHUB_TOKEN` Orchestrator Asset to its `_FALLBACK` sibling via the SDK, so that the failed instance can resume.
26. As Surgeon, I want to resume the paused Maestro instance after asset rotation, so that the run completes without restarting from scratch.
27. As Tester, I want to publish Studio test packages to Orchestrator (not directly to Test Manager via API), so that my output matches UiPath's documented test-automation flow.
28. As Forger-Maestro, I want to emit `bindings.json` + `entry-points.json` + `langgraph.json` (per framework) alongside `process.bpmn`, so that Studio Web can import the project without choking on undocumented extensions.
29. As Forger-Agent, I want to run `uipath init` once at scaffold time and let the SDK author `uipath.json`, so that the manifest validates.
30. As Conductor, I want every cross-fleet handoff to flow through me (no Discovery → Build direct calls), so that the policy gate enforcement remains absolute.
31. As Reviewer, I want the lint suite to enforce all 60+ rules in `.claude/rules/aurora-conventions.md`, so that REFramework discipline is non-negotiable.
32. As the compost step, I want to open a real PR against this repo's `skills/<name>/SKILL.md`, HITL-gated via aurora-promote with `kind: skill_compost_pr`, never auto-merged, so that the swarm's skills evolve deliberately.

### Demo project (`oss-supply-chain-defender`)

33. As the demo process, I want `ResolveLockfiles` to enumerate real repos under `${GITHUB_ORG}` matching `ScanScope`, so that the scan is grounded in real data.
34. As the demo process, I want `ResolveLockfiles` to parse `package-lock.json` / `yarn.lock` / `requirements.txt` / `go.sum`, so that the four parallel-gateway branches receive real dependency lists.
35. As the demo process, I want `MaintainerHealth` to query OpenSSF Scorecard and a commit-recency tool, so that maintainer-health scores are real numbers.
36. As the demo process, I want `MaintainerHealth` to be implemented on the OpenAI Agents framework (not LangGraph), so that the demo showcases the swarm's multi-framework Coded-Agent capability.
37. As the demo process, I want `TyposquatCheck` to apply Levenshtein matching against an allow-list of top-N npm/PyPI packages, so that typosquat suspects are detected with real signal.
38. As the demo process, I want `CheckLicenseDrift` to call ClearlyDefined.io with a GitHub Licenses API fallback, so that license-drift reasoning is grounded in public data.
39. As the demo process, I want `OpenPatchPR` and `OpenAutoPR` to open real GitHub PRs with version bumps, so that the auto-merge DMN policy operates on real artifacts.
40. As the demo process, I want `Notify.SendDigest` to post to a real Slack channel and `Notify.AppendToDigest` to maintain a real digest, so that the operator notifications are live.
41. As the demo process, I want the WaitForCI step to be a Send Task + intermediate message catch event with boundary timer (BPMN-purist pattern), so that Maestro's documented task-execution support is honoured.
42. As the demo process, I want the GitHub webhook handler to live at `webhook/github-check-run/` as a FastAPI service exposed via Cloudflare Tunnel, so that `check_run.completed` events from GitHub correlate against the paused Maestro instance.
43. As the demo process, I want the test cases under `tests/Maestro/` to run unmodified after the BPMN-binding cleanup, so that regression coverage is preserved.

### Documentation and submission

44. As the submission post, I want every claim to map to a shipped artifact verified by `make ci`, so that there is no aspirational language left.
45. As the submission post, I want a "what we changed during the final mile" sub-section, so that the doc-grill verdicts (D1-D7) and their resolutions are visible to reviewers.
46. As the demo script, I want each beat (0:00 to 12:00) to map to a verified action, so that no beat secretly assumes a stub still works.
47. As the webhook-deploy doc, I want a complete `cloudflared tunnel` walkthrough with the exact GitHub webhook secret format and signature header, so that re-deployment from scratch takes < 10 minutes.

### Live environment (already provisioned per D4)

48. As the live UiPath tenant, I want every external call from the swarm to use the External Application's OAuth client-credentials grant minted by `aurora-auth`, so that no static token leaks into source.
49. As the GitHub demo org, I want webhooks from each demo repo configured to forward `check_run` events to the FastAPI service over the Cloudflare Tunnel, so that Maestro gets resumed when CI completes.
50. As the Action Center catalog (`aurora_supply_chain_approvals`), I want to be created idempotently by Concierge on first use, so that catalog 2451 errors never surface.

## Implementation Decisions

The implementation centres on extracting deep modules with simple testable interfaces. Each module has one job; the orchestration glue lives in agents, the integration glue lives in `uipath_client`, and the policy lives in `policy.yaml`.

### D1. BPMN binding shape

`process.bpmn` is reduced to standard BPMN 2.0 elements only (`<bpmn:serviceTask>`, `<bpmn:userTask>`, `<bpmn:scriptTask>`, `<bpmn:businessRuleTask>`, gateways, events). The `<uipath:taskBinding>` extension elements are removed. `bindings.json` is the sole binding source of truth, kept in the project root next to `process.bpmn`. Per-framework manifests (`entry-points.json`, `langgraph.json`, `uipath.json`) are generated by `uipath init` per agent/coded-workflow, never hand-authored.

Verified against: `docs.uipath.com/studio-web/automation-cloud/latest/user-guide/configuring-agentic-process-elements`, `github.com/UiPath/uipath-langchain-python` project layout. (Recorded in `.aurora/grill-2026-05-09.md`.)

### D2. WaitForCI shape

Primary: `Send Task` (post a `pending` comment to the PR) → `intermediate message catch event` (correlation key = `pr_url`) with a boundary timer (escalate after `WaitForCITimeout`). Fallback (kept warm in a feature branch): User Task auto-completed by webhook via `POST /odata/Tasks/{id}/Complete`. Fallback ships if integration reveals Maestro engine refuses intermediate-message-catch.

### D3. Maestro publish bridge

New module `aurora.uipath_client.maestro`. `publish_maestro_project(project_dir: Path, folder: str) -> PublishResult` reverse-engineers the Studio Web HTTP publish API, captured once via Playwright `browser_network_requests` and codified as a Python wrapper (auth header reuse, multipart upload, package version bump). Fallback: full Playwright UI drive (login → click Publish → select folder), invoked when the HTTP call returns a schema error or an unexpected redirect. Module also exposes Maestro instance pause/resume/retry/cancel/move helpers.

### D4. Live environment (already provisioned)

UiPath Automation Cloud tenant has `AURORA-Demo` and `AURORA-Demo-Sandbox` folders, the `aurora_supply_chain_approvals` Action Center catalog, an External App with `OR.*` scopes, and a robot account. GitHub `${GITHUB_ORG}` has demo repos with vulnerable lockfiles and a webhook secret. `.env` on this VPS holds `UIPATH_CLIENT_ID/SECRET` and `GITHUB_TOKEN/FALLBACK`. Orchestrator Assets `GitHubToken` and `LicenseDataApi` exist.

### D5. GitHub webhook host

New module `webhook.github_check_run` (FastAPI). Two endpoints:
- `POST /github/check-run` — verifies HMAC against `GITHUB_WEBHOOK_SECRET`, decodes `check_run.completed`, looks up Maestro instance by correlation key (PR URL), POSTs the correlation message to Maestro's instance message-receive endpoint.
- `GET /healthz` — liveness for Cloudflare Tunnel.

Exposed via `cloudflared tunnel`. Documented end-to-end in `docs/webhook-deploy.md` (tunnel creation, GitHub webhook config, secret rotation, signature spec).

### D6. License-drift data source

`workflows/License/CheckLicenseDrift.xaml` calls ClearlyDefined.io first (`https://api.clearlydefined.io/definitions/{type}/{provider}/{namespace}/{name}/{revision}`); on no-data falls back to the repo's `GET /repos/{owner}/{repo}/license` via the existing `GITHUB_TOKEN`. SPDX-compatibility decision is encoded as a small Config-driven matrix in `Config.xlsx::LicenseCompat`.

### D7. Compost PR target

`aurora.compost.propose_skill_pr(learnings_path)` opens a PR in this repo (`uipath-for-coding-agents`), against `skills/<name>/SKILL.md`. PR title prefix `[compost]`. HITL-gated via `aurora-promote` with `kind: skill_compost_pr`. Never auto-merged. PR body includes the learnings cluster summary, the proposed diff, the policy gate context, and the rollback runbook.

### CLI rename

The fictional `uip` binary becomes `uipath` (the real binary from `uipath-python`) everywhere — all skills, slash commands, hooks, scripts, demo-script.md, submission-post.md, README.md.

### Concierge ↔ Action Center contract

Concierge calls Orchestrator OData `/odata/Tasks/...` with `X-UIPATH-OrganizationUnitId` set. Catalog existence is asserted idempotently on first use by checking `/odata/TaskCatalogs?$filter=Name eq '<catalog>'` and creating if missing. Form Tasks created via `POST /odata/Tasks/UiPath.Server.Configuration.OData.CreateFormTask`.

### Sentry ↔ Diagnostician ↔ Surgeon self-heal contract

Sentry polls Orchestrator at `policy.operate.sentry.poll_interval_seconds` (default 30s) for jobs/queues/assets; emits `kind: job_failed` events. Diagnostician consumes events.jsonl, runs `aurora-fingerprint`, dispatches Surgeon with `auto_fix: true` when cluster confidence ≥ 0.7 AND `policy.operate.surgeon.max_workflows_touched_without_hitl` is honoured. Surgeon spawns into a fresh worktree, calls Cartographer if UI work is needed, calls the relevant Forger to regenerate, calls Tester for regression, opens a PR with the fix. For the demo's auth-failed cluster, Surgeon's remediation is asset rotation (`GITHUB_TOKEN` → `GITHUB_TOKEN_FALLBACK`) followed by Maestro instance resume.

### Replay (`aurora.replay`)

`replay_instance(instance_id: str, sandbox_folder: str = "${UIPATH_FOLDER}-Sandbox") -> ReplayResult`. Pulls the original instance's input variables and event log, deploys a copy of the same Maestro project to the sandbox folder if not already there (per package hash), starts a new instance with the same inputs, returns a structured comparison (same path? same vars at each gateway? same end event?). Wired through MCP tool `aurora_replay_instance`.

### TUI (`aurora.cli.tui`)

`AuroraStatusApp(textual.App)` with four widgets:
- `EventTail` — tails `${AURORA_HOME}/events.jsonl` with kind-coloured lines.
- `AgentGrid` — 19 cells, one per agent, showing last-action timestamp + current state.
- `GatesPane` — pending HITL gates with deadline countdowns.
- `BudgetMeter` — daily token spend per Claude tier, against `policy.budget` ceilings.

`--once` and `--json` paths preserved unchanged; the TUI is the default when stdout is a TTY.

### Compost (`aurora.cli.cmd_compost`)

Reads `${AURORA_HOME}/learnings/<date>.jsonl`, clusters via existing `aurora.fingerprint`, proposes a single skill update per cluster meeting the threshold (≥ 3 occurrences across ≥ 2 projects), drafts the diff, calls `aurora.compost.propose_skill_pr` which routes through `aurora-promote` for the HITL gate, opens the PR via `gh pr create`.

### Coded Agents (MaintainerHealth)

`agents/maintainer-health/` directory: `pyproject.toml`, `main.py`, `tools/scorecard.py`, `tools/commit_recency.py`, `prompts/triage.md`, `evals/triage_eval.json`, `uipath.json` (regenerated by `uipath init`). Framework: OpenAI Agents SDK. `main(input: MaintainerHealthInput) -> MaintainerHealthReport` is the entry point, with `MaintainerHealthInput`/`Report` as Pydantic models. Tools are pure-async functions with type hints + docstrings. Idempotent.

### Coded Workflows (C#)

`coded/Typosquat/`, `coded/ResolveLockfiles/`, `coded/Notify/`, `coded/OpenPatchPR/`, `coded/OpenAutoPR/`, `coded/BatchDigest/`, `coded/AppendToDigest/`. Each follows `Solution.<Module>.<Action>` namespace, in/out arg prefixes, `RetryScope` on every API call, `Try/Catch` on every external boundary, `GetRobotCredential` for secrets at minimum scope, `GetAsset` for config-driven values. Pure helpers (Levenshtein, lockfile parsers, SPDX matrix) extracted into static classes for unit test.

### Tester flow correction

`agents/tester.md` updated. The Tester:
1. Generates Studio test packages (XAML for RPA workflows, `uipath-eval` JSON for Coded Agents).
2. Runs them locally first via `uipath run`.
3. Publishes the package to Orchestrator via `uipath publish`.
4. Links the published automation in Test Manager (Test Manager API where the v2026.x exposes write endpoints; Playwright fallback against Test Manager's "Select Automation" UI otherwise).

The "directly publishes test set to Test Manager via API" claim is removed.

### Submission post update

`docs/submission-post.md` re-pass: every feature claim is either backed by a shipped artifact verified by `make ci`, or removed. New "Final mile changes" sub-section captures D1-D7 + the CLI rename + the Tester flow correction so reviewers see the discipline.

## Testing Decisions

A test is good when it pins external behaviour without coupling to internal structure. We test the contract, not the code path. We test failure modes alongside happy paths. We do not mock the system under test; we mock only the external dependency (and only at the seam, not deeper). Coded Agent evals use Output Evaluators (Contains, Exact Match, JSON Similarity, LLM Judge) — not just exact-match.

### Modules with new tests

- `aurora.replay` — unit tests with synthetic instance fixtures; integration test against the live `AURORA-Demo-Sandbox` folder.
- `aurora.cli.tui` — Textual snapshot tests for each of the four widgets; smoke test for the full app.
- `aurora.compost` — unit tests with synthetic learnings JSONL; integration test that opens a real (but flagged) PR against a `compost-test` branch on this repo.
- `aurora.uipath_client.maestro` — unit tests with a recorded HTTP fixture for the publish call; integration test against the live tenant for a no-op publish.
- `aurora.uipath_client.action_center` — unit tests with a recorded fixture; integration test that creates and immediately completes a test Form Task.
- `webhook.github_check_run` — FastAPI TestClient unit tests with signed payloads (good signature, bad signature, malformed JSON, unexpected event type); integration test that fires a real GitHub webhook through the Cloudflare Tunnel against the demo Maestro instance.
- MaintainerHealth — UiPath `evals/` with both deterministic and LLM-judge evaluators; offline fixture pack for the OpenSSF Scorecard tool to keep tests hermetic.
- Coded Workflow C# helpers (Levenshtein, lockfile parsers, SPDX matrix) — xUnit for the pure functions; integration test that runs `ResolveLockfiles` against a real GitHub demo repo.
- License-drift workflow — Try/Catch + RetryScope unit shape covered by Reviewer's lint; integration test that runs against a known-licensed package and asserts the SPDX outcome.

### Agent definition tests (all 19)

Every agent in `agents/` gets test coverage at three layers:

1. **Frontmatter schema** — name, description, allowed-tools, fleet, must validate against a single shared schema in `tests/schemas/agent_frontmatter.schema.json`. One parametrised pytest covering all 19 files.
2. **Prompt-body invariants** — pytest assertions per agent: (a) the prompt body never references `ANTHROPIC_API_KEY` or any other banned-secret pattern; (b) it cites only skills that exist on disk under `skills/` or are official UiPath skills; (c) it cites only sibling agents that exist (no broken hand-offs); (d) it doesn't claim a UiPath API contradicted in `.aurora/grill-2026-05-09.md` (e.g., no "publish to Test Manager via API," no `<uipath:taskBinding>` references, no `uip` CLI binary); (e) for Build agents, it names the right skill from the picker matrix (`forger-rpa` → `uipath-rpa-workflows`, etc.).
3. **Functional contract** — for agents with programmatic surfaces invoked from Conductor (`conductor`, `sentry`, `diagnostician`, `surgeon`, `auditor`, `concierge`, `cartographer`, `analyst`, `tester`, `reviewer`, `interviewer`, `scout`, `curator`, `strategist`, the four `forger-*`, the meta `architect`), an integration test at `tests/agents/test_<name>.py` that runs the agent against a recorded scenario fixture and asserts the contract output (PDD shape for analyst, ADR shape for architect, Form Task ID for concierge, fingerprint cluster for diagnostician, worktree path + PR URL for surgeon, Test Manager link for tester, etc.). Fixtures live under `tests/agents/fixtures/<agent>/`. The test invokes the agent the same way Conductor does — `Task(subagent_type="aurora:<name>", prompt=...)` — and the assertion is on the structured artefact returned, not on the conversation transcript.

Cross-cutting: a single `tests/agents/test_all_agents_lint.py` runs the Reviewer agent's lint over every agent definition. Lint failures block PR merge.

### Existing Maestro test cases

- `tests/Maestro/` — must pass unchanged after the BPMN-binding cleanup. If a test reference moved (e.g., a binding key relocated from `.bpmn` to `bindings.json`), update the fixture path; do not rewrite the test.

### Prior art

- `tests/unit/test_auth.py` — pattern for OAuth token refresh tests.
- `tests/unit/test_fingerprint.py` — pattern for SQLite-backed module tests.
- `tests/unit/test_policy.py` — pattern for JSON Schema validation + dry-run tests.
- `tests/integration/test_uipath_live.py` — pattern for live-tenant integration tests; keyed by `UIPATH_INTEGRATION=1` env so the suite skips when credentials are absent.

### Test discipline

- Every PDD acceptance criterion → ≥ 1 test. Mapping in `tester-coverage.md`.
- Error-path tests are mandatory.
- Mocks at the seam (`requests`, `httpx`, `octokit`), never inside the system under test.
- For Coded Agents: tests run via `uipath run --eval` or the framework's eval harness, not pytest directly.

## Out of Scope

- Adding new agents to the 19 already defined. The contract is fixed; expanding it requires a separate PDD.
- Replacing the demo project (`oss-supply-chain-defender`) with a different use case. The Open-Source Supply-Chain Defender is the canonical demo.
- Migrating off the Claude subscription OAuth model. The deny rule on `*.anthropic.com/v1/messages` in `.claude/settings.json` is intentional and stays.
- Multi-tenant deployments. The mission targets a single live tenant for the demo.
- Automating UiPath tenant provisioning. D4 is "already provisioned"; reproducing it is documentation, not code.
- Migrating `lib/aurora/cli.py` away from `click`. The TUI is additive.
- Replacing `Config.xlsx` with `policy.yaml`. The two have different roles (per-process vs per-swarm).
- Adding a real Slack integration as opposed to using a single demo channel via webhook. Multi-channel routing is a v0.3 concern.

## Further Notes

- **Convention discipline.** All work conforms to the 60+ rules in `.claude/rules/aurora-conventions.md`. The Reviewer agent is the merge gate; lint-fail on any error-level rule blocks the PR. Notable rules touched by this PDD: R.N (naming), R.S (structure), R.E (error handling), R.X (secrets), R.C (config), R.SE (selectors), R.K (coded), R.M (Maestro), R.SW (swarm), R.T (testing), R.G (governance).
- **HITL gates.** `policy.yaml::gates` defines five gates (`prod_publish`, `emergency_patch`, `deprecation`, `large_fix`, `skill_compost_pr`). Every gate fires in the demo. Bypassing is an instant fail.
- **Worktree pool.** Forger sub-fleet builds in `${AURORA_WORKTREE_DIR}/<job-id>/`. Conductor caps concurrency at 4. Worktrees are torn down on success and preserved on failure (for diagnose).
- **Three-tier memory.** Project tier (`.aurora/projects/<id>/`), Org tier (`.aurora/org/`), Skill tier (`.aurora/learnings/`). Access only via `aurora-recall` and `aurora-fingerprint`. Direct file I/O into these dirs is a lint fail.
- **Auth model.** UiPath: OAuth client-credentials via External App, minted by `aurora-auth`, refreshed proactively. Claude: subscription OAuth via `~/.claude/credentials.json`, no API key anywhere.
- **Demo run-of-show is the integration test.** Beat 0:00 → beat 12:00, no manual intervention beyond the two HITL approvals. If a beat fails, run `diagnose` (Matt Pocock skill) before patching.
- **Refactor cadence.** `improve-codebase-architecture` after every 5 merged tasks. Refactor PRs are separate from feature PRs.
- **Deadline.** 2026-05-15 (six days from drafting). Triage will sequence work; if a sub-task slips, the fallback ladder (D2/D3 fallbacks; license-drift to GitHub-only; webhook to recorded fixtures) preserves the demo.
- **Issue-tracker publish.** This PDD lives at the repo root as `PDD.md`. No issue-tracker push at this stage; `triage` will produce `tasks.md` next.

## Doc-grilling addendum

The seven open questions from the doc-grilling pass are recorded in `.aurora/grill-2026-05-09.md` with their resolutions (D1-D7). The plan file at `/home/claude/.claude/plans/mission-ship-aurora-smooth-meerkat.md` holds the workstream sequencing (A-F) that `triage` will turn into `tasks.md`.
