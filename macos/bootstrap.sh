#!/bin/bash
# Prepare the runtime as the user. The signed/unsigned app bundle stays immutable.
set -euo pipefail
SOURCE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME_ROOT="${TESLARECOVER_RUNTIME_ROOT:-$HOME/Library/Application Support/TeslaRecover}"
mkdir -p "$RUNTIME_ROOT/tools"
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
UV="$(command -v uv || true)"
if [ -z "$UV" ] && [ -x "$RUNTIME_ROOT/tools/uv" ]; then UV="$RUNTIME_ROOT/tools/uv"; fi
if [ -z "$UV" ]; then
  echo 'Przygotowuję narzędzia do pierwszego uruchomienia…'
  curl --fail --location --silent --show-error https://astral.sh/uv/install.sh -o "$RUNTIME_ROOT/tools/install-uv.sh"
  UV_INSTALL_DIR="$RUNTIME_ROOT/tools" UV_NO_MODIFY_PATH=1 sh "$RUNTIME_ROOT/tools/install-uv.sh"
  UV="$RUNTIME_ROOT/tools/uv"
fi
export UV_PROJECT_ENVIRONMENT="$RUNTIME_ROOT/runtime"
echo 'Pobieram Python i składniki aplikacji. Pierwsze uruchomienie może potrwać kilka minut…'
"$UV" sync --locked --project "$SOURCE_DIR"
echo 'Uruchamiam aplikację…'
