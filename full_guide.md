---

## Quick checklist before you begin

1. You are running this locally (Kali Linux recommended for pentest tooling).
2. You have administrative/sudo rights on the machine to install packages.
3. You have explicit permission to scan / test any target networks you will test.
4. You will keep the web UI bound to `localhost` and not expose it publicly.

---

## 1) Create the virtualenv and install Python deps

From the repo root:

```bash
# make setup executable the first time if needed
chmod +x setup.sh

# default install: creates .venv and installs core Python deps
./setup.sh

# activate the virtualenv
source .venv/bin/activate
```

If you want optional heavy tooling installed (impacket, etc.):

```bash
./setup.sh --install-optional
source .venv/bin/activate
```

**Manual pip alternative**:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 2) (Optional) Install AD pentest tools you may want

The project orchestrates local tools but does **not** automatically install or run them for you (except the optional `--install-optional` hint in `setup.sh`).

Recommended tools (install separately after auditing each project):

* `impacket` — `pip install impacket` (or follow impacket docs)
* `crackmapexec` (CME) — follow CME install docs (pipx or distro packages)
* `ldapdomaindump`
* `enum4linux-ng`
* `bloodhound` / SharpHound collector (if you plan to collect BloodHound data)
* `nmap` — system package (Kali has it by default)

**Note:** these tools may require system libraries — read their docs before installing.

---

## 3) Run tests (verify basic functionality)

Run tests while virtualenv is active:

```bash
pytest
```

You should see tests for `JobStore` and `CommandRunner`. Tests validate that jobs can be created and small commands execute.

---

## 4) Run the local web UI (recommended flow)

Start the web UI (binds to all interfaces by default — treat this as local, don't expose publicly):

```bash
source .venv/bin/activate
python3 web_ui.py
```

Open a browser to:

```
http://localhost:5000
```

What the UI gives you:

* Start a discovery job (Nmap) by entering a job name and target network (example `10.10.0.0/24`).
* See a list of jobs and their status.
* Subscribe to a job to receive live streaming output (Socket.IO).
* View sessions (discovered credentials/hashes) that the orchestrator stored.

---

## 6) How the orchestrator works (high level)

1. You start a discovery job (Nmap, ping sweep).
2. The runner records all output to SQLite (table `outputs`) and to per-job log files.
3. After job completion, the orchestrator runs registered parsers (nmap XML parser, CME JSON parser, enum4linux heuristics, BloodHound zip detector, secretsdump and GetNPUsers heuristics, etc.).
4. Based on parser results, the orchestrator automatically schedules follow-up enumeration jobs (enum4linux, ldapdomaindump, CME scans, etc.).
5. If `auto_exploit` is **explicitly enabled** and a valid credential is found, it can schedule exploitation jobs (e.g., Impacket `psexec`). This is *opt-in only*.

---

## 7) Enabling / approving auto-exploit (safety)

Automatic exploitation is intentionally disabled by default. Two ways to enable behavior:

1. **Quick/temporary (unsafe)** — modify `web_ui.py` and set `orch.set_auto_exploit(True)` after the `orch` is instantiated (not recommended for unattended use).

2. **Recommended manual workflow**:

   * Keep auto-exploit disabled in the orchestrator.
   * Review `Sessions` in the web UI at `/` which lists discovered credentials / hashes.
   * If you want to test a discovered credential, manually run a targeted exploitation job from the CLI or edit the orchestrator to schedule a job for that specific credential:

     ```python
     # example manual scheduling (run inside a Python REPL with modules loaded)
     from ad_command_runner import JobStore
     from orchestrator_and_parsers import Orchestrator, SessionStore
     store = JobStore('./ad_runner.db')
     # get your existing runner and orchestrator objects if you run inside web_ui context
     # or create new runner and orchestrator objects here to schedule specific psexec job
     ```
---

## 8) Where results are stored & how to inspect

* SQLite DB: `./ad_runner.db` — the `jobs` and `outputs` tables contain all job metadata and per-line outputs. You can inspect with `sqlite3`:

  ```bash
  sqlite3 ad_runner.db
  sqlite> .tables
  sqlite> SELECT id, name, status, created_at, meta FROM jobs ORDER BY id DESC LIMIT 10;
  ```

* Per-job logs: `./logs/job_<id>.log` — plain text with `[stdout]/[stderr]` prefixes.

* `SessionStore` is in memory by default. You can extend it to persist sessions to DB by modifying `orchestrator_and_parsers.py`.

---

## 9) Troubleshooting tips

* `ImportError` on starting `web_ui.py`:

  * Ensure `.venv` is activated and `pip install -r requirements.txt` ran successfully.
  * Make sure `ad_command_runner.py` and `orchestrator_and_parsers.py` are in the same directory as `web_ui.py`.

* `nmap` command not found:

  * Install `nmap` at the system level: `sudo apt update && sudo apt install nmap`.

* Socket.IO clients can’t connect:

  * Ensure `python3 web_ui.py` is running. Check console logs for errors.
  * Confirm no firewall is blocking `localhost:5000`.

* Commands fail with `ERROR: command not found` in job outputs:

  * The orchestrator tries to run programs like `enum4linux-ng`, `crackmapexec`, etc. Install those tools or adjust the orchestrator job list to tools you have.

* Tests failing:

  * Run `pytest -q` to see detailed failure messages. Tests are intentionally minimal; if a failure refers to missing third-party tools, adjust the tests or install the tools manually.

---


## 14) Responsible use & takedown/disclaimer

This repo includes `DISCLAIMER.md` in the root with explicit responsible-use language. Keep that file present in the repo and follow these rules:

* Only run the software on systems you have written authorization to test.
* If asked by a hosting provider or legal authority to take content down, comply and provide them the information they request; the disclaimer helps explain the intended purpose but does not remove responsibility.

---

## Example workflows (short)

**Start quick discovery from UI**:

1. Run `python3 web_ui.py`.
2. Open `http://localhost:5000`.
3. Set Job name = `nmap-discovery`, Target = `10.10.0.0/24`.
4. Click Start Discovery.
5. Watch live events, review sessions.

**Start a one-off CLI job**:

```bash
source .venv/bin/activate
python3 ad_command_runner.py --name quick-enum --cmd "enum4linux-ng -a 10.10.10.5"
```

---

