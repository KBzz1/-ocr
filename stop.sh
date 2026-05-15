#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$ROOT_DIR/logs"
BACKEND_PID_FILE="$LOG_DIR/backend.pid"
FRONTEND_PID_FILE="$LOG_DIR/frontend.pid"

stop_pid_file() {
  local pid_file="$1"
  local label="$2"

  if [ ! -f "$pid_file" ]; then
    echo "$label PID file does not exist: $pid_file"
    return 0
  fi

  local pid
  pid="$(tr -d '[:space:]' <"$pid_file")"
  if [ -z "$pid" ]; then
    echo "$label PID file is empty. Cleaning file."
    rm -f "$pid_file"
    return 0
  fi

  if ! kill -0 "$pid" >/dev/null 2>&1; then
    echo "$label process is not running. Cleaning stale PID file."
    rm -f "$pid_file"
    return 0
  fi

  echo "Stopping $label (PID: $pid)..."
  kill "$pid" >/dev/null 2>&1 || true

  local waited=0
  while kill -0 "$pid" >/dev/null 2>&1; do
    if [ "$waited" -ge 10 ]; then
      echo "$label did not stop after 10 seconds; forcing stop."
      kill -9 "$pid" >/dev/null 2>&1 || true
      break
    fi
    sleep 1
    waited=$((waited + 1))
  done

  rm -f "$pid_file"
  echo "$label stopped."
}

stop_pid_file "$FRONTEND_PID_FILE" "Frontend"
stop_pid_file "$BACKEND_PID_FILE" "Backend"
