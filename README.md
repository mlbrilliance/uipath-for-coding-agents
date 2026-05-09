# AURORA — UiPath for Coding Agents

A 15-agent swarm that builds, tests, deploys, monitors, and self-heals UiPath automations end-to-end. Built for the [UiPath for Coding Agents challenge](https://forum.uipath.com/t/challenge-build-automations-using-uipath-for-coding-agents/5744067).

+------------------------------------------+
            ¦  Conductor (always running, never sleeps)¦
            +------------------------------------------+
                               ¦
        +----------------------+---------------------+
        ?                      ?                     ?
+--------------+       +--------------+      +--------------+
¦  Discovery   ¦       ¦    Build     ¦      ¦   Operate    ¦
¦  (5 agents)  ¦       ¦  (8 agents)  ¦      ¦  (5 agents)  ¦
+--------------+       +--------------+      +--------------+
   Scout                 Architect              Sentry
   Curator               Cartographer           Diagnostician
   Analyst               Forger-rpa             Surgeon
   Interviewer           Forger-coded           Auditor
   Strategist            Forger-agent           Concierge
                         Forger-maestro
                         Reviewer
                         Tester

## Quick start

Prereqs: Ubuntu VPS with Node.js 18+, Python 3.11+, `git`, `uv`, and `claude` CLI.

```bash
# 1. Install UiPath toolchain
npm install -g @uipath/cli
uipath skills install     # interactive — pick all seven UiPath skills

# 2. Clone and configure
git clone https://github.com/aurora-demo-org/uipath-for-coding-agents.git
cd uipath-for-coding-agents
cp .env.example .env   # fill in UIPATH_*, GITHUB_*, AURORA_*

# 3. Authenticate (one-time)
claude login           # subscription OAuth ? ~/.claude/credentials.json
ln -s CLAUDE.md AGENTS.md

# 4. Install Python deps
uv sync

# 5. Install AURORA as a Claude Code plugin
claude plugin marketplace add ./
claude plugin install aurora@aurora-marketplace

# 6. Validate policy and boot
aurora policy validate
aurora start
```

## Demo

`examples/oss-supply-chain-defender/` contains the Maestro process AURORA builds, deploys, and operates. The 12-minute demo arc covers Discovery ? Build ? Test ? Deploy (with HITL) ? Operate (with self-heal) ? Govern (with deprecation) ? Self-improve (with skill PR). See `docs/demo-script.md`.

## Architecture

See `docs/architecture.md`. TL;DR: three concurrent fleets, one Conductor, three memory tiers, policy-as-code, multi-Claude-tier routing, self-evolving skills via the nightly compost step.

## License

MIT. Built on top of [UiPath/skills](https://github.com/UiPath/skills) and [UiPath/uipath-python](https://github.com/UiPath/uipath-python).

