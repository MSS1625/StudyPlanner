# مستند فنی پروژه — بخش ۵: راهنمای استقرارِ واقعی (Production Deployment)

**پروژه: برنامه‌ریز هوشمند مطالعه (Smart Study Planner)**

> این بخش با چهار بخشِ قبلی فرق دارد: آن‌ها «کدِ موجود» را توضیح می‌دادند؛ این بخش یک **راهنمای عملیِ گام‌به‌گام** است برای این‌که همان کد، بدونِ تغییر، رویِ یک سرورِ واقعیِ لینوکس (Ubuntu 22.04/24.04) با Nginx و گواهیِ TLSِ رایگانِ Let's Encrypt منتشر شود. هر فرمانی که اینجا می‌بینید رویِ محیطِ شبیه‌سازی شده است؛ متغیرهایِ محیطی که معرفی می‌کند از Taskِ 2026-09-10 در `backend/backend/settings.py` معنا می‌گیرند.

**قاعده‌ی طلایی:** کدِ پروژه بینِ توسعه و Production **هیچ فرقی نمی‌کند** — همه‌ی تفاوت‌ها از متغیرهایِ محیطی می‌آیند. اگر جایی مجبور شدید برایِ استقرار فایلِ کد را عوض کنید، چیزی اشتباه است.

---

## فهرست بخش‌های این مستند

| بخش | موضوع |
|---|---|
| ۵.۱ | معماریِ هدف (چه چیزی کجا اجرا می‌شود) |
| ۵.۲ | آماده‌سازیِ سرور (پایتون، پکیج‌های سیستمی، کاربرِ غیر root) |
| ۵.۳ | نصبِ پروژه و وابستگی‌ها (فقط یک‌بار) |
| ۵.۴ | PostgreSQL و انتقالِ داده‌ی SQLite |
| ۵.۵ | فایلِ متغیرهایِ محیطی `.env` (جدولِ کاملِ همه‌ی متغیرها) |
| ۵.۶ | گنیکورن و سرویسِ systemd (اجرایِ همیشگی) |
| ۵.۷ | Nginx به‌عنوانِ دروازه (استاتیک + پروکسی + هدرِ IP واقعی) |
| ۵.۸ | TLS با Certbot (فعال‌کردنِ هدرهایِ امنیتیِ شرطی) |
| ۵.۹ | پایشِ سلامت (`/api/health/`) و محدودسازیِ نرخ (رفتارِ دقیق) |
| ۵.۱۰ | فهرستِ نهاییِ بررسیِ پیش از انتشار (Checklist) |
| ۵.۱۱ | یادداشتِ امنیتیِ حساب (تغییرِ رمز و ابطالِ نشست‌ها) |
| ۵.۱۲ | ایمیلِ بازیابیِ رمز — SMTP |

---

## ۵.۱ معماریِ هدف (چه چیزی کجا اجرا می‌شود)

در توسعه، همه‌چیز داخلِ یک `runserver` است. در Production، همان منطقِ پشتِ سه لایه می‌نشیند که هرکدام فقط یک کار دارند:

```
مرورگر (SPA خام — static/*.html)
   │  https (TLS) — پورتِ 443
   ▼
Nginx  ── ۱) فایل‌هایِ استاتیک را مستقیم از دیسک می‌دهد (static/)
      ── ۲) بقیه‌ی مسیرها را با proxy_pass به گنیکورن می‌فرستد
      ── ۳) TLS را خاتمه می‌دهد و IP واقعی/پروتکل را با هدر اعلام می‌کند
   │  http — پورتِ 8000 فقط رویِ localhost
   ▼
گنیکورن (WSGI) — فرایندهایِ پایتونِ جنگو
   │
   ▼
PostgreSQL (یا SQLite برایِ شروع) — داده‌ها
```

چرا این سه لایه؟ سه دلیلِ عملی: (۱) `runserver` هرگز برایِ Production طراحی نشده — تک‌نخی و بدونِ پایداریِ فرایند است؛ (۲) با `DEBUG=false` جنگو دیگر فایلِ استاتیک سرو نمی‌کند، پس کسی باید این کار را بکند — Nginx برایش ساخته شده؛ (۳) TLS باید پیش از رسیدنِ ترافیک بهِ پایتون خاتمه یابد تا هدرهایِ امنیتیِ شرطیِ پروژه (`SECURE_SSL_REDIRECT` و HSTS و ...) که از 2026-09-10 موجودند، معنا پیدا کنند.

نکته‌ی صادقانه درباره‌ی **کشِ شمارنده‌هایِ محدودسازیِ نرخ**: پیش‌فرضِ جنگو LocMemCache است — هر فرایندِ گنیکورن شمارنده‌ی *جدا* دارد؛ یعنی با `-w 2` سقفِ واقعی = دو برابرِ نرخِ تنظیم‌شده (هر worker سقفِ خودش را دارد). برایِ این پروژه (کاربرانِ محدود، تک‌سرور) قابل‌قبول است و در بخشِ ۵.۹ دقیق حساب شده؛ روزی که shared-cache خواستید، `django-redis` + `DJANGO_...` اضافه کنید — ولی آن روز باید اول به `TODO.md` ثبت شود (قانونِ مستندسازیِ پروژه).

---

## ۵.۲ آماده‌سازیِ سرور (پایتون، پکیج‌های سیستمی، کاربرِ غیر root)

رویِ سرور (Ubuntu؛ برایِ Debian مشابه است):

```bash
# ۱) به‌روزرسانی و ابزارهای پایه
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-venv python3-pip git nginx

# ۲) (فقط اگر PostgreSQL رویِ همین سرور است)
sudo apt install -y postgresql postgresql-contrib

# ۳) کاربرِ اختصاصیِ سرویس — کد نباید با root اجرا شود
sudo adduser --disabled-password --gecos '' planner
sudo mkdir -p /opt/studyplanner && sudo chown planner:planner /opt/studyplanner
```

پورت‌هایِ 80 و 443 باید از فایروال باز باشند (`sudo ufw allow 'Nginx Full'` اگر ufw فعال است).

نسخه‌ی پایتونِ لازم: هر نسخه‌ای که `requirements.txt` پشتیبانی کند (`Python <3.13`؛ رویِ Ubuntu 24.04 پایتونِ پیش‌فرض 3.12 مناسب است).

---

## ۵.۳ نصبِ پروژه و وابستگی‌ها (فقط یک‌بار)

```bash
sudo -u planner -H bash -c '
  cd /opt/studyplanner
  git clone https://github.com/MSS1625/StudyPlanner.git .
  cd backend
  python3 -m venv venv
  venv/bin/pip install -r requirements.txt
'
```

دو وابستگیِ **فقطِ سرورِ Production** (در `requirements.txt` نیستند چون بهِ توسعه/تستِ ویندوزِ محلی ربطی ندارند):

```bash
sudo -u planner -H /opt/studyplanner/backend/venv/bin/pip install gunicorn
```

`gunicorn` یک WSGI-HTTP-серورِ خالصِ پایتون است — هیچ فایلِ کدِ پروژه‌ای را تغییر نمی‌دهد و رابطِش فقط `backend/backend/wsgi.py` است (که از روزِ اول در ریپو هست).

---

## ۵.۴ PostgreSQL و انتقالِ داده‌ی SQLite

می‌توانید اول با SQLite منتشر کنید و بعد مهاجرت کنید — ولی برایِ چندکاربره‌ی واقعی، PostgreSQL از همان روزِ اول منطقی‌تر است (قفلِ `select_for_update` از 2026-09-09 فقط در PostgreSQL واقعاً قفلِ سطری می‌گیرد).

```bash
# ۱) دیتابیس و کاربرِ اختصاصی (رمز را عوض کنید)
sudo -u postgres psql -c "CREATE USER planner_app WITH PASSWORD 'REPLACE-ME-STRONG';"
sudo -u postgres psql -c "CREATE DATABASE planner OWNER planner_app;"

# ۲) اعمالِ اسکیما
sudo -u planner -H bash -c '
  cd /opt/studyplanner/backend
  DATABASE_URL="postgres://planner_app:REPLACE-ME-STRONG@127.0.0.1:5432/planner" \
    venv/bin/python manage.py migrate
'

# ۳) (اختیاری) انتقالِ داده‌ی SQLiteِ محلی — رویِ ماشینِ خودتان:
python manage.py dumpdata auth.user planner --natural-foreign --natural-primary --indent 2 -o backup.json
#   و رویِ سرور (با DATABASE_URL ست‌شده):
venv/bin/python manage.py loaddata backup.json
```

همان URL در فایلِ `.env` بخشِ ۵.۵ می‌نشیند — این‌جا فقط برایِ migrate یک‌بار ست شد.

---

## ۵.۵ فایلِ متغیرهایِ محیطی `.env` (جدولِ کاملِ همه‌ی متغیرها)

تنها مکانیزمِ تفاوتِ محیط‌ها. همه‌ی این‌ها در `backend/backend/settings.py` خوانده می‌شوند؛ **ست‌نشدنِ هر متغیر = پیش‌فرضِ توسعه** (الگویِ dev-safe — رگرسیون‌تستش: `test_boot_dev_defaults_unchanged`). مقدارهایِ بولیِ مثبت: `1`/`true`/`yes`/`on`.

| متغیر | پیش‌فرض (توسعه) | مقدارِ پیشنهادیِ Production | یادداشت |
|---|---|---|---|
| `DJANGO_SECRET_KEY` | کلیدِ توسعه‌ی موجود در فایل | خروجیِ `get_random_secret_key()` | **اجباری** — سپرِ بوت با DEBUG=false کلیدِ توسعه را رد می‌کند |
| `DJANGO_DEBUG` | `true` | `false` | **اجباری** |
| `DJANGO_ALLOWED_HOSTS` | خالی | `your-domain.com,www.your-domain.com` | **اجباری** — خالی با DEBUG=false بوت متوقف می‌شود |
| `DATABASE_URL` | خالی (SQLite) | `postgres://planner_app:PASS@127.0.0.1:5432/planner` | از 2026-09-09 |
| `DJANGO_CORS_ALLOW_ALL` | `true` | `false` | با دامنه‌ی واحد و Nginx، CORS اصلاً رخ نمی‌دهد ولی `false` ایمن‌تر است |
| `DJANGO_ALLOWED_ORIGINS` | خالی | `https://your-domain.com` | فقط وقتی CORS محدود شد لازم می‌شود |
| `DJANGO_ANON_THROTTLE_RATE` | `10000/min` | `120/min` | نرخِ درخواست‌هایِ بی‌احراز، به‌ازایِ IP (از 2026-09-10) |
| `DJANGO_USER_THROTTLE_RATE` | `10000/min` | `600/min` | نرخِ کاربرِ لاگین‌شده، به‌ازایِ کاربر (از 2026-09-10) |
| `DJANGO_AUTH_THROTTLE_RATE` | `10000/min` | `20/min` | سخت‌گیرانه‌ترین — رویِ register/login (دفاعِ brute-force؛ از 2026-09-10) |
| `DJANGO_SECURE_SSL_REDIRECT` | `false` | `1` | ریدایرکتِ http→https — **فقط بعد از فعال‌شدنِ TLS** (بخشِ ۵.۸) |
| `DJANGO_COOKIES_SECURE` | `false` | `1` | فلگِ Secure رویِ کوکی‌هایِ Session/CSRF |
| `DJANGO_HSTS_SECONDS` | `0` (خاموش) | `31536000` (یک سال) | «فقط https تا یک سال» — **فقط بعد از TLS مطمئن** (قابلِ لغویِ فوری نیست) |
| `DJANGO_PROXY_SSL_HEADER` | خالی | `HTTP_X_FORWARDED_PROTO,https` | جنگو از این هدر می‌فهمد ترافیک https بوده — با `proxy_set_header` بخشِ ۵.۷ جفت می‌شود |
| `DJANGO_EMAIL_BACKEND` | `...console.EmailBackend` | `...smtp.EmailBackend` | موتورِ ایمیلِ بازیابیِ رمز؛ پیش‌فرضِ console = ایمیل در stdout (بدونِ SMTP) — در Production حتماً SMTP (از 2026-09-12) |
| `DJANGO_EMAIL_HOST` | خالی | `smtp.example.com` | سرورِ SMTP (از 2026-09-12) |
| `DJANGO_EMAIL_PORT` | `587` | `587` یا `465` | 465 = TLSِ ضمنِ اتصال (`USE_TLS=false` بگذارید) (از 2026-09-12) |
| `DJANGO_EMAIL_HOST_USER` | خالی | `no-reply@example.com` | کاربرِ SMTP (از 2026-09-12) |
| `DJANGO_EMAIL_HOST_PASSWORD` | خالی | رمزِ SMTP | در `.env` با `chmod 600` (از 2026-09-12) |
| `DJANGO_EMAIL_USE_TLS` | `true` | `true` (587) / `false` (465) | STARTTLS (از 2026-09-12) |
| `DJANGO_DEFAULT_FROM_EMAIL` | `webmaster@localhost` | `no-reply@your-domain.com` | فرستنده‌ی ایمیلهایِ سیستمی — با حسابِ SMTP هم‌خوان باشد (از 2026-09-12) |
| `DJANGO_PASSWORD_RESET_TIMEOUT` | `3600` (یک ساعت) | `3600` | عمرِ لینکِ بازیابی به ثانیه؛ غیرمثبت = بوت متوقف (از 2026-09-12) |
| `DJANGO_FRONTEND_BASE_URL` | `http://127.0.0.1:8000` | `https://your-domain.com` | مبدأِ لینکِ داخلِ ایمیلِ بازیابی — در Production آدرسِ عمومی (از 2026-09-12) |

فرمتِ نرخ‌ها دقیقاً `<عدد>/<sec|min|hour|day>` مثلِ `20/min` است؛ مقدارِ خراب = بوت با پیامِ راهنما متوقف می‌شود (fail-fast — تستش `test_boot_invalid_throttle_rate_refuses_to_boot`).

فایلِ `.env` را **بیرونِ ریپوی git** نگه دارید (چون رمزها در آن است):

```bash
sudo -u planner -H tee /opt/studyplanner/backend/.env > /dev/null <<'EOF'
DJANGO_SECRET_KEY=django-insecure-REPLACE-WITH-REAL-KEY
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=your-domain.com,www.your-domain.com
DATABASE_URL=postgres://planner_app:REPLACE-ME-STRONG@127.0.0.1:5432/planner
DJANGO_ANON_THROTTLE_RATE=120/min
DJANGO_USER_THROTTLE_RATE=600/min
DJANGO_AUTH_THROTTLE_RATE=20/min
EOF
sudo chmod 600 /opt/studyplanner/backend/.env && sudo chown planner:planner /opt/studyplanner/backend/.env
```

سه متغیرِ TLS (`DJANGO_SECURE_SSL_REDIRECT`/`DJANGO_COOKIES_SECURE`/`DJANGO_HSTS_SECONDS`/`DJANGO_PROXY_SSL_HEADER`) را **فعلاً در فایل نگذارید** — بعد از بخشِ ۵.۸ اضافه می‌شوند. اگر قبل از TLS فعالشان کنید، همه‌ی کاربرانِ http قفل می‌شوند (این عمدی است؛ فعال‌کردنش بدونِ TLS واقعی اشتباهِ پیکربندی است نه باگ).

نکته: این پروژه **کتابخانه‌ی `python-dotenv` ندارد** — فایلِ `.env` خودش خوانده نمی‌شود؛ در بخشِ ۵.۶ سرویسِ systemd آن را با `EnvironmentFile` داخلِ محیطِ فرایند تزریق می‌کند. هیچ وابستگیِ جدیدی لازم نیست.

---

## ۵.۶ گنیکورن و سرویسِ systemd (اجرایِ همیشگی)

فایلِ `sudo tee /etc/systemd/system/studyplanner.service`:

```ini
[Unit]
Description=Study Planner (Django/gunicorn)
After=network.target postgresql.service

[Service]
User=planner
Group=planner
WorkingDirectory=/opt/studyplanner/backend
EnvironmentFile=/opt/studyplanner/backend/.env
ExecStart=/opt/studyplanner/backend/venv/bin/gunicorn backend.wsgi:application \
    --bind 127.0.0.1:8000 \
    --workers 2 \
    --threads 4 \
    --timeout 60 \
    --access-logfile - --error-logfile -
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

توضیحِ انتخاب‌ها: `--workers 2 --threads 4` = دو فرایندِ پایتون با چهار نخِ هرکدام؛ برایِ این اپ (APIهایِ سبک + SQLite/PG محلی) کاملاً کافی است و از حد نصابِ شلوغی فاصله دارد. نکته‌ی صادقانه: با دو worker، سقفِ واقعیِ هر throttle = ۲×نرخ (کشِ LocMem هر فرایند جدا است — بخشِ ۵.۹). اگر روزی workerها را زیاد کردید، نرخ‌ها را به‌ همان نسبت تنظیم کنید یا به shared-cache مهاجرت کنید (اول ثبت در `TODO.md`).

`WorkingDirectory` عمداً `backend/` است چون همه‌ی مسیرهایِ پروژه (`BASE_DIR` و دو سطحِ `backend/backend/`) از آن‌جا معتبرند — همان چیزی که `manage.py` هم فرض می‌کند.

فعال‌سازی:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now studyplanner
systemctl status studyplanner --no-pager     # باید active (running) باشد
curl -s http://127.0.0.1:8000/api/health/    # {"status": "ok", ...} — اولین کارِ درستِ هر استقرار
```

آخرین فرمانِ بالا مهم‌ترین بُرشِ این بخش است: endpointِ سلامتِ `GET /api/health/` (از 2026-09-10) عمداً بدونِ لاگین و بدونِ throttle در دسترس است؛ اولین چیزی که باید بعدِ هر ری‌استارت چک کنید همین است. اگر `"database": "error"` دیدید، `DATABASE_URL` را در `.env` بررسی کنید.

---

## ۵.۷ Nginx به‌عنوانِ دروازه (استاتیک + پروکسی + هدرِ IP واقعی)

فایلِ `sudo tee /etc/nginx/sites-available/studyplanner`:

```nginx
server {
    listen 80;
    server_name your-domain.com www.your-domain.com;

    # ۱) فایل‌هایِ رابطِ کاربری — مستقیم از دیسک (جنگو با DEBUG=false سروشان نمی‌کند)
    location /static/ {
        alias /opt/studyplanner/static/;
        expires 7d;
        add_header Cache-Control "public";
    }

    # ۲) بقیه‌ی مسیرها — به گنیکورن
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        # ⚠ مهم: «بازنویسی» نه الحاق — $remote_addr چیزی است که Nginx خودش دیده،
        # نه چیزی که کلاینت ادعا کرده. الحاق ($proxy_add_x_forwarded_for)
        # اجازه‌ی جعلِ IP (و دورزدنِ throttle) به کلاینت می‌دهد.
        proxy_set_header X-Forwarded-For $remote_addr;
        # این هدر جفتِ DJANGO_PROXY_SSL_HEADER در .env است — بخشِ ۵.۸
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

فعال‌سازی:

```bash
sudo ln -s /etc/nginx/sites-available/studyplanner /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

از این لحظه `http://your-domain.com/static/login.html` از دیسک می‌آید و `http://your-domain.com/api/...` به گنیکورن می‌رسد. **فعلاً همه‌چیز رویِ http است** — هدرهایِ امنیتیِ شرطی هنوز در `.env` نیستند و این درست است.

چرا `X-Forwarded-For $remote_addr` (بازنویسی) و نه `$proxy_add_x_forwarded_for` (الحاق)؟ DRF در حالتِ پیش‌فرض اولینِ مقدِ XFF را به‌عنوانِ هویتِ IP می‌گیرد (`SimpleRateThrottle.get_ident`). اگر Nginx مقدارِ کلاینت را «الحاق» کند، یک مهاجم می‌تواند خودش هدرِ `X-Forwarded-For: 1.2.3.4` بفرستد و Nginx آن را نگه می‌دارد — نتیجه: هر درخواست IPِ «متفاوتی» به نظر می‌رسد و محدودسازیِ نرخِ per-IP بی‌اثر می‌شود. با بازنویسی، IPِ شمارش‌شده همیشه چیزی است که TCP از آن آمده. برایِ همین، همین‌طور که در بخشِ ۵.۹ آمده، «اعتمادِ XFF» فقط تا یک پروکسیِ معتبر معنی دارد.

---

## ۵.۸ TLS با Certbot (فعال‌کردنِ هدرهایِ امنیتیِ شرطی)

گواهیِ رایگانِ Let's Encrypt + خودکارِ تمدید:

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com -d www.your-domain.com
# Certbot خودش بلوکِ 443 + ریدایرکتِ 80 را به nginx اضافه می‌کند
sudo nginx -t && sudo systemctl reload nginx
curl -I https://your-domain.com/api/health/    # HTTP/2 200 ... SSL-protocol OK
```

حالا که TLS واقعی روشن است، سه متغیرِ امنیتیِ شرطی را به `.env` اضافه کنید (همان‌هایی که در ۵.۵ عمداً نگه داشتیم):

```bash
sudo -u planner -H tee -a /opt/studyplanner/backend/.env > /dev/null <<'EOF'
DJANGO_SECURE_SSL_REDIRECT=1
DJANGO_COOKIES_SECURE=1
DJANGO_PROXY_SSL_HEADER=HTTP_X_FORWARDED_PROTO,https
EOF
# HSTS را مرحله‌ی آخر اضافه کنید (قابلِ لغویِ فوری نیست — اول مطمئن شوید
# همه‌ی مسیرها (ازجمله admin) رویِ https کار می‌کنند، بعد):
# DJANGO_HSTS_SECONDS=31536000
sudo systemctl restart studyplanner
```

راستی‌آزماییِ عملی از بیرون:

```bash
# ۱) ریدایرکت: http باید 301 به https بزند
curl -sI http://your-domain.com/api/health/ | grep -E 'HTTP|Location'
#    HTTP/1.1 301 Moved Permanently
#    Location: https://your-domain.com/api/health/

# ۲) هدرِ HSTS (بعد از افزودنِ DJANGO_HSTS_SECONDS):
curl -sI https://your-domain.com/api/health/ | grep -i strict-transport
#    Strict-Transport-Security: max-age=31536000
```

**ترتیبِ فعال‌سازی مهم است:** `SECURE_SSL_REDIRECT` قبل از TLS = قفل‌شدنِ همه‌ی کاربرانِ http. `HSTS` = اعلامِ «از الان فقط https» به مرورگرها تا یک سال — اگر روزی به http برگردید، مرورگرهایِ قبلی تا انقضای مدت مقاومت می‌کنند. عمداً آخر اضافه می‌شود. (رفتارِ هر سه در تست‌هایِ `SecurityHeadersResponseTests` با همان ترتیبِ منطقی قفل شده.)

چرا این سه متغیر «شرطی»اند و پیش‌فرضِ خاموش؟ چون فقط پشتِ TLSِ واقعی معنا دارند؛ فعال‌بودنشان در توسعه (runserver رویِ http) یعنی قفل‌شدنِ کلاینتِ محلی — الگویِ dev-safeِ پروژه: هیچ متغیری ست نشود = همانِ رفتارِ قبل (تستِ `test_no_hsts_header_by_default`/`test_no_ssl_redirect_by_default`).

---

## ۵.۹ پایشِ سلامت (`/api/health/`) و محدودسازیِ نرخ (رفتارِ دقیق)

### `GET /api/health/` — برایِ مانیتورینگ/Load Balancer

- عمومی (بدونِ لاگین) و **معاف از throttle** (`@throttle_classes([])`) — چون خودِ «فشارِ پایش» نباید سرویسِ سالم را «بیمار» نشان دهد (تست: `test_health_is_never_throttled`).
- payload ماشین‌خوان: `{"status", "database", "engine", "debug"}`؛ ۲۰۰ = فرایند زنده + دیتابیس به `SELECT 1` جواب داد؛ ۵۰۳ = دیتابیس ناسالم (تست: `test_health_returns_503_when_db_down`).
- فقط GET (POST → 405). هیچ مدلی لمس نمی‌شود تا خرابیِ یک جدول، گزارشِ سلامتِ فرایند را خراب نکند.
- برایِ پایشِ دوره‌ای (cron یا uptime-مانیتور): `curl -fsS https://your-domain.com/api/health/` هر ۱ دقیقه کافی است؛ خطا فقط وقتی است که کدِ HTTP ≠ 200.

### محدودسازیِ نرخ — دقیقاً چه چیزی شمرده می‌شود؟

سه scope از 2026-09-10 فعال است (تنظیم در `.env`؛ جزئیاتِ فنی در `backend/planner/throttles.py`):

| Scope | چه چیزی می‌شمارد | کلید | رویِ کدام مسیر |
|---|---|---|---|
| `auth` | هر درخواستِ register/login | IP (XFF توسطِ Nginx بازنویسی‌شده) | فقط این دو مسیر — سخت‌گیرانه‌ترین نرخ را بگیرد |
| `anon` | درخواستِ بی‌احرازِ هویت | IP | مسیرهایِ عمومی دیگر مثلِ refresh |
| `user` | درخواستِ احرازِشده | شناسه‌ی کاربر | همه‌ی endpointهایِ داده |

- پاسخِ ۴۲۹ همراهِ هدرِ `Retry-After` (ثانیه) است — کلاینتِ مهربان منتظر می‌ماند.
- ترتیبِ DRF: درخواستِ بی‌توکن بهِ مسیرِ محافظت‌شده قبل از throttle با 401 رد می‌شود و هیچ شمارنده‌ای نمی‌سوزاند (تست: `test_unauthenticated_data_requests_are_401_not_429`).
- با `-w 2` گنیکورن: هر worker کشِ جدا دارد؛ سقفِ واقعیِ هر scope = ۲× نرخ. برایِ «۲۰/min یعنی حداکثرِ ~۴۰/min» در این مقیاس دفاعِ معقولی است؛ دفاعِ سرِ سختِ لایه‌ی ۴ (Nginx `limit_req`) اضافه‌کردنش روزی لازم شد، اول در `TODO.md` ثبت شود.
- پنجره‌ی شمارشِ `X/min` دقیقاً ۶۰ ثانیه‌ی لغزان است (رفتارِ DRF `SimpleRateThrottle`).

### چرا نرخ‌هایِ پیش‌فرضِ توسعه 10000/min است؟

چون الگویِ dev-safe: بدونِ هیچ متغیری، رفتارِ محلی/تست دست‌نخورده می‌ماند (تست: `test_heavy_dev_traffic_never_throttled`). اگر با `DJANGO_DEBUG=false` بوت کنید و هر سه نرخ هنوز پیش‌فرض باشند، جنگو هشداریِ یک‌خطی رویِ stderr می‌نویسد (بوت متوقف نمی‌شود؛ قابلِ دیدن در `journalctl -u studyplanner`) — بیدارباشِ «دمو باشی یا انتشارِ واقعی؟» (تست: `test_boot_prod_warns_on_default_throttle_rates`).

---

## ۵.۱۰ فهرستِ نهاییِ بررسیِ پیش از انتشار (Checklist)

به‌ترتیبِ منطقیِ راهنما (هر خط باید ✅ باشد):

1. ☐ سرور: کاربرِ `planner` غیر-root؛ پورت‌هایِ 80/443 باز.
2. ☐ کد: `git clone` در `/opt/studyplanner`؛ `venv` ساخته؛ `pip install -r requirements.txt` + `gunicorn`.
3. ☐ دیتابیس: PostgreSQL با کاربرِ اختصاصی؛ `migrate` با `DATABASE_URL` اجرا شد؛ (اختیاری) `loaddata backup.json`.
4. ☐ `.env`: پنج متغیرِ اجباری (SECRET_KEY/DEBUG/ALLOWED_HOSTS/DATABASE_URL + نرخ‌ها) ست؛ `chmod 600`.
5. ☐ systemd: `studyplanner` فعال و `curl http://127.0.0.1:8000/api/health/` = `{"status": "ok", ...}`.
6. ☐ Nginx: سایت فعال؛ `http://domain/static/login.html` باز می‌شود؛ `http://domain/api/health/` = ok؛ XFF **بازنویسی** می‌شود نه الحاق.
7. ☐ TLS: `certbot --nginx` موفق؛ `https://domain/api/health/` = 200.
8. ☐ `.env` تکمیل: `DJANGO_SECURE_SSL_REDIRECT=1` + `DJANGO_COOKIES_SECURE=1` + `DJANGO_PROXY_SSL_HEADER=...`؛ ری‌استارت؛ `curl -sI http://.../api/health/` → 301.
9. ☐ (آخر) `DJANGO_HSTS_SECONDS=31536000`؛ ری‌استارت؛ هدرِ `Strict-Transport-Security` دیده می‌شود.
10. ☐ ثبت‌نام/ورود واقعی از مرورگر رویِ دامنه؛ یک login عادی و یک بورستِ ۴× پشتِ‌سرِهم برایِ دیدنِ ۴۲۹ (رفتارِ سالمِ دفاع).
11. ☐ `journalctl -u studyplanner -e` بدونِ هشدارِ نرخِ پیش‌فرض و بدونِ خطایِ تکراری.
12. ☐ `sudo systemctl enable studyplanner` — ری‌بوتِ سرور هم سرویس را برمی‌گرداند.
13. ☐ ایمیلِ بازیابی: `.env` پنج متغیرِ SMTP + `DJANGO_FRONTEND_BASE_URL=https://your-domain.com`؛ ری‌استارت؛ «فراموشیِ رمز» از مرورگر = ایمیلِ واقعی با لینکِ سالم و کلیک‌پذیر (بخشِ ۵.۱۲).

بعد از این فهرست، پروژه «Production-ready» بودنِ خود را عملاً نشان داده است: تمامِ آن‌چه در `README.md` بخشِ ۱۱ «کارهایِ آینده» برایِ استقرار لازم بود، همین راهنما بود.

---

*این مستند بخشِ پنجمِ مستنداتِ پروژه است: ۰۱ پیکربندی و مدل‌ها، ۰۲ منطقِ سرور و API، ۰۳ صفحاتِ فرانت‌اند، ۰۴ منطقِ فرانت‌اند — و این بخش: استقرارِ واقعی. مستندِ مرجعِ متغیرها جدولِ بخشِ ۱۰ِ `README.md` است؛ در تعارضِ نادر، کد (`backend/backend/settings.py`) مرجعِ نهایی است.*


---

## ۵.۱۱ یادداشتِ امنیتیِ حساب (از 2026-09-10)

`POST /api/auth/password/` (رمزِ فعلی + رمزِ جدید) همه‌ی نشست‌هایِ دیگر را باطل می‌کند — همه‌ی توکن‌هایِ Refreshِ برجسته (لیستِ سیاه) «و» توکن‌هایِ دسترسیِ صادرشده قبل ازِ تغییر (کلاسِ `planner/authentication.py` با مقایسه‌یِ `iat`). برایِ عملیات یعنی: گزارشِ کاربرِ «رمزم لو رفته» فقط یک تغییرِ رمز فاصله دارد تا همه‌ی دستگاه‌هایِ دیگر از کار بیفتند؛ نیازی به ری‌استارتِ سرویس یا دستکاریِ دیتابیس نیست. سیاستِ رمز (حداقلِ ۸ نویسه/غیرِ رایج/...) هم در ثبت‌نام و تغییرِ رمز اجباری است — پیام‌هایش fa/en خودکار است.


## ۵.۱۲ ایمیلِ بازیابیِ رمز — SMTP (از 2026-09-12)

بازیابیِ رمزِ فراموش‌شده (`POST /api/auth/password/reset/` + لینکِ یک‌بارمصرف) تنها مصرف‌کننده‌ی ایمیلِ
پروژه است. در توسعه موتورِ `console` لینک را در stdoutِ runserver می‌نویسد (بی‌SMTP — الگویِ dev-safe)؛
در Production سه قدم:

1. **SMTP در `.env`**: `DJANGO_EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend` + پنج متغیرِ
   HOST/PORT/USER/PASSWORD/USE_TLS + `DJANGO_DEFAULT_FROM_EMAIL` (جدولِ ۵.۵). سرویس‌هایِ ایمیلِ رایج
   (Gmail/SendGrid/Mailgun) همه SMTP می‌دهند؛ پورتِ 587 با STARTTLS (= `USE_TLS=true`) توصیه می‌شود.
2. **مبدأِ لینک**: `DJANGO_FRONTEND_BASE_URL=https://your-domain.com` — لینکِ ایمیل باید به Nginxِ شما
   بیفتد نه به 127.0.0.1.
3. **آزمایشِ سرِانگشتی**: از مرورگر «فراموشیِ رمز» را با حسابِ واقعی اجرا کنید؛ ایمیل باید برسد و لینک،
   صفحه‌ی `reset-password.html` را با uid/token باز کند. اگر نرسید: `journalctl -u studyplanner -e`
   (شکستِ ارسال با سطحِ ERROR لاگ می‌شود — پاسخِ API عمداً همان پیامِ عمومی را می‌دهد؛ الگویِ ضدِ کشفِ حساب).

هشدارِ صادقانه‌ی بوت: `DEBUG=false` + backendِ console = هشدارِ stderr (ایمیل به stdoutِ worker می‌رود و به
هیچ‌کس نمی‌رسد) — بوت ادامه می‌یابد تا پیکربندیِ SMTP بعداً کامل شود ولی بازیابیِ رمز تا آن‌وقت کار نمی‌کند.

---

