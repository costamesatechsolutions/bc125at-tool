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

if [[ -z "${LIBUSB_PREFIX:-}" ]]; then
  if command -v brew >/dev/null 2>&1; then
    LIBUSB_PREFIX="$(brew --prefix libusb 2>/dev/null || brew --prefix)"
  else
    LIBUSB_PREFIX="${HOMEBREW_PREFIX:-/opt/homebrew}"
  fi
fi
export DYLD_LIBRARY_PATH="$LIBUSB_PREFIX/lib${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"

python -m bc125at.web.app
