#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$ROOT_DIR/logs"
DATA_DIR="$ROOT_DIR/data"
EXPORT_DIR="$ROOT_DIR/exports"
FRONTEND_DIR="$ROOT_DIR/app/frontend"
FRONTEND_DIST_INDEX="$FRONTEND_DIR/dist/index.html"
LOCAL_CONFIG="$ROOT_DIR/app/config/local.yaml"

BACKEND_PID_FILE="$LOG_DIR/backend.pid"
BACKEND_LOG="$LOG_DIR/backend.log"
FRONTEND_LOG="$LOG_DIR/frontend.log"
BACKEND_HEALTH_URL="http://127.0.0.1:8081/api/system/status"
WORKSTATION_URL="http://127.0.0.1:8081/"
OCR_VLM_HEALTH_URL="http://127.0.0.1:8082/v1/models"
OCR_VLM_MODEL_DIR="$ROOT_DIR/models/ppstructure/PaddleOCR-VL-1.6"
OCR_VLM_SERVER_TAR="$ROOT_DIR/deploy/offline-images/paddleocr-vlm-server.tar"
OCR_VLM_SERVER_SOURCE_IMAGE="ccr-2vdh3abv-pub.cnc.bj.baidubce.com/paddlepaddle/paddleocr-genai-vllm-server@sha256:1cee5e7e26e666bcd80d2a9741c450438bf507268cbfb14e0e0d33b8d5259621"
OCR_VLM_SERVER_LOCAL_TAG="paddleocr-vlm-server:verified-digest-1cee5e7e"
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

ensure_local_config() {
  cat >"$LOCAL_CONFIG" <<EOF
algorithms:
  enable_local_ocr: true
  local_ocr_vlm_server_url: "http://127.0.0.1:8082/v1"
  local_ocr_vlm_timeout_seconds: 240
  local_ocr_max_new_tokens: 1024
  local_ocr_max_pixels: 501760
  gpu_stage_queue_enabled: true
  enable_copd_extractor: true
  llm_model_path: "./models/llm/qwen2.5-7b-instruct-gguf/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf"
  llm_context_tokens: 8192
  llm_max_tokens: 4096
  llm_extraction_batch_size: 25
  llm_enable_verification: true
EOF
  echo "Local config uses OCR VLM server: $LOCAL_CONFIG"
}

ensure_ocr_vlm_server() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "docker command not found; OCR VLM server cannot start."
    return 1
  fi

  if [ ! -d "$OCR_VLM_MODEL_DIR" ] || [ ! -s "$OCR_VLM_MODEL_DIR/model.safetensors" ]; then
    echo "PaddleOCR-VL-1.6 model not found at $OCR_VLM_MODEL_DIR"
    echo "Place PaddleOCR-VL-1.6 under models/ppstructure before running ./run.sh."
    return 1
  fi

  # verified 镜像里的 paddlex 3.5.0 只注册了 PaddleOCR-VL-0.9B / PaddleOCR-VL-1.5-0.9B，
  # 尚未注册 1.6。1.5 与 1.6 共享同一 PaddleOCRVLForConditionalGeneration 架构，
  # 因此用 1.5 的 registry 名字加载 1.6 的模型权重，避开镜像版本与模型版本的耦合。
  export OCR_VLM_MODEL_NAME="PaddleOCR-VL-1.5-0.9B"
  export OCR_VLM_MODEL_DIR="/workspace/model/PaddleOCR-VL-1.6"

  if ! docker image inspect "$OCR_VLM_SERVER_LOCAL_TAG" >/dev/null 2>&1; then
    echo "Local OCR VLM image not found: $OCR_VLM_SERVER_LOCAL_TAG"
    if [ -f "$OCR_VLM_SERVER_TAR" ]; then
      echo "Loading VLM server image from tar: $OCR_VLM_SERVER_TAR"
      load_output="$(docker load -i "$OCR_VLM_SERVER_TAR" 2>&1)"
      echo "$load_output"
      loaded_image="$(printf '%s\n' "$load_output" | sed -n 's/^Loaded image: //p' | head -1)"
      if [ -z "$loaded_image" ]; then
        loaded_image="$(printf '%s\n' "$load_output" | sed -n 's/^Loaded image ID: //p' | head -1)"
      fi
      if [ -z "$loaded_image" ]; then
        echo "docker load did not report a loaded image. tar may be corrupt."
        return 1
      fi
      if [ "$loaded_image" != "$OCR_VLM_SERVER_LOCAL_TAG" ]; then
        docker tag "$loaded_image" "$OCR_VLM_SERVER_LOCAL_TAG"
      fi
    else
      echo "Pulling verified source image: $OCR_VLM_SERVER_SOURCE_IMAGE"
      docker pull "$OCR_VLM_SERVER_SOURCE_IMAGE"
      docker tag "$OCR_VLM_SERVER_SOURCE_IMAGE" "$OCR_VLM_SERVER_LOCAL_TAG"
    fi

    if ! docker image inspect "$OCR_VLM_SERVER_LOCAL_TAG" >/dev/null 2>&1; then
      echo "Failed to make OCR VLM image available: $OCR_VLM_SERVER_LOCAL_TAG"
      return 1
    fi
  fi

  echo "Starting OCR VLM server..."
  (
    cd "$ROOT_DIR"
    docker compose up -d paddleocr-vlm-server
  )

  wait_for_url "$OCR_VLM_HEALTH_URL" "OCR VLM server" 240
  echo "OCR VLM server is ready: $OCR_VLM_HEALTH_URL"
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
ensure_ocr_vlm_server
ensure_frontend_dist
ensure_backend

cat <<EOF

Open this URL in your browser:
  $WORKSTATION_URL

Backend health:
  $BACKEND_HEALTH_URL

OCR VLM server health:
  $OCR_VLM_HEALTH_URL

Stop services:
  ./stop.sh
EOF
