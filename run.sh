#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$ROOT_DIR/logs"
DATA_DIR="$ROOT_DIR/data"
EXPORT_DIR="$ROOT_DIR/exports"
FRONTEND_DIR="$ROOT_DIR/app/frontend"
FRONTEND_DIST_INDEX="$FRONTEND_DIR/dist/index.html"

BACKEND_PID_FILE="$LOG_DIR/backend.pid"
BACKEND_LOG="$LOG_DIR/backend.log"
FRONTEND_LOG="$LOG_DIR/frontend.log"
BACKEND_HEALTH_URL="http://127.0.0.1:8081/api/system/status"
WORKSTATION_URL="http://127.0.0.1:8081/"
CONDA_PYTHON="/home/kbzz1/miniconda3/envs/manzufei_ocr/bin/python"

mkdir -p "$LOG_DIR" "$DATA_DIR" "$EXPORT_DIR"

check_url() {
  curl --noproxy '*' --silent --fail --max-time 2 "$1" >/dev/null 2>&1
}

wait_for_url() {
  local url="$1"
  local label="$2"
  local max_wait="${3:-30}"
  local waited=0

  until check_url "$url"; do
    if [ "$waited" -ge "$max_wait" ]; then
      echo "$label startup timed out. Check logs in $LOG_DIR"
      return 1
    fi
    sleep 1
    waited=$((waited + 1))
  done
}

ensure_backend() {
  if [ -f "$BACKEND_PID_FILE" ]; then
    old_pid="$(cat "$BACKEND_PID_FILE" 2>/dev/null || true)"
    if [ -n "$old_pid" ] && kill -0 "$old_pid" >/dev/null 2>&1; then
      echo "Stopping existing backend before restart: $old_pid"
      kill "$old_pid" >/dev/null 2>&1 || true
      sleep 1
      if kill -0 "$old_pid" >/dev/null 2>&1; then
        kill -9 "$old_pid" >/dev/null 2>&1 || true
      fi
    else
      echo "Removing stale backend PID file: $BACKEND_PID_FILE"
    fi
    rm -f "$BACKEND_PID_FILE"
  fi

  for _ in $(seq 1 10); do
    if ! check_url "$BACKEND_HEALTH_URL"; then
      break
    fi
    sleep 1
  done

  if check_url "$BACKEND_HEALTH_URL"; then
    echo "Backend port is already in use without a valid PID file: http://127.0.0.1:8081"
    return 1
  fi

  echo "Starting backend..."
  if [ ! -x "$CONDA_PYTHON" ]; then
    echo "Conda python not found: $CONDA_PYTHON"
    return 1
  fi

  (
    cd "$ROOT_DIR"
    setsid -f "$CONDA_PYTHON" -m app.backend.main >>"$BACKEND_LOG" 2>&1
  )

  wait_for_url "$BACKEND_HEALTH_URL" "Backend" 30
  echo "Backend is ready: http://127.0.0.1:8081"
}

ensure_frontend_dist() {
  if [ ! -f "$FRONTEND_DIR/package.json" ]; then
    echo "Frontend package.json not found: $FRONTEND_DIR/package.json"
    return 1
  fi

  echo "Rebuilding frontend dist..."
  (
    cd "$FRONTEND_DIR"
    npm run build >>"$FRONTEND_LOG" 2>&1
  )

  if [ ! -f "$FRONTEND_DIST_INDEX" ]; then
    echo "Frontend build did not create: $FRONTEND_DIST_INDEX"
    return 1
  fi

  echo "Frontend dist is ready: $FRONTEND_DIST_INDEX"
}

ensure_frontend_dist
ensure_backend

cat <<EOF

Open this URL in your browser:
  $WORKSTATION_URL

Backend health:
  $BACKEND_HEALTH_URL

Stop services:
  ./stop.sh
EOF
