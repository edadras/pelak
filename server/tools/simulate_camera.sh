#!/usr/bin/env bash
# Publish a video file as an RTSP camera for testing (needs docker):
#   ./tools/simulate_camera.sh ../lite/output/sample.mp4
# Then add a camera with vendor "RTSP" and URL rtsp://<server-ip>:8554/cam1
set -euo pipefail
VIDEO="$(realpath "$1")"
docker run -d --rm --name pelak-rtsp -p 8554:8554 bluenviron/mediamtx:latest >/dev/null
sleep 2
exec docker run --rm --network host -v "$VIDEO":/v.mp4:ro jrottenberg/ffmpeg:6.1-ubuntu \
  -re -stream_loop -1 -i /v.mp4 -c copy -f rtsp rtsp://127.0.0.1:8554/cam1
