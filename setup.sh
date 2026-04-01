#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-/opt/homebrew/bin/python3}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Homebrew Python was not found at $PYTHON_BIN."
  echo "Install it with: brew install python"
  exit 1
fi

if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew is required."
  echo "Install it from https://brew.sh/"
  exit 1
fi

if [[ ! -d .venv ]]; then
  echo "Creating virtual environment..."
  "$PYTHON_BIN" -m venv .venv
fi

source .venv/bin/activate

echo "Ensuring libusb is installed..."
brew list libusb >/dev/null 2>&1 || brew install libusb

echo "Installing Python dependencies..."
python -m pip install --upgrade pip
python -m pip install -e ".[gui]"

cat <<'EOF'

Setup complete.

Next time, start the web app with:
  ./run.sh

Or use the CLI with:
  source .venv/bin/activate
  export DYLD_LIBRARY_PATH=/opt/homebrew/lib
  python -m bc125at --help
EOF
