#!/usr/bin/env bash
# One-shot setup + run for a fresh checkout of this project.
# Usage:
#   bash run.sh            # dry run — discovers and scores jobs, applies to nothing
#   bash run.sh --live     # full run — actually tailors CVs and applies
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v python3 &>/dev/null; then
  echo "Python 3.11+ is required but wasn't found. Install it from https://www.python.org/downloads/ and re-run this script."
  exit 1
fi

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
if [ ! -d .venv ]; then
  echo "==> Setting up a private Python environment in .venv (first run only)..."
  python3 -m venv .venv
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
