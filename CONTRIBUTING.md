# Contributing to AURORA

PRs welcome. Please follow the conventions below — the Reviewer agent (or a human reviewer using
the same rule set) will check compliance on every PR.

## The merge gate is `make ci`

`make ci` is the single source of truth for whether a change is mergeable. It runs:

- `make lint` — `ruff check lib tests`
- `make typecheck` — `mypy lib` (strict mode; `aurora.mcp.server` has a narrow
  override for the untyped MCP decorators)
- `make test` — `pytest tests/unit -v`
- `make policy-strict` — `aurora policy validate --strict`

The GitHub Actions workflow `.github/workflows/ci.yml` invokes `make ci` directly so the CI
result and your local result are identical. The required status check on `main` is named
**`make ci`**.

If you maintain the branch protection on `main`, configure:

- Settings → Branches → Branch protection rules → `main`
- Require status checks to pass before merging: ✓
- Require branches to be up to date before merging: ✓
- Status checks: search for **`make ci`** and tick it
- Require linear history: ✓ (recommended)

## Local development

```bash
# Setup
uv sync --extra dev

# Verify before push
make ci

# Run just the changed area's tests for fast feedback
.venv/bin/python -m pytest tests/agents -v   # agent contract tests
.venv/bin/python -m pytest tests/lint -v     # convention/schema lints
```

## Test discipline

- Every new behavior, bug fix, or refactor that touches logic gets a **failing test first**.
- Red → green → refactor.
- Per `R.T.01`: every PDD acceptance criterion maps to ≥ 1 test. The mapping lives in
  [`tester-coverage.md`](tester-coverage.md). If you add a user story, add a row.
- Per `R.T.03`: mock dependencies (NVD, GitHub, Slack); never mock the system under test.
- Per `R.T.04`: error-path tests are mandatory.

## Convention discipline

`.claude/rules/aurora-conventions.md` holds 60+ rules covering REFramework discipline, secrets,
BPMN/DMN structure, and the swarm conventions. Highlights:

- **R.SW.02** — cross-fleet handoffs go through Conductor.
- **R.SW.05** — HITL gates from `policy.yaml::gates` are absolute. Never bypass.
- **R.G.05** — compost-step skill PRs are NEVER auto-merged.
- **R.X.01** — credentials are always `SecureString`. `String` passwords are an instant lint
  fail.
- **R.X.04** — no `os.environ["ANTHROPIC_API_KEY"]` anywhere; subscription OAuth via
  `~/.claude/credentials.json`.

The Reviewer-driven agent lint (`tests/agents/test_all_agents_lint.py`) enforces 10 additional
R.G4.* rules over agent prompt bodies.

## Claims-mapping invariant

Every load-bearing claim in [`docs/submission-post.md`](docs/submission-post.md) maps to an
on-disk artifact via [`docs/submission-claims.json`](docs/submission-claims.json), enforced by
[`tests/docs/test_submission_claims.py`](tests/docs/test_submission_claims.py). If you rename or
remove a referenced artifact, also update the claims map — or CI breaks.

## Live-tenant integration tests

Tests under `tests/integration/` are gated by `UIPATH_INTEGRATION=1` and require a provisioned
`.env`. Don't run them from a PR on a fork (they hit a real UiPath tenant). Reviewers run them
locally before promote-to-prod.

To run them:

```bash
UIPATH_INTEGRATION=1 .venv/bin/pytest tests/integration -v
```

The F5 self-heal chain test (`test_f5_self_heal_live.py`) does a real round-trip rotation of
an Orchestrator Credential asset; the asset is restored on every run via a `try/finally`
block, but be aware the change is visible in your audit log.

## Commit message format

Conventional Commits, with the AURORA task ID where applicable:

```
T-D1 [green]: webhook implementation
T-G3a: Discovery-fleet functional contract tests (5 agents)
fix(hooks): post-tool JQ paths match Claude Code's real PostToolUse schema
docs(README): rewrite as the front door
```

The first line is a single subject (≤ 72 chars). The body explains *why*; the test that makes
it green is referenced in the body. Always end with a `Co-Authored-By:` trailer.
