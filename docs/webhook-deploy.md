# Deploying the GitHub Check-Run Webhook via Cloudflare Tunnel

This guide covers exposing the AURORA GitHub check-run webhook to the public
internet using **Cloudflare Tunnel** (`cloudflared`), configuring the GitHub
organisation webhook, and rotating the HMAC secret.

## Architecture

```
GitHub ────HTTPS──── cloudflared ────localhost:8000──── FastAPI (app.py)
                    (tunnel)                            │
                                                        ▼
                                              UiPath Maestro API
                                            (correlation message)
```

The webhook runs behind `cloudflared` on a VPS or container.  No inbound
ports are opened — the tunnel initiates an outbound connection to
Cloudflare's edge.

## 1. Install cloudflared

```bash
# Debian / Ubuntu
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg
echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared $(lsb_release -cs) main" \
  | sudo tee /etc/apt/sources.list.d/cloudflared.list
sudo apt-get update && sudo apt-get install cloudflared

# macOS
brew install cloudflared
```

Authenticate (one-time):

```bash
cloudflared tunnel login
```

## 2. Create a tunnel

```bash
cloudflared tunnel create aurora-webhook
# Note the tunnel ID from the output
```

Write a config file at `~/.cloudflared/config.yml`:

```yaml
tunnel: <TUNNEL_ID>
credentials-file: ~/.cloudflared/<TUNNEL_ID>.json

ingress:
  - hostname: webhook.aurora-demo.org
    service: http://localhost:8000
  - service: http_status:404
```

Create a DNS CNAME pointing `webhook.aurora-demo.org` to `<TUNNEL_ID>.cfargotunnel.com`:

```bash
cloudflared tunnel route dns aurora-webhook webhook.aurora-demo.org
```

## 3. Run the webhook service

### Docker (recommended)

```bash
cd webhook/github-check-run
docker build -t aurora-github-webhook .

docker run -d \
  --name aurora-github-webhook \
  --restart unless-stopped \
  -p 127.0.0.1:8000:8000 \
  -e GITHUB_WEBHOOK_SECRET="$(pass github/webhook-secret)" \
  -e UIPATH_URL="https://cloud.uipath.com/acct/tenant/orchestrator_" \
  -e UIPATH_FOLDER="AURORA-Demo" \
  -e UIPATH_ACCESS_TOKEN="$(pass uipath/access-token)" \
  aurora-github-webhook
```

### Bare-metal

```bash
cd webhook/github-check-run
pip install -e .
GITHUB_WEBHOOK_SECRET=... UIPATH_URL=... uvicorn app:app --host 127.0.0.1 --port 8000
```

### Start the tunnel

```bash
cloudflared tunnel run aurora-webhook
```

## 4. Configure the GitHub organisation webhook

1. Navigate to **GitHub → Organisation → Settings → Webhooks → Add webhook**.
2. **Payload URL**: `https://webhook.aurora-demo.org/github/check-run`
3. **Content type**: `application/json`
4. **Secret**: the same value as `GITHUB_WEBHOOK_SECRET`.
5. **Which events**: select **Let me select individual events** → check
   **Check runs** only.
6. **Active**: ✓
7. Save.  GitHub sends a `ping` event — the webhook returns `204` (not a
   `check_run.completed` event, so it is ignored as expected).

## 5. Secret rotation

1. Generate a new secret: `openssl rand -hex 32`
2. Update `GITHUB_WEBHOOK_SECRET` in the running service (restart container
   or update `.env`).
3. Update the secret in the GitHub webhook settings.
4. GitHub re-sends the `ping` — confirm `204` in the Recent Deliveries tab.

**Rotation window**: both old and new secrets are valid during the overlap.
To minimise failures, update the service first, then GitHub.

## 6. Monitoring

| Signal | Where | Action |
|--------|-------|--------|
| `401` spike | GitHub webhook delivery log | Secret mismatch — rotate |
| `502` spike | webhook container logs | Maestro API down — check UiPath status |
| `204` with no Maestro instance | structlog `no_maestro_instance_for_pr` | PR not tracked — check Maestro process |
| Duplicate deliveries | structlog `duplicate_event` | Normal — GitHub retries on timeout |

## 7. Systemd unit (optional)

```ini
# /etc/systemd/system/aurora-webhook.service
[Unit]
Description=AURORA GitHub check-run webhook
After=network.target

[Service]
Type=simple
User=appuser
WorkingDirectory=/opt/aurora-webhook
ExecStart=/opt/aurora-webhook/.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=5
EnvironmentFile=/opt/aurora-webhook/.env

[Install]
WantedBy=multi-user.target
```
