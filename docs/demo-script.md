# AURORA — 12-minute demo runbook

> Single take. Three split-screens. Two human approvals. One injected failure. One self-heal.

## Pre-demo checklist (the day before)

- [ ] On the VPS: `aurora policy validate` returns `valid` with ≤ 1 warning
- [ ] Curl test for UiPath OAuth returns 200 with all 15 scopes
- [ ] `gh auth status` (or `curl -H "Authorization: Bearer $GITHUB_TOKEN" https://api.github.com/orgs/${GITHUB_ORG}`) returns 200
- [ ] Three fixture repos exist under `${GITHUB_ORG}` with `KNOWN_VULNS.md` and the lockfiles committed
- [ ] `claude login` was run; `~/.claude/credentials.json` exists and has a valid token
- [ ] Action Center catalog `aurora_supply_chain_approvals` exists in folder `AURORA-Demo`
- [ ] `aurora start --skip-daemons` boots cleanly
- [ ] Recording software is set up; three terminal panes pre-arranged
- [ ] `restore.sh` works (test break.sh + restore.sh once on a non-prod folder)

## Screen layout

| Pane | Content |
|---|---|
| Left, top half (60% wide) | `aurora status` TUI — agent activity, backlog, gates, events |
| Left, bottom half (60% wide) | `claude` interactive — where Conductor and Build subagents work |
| Right, top half (40% wide) | Browser: Slack workspace (mock channel `#rpa-asks` and Action Center) |
| Right, bottom half (40% wide) | Browser: UiPath Automation Cloud → Orchestrator → AURORA-Demo folder |

## Beat sheet

### 0:00 — Boot

```
$ aurora start
[aurora] policy: valid (1 warning)
[aurora] uipath token: minted, scopes=15
[aurora] conductor: ready
[aurora] sentry daemon: started (pid 4123)
[aurora] auditor cron: scheduled
[aurora] strategist cron: scheduled
[aurora] compost cron: scheduled
```

Then `aurora status` in the second pane. Dashboard goes green: 19 agents online, 0 in-flight work, budget $0.00 of $50.00 today.

**Talking point**: "AURORA boots in two seconds. From here on, no human keystrokes are required for the build."

### 1:00 — Discovery picks up a friction signal

In the Slack pane, paste a message into `#rpa-asks`:

> *"i'd like to defend our public-facing GitHub org from the next supply-chain attack. need automated scanning of lockfiles against NVD/OSV/scorecard, with auto-PRs for non-critical fixes and security-lead approval for the scary ones. is anyone working on this?"*

Within 30 seconds, the dashboard's "Backlog" pane shows:

```
Pending-analyst:
  CAND-2026-05-09-…  · OSS supply-chain defender · 1 mention
```

**Talking point**: "Scout caught the message; Curator dedupes against the backlog. We've already had 4 mentions of this same problem over two weeks — the cluster ID matches a prior signal."

### 2:00 — Analyst writes the PDD; Interviewer asks four questions

Scroll the bottom-left pane. Analyst's output:

```
analyst: CAND-… scored 78, ambiguity 0.42 → needs-interviewer
```

In the Action Center pane (right top), an Action appears titled *"AURORA: 5 questions about OSS Supply-Chain Defender"*. Open it. Four sharp questions:

- *Severity floor for auto-PRs (CVSS ≥ ?)*: select `7.0`
- *Approver for emergency patches*: type `puneetsatyawan@gmail.com`
- *Repos in scope*: select `node-app, python-app, go-app`
- *Digest cadence*: select `weekly`

Submit.

**Talking point**: "The PDD's ambiguity score dropped from 0.42 to 0.15. Four questions, 30 seconds, no Slack ping-pong."

### 3:00 — Architect picks Maestro; Forger sub-fleet starts

Analyst's status updates to `ready-for-architect`. Architect's ADR appears in `bottom-left`:

```
# ADR — OssSupplyChainDefender
Pattern: Maestro
Forgers needed: forger-maestro, forger-rpa, forger-coded, forger-agent
HITL gates: prod_publish, emergency_patch
Test strategy: Test Manager + Maestro instance tests + Coded Agent evals
```

The dashboard's "Agents" pane lights up: four Forgers go from `idle` to `active`. The "Backlog" pane shows the candidate at `forging`.

In the Orchestrator browser pane, switch to Studio Web. The BPMN canvas has appeared.

### 5:00 — BPMN streams in; Reviewer comments live; Tester writes 12 cases

Watch the BPMN render task by task:

```
forger-maestro: emitted process.bpmn (12 tasks, 3 gateways, 1 boundary timer), 2 DMN tables, bindings
forger-rpa: emitted Workflows/License/CheckLicenseDrift.xaml
forger-coded: emitted Workflows/Coded/GitHub/ResolveLockfiles.cs and Typosquat/CheckLockfiles.cs
forger-agent: scaffolded vuln-lookup (LangGraph, 3 tools, 8 evals)

reviewer: 0 errors, 2 warnings, 5 info → ready-for-tester
tester: 14 tests written, 14 green, coverage 0.92 → ready-for-deploy
```

**Talking point**: "Reviewer caught two warnings — log message bookends missing in two helpers. They're warnings, not errors, so they don't block. Tester wrote one test case per acceptance criterion in the PDD plus four error-path cases."

### 6:30 — Local validation green; publish to dev folder

In the bottom-left pane:

```
$ uipath publish --folder AURORA-Demo-Dev
[uipath] OssSupplyChainDefender@0.1.0 published
[uipath] AuroraVulnLookup@0.1.0 published
[uipath] AuroraSupplyChainDefender@0.1.0 published (XAML + coded workflows)
```

Auto-promote to test (per `policy.yaml::deploy.test.auto: true`).

### 7:00 — Production HITL gate

In Action Center, an action appears titled *"AURORA: production publish approval — OssSupplyChainDefender@0.1.0"*. Approve. Dashboard's "Gates" pane clears. The bot is live.

**Talking point**: "This is the only approval the human gives during the build."

### 8:00 — Run the bot once; critical finding fires the sub-process

In the Orchestrator pane, switch to Maestro → Processes → OssSupplyChainDefender → Start a Job. Use the demo input:

```json
{
  "GitHubOrg": "aurora-demo-org",
  "ScanScope": ["node-app"],
  "EmergencyApprovers": ["puneetsatyawan@gmail.com"]
}
```

The instance opens in Maestro's Instance Management view. The path lights up step by step: `ResolveLockfiles → FanOut → (4 parallel branches) → JoinFanOut → ScoreSeverity → RouteSeverity → CriticalSubProcess`.

In Action Center, a high-priority task appears titled *"AURORA: emergency patch approval"*. Open it. The form shows:
- Triage summary (the LLM's analysis)
- Fingerprint: `npm/minimist@0.2.0 — CVE-2021-44906 (CVSS 9.8, exploit_in_wild=true)`
- Proposed diff: `package.json: minimist 0.2.0 → 1.2.6`
- Files touched: 1

Approve.

In the GitHub pane (or `gh pr list` on terminal): a real PR opens against `node-app`. CI runs (real or mocked via the test fixture). Green. Per the DMN auto-merge policy: severity = critical → `human-review` (we just approved). PR merges.

**Talking point**: "Two human approvals so far: the prod publish, and this emergency patch. Everything else was the swarm."

### 9:00 — Failure injection

In the bottom-left pane:

```
$ ./examples/oss-supply-chain-defender/break.sh
[break] backed up .env → .env.break-backup
[break] GITHUB_TOKEN set to invalid value
[break] Maestro instance started
[break] DONE. Now watch...
```

Within 30-60 seconds:

- Sentry pane (events): `kind: job_failed | exception_type: Octokit.HttpError | message: 401 Bad credentials`
- Diagnostician pane: `fingerprint=auth-failed/token-expired locality=GitHub.ResolveLockfiles cluster_size=N confidence=0.78`
- Surgeon pane: `triage 2026-05-09T14:30 → spawning fix in worktree surgery-…`

Surgeon's actions, visible in the dashboard's "Recent runs" stream:
1. Identifies the cluster's prior remediation: rotate to `GITHUB_TOKEN_FALLBACK`
2. Updates the Orchestrator Asset `GitHubToken` via the SDK
3. Re-publishes the affected package
4. Resumes the paused Maestro instance via the SDK's pause/resume API

Within 90-120 seconds total: the instance retries and goes green.

**Talking point**: "The Surgeon agent never asked the human anything. It rotated a credential, re-published a package, and resumed a Maestro instance — exactly the playbook the cluster's prior occurrences had recorded. If the same fingerprint had been novel, it would have escalated; with confidence 0.78, the policy says auto-fix."

### 10:30 — Strategist proposes consolidation

(Optional — only if you have time and have pre-seeded a near-duplicate process.)

The Strategist's nightly cron fires. In the dashboard:

```
strategist: 2026-Q2 report — 1 consolidation, 2 deprecations, 0 re-prioritizations
  - merge BOT-vendor-invoice-pull-eu and BOT-vendor-invoice-pull-us (89% similar)
```

In Action Center, a task: *"AURORA: deprecate process candidates"*. Approve one of the deprecations (the easier of the two). The `aurora-deprecate` skill stops triggers, archives the package, writes the runbook, and notifies former owners.

### 11:30 — Compost step proposes a skill update

This requires having run `break.sh` at least 3 times across multiple "projects" so the cluster crosses the compost threshold. If you've been demoing for two weeks before submission, this works naturally.

In the dashboard:

```
aurora-compost: 2026-05-09 — 1 PR opened, 2 watching, 0 deferred
  - https://github.com/aurora-demo-org/uipath-for-coding-agents/pull/47
```

Open the PR. Title: *"Skill update: aurora-fingerprint: refine `auth-failed/token-expired` for GitHub Octokit specifically"*. Diff shows a refinement added to `derive_refinement` — instead of just `token-expired`, the cluster splits `token-expired-github` from `token-expired-uipath` so future Surgeon dispatches don't conflate the two remediations.

The PR has CI green and is awaiting your review.

**Talking point**: "AURORA just proposed a change to its own skill set, based on what it observed today. It will not auto-merge — that's the only thing the compost-step gate is non-negotiable about. The swarm gets smarter with use, but always under human supervision."

### 12:00 — Closing

Switch the dashboard to summary view:

```
Today's run summary:
  - 1 process built end-to-end (Discovery → Build → Deploy)
  - 1 critical vulnerability auto-patched (with HITL approval)
  - 1 token-failure self-healed (no human input)
  - 1 process consolidated
  - 1 skill upgrade proposed
  
Human approvals total: 2
```

**Closing line**: "Two human approvals. One swarm. End-to-end. Everything else — Discovery, scoring, ADR, BPMN, DMN, XAML, Coded Agents, Test Manager, deploy, monitoring, self-healing, deprecation, and self-improvement — was the agents."

## What can go wrong on stage (and what to do)

| Failure | Mitigation |
|---|---|
| GitHub API rate-limited mid-demo | Use the GitHub Enterprise dummy responses; or pause and explain |
| Action Center notification delays > 30s | Have the form pre-pasted in a browser tab; click submit there |
| `break.sh` doesn't trigger the failure within 60s | The bash script has a manual fallback comment; trigger via the Orchestrator UI |
| Maestro Instance Management lags | Don't depend on visual rendering; describe what's happening from the events.jsonl tail |
| The compost step PR isn't ready | Skip beat 11:30 entirely; pre-record it |
| Audio glitch during recording | Cut to a 2-minute summary and re-record after the live demo |

## Recording notes

- **Length**: 12 minutes is the target. ±2 minutes is fine. Going over 15 loses jurors.
- **Voice**: calm, present-tense, "the swarm is now..." not "I'm going to make it...".
- **Cut quickly to action**. Don't narrate setup; the dashboard tells the story.
- **Show, don't tell, the second human approval.** That's the surprise — most submissions will have many. AURORA has two.
- **Hold the closing dashboard view for 5 seconds.** Let the summary register.
