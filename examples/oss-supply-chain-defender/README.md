# OSS Supply-Chain Defender — AURORA's demo target

> The Maestro-orchestrated agentic process AURORA builds, deploys, and operates end-to-end.
> 12-minute live demo. Two human approvals. One injected failure. One self-heal.

## What this is

A complete, runnable example of what AURORA produces. Files in this directory are **the output of the swarm**, not hand-authored:

- `process.bpmn` — emitted by `forger-maestro`
- `decisions/*.dmn` — emitted by `forger-maestro`
- `bindings.json` — emitted by `forger-maestro` for the `uipath-platform` skill
- `agents/vuln-lookup/` — emitted by `forger-agent` (LangGraph; entry points `main` and `triage`)
- `workflows/License/CheckLicenseDrift.xaml` — emitted by `forger-rpa`
- `tests/Maestro/*.json` — emitted by `tester` from PDD acceptance criteria

The `fixtures/` folder contains the Discovery-fleet input and the deliberately vulnerable lockfiles AURORA scans during the demo.

## What it does

A timer-driven agentic process that:

1. **Resolves** lockfiles across a GitHub org's repos (RPA / coded workflow)
2. **Fans out** four parallel checks:
   - VulnLookup AI Agent — NVD + OSV + GitHub Advisory
   - MaintainerHealth AI Agent — OpenSSF Scorecard + commit recency
   - TyposquatCheck — npm/PyPI registry diff
   - LicenseDrift — declared vs transitive license conflict
3. **Joins** and runs the **DMN severity matrix** (Critical / High / Medium / Low)
4. **Routes** by severity:
   - **Critical** → triage AI agent → Action Center approval (4h boundary timer escalates to backup) → patch PR → CI wait → auto-merge per DMN policy → notify
   - **High** → auto-PR with version bump
   - **Medium** → batch into the weekly digest
   - **Low** → log only

Every actor type is involved: RPA bots, AI agents, humans, decisions. Every BPMN construct that matters is exercised: timer-start, parallel gateway, exclusive gateway, business-rule (DMN), service tasks, user task, send task, receive task, boundary timer, sub-process.

## How to run the demo

Prereqs (already done if you followed the previous batches):

- `policy.yaml` validates: `aurora policy validate`
- UiPath token mints: the curl test from `CLAUDE.md` returns `access_token`
- Three fixture repos exist as actual GitHub repos under `${GITHUB_ORG}` (or live as the contents of `examples/oss-supply-chain-defender/fixtures/repos/` for offline runs)
- `claude login` has been run on the VPS; `~/.claude/credentials.json` exists

Then:

```bash
# 1. Boot the swarm
aurora start
#    → Conductor live, Sentry polling, Auditor cron scheduled, Compost cron scheduled

# 2. Watch the dashboard
aurora status
#    (or aurora status --once for a non-TUI snapshot)

# 3. From a second terminal: trigger one full Discovery -> Build -> Deploy cycle
#    Drop the Slack fixture into the channel Scout watches:
cat fixtures/slack-channel.jsonl
#    Scout flags it. Curator dedupes. Analyst writes the PDD. Interviewer
#    asks 4 questions (Action Center). After you approve, Architect picks
#    Maestro, Forger sub-fleet builds, Tester runs the suites, HITL gate
#    fires for the prod publish. Approve in Action Center; deployed.

# 4. Inject a failure
./break.sh
#    Sets GITHUB_TOKEN to invalid; triggers a Maestro instance.
#    Within ~60s, Sentry catches the auth failure. Diagnostician
#    fingerprints `auth-failed/token-expired`. Surgeon rotates to
#    GITHUB_TOKEN_FALLBACK, re-publishes, the next attempt goes green.

# 5. (Optional) Manually restore
./restore.sh
```

## The 12-minute demo arc

Recorded as a single take, three split-screens (terminal with `aurora status` TUI / Slack mock / Orchestrator browser).

| Min | Beat |
|---|---|
| 0:00 | `aurora start` — swarm comes up |
| 1:00 | Slack message in fixture channel — Scout flags, Curator dedupes, Analyst scores 78 |
| 2:00 | Interviewer asks 4 questions in Slack/Action Center — I answer |
| 3:00 | Architect picks Maestro; ADR appears; Forger sub-fleet starts in worktrees |
| 5:00 | BPMN streams into Studio Web canvas; Reviewer comments live; Tester writes 12 cases |
| 6:30 | Local validation green; publish to dev folder; auto-promote to test |
| 7:00 | Prod HITL gate fires in Action Center — approve |
| 8:00 | Live run hits a planted CVE; Critical sub-process; Action Center approval; auto-PR opens |
| 9:00 | `./break.sh` runs; Sentry catches auth-failed; Diagnostician fingerprints; Surgeon rotates token |
| 10:30 | Strategist nightly view recommends consolidating two near-duplicate processes; HITL approve |
| 11:30 | Compost step proposes a skill-update PR; review and merge |
| 12:00 | Dashboard summary: 1 process built, 1 critical patched, 1 token-failure self-healed, 1 process consolidated, 1 skill upgraded — **2 human approvals total** |

## File map

```
oss-supply-chain-defender/
├── README.md                          ← you are here
├── process.bpmn                       ← BPMN 2.0 + UiPath extensions
├── bindings.json                      ← task → package mapping (uipath-platform reads this)
├── decisions/
│   ├── severity-matrix.dmn            ← PRIORITY hit policy
│   └── auto-merge-policy.dmn          ← FIRST hit policy
├── agents/
│   └── vuln-lookup/                   ← LangGraph Coded Agent
│       ├── pyproject.toml
│       ├── uipath.json                ← agent manifest
│       ├── main.py                    ← entry: main(input), triage(input)
│       ├── graph.py                   ← LangGraph state machine
│       ├── models.py                  ← Pydantic contract
│       ├── tools/
│       │   ├── nvd.py
│       │   ├── osv.py
│       │   └── github_advisory.py
│       ├── prompts/triage.md          ← system prompt as a file
│       └── evals/triage_eval.json     ← Output Evaluators per AC
├── workflows/
│   └── License/CheckLicenseDrift.xaml ← XAML stub (Try/Catch + RetryScope discipline)
├── tests/
│   └── Maestro/                       ← end-to-end instance tests
│       ├── OssSupplyChainDefender_Critical.json
│       ├── OssSupplyChainDefender_TimerEscalation.json
│       ├── OssSupplyChainDefender_HighAutoMerges.json
│       └── fixtures/                  ← deterministic sub-task outputs for testing
├── fixtures/
│   ├── slack-channel.jsonl            ← Scout's input
│   └── repos/                         ← three fixture repos with vulnerable lockfiles
│       ├── node-app/   (lodash, minimist, axios, jsonwebtoken, express)
│       ├── python-app/ (pyyaml, requests, urllib3, jinja2, cryptography, pillow)
│       └── go-app/     (gin, jwt-go, echo, x/crypto, x/text, yaml.v2)
├── break.sh                           ← failure injection: invalidates GITHUB_TOKEN
└── restore.sh                         ← undo break.sh
```

## What's deliberately out of scope for v1

- **forger-app**: the Coded Web App for a "Defender Dashboard" (read-only view of recent findings) is mentioned in CLAUDE.md but not in this batch. Add when there's runway; the BPMN doesn't need it.
- **MaintainerHealth agent project**: BPMN references it; the implementation is a duplicate of vuln-lookup with different prompts/tools. Skipped to keep the demo focused.
- **TyposquatCheck coded workflow**: BPMN references it; demo runs use the fixture override.
- **GitHub webhook handler** for the `WaitForCI` Receive Task: in the demo we resolve the message via fixture; in production a small Lambda or Worker forwards GitHub `check_run` events to Maestro's message-receive endpoint.

These are all stubbable for the demo and mentioned in `bindings.json` so they have a deploy slot reserved.
