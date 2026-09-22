#!/usr/bin/env bash
# Idempotent Cloud Agent setup for emg-compare (Streamlit app).
set -euo pipefail

# Resolve repo root (parent of this scripts/ directory) so the script works
# regardless of the checkout path.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

# Ensure the stdlib venv builder is available (Debian/Ubuntu split it out).
if ! python3 -c "import ensurepip" >/dev/null 2>&1; then
  echo "[setup] Installing python3-venv prerequisites..."
  sudo apt-get update -qq
  sudo apt-get install -y -qq python3-venv >/dev/null
fi

# Create the virtual environment once; reuse it on subsequent runs.
if [ ! -x ".venv/bin/python" ]; then
  echo "[setup] Creating virtual environment (.venv)..."
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
. .venv/bin/activate

echo "[setup] Upgrading pip..."
python -m pip install --upgrade pip --quiet

echo "[setup] Installing Python dependencies..."
python -m pip install -r requirements.txt --quiet

# Make sure the local data directories exist (app also does this at runtime).
python -c "from paths import ensure_data_dirs; ensure_data_dirs()"

echo "[setup] Done. Activate with: source .venv/bin/activate"
