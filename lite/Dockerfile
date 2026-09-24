FROM python:3.11-slim-bookworm

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app \
    LITE_MODE=server \
    LITE_PORT=8502

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libgomp1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY lite/requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip && \
    pip install torch==2.2.1 torchvision==0.17.1 --index-url https://download.pytorch.org/whl/cpu && \
    pip install -r /tmp/requirements.txt

COPY configParams.py config.ini ./
COPY helper/ ./helper/
COPY yolov5/ ./yolov5/
COPY lite/ ./lite/

COPY model/ ./model/

RUN sed -i 's/\r$//' /app/lite/entrypoint.sh && chmod +x /app/lite/entrypoint.sh

RUN pip install "numpy==1.26.4" --force-reinstall && \
    PYTHONPATH=/app python -c "from lite.reader import PlateReader; PlateReader.get(); print('models ok')"

EXPOSE 8502

ENTRYPOINT ["/app/lite/entrypoint.sh"]
