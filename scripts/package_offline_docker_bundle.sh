#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE_NAME="${IMAGE_NAME:-manzufei-ocr:0.1.0}"
BUNDLE_NAME="${BUNDLE_NAME:-manzufei_ocr_offline_bundle}"
BUNDLE_DIR="${BUNDLE_DIR:-$ROOT_DIR/output/$BUNDLE_NAME}"
ARCHIVE_PATH="${ARCHIVE_PATH:-$ROOT_DIR/output/$BUNDLE_NAME.zip}"

cd "$ROOT_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker command not found"
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "Docker is not running"
  exit 1
fi

echo "Building frontend dist..."
(
  cd "$ROOT_DIR/app/frontend"
  npm run build
)

echo "Building Docker image: $IMAGE_NAME"
docker build -t "$IMAGE_NAME" "$ROOT_DIR"

echo "Creating offline bundle: $BUNDLE_DIR"
rm -rf "$BUNDLE_DIR"
mkdir -p "$BUNDLE_DIR/images" \
  "$BUNDLE_DIR/app/config" \
  "$BUNDLE_DIR/data" \
  "$BUNDLE_DIR/exports" \
  "$BUNDLE_DIR/logs"

docker save "$IMAGE_NAME" -o "$BUNDLE_DIR/images/manzufei-ocr.tar"
cp "$ROOT_DIR/docker-compose.yml" "$BUNDLE_DIR/docker-compose.yml"
cp "$ROOT_DIR/app/config/local.docker.yaml" "$BUNDLE_DIR/app/config/local.yaml"
cp "$ROOT_DIR/deploy/windows/00_import_image.bat" "$BUNDLE_DIR/00_import_image.bat"
cp "$ROOT_DIR/deploy/windows/01_start.bat" "$BUNDLE_DIR/01_start.bat"
cp "$ROOT_DIR/deploy/windows/02_stop.bat" "$BUNDLE_DIR/02_stop.bat"
cp "$ROOT_DIR/deploy/windows/03_logs.bat" "$BUNDLE_DIR/03_logs.bat"
cp "$ROOT_DIR/deploy/windows/README_DEPLOY.txt" "$BUNDLE_DIR/README_DEPLOY.txt"

if [ -d "$ROOT_DIR/models" ]; then
  echo "Copying models..."
  mkdir -p "$BUNDLE_DIR/models"
  tar \
    --exclude='README.md' \
    --exclude='.gitignore' \
    --exclude='*.tmp' \
    --exclude='*.log' \
    -C "$ROOT_DIR" -cf - models | tar -C "$BUNDLE_DIR" -xf -
else
  mkdir -p "$BUNDLE_DIR/models"
fi

echo "Bundle ready:"
echo "  $BUNDLE_DIR"

if command -v python3 >/dev/null 2>&1; then
  echo "Creating zip archive: $ARCHIVE_PATH"
  rm -f "$ARCHIVE_PATH"
  (
    cd "$(dirname "$BUNDLE_DIR")"
    python3 -m zipfile -c "$ARCHIVE_PATH" "$(basename "$BUNDLE_DIR")"
  )
  echo "Archive ready:"
  echo "  $ARCHIVE_PATH"
else
  echo "python3 not found; skipped zip archive creation"
fi

echo
echo "Copy this directory to the target Windows computer, then run:"
echo "  00_import_image.bat"
echo "  01_start.bat"
