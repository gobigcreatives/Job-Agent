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

echo "==> Installing dependencies (first run only takes a minute or two)..."
pip install -e ".[dev]" --quiet

echo "==> Installing the browser used for filling in applications..."
playwright install chromium

if [ "${1:-}" = "--live" ]; then
  echo "==> Running for real — this will tailor CVs, generate cover letters, and apply to strong matches."
  jobagent run
else
  echo "==> Running in dry-run mode — finds and scores jobs, applies to nothing."
  jobagent run --dry-run
fi
