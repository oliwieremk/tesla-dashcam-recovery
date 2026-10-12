#!/bin/bash
set -e
export PYTHONDONTWRITEBYTECODE=1
cd "$(dirname "$0")"
if ! /bin/bash macos/bootstrap.sh; then
  echo 'Nie udało się przygotować aplikacji. Sprawdź połączenie z internetem.'
  read -r -p 'Naciśnij Enter, aby zamknąć…'
  exit 1
fi
RUNTIME_ROOT="${TESLARECOVER_RUNTIME_ROOT:-$HOME/Library/Application Support/TeslaRecover}"
"$RUNTIME_ROOT/runtime/bin/python" mac_launch.py "$@"
