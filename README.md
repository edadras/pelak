# Persian License Plate Recognition

> **سامانه کامل پایش تردد شهری** (دوربین‌های نامحدود، پلاک‌خوانی، نوع/رنگ/سرعت/بار خودرو، پارک حاشیه‌ای و دوبل،
> قوانین تردد مناطق شهر، داشبورد فارسی): راهنمای نصب در [server/README.md](server/README.md)
>
> ```bash
> cd server && cp .env.example .env && docker compose up -d --build   # http://<server>:8080
> ```

## نسخه سبک (Lite)

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
├── server/               # سامانه کامل پایش تردد شهری (API، workers، داشبورد)
├── lite/                 # API، UI، Docker
├── helper/               # منطق OCR (plate_recognition, text_decorators)
├── model/                # plateYolo.pt, CharsYolo.pt
├── yolov5/               # موتور YOLOv5
├── configParams.py
└── config.ini
```
