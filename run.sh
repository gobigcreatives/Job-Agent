#!/usr/bin/env bash
# One-shot setup + run for a fresh checkout of this project.
# Usage:
#   bash run.sh            # dry run — discovers and scores jobs, applies to nothing
#   bash run.sh --live     # full run — actually tailors CVs and applies
set -euo pipefail
cd "$(dirname "$0")"

# Macs ship an old built-in `python3` (often 3.9) that this project can't
# use. Look for a real 3.11+ interpreter under any common name rather than
# assuming plain `python3` is new enough.
PYTHON_BIN=""
for candidate in python3.13 python3.12 python3.11 python3; do
  if command -v "$candidate" &>/dev/null; then
    if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
      PYTHON_BIN="$candidate"
      break
    fi
  fi
done

if [ -z "$PYTHON_BIN" ]; then
  echo "Python 3.11+ is required but wasn't found (only an older python3 is installed)."
  echo "Install it from https://www.python.org/downloads/ (download the macOS installer,"
  echo "run it like any other app), then run this script again."
  exit 1
fi
echo "==> Using $($PYTHON_BIN --version) ($PYTHON_BIN)"

if [ ! -f .env ]; then
  echo "No .env file found in this folder. Copy your .env (with your API keys) here first."
  exit 1
fi
if [ ! -f config/profile.yaml ]; then
  echo "No config/profile.yaml found. Copy your profile.yaml, preferences.yaml, and resume.md into config/ first."
  exit 1
fi

# A private virtual environment inside this folder, rather than relying on
# a global `pip`/`playwright`/`jobagent` command being on PATH (which
# varies a lot between machines and is a common source of "command not
# found" errors, especially on Mac).
if [ -d .venv ] && ! .venv/bin/python -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
  echo "==> Removing an existing .venv that was built with too old a Python..."
  rm -rf .venv
fi

if [ ! -d .venv ]; then
  echo "==> Setting up a private Python environment in .venv (first run only)..."
  "$PYTHON_BIN" -m venv .venv
fi

PY=".venv/bin/python"

echo "==> Installing dependencies (first run only takes a minute or two)..."
"$PY" -m pip install --quiet --upgrade pip
"$PY" -m pip install --quiet -e ".[dev]"

echo "==> Installing the browser used for filling in applications..."
if ! "$PY" -m playwright install chromium; then
  echo "Warning: couldn't install the browser (needed for --live, not for a dry run). Continuing..."
fi

if [ "${1:-}" = "--live" ]; then
  echo "==> Running for real — this will tailor CVs, generate cover letters, and apply to strong matches."
  "$PY" -m jobagent.cli run
else
  echo "==> Running in dry-run mode — finds and scores jobs, applies to nothing."
  "$PY" -m jobagent.cli run --dry-run
fi
