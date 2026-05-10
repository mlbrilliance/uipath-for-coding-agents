# GitHub Check-Run Webhook

FastAPI service that bridges GitHub `check_run.completed` events to UiPath
Maestro correlation messages.  Part of the AURORA swarm's Operate fleet.

## Quick start

```bash
# Install dependencies
pip install -e ".[test]"

# Set required environment variables
export GITHUB_WEBHOOK_SECRET="your-hmac-secret"
export UIPATH_URL="https://cloud.uipath.com/acct/tenant/orchestrator_"
export UIPATH_FOLDER="AURORA-Demo"
export UIPATH_ACCESS_TOKEN="your-uipath-token"

# Run the server
uvicorn app:app --reload --port 8000
```

## Endpoints

### `POST /github/check-run`

| Condition | Status |
|-----------|--------|
| Valid signature + `check_run.completed` | `200` |
| Valid event, no matching Maestro instance | `204` |
| Non-`completed` action or non-`check_run` event | `204` |
| Malformed JSON (valid signature) | `400` |
| Bad / missing `X-Hub-Signature-256` | `401` |
| Maestro API unreachable | `502` |

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GITHUB_WEBHOOK_SECRET` | ✓ | HMAC key shared with GitHub |
| `UIPATH_URL` | ✓ | Orchestrator base URL |
| `UIPATH_FOLDER` | ✓ | Folder ID for Maestro API |
| `UIPATH_ACCESS_TOKEN` | ✓ | Bearer token (minted by `aurora-auth`) |

## Running tests

```bash
pytest tests/ -v
```

## Docker

```bash
docker build -t aurora-github-webhook .
docker run -p 127.0.0.1:8000:8000 \
  -e GITHUB_WEBHOOK_SECRET=... \
  -e UIPATH_URL=... \
  -e UIPATH_FOLDER=... \
  -e UIPATH_ACCESS_TOKEN=... \
  aurora-github-webhook
```

## Deployment

See [docs/webhook-deploy.md](../../docs/webhook-deploy.md) for the full
Cloudflare Tunnel deployment guide, GitHub webhook configuration, and
secret rotation procedure.
