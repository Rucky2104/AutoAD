#!/usr/bin/env bash
set -euo pipefail


# AD Orchestrator - setup script
# Usage: sudo ./setup.sh --install-optional
# By default this sets up a Python virtualenv and installs required Python packages.


REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$REPO_ROOT/.venv"
REQ_FILE="$REPO_ROOT/requirements.txt"


INSTALL_OPTIONAL=false


for arg in "$@"; do
  case "$arg" in
    --install-optional) INSTALL_OPTIONAL=true ;;
    --help) echo "Usage: $0 [--install-optional]"; exit 0 ;;
  esac
done


echo "Setting up project in $REPO_ROOT"


if [ ! -f "$REQ_FILE" ]; then
  echo "requirements.txt not found. Aborting.";
  exit 1
fi


python3 -m venv "$VENV_DIR"
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"


pip install --upgrade pip
pip install -r "$REQ_FILE"


if [ "$INSTALL_OPTIONAL" = true ]; then
  echo "Installing optional heavy tooling (impacket, crackmapexec, bloodhound)"
  # These commands are optional and may require system-level dependencies; review before running.
  # Impacket (pip)
  pip install impacket || echo "impacket install failed; install manually"
  # CrackMapExec via pipx or distribution packages is recommended; we only give a hint here
  echo "If you want CrackMapExec, install from your package manager or its project repo."
fi


echo
echo "Setup complete. Activate the virtualenv with:"
echo " source $VENV_DIR/bin/activate"
echo "Run tests with: pytest"
