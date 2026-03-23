#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WEB_DIR="$ROOT_DIR/chatui-taiwild"

if [[ -f "$WEB_DIR/.env.local" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$WEB_DIR/.env.local"
  set +a
fi

cd "$WEB_DIR"
exec npm run dev
