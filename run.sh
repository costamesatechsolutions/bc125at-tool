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
HOMEBREW_PREFIX="${HOMEBREW_PREFIX:-$(brew --prefix 2>/dev/null || true)}"
if [[ -z "${HOMEBREW_PREFIX}" ]]; then
  HOMEBREW_PREFIX="/opt/homebrew"
fi
export DYLD_LIBRARY_PATH="$HOMEBREW_PREFIX/lib"

python -m bc125at.web.app
