# AI_CONTEXT.md

> این فایل یک مرجع فشرده و پایدار برای هر AI/توسعه‌دهنده‌ای است که می‌خواهد **بدون خواندن کامل کد**، سریع بفهمد این پروژه چطور کار می‌کند و هنگام تغییرِ کد چه نکاتی را نباید نادیده بگیرد.
>
> این فایل **جایگزینِ** `README.md` نیست؛ توضیحاتِ روایی، دیاگرام معماری، فرمولِ کاملِ الگوریتم و راهنمای نصب همگی در `README.md` هستند و اینجا تکرار نمی‌شوند. اگر توضیحِ بیشتری لازم داشتی، به فایل‌های زیر مراجعه کن:
> - `README.md` — معرفی کامل پروژه، معماری، الگوریتم، API، نصب
> - `01_config_and_models.md` (در ریشه) تا `04_frontend_logic_and_design.md` (در ریشه) — توضیح خط‌به‌خط و فایل‌به‌فایلِ کل پروژه

---

## ۱. هدف پروژه (خلاصه)

سامانه‌ای که بر اساسِ درس‌ها، امتحان‌ها (با تاریخ و ساعتِ باقی‌مانده) و ساعتِ آزادِ روزانه‌ی کاربر، یک برنامه‌ی مطالعه‌ی روزانه/هفتگی پیشنهاد می‌دهد. هیچ سرویسِ هوش مصنوعیِ خارجی استفاده نشده؛ «هوشمندی» یک الگوریتمِ وزن‌دهیِ ریاضیِ قطعی در پایتونِ خالص است (`backend/planner/utils.py`).

## ۲. پشته‌ی فناوری (نسخه‌های دقیق از `backend/requirements.txt`)

```
Django>=5.2,<5.3
djangorestframework>=3.15
djangorestframework-simplejwt>=5.3
django-cors-headers>=4.4
```

- دیتابیس: SQLite (`backend/db.sqlite3`)
- فرانت‌اند: HTML/CSS/JavaScript خالص، بدون فریم‌ورک و بدون فرآیندِ Build

## ۳. معماری (خلاصه)

دو بخشِ کاملاً مجزا که فقط از طریق REST API (JSON روی HTTP) با هم حرف می‌زنند:

- **بک‌اند**: `backend/` — یک پروژه‌ی Django با یک اپلیکیشن (`planner`)
- **فرانت‌اند**: `static/` — ۸ صفحه‌ی HTML مستقل (هشتمین: `reset-password.html` از 2026-09-12) + یک `app.js` مشترک + یک `i18n.js` مشترک (چندزبانی؛ از 2026-09-09) + یک `styles.css` مشترک

هردو با یک دستور (`python manage.py runserver`) قابل‌اجرا هستند، چون `STATICFILES_DIRS` در `settings.py` پوشه‌ی `static/` را هم زیرِ همان سرور سرو می‌کند (توضیح در README بخش ۱۰).

## ۴. نقشه‌ی فایل‌ها و مسئولیت‌ها (Quick Reference)

### بک‌اند (`backend/planner/`)

| فایل | مسئولیت |
|---|---|
| `models.py` | ۵ مدل: `Subject`, `Exam`, `StudyPlan`, `StudyLog`, `UserSecurityProfile` (از 2026-09-10: یک‌به‌یک به User؛ مهرِ زمانِ آخرینِ تغییرِ رمز — محرکِ ابطالِ توکن در `authentication.py`؛ نکته‌ی ۶.۱۷) |
| `serializers.py` | تبدیل مدل↔JSON + اعتبارسنجی؛ فیلدهای محاسباتی (پیشرفت) اینجا ساخته می‌شوند |
| `views.py` | تمام ViewSetها/Viewهای API؛ شاملِ الگوریتمِ داشبورد و برنامه‌ریزی در سطحِ درخواست؛ از 2026-09-12 تابعِ مشترکِ `_invalidate_all_sessions` (ابطالِ دولایه‌ی نشست — نکته‌ی ۶.۱۸) + دو ویوی بازیابیِ رمز (request/confirm) |
| `urls.py` | نقشه‌ی مسیرهای اپلیکیشن (زیرِ پیشوندِ `/api/`) |
| `utils.py` | **قلبِ الگوریتمی**: `compute_subject_progress`, `generate_study_plan`, `format_plan_for_frontend`, `build_subject_distribution` |
| `ml.py` | مؤلفه‌ی یادگیریِ آماری (از 2026-09-09): `fit_calibration_model`/`classify_bias`/`predict_hours`/`assess_exam_risk` (خالص، بدونِ ORM) + `build_training_samples`/`get_prediction_report` (ORM؛ نکته‌ی ۶.۱۵) |
| `throttles.py` | کلاسِ `AuthBurstThrottle` (از 2026-09-10): محدودسازیِ نرخِ مسیرهایِ احرازِ هویت با scopeِ سفت‌شده‌ی 'auth' و کلیدِ هر IP؛ نرخ از `DJANGO_AUTH_THROTTLE_RATE` (نکته‌ی ۶.۱۶) |
| `authentication.py` | کلاسِ `SessionInvalidatingJWTAuthentication` (از 2026-09-10): فرزندِ `JWTAuthentication`ِ SimpleJWT؛ در `get_user` اگر `iat` توکن < `password_changed_at` کاربر باشد ۴۰۱ با code='password_changed' (نکته‌ی ۶.۱۷) |
| `admin.py` | ثبتِ مدل‌ها در پنلِ `/admin/` |
| `management/commands/seed_demo_data.py` | دستورِ تولیدِ داده‌ی نمونه برای تست |
| `tests.py` | ۲۴۶ تستِ خودکارِ Django/DRF: هشت کلاسِ API (Auth تا الگوریتم؛ Auth شامل تست‌های تمدیدِ توکن) + کلاسِ `JWTTokenRotationBlacklistTests` (چرخش/لیستِ سیاه/خروجِ سرور-محور) + کلاسِ `PaginationAPITests` (صفحه‌بندیِ اختیاری) + کلاسِ `SettingsEnvVarsTests` (متغیرهایِ محیطیِ Production؛ شاملِ بوتِ واقعیِ مفسرِ جدا) + کلاسِ `StudyPlanUniqueConstraintTests` با `TransactionTestCase` برای قیدِ DB + کلاس‌های `StudyLogConcurrencyLockTests`/`StudyLogOrphanDeleteTests` (قفلِ هم‌زمانیِ select_for_update و حذفِ یتیم؛ نکته‌ی ۶.۱۲) + کلاس‌های `DatabaseUrlSettingsTests`/`PostgresForUpdateTests` (متغیرِ DATABASE_URL + قفلِ FOR UPDATE در PostgreSQL؛ نکته‌ی ۶.۱۳) + کلاس‌های `I18nAcceptLanguageTests`/`I18nCatalogIntegrityTests` (ترجمه‌ی پیام‌ها با Accept-Language + سلامتِ کاتالوگِ locale/en؛ نکته‌ی ۶.۱۴) + کلاس‌های `MLCalibrationMathTests`/`MLTrainingDataTests`/`MLPredictionsAPITests` (ریاضیاتِ خالص + داده‌ی آموزشی + endpointِ پیش‌بینی؛ نکته‌ی ۶.۱۵) + کلاس‌های `HealthEndpointTests`/`ThrottlingAPITests`/`ThrottleDevSafeDefaultsTests`/`ThrottleAndSecuritySettingsTests`/`SecurityHeadersResponseTests` (سلامت + محدودسازیِ نرخ + هدرهایِ امنیتیِ شرطی؛ نکته‌ی ۶.۱۶) + کلاس‌های `RegisterPasswordPolicyTests`/`ChangePasswordAPITests`/`StaleAccessTokenInvalidationTests`/`UserSecurityProfileModelTests` (سیاستِ رمز + تغییرِ رمز + ابطالِ توکن‌هایِ قبل ازِ تغییر + مدلِ پروفایل؛ نکته‌ی ۶.۱۷) + کلاس‌های `PasswordResetRequestAPITests`/`PasswordResetThrottleTests`/`PasswordResetConfirmAPITests`/`PasswordResetSessionInvalidationTests`/`PasswordResetSettingsTests` (بازیابیِ رمز: ضدِ کشفِ حساب + ماتریسِ رد/پذیرش + یک‌بارمصرف/انقضا + ابطالِ نشست از مسیرِ کاملِ API + بوتِ واقعیِ ایمیل؛ نکته‌ی ۶.۱۸)؛ اجرا با `python manage.py test planner` |
| `migrations/0001` تا `0008` | تاریخچه‌ی واقعیِ تکاملِ اسکیمای دیتابیس (تاریخ‌ها در `CHANGELOG.md`) |

### فرانت‌اند (`static/`)

| فایل | مسئولیت |
|---|---|
| `login.html` / `register.html` | صفحاتِ احراز هویت (بدونِ سایدبار) |
| `index.html` | داشبورد (`data-page="dashboard"`) |
| `subjects.html` | مدیریتِ درس‌ها (`data-page="subjects"`) |
| `exams.html` | مدیریتِ امتحان‌ها (`data-page="exams"`) |
| `study_plan.html` | برنامه‌ی مطالعه (`data-page="study-plan"`) |
| `study_log.html` | ثبتِ مطالعه (`data-page="study-log"`) |
| `app.js` | تمامِ منطقِ جاوااسکریپتی؛ روترِ سبک بر مبنایِ `data-page` در انتهای فایل |
| `i18n.js` | زیرساختِ چندزبانیِ فرانت‌اند (از 2026-09-09): دیکشنریِ ۲۲۰ کلیدی (۱۵ کلیدِ بازیابیِ رمز، 2026-09-12) + `t()` + `applyI18n()`؛ باید قبل از app.js لود شود (نکته‌ی ۶.۱۴) |
| `styles.css` | سیستمِ طراحی؛ متغیرهای رنگ/فاصله در بالای فایل (`:root`) |

## ۵. مدل‌های داده (ساختارِ رابطه‌ای)

```
User → Subject (1→N, unique_together=[user,name])
Subject → Exam (1→N)
Exam → StudyLog (1→N)
User → StudyPlan (1→N در سطحِ مدل، ولی در عمل هر کاربر فقط ۱ رکورد دارد — نکته‌ی ۶.۴ را ببین)
```

جزئیاتِ فیلد‌به‌فیلد در `README.md` بخش ۶ و `01_config_and_models.md` (در ریشه) بخش ۱.۶.

## ۶. نکاتِ حیاتی هنگام ویرایشِ کد (این‌ها را نقض نکن)

۶.۱ **منطقِ کسر/بازگرداندنِ ساعت در مدل است، نه در View.** `StudyLog.save()` به‌صورتِ خودکار `exam.study_hours_remaining` را کم می‌کند (فقط برای رکوردهای *جدید*، نه ویرایش) و `StudyLog.delete()` (از 2026-09-03) دقیقاً همان ساعتِ کسرشده را برمی‌گرداند. عددِ کسرشده در فیلدِ `hours_deducted` ذخیره می‌شود = کمینه‌ی «ساعتِ مطالعه» و «ساعتِ موجودِ امتحان» (کسرِ محدود: اگر ۲ ساعت مانده باشد و ۵ ساعت ثبت شود، ۲ ساعت کم و ۲ ساعت برمی‌گردد، نه ۵). اگر جایی منطقِ مشابه در `views.py` اضافه شود، ساعت **دو بار** کم/برگشت خواهد شد. نکته‌ی حذف: مسیرِ BulkDeleteِ جنگو `delete()` مدل را صدا نمی‌زند، پس حذفِ دسته‌ایِ QuerySet یا حذفِ آبشاری (حذفِ خودِ امتحان) ساعتی برنمی‌گرداند — رفتارِ عمدی، مستند در docstringِ خودِ متد.

۶.۲ **ترتیبِ `router.register` در `urls.py` حیاتی است.** همه‌ی `router.register(...)` باید قبل از `path('', include(router.urls))` بیایند؛ چون `router.urls` فقط ViewSetهای *تا آن لحظه ثبت‌شده* را می‌بیند. این پروژه قبلاً همین باگ را داشته (کامنتِ خودِ فایل).

۶.۳ **`get_queryset` در هر ViewSet باید همیشه بر اساسِ `self.request.user` فیلتر شود.** حذفِ این فیلتر یعنی یک کاربر می‌تواند داده‌ی کاربرِ دیگر را ببیند (آسیب‌پذیریِ IDOR). این الگو در `SubjectViewSet`, `ExamViewSet`, `StudyLogViewSet`, `StudyPlanViewSet` رعایت شده و باید در هر ViewSetِ جدید هم رعایت شود.

۶.۴ **`StudyPlan.user` از مایگریشنِ 0008 (2026-09-05) `OneToOneField` است و در خودِ دیتابیس یکتاست.** «هر کاربر حداکثر یک رکوردِ تنظیماتِ برنامه» حالا قیدِ UNIQUE دارد؛ Migrationِ 0008 پیش از اعمالِ قید رکوردهایِ تکراریِ قدیمی را پاکسازی می‌کند (جدیدترینِ هر کاربر نگه داشته می‌شود) و الگوی `get_or_create` در `views.py` در برابرِ درخواست‌هایِ هم‌زمان (Race Condition) مصون است. POST دوباره به `/api/study-plan/` پاسخِ ۴۰۰ خوانا می‌گیرد.

۶.۵ **نام‌گذاریِ `target_score` در برابرِ `target_grade`.** فرانت‌اند و API از نامِ `target_score` استفاده می‌کنند؛ مدل و دیتابیس از `target_grade`. این نگاشت در `SubjectSerializer` با `source='target_grade'` انجام می‌شود. اگر این فیلد را جایی دستی دست بزنی، نامِ درست را گم نکن.

۶.۶ **فیلدِ `notes` از 2026-08-25 بخشی از مدلِ `Subject` است (Migrationِ `0005`) و در سریالایزر هم هست؛ فرمِ `subjects.html` آن را می‌فرستد و جدولِ درس‌ها زیرِ نامِ درس نمایشش می‌دهد.** فیلدِ `total_hours` برعکس، به‌طور کامل از فرم حذف شد. دلیلِ تصمیم: «کل ساعت» در این سیستم در سطحِ امتحان (`Exam.study_hours_remaining`) دنبال می‌شود و فیلدِ محاسباتیِ `total_hours` در `to_representation` از همان‌جا مشتق می‌شود؛ یک ورودیِ دستیِ هم‌نام با معنای متفاوت فقط گمراه‌کننده بود. اگر روزی خواستی ساعتِ دستی در سطحِ درس اضافه کنی، آن را با نامِ دیگری (مثلاً `estimated_hours`) بیاور تا با فیلدِ محاسباتیِ هم‌نام تداخل نکند. شرحِ کامل: `CHANGELOG.md` بخشِ 2026-08-25. **الگوی همان تصمیم در سطحِ امتحان (2026-08-29):** فیلدِ `notes` به مدلِ `Exam` هم اضافه شد (Migrationِ `0006`) و فرمِ امتحان (`name="notes"`) از این پس واقعاً ذخیره می‌شود؛ همراهِ آن، قابلیتِ «ویرایشِ امتحان» کامل شد (`startExamEdit` + تشخیصِ POST/PATCH در `handleExamForm` + `perform_update` امنیتی در `ExamViewSet` که تغییرِ درسِ امتحان به درسِ کاربرِ دیگری را رد می‌کند) و کلاس‌های CSSِ فرمِ امتحان با `styles.css` هم‌راستا شدند.

۶.۷ **مسیرِ `/api/study-plan/` متدِ پیش‌فرضِ `list()` را Override کرده.** این مسیر رکوردهای خامِ `StudyPlan` را برنمی‌گرداند؛ همیشه برنامه را زنده با `generate_study_plan` + `format_plan_for_frontend` می‌سازد. اگر قرار است رفتارِ CRUD خامِ این مدل هم لازم شود، باید یک Endpoint جداگانه ساخت، نه اینکه `list()` را به حالتِ استاندارد برگرداند (چون فرانت‌اند به فرمتِ فعلی وابسته است).

۶.۸ **الگوریتمِ `generate_study_plan` سقفِ ۶۰ روز دارد** (`min((last_exam_date - today).days + 1, 60)`) تا برای امتحان‌های خیلی دور، محاسبه‌ی بی‌فایده انجام نشود. نمای «هفتگی» فقط از ۷ روزِ اول استفاده می‌کند، پس این سقف تأثیری در نتیجه‌ی نمایشی ندارد.

۶.۹ **صفحه‌بندیِ لیست‌ها «اختیاری» است و باید همین‌طور بماند.** از 2026-09-06 کلاسِ `OptionalPageNumberPagination` رویِ `SubjectViewSet`/`ExamViewSet`/`StudyLogViewSet` نشسته: تا وقتی کلاینت نه `?page=` فرستاده و نه `?page_size=`، پاسخ همان «لیستِ کاملِ JSON» است — فرانت‌اندِ فعلیِ `app.js` پارامتری نمی‌فرستد و اگر این پیش‌فرضِ «لیستِ کامل» بشکند، همه‌ی صفحاتِ فهرست می‌شکنند. قواعد: سقفِ `page_size` صد رکورد؛ فقط `?page=` یعنی اندازه‌ی ۲۰؛ `page_size` نامعتبر/غیرمثبتِ تنها → صفحه‌بندی غیرفعال؛ صفحه‌ی نامعتبر → ۴۰۴. مرتب‌سازیِ قطعی از `Meta.ordering` خودِ مدل‌ها می‌آید (درس: جدیدترین اول؛ امتحان: نزدیک‌ترین تاریخ اول؛ گزارش: جدیدترین اول).
۶.۱۰ **پیش‌فرض‌هایِ تنظیمات باید «dev-safe» بمانند و سپرِ Production حذف نشود.** از 2026-09-06 مقادیرِ حساس از متغیرهایِ محیطی خوانده می‌شوند (`DJANGO_SECRET_KEY`/`DJANGO_DEBUG`/`DJANGO_ALLOWED_HOSTS`/`DJANGO_CORS_ALLOW_ALL`/`DJANGO_ALLOWED_ORIGINS`)؛ بدونِ هیچ متغیری باید دقیقاً همانِ رفتارِ قبلی برقرار باشد (تستِ `test_boot_dev_defaults_unchanged` رگرسیونش است). دو سپرِ راه‌اندازی (DEBUG=false با کلیدِ توسعه → خطا؛ بدونِ Host → خطا) عمداً هستند: حذفِ آنها یعنی بوتِ بی‌صدایِ ناامن در Production. بولی‌ها فقط با `1`/`true`/`yes`/`on` مثبت می‌شوند — مقادیرِ دیگر (حتیِ «2») عمداً منفی‌اند تا مقدارِ اشتباهِ env، بی‌صدا حالتِ امن را باز نکند.
۶.۱۱ **چرخش و لیستِ سیاهِ توکنِ Refresh نباید خاموش شود و خروج باید توکن را باطل کند.** از 2026-09-08 `ROTATE_REFRESH_TOKENS=True` و `BLACKLIST_AFTER_ROTATION=True` است و اپِ `rest_framework_simplejwt.token_blacklist` در `INSTALLED_APPS` نشسته (جدول‌هایش با یک‌بار `migrate` ساخته می‌شوند): هر تمدید توکنِ Refreshِ تازه صادر می‌کند و قبلی را باطل — توکنِ هر نسل فقط یک‌بار قابلِ استفاده است. `refreshAccessToken` در `app.js` موظف است توکنِ تازه را ذخیره کند (بدونِ آن، نشست بعد از اولین تمدید می‌شکند) و `logout()` باید اول `POST /api/auth/logout/` را بزند و بعد localStorage را پاک کند — قطعیِ سرور در خروج، خروجِ محلی را مسدود نمی‌کند (fail-open عمدی است). رگرسیون‌تست‌ها: کلاسِ `JWTTokenRotationBlacklistTests`.

۶.۱۲ **کسر/بازگشتِ ساعتِ امتحان باید رویِ سطرِ «قفل‌شده و تازه‌خوانده‌شده» انجام شود.** از 2026-09-09 `StudyLog.save()`/`delete()` امتحان را داخلِ تراکنشِ اتمیک با `Exam.objects.select_for_update().get(pk=...)` می‌خوانند و کم/زیادکردنِ ساعت رویِ همان نمونه‌یِ تازه انجام می‌شود — نه رویِ `self.exam` یا snapshotِ کش‌شده (مثلِ `select_related` از ابتدایِ درخواست)؛ وگرنه Lost Update برمی‌گردد (رگرسیون‌تست‌ها: کلاسِ `StudyLogConcurrencyLockTests`). ترتیبِ قفل در هر دو متد «اول امتحان، بعد گزارش» است تا Deadlock نگیرد؛ ویرایشِ گزارش (pk دارد) عمداً قفل نمی‌گیرد و ساعت کسر نمی‌کند. در SQLite قفلِ FOR UPDATE بی‌صدا نادیده گرفته می‌شود (خواندنِ تازه همچنان مؤثر است)؛ قفلِ واقعی در PostgreSQL/MySQL فعال می‌شود.

۶.۱۳ **موتورِ دیتابیس فقط از متغیرِ محیطیِ `DATABASE_URL` عوض می‌شود و کد نباید به SQLite گره بخورد.** از 2026-09-09 بخشِ `DATABASES` با تابعِ `_resolve_database()` ساخته می‌شود: بدونِ متغیر = SQLite (رفتارِ قبل)، با `postgres://` = PostgreSQL (درایورِ psycopg). هیچ کدی نباید به `sqlite3` یا فایلِ `db.sqlite3` فرضِ صریح داشته باشد؛ تست‌ها باید روی هر دو موتور سبز بمانند — SQL اختصاصیِ یک موتور باید با `connection.vendor` و `skipUnless` شرطی شود (نمونه‌ها: `PRAGMA foreign_keys` در `StudyLogOrphanDeleteTests` و `FOR UPDATE` در `PostgresForUpdateTests`). ترتیبِ بررسی‌ها در `_resolve_database`: scheme → نامِ دیتابیس → پورت → پارامترهای query → درایور؛ این ترتیب را حفظ کن تا پیام‌هایِ خطا دقیق بمانند.

۶.۱۴ **در چندزبانی، msgid همان «متنِ فارسیِ اصلی» است و رشته‌ی رابطِ جدید باید هم‌زمان در سه جا بیاید.** از 2026-09-09 پیام‌های بک‌اند با `gettext`/`gettext_lazy` پیچیده شده‌اند (`views.py`/`serializers.py`/`utils.py`)، کاتالوگِ انگلیسی در `backend/locale/en/LC_MESSAGES/django.po` است و `django.mo` کامپایل‌شده عمداً commit شده (روی ویندوزِ کاربر msgfmt نیست؛ کامپایل فقط بعد از تغییرِ ترجمه با `scripts/compile_mo.py`). برایِ افزودن/تغییرِ پیام: (۱) متنِ فارسی در کد با `_()`، (۲) کلید/ترجمه در django.po + کامپایلِ مجدد، (۳) برایِ رشته‌ی فرانت‌اند، کلید در دیکشنریِ `static/i18n.js` (کلید = همان متنِ فارسی؛ فارسی خودِ کلید را برمی‌گرداند). `i18n.js` باید در HTML «قبل از» app.js لود شود (t باید قبل از اولین رندر موجود باشد) و app.js هدرِ Accept-Language را می‌فرستد — پیام‌های خطای API با زبانِ کاربر برمی‌گردند. رشته‌های دارایِ متغیر با الگوی `%(name)s` در بک‌اند و `{name}` در فرانت‌اند پارامتری‌اند (ترتیبِ کلمات در ترجمه آزاد). رگرسیون‌تست‌ها: کلاس‌های `I18nAcceptLanguageTests`/`I18nCatalogIntegrityTests` + تستِ Node خارج از ریپو.

۶.۱۵ **مؤلفه‌ی ML (`planner/ml.py`) کاربر-محور و بدون‌ تغییرِ اسکیماست؛ قراردادهایش را نشکن.** (از 2026-09-09) مدلِ کالیبراسیونِ β هر کاربر فقط از امتحان‌هایِ *گذشته‌ی خودش* می‌آموزد (`build_training_samples`: exam_date < today و حداقل یک لاگ؛ planned = باقی‌مانده + Σhours_deducted و actual = Σhours_studied) — امتحان‌هایِ آینده/امروزی هرگز در آموزش نیستند (نشتِ آینده) ولی در پیش‌بینی (`exam_date >= today` و `study_hours_remaining > 0`) هستند. ریاضیات در توابعِ خالص (`fit_calibration_model` = LSQ از مبدأ + انقباضِ بیزی به ۱ با PRIOR_STRENGTH=4 + مهارِ [۰٫۲۵ , ۴]) جدا از ORM مانده تا با SimpleTestCase بدونِ DB تست شوند. `GET /api/predictions/` داده‌ی **ماشین‌خوان** برمی‌گرداند (risk/bias مقادیرِ enumاند، نه پیام) — متنِ نمایشی فقط در فرانت‌endet با `RISK_LABELS`/`BIAS_LABELS` و کلیدهایِ i18n.js ساخته می‌شود؛ پس این endpoint هرگز رشته‌ی gettext جدید نمی‌سازد و کاتالوگِ locale/en نباید به‌خاطرِ آن دست بخورد. ساعتِ آزادِ روزانه از همان `_get_or_create_plan_settings` ویو می‌آید (یک منبعِ حقیقت با الگوریتمِ برنامه‌ریزی). الگوریتمِ قانون‌محورِ `generate_study_plan` عمداً دست‌نخورده ماند: پیش‌بینیِ ML قرینه/مکملِ برنامه است، نه جایگزینش — اگر روزی قرار شد β در تخصیصِ ساعت هم اثر بگذارد، باید opt-in با پارامتر باشد و رگرسیون‌تستِ «بدونِ پارامتر = رفتارِ قبلی» بگیردش. رگرسیون‌تست‌ها: کلاس‌های `MLCalibrationMathTests`/`MLTrainingDataTests`/`MLPredictionsAPITests`.

۶.۱۶ **محدودسازیِ نرخ/سلامت/TLS-شرطی: سه قراردادِ «آمادگیِ استقرار» (2026-09-10) را نشکن.** (۱) `GET /api/health/` عمومی و **معاف از throttle** است (`@throttle_classes([])` در `views.py`) و payload عمداً gettext ندارد (مخاطب = مانیتور/LB؛ کاتالوگِ locale/en نباید برایِ آن دست بخورد) — معاف‌بودن یعنی «فشارِ پایش، سرویسِ سالم را بیمار نشان ندهد»؛ endpoint جدیدِ عمومیِ دیگری اگر روزی اضافه شد، throttleهایِ پیش‌فرض (`anon`/`user`) رویش می‌نشینند مگر این‌که دلیلِ مشخصی برایِ معافیت باشد. (۲) `register`/`login` فقط `AuthBurstThrottle` (scopeِ سفتِ 'auth' در `planner/throttles.py`) دارند — نه throttleهایِ پیش‌فرض؛ decoratorهایِ `@throttle_classes` ویو را از DEFAULT_THROTTLE_CLASSES جایگزین می‌کنند (شمارشِ مضاعف نکنید و scope را در کلاس سفت نگه دارید تا با فراموشیِ view.throttle_scope از کار نیفتد). (۳) نرخ‌ها و تنظیماتِ TLS از متغیرهایِ محیطی با الگویِ dev-safe می‌آیند: پیش‌فرضِ نرخ‌ها 10000/min (مؤثراً نامحدود) و تنظیماتِ SSL/HSTS/کوکی/پروکسی همه خاموشند — «بدونِ متغیر = همانِ رفتارِ قبل» رگرسیون‌تست دارد (`test_boot_dev_defaults_unchanged` و `test_heavy_dev_traffic_never_throttled`)؛ قالبِ نرخِ خراب و HSTSِ منفی = بوت با پیام (fail-fast — توابعِ `_env_throttle_rate`/`_env_int`/`_env_proxy_ssl_header` را از `tests.py` هم import می‌کنیم؛ امضایشان را تغییر ندهید). تنظیماتِ TLS را هرگز پیش‌فرض-روشن نکنید: فعال‌بودنش بدونِ TLSِ واقعی یعنی قفل‌شدنِ کاربرانِ http — روشن‌کردنش کارِ `.env` در سرور است (`05_deployment.md`). نکته‌ی مکانیکی برایِ تست‌ها: `SimpleRateThrottle.THROTTLE_RATES` در زمانِ importِ DRF snapshot می‌شود و `override_settings` آن را تازه نمی‌کند — در تست، نرخ‌ها را مستقیم رویِ خودِ کلاس patch کنید (`@patch.object(SimpleRateThrottle, 'THROTTLE_RATES', ...)`)؛ و `BaseAPITestCase.tearDown` عمداً `cache.clear()` می‌کند (شمارنده‌هایِ throttle بینِ تست‌ها نشت نکنند). رگرسیون‌تست‌ها: کلاس‌های `HealthEndpointTests`/`ThrottlingAPITests`/`ThrottleDevSafeDefaultsTests`/`ThrottleAndSecuritySettingsTests`/`SecurityHeadersResponseTests`.

۶.۱۷ **امنیتِ حسابِ کاربری (2026-09-10) — دو قراردادِ «رمز» را نشکن.** (۱) سیاستِ رمز در «دو» نقطه‌ی ورودیِ رمزِ جدید اجرا می‌شود: `UserSerializer.validate` (ثبت‌نام — با نمونه‌یِ گذرایِ User برایِ سنجشِ شباهت) و ویوی `change_password` (با `request.user` واقعی). پیام‌هایِ خطا مالِ خودِ جنگوند (کاتالوگِ fa/en جنگو) — «هیچ‌چیز» به کاتالوگِ locale/en پروژه برایِ این پیام‌ها اضافه نشده؛ فقط سه پیامِ اختصاصیِ change_password/ابطال در کاتالوگ هست. اگر قواعد را در یک نقطه سخت‌تر کردید، هر دو را تغییر دهید. (۲) ابطالِ نشست دو لایه دارد و «ترتیبش» حیاتی است: اول همه‌ی `OutstandingToken`هایِ کاربر سیاه + `UserSecurityProfile` با `timezone.now()`، «بعد» صدورِ جفتِ توکنِ تازه (مگر توکنِ تازه هم سیاه/رد شود). کلاسِ `planner.authentication.SessionInvalidatingJWTAuthentication` (تنها عضوِ `DEFAULT_AUTHENTICATION_CLASSES`) در `get_user` مقایسه‌ی `iat < int(password_changed_at.timestamp())` را اجرا می‌کند — علامتِ «کمترِ سخت» عمدی است تا توکنِ صادرشده در همانِ ثانیه‌یِ تغییر زنده بماند (رزولوشنِ iat ثانیه است؛ رگرسیون‌تستِ مرز: `test_same_second_edge_keeps_token_valid`)؛ آن را به `<=` تبدیل نکنید — توکنِ تازه‌ی پاسخِ تغییرِ رمز را همان لحظه می‌کُشد. کاربرانِ بدونِ رکوردِ پروفایل (هرگز رمز عوض نکرده‌اند) فقط یک SELECT کوچکِ خالی اضافه دارند — رکورد فقط در تغییرِ رمزِ موفق ساخته می‌شود؛ ساختش در ثبت‌نام ممنوع (dev-safe می‌مانَد). `change_password` فقط `IsAuthenticated` + throttleِ پیش‌فرضِ 'user' دارد (رمزِ فعلی لازم است؛ حمله‌ی حدسی رویش بی‌معناست) و `set_password` را با `update_fields=['password']` ذخیره می‌کند. رگرسیون‌تست‌ها: کلاس‌های `RegisterPasswordPolicyTests`/`ChangePasswordAPITests`/`StaleAccessTokenInvalidationTests`/`UserSecurityProfileModelTests`.

۶.۱۸ **بازیابیِ رمز (2026-09-12) — سه قراردادِ غیرقابل‌مذاکره.** (۱) **پاسخِ عمومیِ ضدِ کشفِ حساب:** `password_reset_request` برایِ همه‌ی حالت‌ها (حسابِ موجودِ ایمیل‌دار / ناموجود / بدونِ ایمیل / غیرفعال) دقیقاً همان status و همان بدنه را برمی‌گرداند؛ شکستِ ارسالِ SMTP هم «ثبت و بلعیده» می‌شود (`logger.exception` — ۵۰۰ برایِ موجود و ۲۰۰ برایِ ناموجود یعنی oracle)؛ خطایِ ۴۰۰ فقط برایِ «بدونِ identifier» است که فاش‌کننده نیست. (۲) **توکنِ امضاشده، نه جدول:** uid/token از `PasswordResetTokenGenerator` جنگو می‌آیند (امضا با SECRET_KEY + هشِ وضعیتِ کاربر) — یک‌بارمصرف است چون بعد از `set_password` هش عوض می‌شود و توکن می‌میرد؛ بدونِ مایگریشن و بدونِ جدولِ توکن. (۳) **هر تغییرِ رمز = ابطالِ همه‌ی نشست‌ها + ورودِ تازه:** هر دو مسیرِ `change_password` و `password_reset_confirm` باید داخلِ `transaction.atomic` از **همان یک** تابعِ `_invalidate_all_sessions(user)` استفاده کنند (لیستِ سیاهِ همه‌ی Refreshها + مهرِ `password_changed_at`)؛ confirm عمداً **هیچ توکنی صادر نمی‌کند** (مالکیتِ ایمیل به نشستِ خودکار تبدیل نشود). تنظیمات: `EMAIL_BACKEND` پیش‌فرضِ console (dev-safe — بدونِ SMTP، لینک در stdoutِ runserver)؛ با `DEBUG=false` + console، هشدارِ stderr؛ `PASSWORD_RESET_TIMEOUT` پیش‌فرضِ ۳۶۰۰ (کوتاه‌تر از ۳ روزِ جنگو — عمدی) و غیرمثبت = fail-fastِ بوت؛ `FRONTEND_BASE_URL` مبدأِ لینک است (پیش‌فرضِ runserverِ محلی). نکته‌ی ایمیلِ فارسی: Subject طبقِ RFC 2047 base64 می‌شود (استانداردِ ایمیل — کلاینت‌هایِ واقعی برمی‌گردانندش)؛ بدنه خوانا می‌ماند. رگرسیون‌تست‌ها: کلاس‌های `PasswordResetRequestAPITests`/`PasswordResetThrottleTests`/`PasswordResetConfirmAPITests`/`PasswordResetSessionInvalidationTests`/`PasswordResetSettingsTests`.


## ۷. Conventions رعایت‌شده در کد

- تمامِ کامنت‌های کد و پیام‌های خطا/UI به **فارسی** نوشته شده‌اند؛ نام‌های متغیر/تابع/کلاس به **انگلیسی**.
- الگوی رایج در `app.js`: هر صفحه یک ترکیبِ `render...()` (ساختِ HTML) + `load...()` (گرفتنِ داده از API و صدا زدنِ render) + گاهی `handle...Form()` (گرفتنِ رویدادِ Submit).
- قاعده‌ی امنیتیِ رندر (از 2026-09-04): هر مقدارِ متنیِ API پیش از درج در `innerHTML` باید با `escapeHtml()` (در بخشِ توابعِ کمکیِ `app.js`) پاک‌سازی شود؛ تنها اعدادِ اعتبارسنجی‌شده‌ی سرور (ساعت/درصد/تاریخ) و مسیرهایِ `textContent` مستثنا هستند.
- هر `init...Page()` در `app.js` با `requireAuth()` و `bindGlobalEvents()` شروع می‌شود.
- توابعِ `utils.py` تا حدِ امکان «خالص» نوشته شده‌اند (ورودی/خروجیِ ساده، وابستگیِ کمینه به ORM) تا قابلِ تست‌کردنِ مجزا باشند.

## ۸. احراز هویت (خلاصه)

JWT با `djangorestframework-simplejwt`. توکنِ دسترسی: ۱ روز. توکنِ تمدید: ۷ روز. `ROTATE_REFRESH_TOKENS=False`. هر دو توکن در `localStorage` مرورگر ذخیره می‌شوند (کلیدهای `ssp_token` و `ssp_refresh_token` در آبجکتِ `storageKeys`). از 2026-09-06 مسیرِ `POST /api/auth/refresh/` (ویویِ آماده‌ی `TokenRefreshView`) فعال است و `apiRequest` در پاسخِ 401 اول یک‌بار بی‌صدا تمدید و درخواست را دوباره می‌زند؛ اگر تمدید ممکن نبود، `forceLogoutExpired` کاربر را به `login.html?expired=1` هدایت می‌کند (جزئیات در `app.js` و `docs/04`).

## ۹. Configuration مهم (`backend/backend/settings.py`)

| تنظیم | مقدار فعلی | نکته |
|---|---|---|
| `DEBUG` | از `DJANGO_DEBUG`؛ پیش‌فرض `True` | فقط برای توسعه؛ در Production = false (سپرِ بوت فعال می‌شود) |
| `SECRET_KEY` | از `DJANGO_SECRET_KEY`؛ پیش‌فرض = کلیدِ توسعه | در Production کلیدِ واقعی (الزامی) |
| `ALLOWED_HOSTS` | از `DJANGO_ALLOWED_HOSTS`؛ پیش‌فرض خالی | در Production الزامی (سپرِ بوت) |
| `CORS_ALLOW_ALL_ORIGINS` | از `DJANGO_CORS_ALLOW_ALL`؛ پیش‌فرض `True` | در Production = false + `DJANGO_ALLOWED_ORIGINS` |
| `DATABASES` | از `DATABASE_URL`؛ پیش‌فرض SQLite | بدونِ متغیر = `backend/db.sqlite3`؛ با `postgres://` = PostgreSQL (نکته‌ی ۶.۱۳) |
| `STATICFILES_DIRS` | `[BASE_DIR.parent / 'static']` | فرانت‌اند را هم سرو می‌کند |
| `SIMPLE_JWT` | دسترسی ۱ روز / تمدید ۷ روز | چرخش + لیستِ سیاه فعال (از 2026-09-08؛ نکته‌ی ۶.۱۱) |
| `REST_FRAMEWORK['DEFAULT_THROTTLE_*']` | نرخ‌هایِ `anon`/`user`/`auth` از متغیرهایِ محیطی؛ پیش‌فرض 10000/min | محدودسازیِ نرخ (از 2026-09-10؛ نکته‌ی ۶.۱۶) — register/login فقط scopeِ auth | 
| `SECURE_SSL_REDIRECT`/`SESSION_COOKIE_SECURE`/`CSRF_COOKIE_SECURE`/`SECURE_HSTS_SECONDS`/`SECURE_PROXY_SSL_HEADER` | از متغیرهایِ محیطی؛ همه خاموش/خالی | فقط پشتِ TLSِ واقعی فعال شوند (از 2026-09-10؛ نکته‌ی ۶.۱۶ — راهنما: `05_deployment.md`) |

پیش‌فرض‌ها عمداً «dev-safe»اند: بدونِ ست‌کردنِ هیچ متغیری، همان رفتارِ قبل برقرار است (۲۴۶ تست بدونِ متغیر سبز می‌شوند). فایلِ `.env` هنوز در ریپو وجود ندارد و کتابخانه‌ی dotenv هم اضافه نشده (در سرورِ Production با `EnvironmentFile` سرویسِ systemd تزریق می‌شود — `05_deployment.md`)؛ متغیرها با `set`/`setx` (ویندوز) یا `export` (لینوکس) ست می‌شوند — جدولِ کامل در `README.md` بخشِ ۱۰.

## ۱۰. فایل‌های مستندات مرتبط

| فایل | محتوا |
|---|---|
| `README.md` | معرفیِ کامل، معماری، الگوریتم، API، نصب |
| `01_config_and_models.md` (در ریشه) | توضیحِ خط‌به‌خطِ پیکربندی و مدل‌ها |
| `02_server_logic_and_api.md` (در ریشه) | توضیحِ خط‌به‌خطِ سریالایزر/ویو/الگوریتم |
| `03_frontend_pages.md` (در ریشه) | توضیحِ هر ۸ صفحه‌ی HTML |
| `04_frontend_logic_and_design.md` (در ریشه) | توضیحِ `app.js` و `styles.css` |
| `05_deployment.md` (در ریشه) | راهنمایِ گام‌به‌گامِ استقرارِ Production (از 2026-09-10): PostgreSQL + گنیکورن + systemd + Nginx + Certbot |
| `CHANGELOG.md` | تاریخچه‌ی تغییرات |
| `TODO.md` | کارهای باقی‌مانده |
| `HANDOFF.md` | وضعیتِ فعلی و نقطه‌ی ادامه‌ی کار (اولین فایلی که باید خواند) |
