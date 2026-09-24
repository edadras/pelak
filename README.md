# Persian License Plate Recognition (Lite)

نسخه سبک تشخیص پلاک ایرانی — API + UI برای تصویر، ویدیو و دوربین.

## اجرا

```powershell
cd lite
docker compose up -d --build plpr-lite
```

مرورگر: **http://localhost:8502**

راهنمای کامل: [lite/README.md](lite/README.md)

## ساختار پروژه

```
├── lite/                 # API، UI، Docker
├── helper/               # منطق OCR (plate_recognition, text_decorators)
├── model/                # plateYolo.pt, CharsYolo.pt
├── yolov5/               # موتور YOLOv5
├── configParams.py
└── config.ini
```
