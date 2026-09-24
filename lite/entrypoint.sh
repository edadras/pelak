#!/bin/bash
set -e
cd /app
export PYTHONPATH=/app

MODE="${LITE_MODE:-server}"

case "${MODE}" in
  server|camera|webcam|rtsp)
    echo "PLPR Lite API: http://0.0.0.0:${LITE_PORT:-8502} (mode=${MODE})"
    exec python -m lite.main
    ;;
  file|video)
    exec python -m lite.cli
    ;;
  *)
    echo "Unknown LITE_MODE=${MODE}. Use server|file|video|camera|rtsp"
    exit 1
    ;;
esac
