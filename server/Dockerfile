# Build from the repository root:  docker build -f server/Dockerfile -t pelak-server .
# GPU build:  --build-arg TORCH_INDEX=https://download.pytorch.org/whl/cu121
# Registry mirror (e.g. inside Iran): --build-arg BASE_IMAGE=docker.arvancloud.ir/python:3.11-slim-bookworm
ARG BASE_IMAGE=python:3.11-slim-bookworm
FROM ${BASE_IMAGE}

ARG TORCH_INDEX=https://download.pytorch.org/whl/cpu
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    PLATE_REPO_DIR=/app VEHICLE_MODEL=/app/model/yolov8n.pt PYTHONPATH=/app/server \
    YOLO_CONFIG_DIR=/tmp/Ultralytics

RUN apt-get update && apt-get install -y --no-install-recommends \
      libgl1 libglib2.0-0 libgomp1 ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY server/requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip \
    && pip install torch==2.3.1 torchvision==0.18.1 --index-url ${TORCH_INDEX} \
    && pip install -r /tmp/requirements.txt

# Existing plate recognizer (models + yolov5 engine + helpers)
COPY configParams.py config.ini ./
COPY helper/ ./helper/
COPY yolov5/ ./yolov5/
COPY lite/__init__.py lite/reader.py lite/image_utils.py lite/plate_validation.py ./lite/
COPY model/ ./model/
# Platform
COPY server/ ./server/

# Fetch the vehicle detector if it is not in model/ and verify that all models load
RUN cd /app/model && python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')" \
    && cd /app/server && python -c "from app.vision.engines import Engines; e = Engines.get(); assert not e.errors, e.errors; print('models ok')"

WORKDIR /app/server
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s CMD curl -fs http://localhost:8080/health || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers"]
