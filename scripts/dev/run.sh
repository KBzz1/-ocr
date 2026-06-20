#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOG_DIR="$ROOT_DIR/logs"
DATA_DIR="$ROOT_DIR/data"
EXPORT_DIR="$ROOT_DIR/exports"
FRONTEND_DIR="$ROOT_DIR/app/frontend"
FRONTEND_DIST_INDEX="$FRONTEND_DIR/dist/index.html"
LOCAL_CONFIG="$ROOT_DIR/app/config/local.yaml"
VLLM_CACHE_DIR="$ROOT_DIR/vllm_cache"

BACKEND_PID_FILE="$LOG_DIR/backend.pid"
BACKEND_LOG="$LOG_DIR/backend.log"
FRONTEND_LOG="$LOG_DIR/frontend.log"
BACKEND_HEALTH_URL="http://127.0.0.1:8081/api/system/status"
WORKSTATION_URL="http://127.0.0.1:8081/"
QWEN_VLLM_HEALTH_URL="http://127.0.0.1:8082/v1/models"
QWEN_VLLM_MODEL_DIR="$ROOT_DIR/models/llm/Qwen3.5-4B-AWQ-4bit"
QWEN_VLLM_SERVER_TAR="$ROOT_DIR/deploy/offline-images/qwen-vllm-server.tar"
QWEN_VLLM_SERVER_LOCAL_TAG="qwen-vllm-openai:verified"
CONDA_PYTHON="/home/kbzz1/miniconda3/envs/manzufei_ocr/bin/python"

mkdir -p "$LOG_DIR" "$DATA_DIR" "$EXPORT_DIR" "$VLLM_CACHE_DIR"

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

ensure_local_config() {
  cat >"$LOCAL_CONFIG" <<EOF
algorithms:
  enable_local_ocr: true
  qwen_vllm_server_url: "http://127.0.0.1:8082/v1"
  qwen_vllm_model_name: "Qwen3.5-4B-AWQ-4bit"
  qwen_vllm_model_dir: "./models/llm/Qwen3.5-4B-AWQ-4bit"
  qwen_vllm_max_model_len: 16384
  qwen_vllm_gpu_memory_utilization: 0.85
  qwen_vllm_max_num_seqs: 1
  qwen_ocr_temperature: 0.0
  qwen_ocr_max_tokens: 4096
  qwen_ocr_timeout_seconds: 240
  qwen_extraction_temperature: 0.0
  qwen_extraction_max_tokens: 8192
  qwen_extraction_timeout_seconds: 360
  gpu_stage_queue_enabled: true
  enable_copd_extractor: true
EOF
  echo "Local config uses Qwen vLLM server: $LOCAL_CONFIG"
}

ensure_qwen_vllm_server() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "docker command not found; Qwen vLLM server cannot start."
    return 1
  fi

  if [ ! -d "$QWEN_VLLM_MODEL_DIR" ] || [ ! -s "$QWEN_VLLM_MODEL_DIR/config.json" ]; then
    echo "Qwen3.5-4B-AWQ-4bit model not found at $QWEN_VLLM_MODEL_DIR"
    echo "Place Qwen3.5-4B-AWQ-4bit under models/llm before running ./run.sh."
    return 1
  fi

  if ! docker image inspect "$QWEN_VLLM_SERVER_LOCAL_TAG" >/dev/null 2>&1; then
    echo "Local Qwen vLLM image not found: $QWEN_VLLM_SERVER_LOCAL_TAG"
    if [ -f "$QWEN_VLLM_SERVER_TAR" ]; then
      echo "Loading Qwen vLLM server image from tar: $QWEN_VLLM_SERVER_TAR"
      load_output="$(docker load -i "$QWEN_VLLM_SERVER_TAR" 2>&1)"
      echo "$load_output"
      loaded_image="$(printf '%s\n' "$load_output" | sed -n 's/^Loaded image: //p' | head -1)"
      if [ -z "$loaded_image" ]; then
        loaded_image="$(printf '%s\n' "$load_output" | sed -n 's/^Loaded image ID: //p' | head -1)"
      fi
      if [ -z "$loaded_image" ]; then
        echo "docker load did not report a loaded image. tar may be corrupt."
        return 1
      fi
      if [ "$loaded_image" != "$QWEN_VLLM_SERVER_LOCAL_TAG" ]; then
        docker tag "$loaded_image" "$QWEN_VLLM_SERVER_LOCAL_TAG"
      fi
    else
      echo "Offline Qwen vLLM tar not found: $QWEN_VLLM_SERVER_TAR"
      echo "Place the verified vllm/vllm-openai image tar under deploy/offline-images/."
      return 1
    fi

    if ! docker image inspect "$QWEN_VLLM_SERVER_LOCAL_TAG" >/dev/null 2>&1; then
      echo "Failed to make Qwen vLLM image available: $QWEN_VLLM_SERVER_LOCAL_TAG"
      return 1
    fi
  fi

  echo "Starting Qwen vLLM server..."
  (
    cd "$ROOT_DIR"
    docker compose up -d qwen-vision-vllm-server
  )

  wait_for_url "$QWEN_VLLM_HEALTH_URL" "Qwen vLLM server" 360
  echo "Qwen vLLM server is ready: $QWEN_VLLM_HEALTH_URL"
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

ensure_local_config
ensure_qwen_vllm_server
ensure_frontend_dist
ensure_backend

cat <<EOF

Open this URL in your browser:
  $WORKSTATION_URL

Backend health:
  $BACKEND_HEALTH_URL

Qwen vLLM server health:
  $QWEN_VLLM_HEALTH_URL

Stop services:
  ./stop.sh
EOF
