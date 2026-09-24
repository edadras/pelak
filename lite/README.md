# PLPR Lite

نسخه سبک تشخیص پلاک — **همان مدل و `recognize_plates()`**، بدون Streamlit / PySide6 / TensorFlow.

## اجرا

```powershell
cd lite
docker compose up -d --build plpr-lite
```

مرورگر: **http://localhost:8502**

## حالت‌ها

| حالت | دستور |
|------|--------|
| سرور (تصویر + ویدیو + دوربین از UI) | `docker compose up -d plpr-lite` |
| یک تصویر | فایل را در `lite/data/` بگذارید، سپس `docker compose --profile file run --rm plpr-lite-file` |
| ویدیو | `LITE_SOURCE=/data/video.mp4 docker compose --profile video run --rm plpr-lite-video` |
| RTSP | `docker compose --profile rtsp up -d plpr-lite-rtsp` |

## API

- `POST /api/recognize` — آپلود تصویر
- `POST /api/recognize/video` — آپلود ویدیو
- `POST /api/camera/start` — شروع دوربین (`source=0` یا RTSP)
- `GET /api/stream.mjpg` — استریم زنده
- `GET /health` — وضعیت سرویس

## کیفیت

- مدل‌ها: `plateYolo.pt` + `CharsYolo.pt` (mount از پوشه اصلی)
- Pipeline: `helper/plate_recognition.py` کامل
- برای CPU ضعیف: `LITE_FRAME_SKIP=5` (سرعت ↑، دقت هر فریم همان است)
- voting بین چند فریم برای ثبات نتیجه دوربین

## پوشه‌ها

- `data/` — فایل‌های ورودی
- `output/` — خروجی تصویر/ویدیو/JSON

## دوربین Windows

Docker روی Windows معمولاً به webcam USB دسترسی مستقیم ندارد. از **RTSP** دوربین IP یا آپلود **فایل/ویدیو** استفاده کنید.
