# Windows runbook — capture Studio Web's Maestro publish HTTP request

**Goal:** capture one HTTP request shape so AURORA can publish Maestro processes
headlessly from the VPS. **Time required:** ~10 minutes of your time on a Windows
machine that has a browser and Python 3.11+.

You only need to do this **once**. After the capture, the VPS can replay the publish
call for any version bump of any Maestro project, programmatically.

---

## What you'll do

1. Install Python + Playwright + Chromium on Windows (one-time, ~3 min).
2. Download a single Python script from the repo.
3. Run it. A Chromium window opens.
4. Log in to UiPath normally.
5. Click Publish on any Maestro / Agentic Process project.
6. Send the resulting `publish_request.json` back to me.

---

## Step 0 — Python check

In a PowerShell window, run:

```powershell
py --version
```

Expected: `Python 3.11.x` or newer. If that fails or shows something older, install
Python from <https://www.python.org/downloads/windows/> (tick **"Add Python to PATH"**
during install).

---

## Step 1 — Install Playwright (one-time)

```powershell
py -m pip install --upgrade pip
py -m pip install playwright
py -m playwright install chromium
```

The last command downloads ~140 MB of browser binaries. It only runs once.

---

## Step 2 — Get the capture script

The script lives in the repo at `scripts/windows-capture-publish.py`. Easiest way to
get it onto Windows:

```powershell
# In PowerShell, in a directory where you want the capture output to land
# (e.g. C:\Users\<you>\Desktop\aurora-capture):
mkdir aurora-capture
cd aurora-capture
curl.exe -L -o capture-publish.py https://raw.githubusercontent.com/mlbrilliance/uipath-for-coding-agents/feature/aurora-final-mile/scripts/windows-capture-publish.py
```

(or just open <https://raw.githubusercontent.com/mlbrilliance/uipath-for-coding-agents/feature/aurora-final-mile/scripts/windows-capture-publish.py>
in your browser and Save As `capture-publish.py`.)

---

## Step 3 — Run the script

In the same PowerShell window, in the same directory:

```powershell
py capture-publish.py
```

You should see:

```
Launching Chromium…

======================================================================
  STUDIO WEB MAESTRO PUBLISH CAPTURE
======================================================================

Step 1.  A Chromium window just opened at cloud.uipath.com.
Step 2.  LOG IN to UiPath (your normal Auth0 / MFA flow).
Step 3.  Open Studio Web (top-right launcher → Studio Web).
Step 4.  Open ANY Maestro / Agentic Process project.
         If you have none, click 'Create new project' →
         'Agentic Process' and accept the defaults.
Step 5.  Click PUBLISH (top right of the Studio Web canvas).
Step 6.  Pick any folder when prompted (AURORA-Demo is ideal).

This script will wait up to 10 minutes for the
publish call to fire. As soon as it does, you'll see
    ✓ captured: POST /...  (followed by the URL)
and the script will close the browser + write the fixture.

Output will be written to: C:\Users\<you>\Desktop\aurora-capture\publish_request.json
======================================================================
```

A Chromium window opens. Don't close it.

---

## Step 4 — Drive the browser

1. **Log in** to UiPath normally (email + password, MFA if you have it). Cloudflare
   may show a "Verify you are human" challenge — just complete it.
2. After login, you land on `cloud.uipath.com`. Click the **app launcher**
   (9-dot grid in the top right) → **Studio Web**.
3. If you already have a Maestro / Agentic Process project, **open it** and skip to
   the next bullet. If you don't:
   - Click **+ New** (or **Create a project** on the welcome screen).
   - Pick **Agentic Process** as the project type.
   - Name it anything (e.g. `aurora-capture-helloworld`).
   - Accept the defaults; you don't need to design anything.
4. With the project open, click **Publish** (top right). Pick **AURORA-Demo** as
   the target folder when prompted.
5. The PowerShell window should print:
   ```
     ✓ captured: POST /<account>/studio_/api/.../publish
   ✓ Wrote C:\Users\<you>\Desktop\aurora-capture\publish_request.json
   ```
   …and the Chromium window closes automatically.

---

## Step 5 — Send the fixture back

Open `publish_request.json` in Notepad (right-click → Open with → Notepad).

It looks like:

```json
{
  "synthetic": false,
  "note": "Captured via scripts/windows-capture-publish.py ...",
  "method": "POST",
  "url_path": "/webfiji/studio_/api/v1/projects/.../publish",
  "url_query": "",
  "headers": {
    "Authorization": "Bearer {{UIPATH_ACCESS_TOKEN}}",
    "X-UIPATH-OrganizationUnitId": "{{folder_id}}",
    "Content-Type": "application/json",
    ...
  },
  "body": {
    "version": "...",
    "projectKey": "...",
    ...
  }
}
```

**Copy the entire JSON text** (Ctrl+A, Ctrl+C in Notepad). **Paste it back to me in
chat** inside triple-backticks:

````
```json
{
  "synthetic": false,
  ... paste full contents ...
}
```
````

I'll then:

1. Save it as `tests/fixtures/maestro/publish_request.json`, replacing the synthetic stub.
2. Run `aurora.uipath_client.publish_maestro_project()` on the VPS — this replays the
   captured shape against the live tenant with the real bearer token + folder id
   substituted at runtime.
3. Verify the AURORA `OssSupplyChainDefender` Maestro process appears in the
   `AURORA-Demo` folder's Processes list.

---

## Troubleshooting

**"No publish request seen within 10 minutes."**
The URL pattern may have changed. Look at the Chromium window's DevTools (F12) →
Network tab → click Publish, find the actual POST that fires, and send me the URL.
I'll update `PUBLISH_URL_PATTERN` in the script and we'll retry.

**"py is not recognized as a command."**
Python isn't on your PATH. Try `python` instead of `py`. If that also fails, reinstall
Python from python.org with the "Add to PATH" box checked.

**The Chromium window is showing "Cloudflare wants to verify you're human" forever.**
You may be behind a corporate proxy that blocks the Cloudflare challenge. Try a
different network (mobile hotspot, home wifi) or run the capture from a personal
laptop instead of work.

**You don't see Studio Web in the app launcher.**
Your UiPath account needs a Studio Web license. Either ask your admin to assign one,
or use the trial: <https://www.uipath.com/product/studio-web>.

**You created a Maestro project but Publish is greyed out.**
The project needs at least one task in the BPMN canvas. Drag any task block onto the
canvas, then Publish.

---

## What we'll do once the fixture is captured

I take ~30 minutes to:

1. Replace `tests/fixtures/maestro/publish_request.json` with the captured content.
2. Run `MaestroService.publish_maestro_project(project_dir=Path("examples/oss-supply-chain-defender"), version_bump="patch")` against the live tenant.
3. Verify the process appears in `AURORA-Demo` → Processes via the OData API.
4. Optionally start a Maestro instance from the UI and watch it run through the High path → real PR on `mlbrilliance/aurora-demo-lockfile`.

That closes the last big "live evidence" gap.
