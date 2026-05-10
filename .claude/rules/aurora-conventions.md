# AURORA conventions — auto-injected before every tool call

These conventions are loaded as a Claude Code rule file. They're a condensed, normative version of the disciplines spelled out in `CLAUDE.md` and individual agent definitions. If you're an agent and you're about to act, this is the checklist.

## R.NAMING — UiPath naming

- **R.N.01** Variables: type prefix + PascalCase. `strUrl`, `dt_Lockfile`, `boolFound`, `intCount`. Never `URL`, `lockfile`, `found`, `count`.
- **R.N.02** Arguments: direction prefix mandatory. `in_strRepoName`, `out_intCount`, `io_dictConfig`. Never an unprefixed argument.
- **R.N.03** Workflow filenames: `<AppName>_<Action>.xaml` in PascalCase. `GitHub_FetchLockfile.xaml`, never `Fetch lockfile.xaml`.
- **R.N.04** Project namespaces (coded workflows): `<Solution>.<Module>.<Action>`. PascalCase, no spaces.

## R.STRUCT — Code structure

- **R.S.01** `Main.xaml` and `Process.xaml` orchestrate via `Invoke Workflow File`. Never embed business logic.
- **R.S.02** REFramework's `SetTransactionStatus.xaml` is unmodified. If you think you need to change it, your design is wrong.
- **R.S.03** `InitAllApplications.xaml` opens apps and reaches ready state only. No business logic, no `GetRobotCredential`.
- **R.S.04** Action workflows attach with `OpenMode="Never"`. Login stays in `<App>_Launch.xaml`.
- **R.S.05** Browser: incognito by default; one instance per app; navigate by URL via `NGoToUrl` when the page has a direct URL.

## R.ERR — Error handling

- **R.E.01** `Try/Catch` wraps every external boundary: HTTP, file I/O, UI automation, DB, queue ops.
- **R.E.02** `RetryScope` wraps every API call. NumberOfRetries ≥ 3, RetryInterval ≥ 5s.
- **R.E.03** Don't retry on 4xx auth failures. Surface those.
- **R.E.04** Catch `System.Exception` only if you rethrow as `BusinessException` with context.
- **R.E.05** Never `ContinueOnError = True` to mask failures. If a step is genuinely optional, design for it explicitly.

## R.SEC — Credentials & secrets

- **R.X.01** Credentials are always `SecureString`. `String` passwords are an instant lint fail.
- **R.X.02** Fetch via `GetRobotCredential` at the smallest scope that needs it. Never pass between workflows as arguments.
- **R.X.03** Never store secrets in `Config.xlsx`, memory, learnings, or git. Use Orchestrator Assets.
- **R.X.04** No `os.environ["ANTHROPIC_API_KEY"]` anywhere. Subscription OAuth via `~/.claude/credentials.json`.
- **R.X.05** UiPath OAuth tokens are minted by `aurora-auth` skill. Don't hardcode `UIPATH_ACCESS_TOKEN`.

## R.CFG — Configuration

- **R.C.01** URLs, asset names, queue names, file paths: read from `Config.xlsx::Settings` or Orchestrator Asset. Never hardcoded in workflow code.
- **R.C.02** Environment-dependent values (URLs, IDs, thresholds): always Config-driven.
- **R.C.03** Constants that won't ever vary across environments: OK to hardcode in `Config.xlsx::Constants` sheet (still not in workflow code).

## R.SEL — Selectors

- **R.SE.01** Strict (single-find) only. A selector that matches 0 or >1 elements is rejected.
- **R.SE.02** Single-quoted attributes. `<wnd app='chrome.exe' />`, never double quotes.
- **R.SE.03** Every selector ships with at least one fallback using a different stable attribute.
- **R.SE.04** Selectors live in `.objects/` (Object Repository). Never inline in workflow.
- **R.SE.05** Dynamic values via Config: `aaname='{{vendor}}'` with `vendor` in `Config.xlsx::Settings`.

## R.LOG — Logging

- **R.L.01** Every workflow opens with `Log Message` (Info: "Starting <name>") and closes with `Log Message` (Info: "Completed <name>").
- **R.L.02** Use `AddLogFields` for transaction IDs.
- **R.L.03** Coded workflows: `Log.Information("Starting {Action} for {Repo}", ...)`. Never `print()`.
- **R.L.04** Coded agents: `@traced` decorator + structured fields. Never `print()`.

## R.CODED — Coded workflows / agents

- **R.K.01** Pure functions where possible. Extract logic into helpers that take primitives so Tester can unit-test outside the runtime.
- **R.K.02** No `async void`. `async Task<T>` and let the runtime handle awaits.
- **R.K.03** Reuse activities. If `WebAPI.Activities` ships a `HttpRequest`, use it instead of `HttpClient` directly.
- **R.K.04** Coded Agents: prompts in `prompts/*.md` files, never inlined. Tools in `tools/<service>.py` with type hints + docstrings.
- **R.K.05** Coded Agents: structured output via Pydantic models. `main()` returns a typed object.
- **R.K.06** Coded Agents: idempotent if invoked twice with same input — same output, or detect duplicates.

## R.MAESTRO — BPMN / DMN

- **R.M.01** Every Parallel Gateway has a matching join.
- **R.M.02** Every User Task has a boundary timer with explicit timeout.
- **R.M.03** DMN tables specify hit policy explicitly (UNIQUE, FIRST, PRIORITY, ANY, COLLECT).
- **R.M.04** No business logic in `<scriptTask>`. One-line expressions only.
- **R.M.05** `User Task` binds only to Action Center. That's where humans are.
- **R.M.06** Decisions live in DMN, not in agent prompts or XAML expressions.

## R.SWARM — AURORA-specific

- **R.SW.01** One agent, one job. If you're doing two things, hand the second to the right peer.
- **R.SW.02** Cross-fleet handoffs go through Conductor. No direct Discovery → Build calls.
- **R.SW.03** Forger sub-fleet works in `${AURORA_WORKTREE_DIR}/<job-id>/`. Never the main checkout.
- **R.SW.04** Memory access is via `aurora-recall` (read) and `aurora-fingerprint` (write). Don't read `.aurora/` directly.
- **R.SW.05** HITL gates from `policy.yaml::gates` are absolute. Never bypass, even when "obvious."
- **R.SW.06** Skills the Architect picked are the contract. If a skill is missing a generator you need, escalate via `.aurora/learnings/` — don't reinvent.
- **R.SW.06.1** The official UiPath skill catalogue at <https://github.com/UiPath/skills> is canonical. Default to its skills (`uipath-rpa-workflows`, `uipath-coded-workflows`, `uipath-coded-agents`, `uipath-flow`, `uipath-platform`, `uipath-coded-apps`, `uipath-servo`) wherever applicable; install via `uipath skills install`. AURORA's ten custom skills under `skills/` extend the catalogue — they never replace a UiPath/skills equivalent. Before authoring a new builder skill, check UiPath/skills first; if the gap is real, file a `.aurora/learnings/` entry rather than write a parallel custom skill.
- **R.SW.08** Factory.ai Droid CLI is the default coding-agent dispatch for parallel worktree work — `mcp__multi-model-router__consult_droid` / `/droid` / direct `droid` CLI. Do not default to `Agent(subagent_type="general-purpose")` for "implement T-Xn end-to-end and commit" work. General-purpose Task() agents are for research and read-only exploration; Factory droids run the production-grade red→green→refactor coding loops. `consult_codex` is acceptable for narrow Codex-suited cases. The Conductor's worktree pool dispatch maps to Factory droids 1:1.
- **R.SW.07** Decisions that recur belong in `policy.yaml`. If you find yourself making the same call repeatedly, propose a policy update.

## R.TEST — Testing discipline

- **R.T.01** Every PDD acceptance criterion maps to ≥ 1 test. The mapping lives in `tester-coverage.md`.
- **R.T.02** Tests test the contract, not the code path.
- **R.T.03** Mock dependencies (NVD, GitHub, Slack), never the system under test.
- **R.T.04** Error-path tests are mandatory. "Happy path covers it" is wrong.
- **R.T.05** Coded Agent evals use Output Evaluators (Contains, Exact Match, JSON Similarity, LLM Judge) — not just exact-match.

## R.GOV — Governance & deploy

- **R.G.01** No prod deploy without Reviewer green AND Tester green AND Auditor drift-free AND CI green.
- **R.G.02** Cross-folder dependency check passes before any prod publish.
- **R.G.03** Auto-merge in dev only when CI is green AND policy permits.
- **R.G.04** Surgeon's auto-fix is bounded by `policy.operate.surgeon.max_workflows_touched_without_hitl`. Above that → HITL.
- **R.G.05** Compost-step skill PRs are NEVER auto-merged. Always HITL.
