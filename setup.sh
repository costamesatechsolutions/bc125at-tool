#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew is required."
  echo "Install it from https://brew.sh/"
  exit 1
fi

HOMEBREW_PREFIX="${HOMEBREW_PREFIX:-$(brew --prefix)}"
PYTHON_BIN="${PYTHON_BIN:-$HOMEBREW_PREFIX/bin/python3}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Homebrew Python was not found at $PYTHON_BIN."
  echo "Install it with: brew install python, or set PYTHON_BIN to your preferred Python 3 path."
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
  export DYLD_LIBRARY_PATH=$HOMEBREW_PREFIX/lib
  python -m bc125at --help
EOF
