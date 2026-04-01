#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

if [[ ! -d .venv ]]; then
  echo "No virtual environment found."
  echo "Run ./setup.sh first."
  exit 1
fi

source .venv/bin/activate
export DYLD_LIBRARY_PATH=/opt/homebrew/lib

python -m bc125at.web.app
