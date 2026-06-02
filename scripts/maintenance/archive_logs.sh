#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STAMP="${1:-$(date +%Y-%m-%d_%H%M%S)}"
ARCHIVE_DIR="$ROOT_DIR/.local/archive/$STAMP/logs"
LOG_DIR="$ROOT_DIR/logs"

mkdir -p "$ARCHIVE_DIR"

move_if_exists() {
  local path="$1"
  if [ -e "$path" ]; then
    mv "$path" "$ARCHIVE_DIR/"
  fi
}

move_if_exists "$LOG_DIR/backend.log"
move_if_exists "$LOG_DIR/backend-events.jsonl"
move_if_exists "$LOG_DIR/access.log"
move_if_exists "$LOG_DIR/debug.log"
move_if_exists "$LOG_DIR/boot.log"
move_if_exists "$LOG_DIR/frontend.log"
move_if_exists "$LOG_DIR/backend.pid"
move_if_exists "$LOG_DIR/frontend.pid"
move_if_exists "$LOG_DIR/archive"

echo "Logs archived to $ARCHIVE_DIR"
