# AutoAD
The absolute worst project I've ever made.

# AD Orchestrator — Repository Scaffold


A local orchestration framework and web UI for automating Windows Active Directory
penetration testing workflows. This repo contains:


- `ad_command_runner.py` — async command runner and SQLite job store
- `orchestrator_and_parsers.py` — orchestration engine and many parsers
- `web_ui.py` — Flask + Socket.IO local web interface
- `setup.sh` — convenience script to create a venv and install Python deps
- `requirements.txt` — Python requirements
- `tests/` — pytest tests for core components




## IMPORTANT LEGAL NOTICE
You must have **explicit written permission** from the owner of any network, host,
or Active Directory environment you scan or test with this tool. Unauthorized
scanning or exploitation is illegal and unethical. See `DISCLAIMER.md` for full
language to include in README or project pages.


## Quick start (local, on Kali Linux)


1. Clone the repo locally.
2. `cd` into the repo directory.
3. Run the setup script to create and populate a virtualenv:


```bash
sudo ./setup.sh
source .venv/bin/activate
