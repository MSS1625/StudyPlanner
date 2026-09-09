# planner/ml.py
# ----------------------------------------------------------------------------
# مؤلفه‌ی «یادگیری آماری» سامانه (از 2026-09-09) — پاسخِ آیتمِ آخرِ TODO.md
# («افزودنِ یک مؤلفه‌ی یادگیریِ آماری/ماشینی واقعی»، بر مبنایِ ایده‌ی
# README.md بخشِ ۱۱: «یک مدلِ رگرسیونیِ ساده که بر اساسِ داده‌هایِ تاریخیِ
# StudyLog هر کاربر، زمانِ واقعیِ موردنیاز را پیش‌بینی کند»).
#
# مدل چیست؟ «کالیبراسیونِ تخمین‌هایِ ساعتیِ کاربر»:
#   هر کاربر وقتی امتحانی می‌سازد، عددِ «ساعتِ باقی‌مانده» را *دستی* وارد
#   می‌کند (Exam.study_hours_remaining). تجربه نشان می‌دهد این تخمین‌ها
#   سیستماتیک خطا دارند: بعضی‌ها همیشه کمتر از واقع تخمین می‌زنند (ساعتِ
#   بیشتری از طرحِ اولیه مطالعه می‌کنند) و بعضی برعکس. از تاریخچه‌ی
#   گزارش‌های مطالعه (StudyLog) می‌توان این خطای سیستماتیک را *آموخت*:
#
#     برای هر امتحانِ «تمام‌شده» (تاریخش گذشته و گزارشِ مطالعه دارد):
#       planned  = تخمینِ اولیه‌ی کاربر  (باقی‌مانده‌ی نهایی + جمعِ کسرشده‌ها)
#       actual   = واقعیتِ ثبت‌شده         (جمعِ hours_studied همه‌ی گزارش‌ها)
#
#   رابطه‌ی actual ≈ β × planned با «رگرسیونِ کمینه‌ی مربعات از مبدأ»
#   برازش می‌شود (β = Σxy / Σx²). چون نمونه‌ها (امتحان‌هایِ تمام‌شده) در
#   ابتدا کم‌اند، β خام با «انقباضِ بیزی» به‌سمتِ ۱ (یعنی «تخمینِ دستی را
#   بی‌خیال خطا قبول کن») کشیده می‌شود؛ هرچه نمونه بیشتر شود، نظرِ داده‌ی
#   تاریخی وزنِ بیشتری می‌گیرد. خروجی روی هر امتحانِ آینده اعمال می‌شود:
#   «ساعتِ واقعیِ موردنیاز = β × ساعتِ باقی‌مانده‌ی اعلام‌شده».
#
# چرا رگرسیونِ از مبدأ (نه با عرض از مبدأ)؟ دو دلیل: (۱) در مسئله‌ی ما
#   «صفر ساعتِ تخمینی = صفر ساعتِ واقعی» است و عرض از مبدال فقط نویز
#   می‌سازد؛ (۲) برآوردِ از مبدأ به‌طور طبیعی نمونه‌هایِ بزرگ‌تر (امتحان‌های
#   پرحجم‌تر) را وزنِ بیشتری می‌دهد — همان چیزی که در داده‌ی کم‌نمونه
#   پایداریِ بیشتری دارد.
#
# چرا کتابخانه‌ای مثلِ scikit-learn نیامده؟ محدودیتِ عملیاتی: یک وابستگیِ
#   سنگینِ جدید رویِ مسیرِ نصبِ کاربر (که همین حالا هم با شبکه‌ی pypi درگیر
#   است) اضافه می‌کرد؛ در حالی که کلِ مدلِ ما «یک تقسیم و یک جمع» است و در
#   پایتونِ خالص، دقیق و تست‌شدنی نوشته می‌شود — بدونِ هیچ نصبِ جدید.
#
# نکته‌ی طراحی (همان قراردادِ utils.py): توابعِ ریاضیِ این فایل «خالص»
#   هستند — ورودی/خروجیِ ساده‌ی پایتون، بدونِ ORM — تا بدونِ بالا آوردنِ
#   دیتابیس جداگانه تست شوند. فقط دو تابعِ پایینِ فایل (build_training_
#   samples و get_prediction_report) به ORM دست می‌زنند و import مدل‌ها
#   را داخلِ بدنه انجام می‌دهند تا از import چرخه‌ای در امان بمانیم.
#
# محدودیت‌های صادقانه‌ی مدل (مستند می‌مانند):
#   - بازسازیِ «تخمینِ اولیه» فرض می‌کند study_hours_remaining فقط از مسیرِ
#     گزارش‌های مطالعه کم شده است؛ ویرایشِ دستیِ امتحان (PATCH) نویز وارد
#     می‌کند — با انقباضِ بیزی اثرش مهار می‌شود.
#   - امتحانِ نیمه‌کاره‌ی «امروزی» عمداً در آموزش نیست (وگرنه داده‌ی آینده
#     به گذشته نشت می‌کرد — Data Leakage).
# ----------------------------------------------------------------------------

from datetime import date

# --- پارامترهایِ مدل (ثابت‌هایِ ماژول تا در تست‌ها هم قابل‌استناد باشند) ----

# قوتِ «پیشینِ خنثی»: معادلِ ۴ نمونه‌ی فرضی که می‌گویند «β = ۱». با n نمونه‌ی
# واقعی، وزنِ نهایی = (n·β_خام + ۴·۱) / (n + ۴)؛ مثلاً n=2 → داده‌ی کاربر
# فقط یک‌سومِ وزن را دارد و n=12 → سه‌چهارم.
PRIOR_STRENGTH = 4.0

# مهارِ نهاییِ β در بازه‌ی [۰٫۲۵ , ۴] — سپرِ آخر در برابرِ داده‌ی خراب
# (مثلاً گزارش‌های آزمایشیِ غیرواقعی). حتی β=۴ یعنی «کاربر چهار برابرِ
# تخمینش مطالعه کرده» که خودش هشدار جدی است.
FACTOR_MIN = 0.25
FACTOR_MAX = 4.0

# تلورانسِ برچسبِ سوگیری: |β − ۱| ≤ ۱۵٪ → «تخمینِ دقیق».
BIAS_TOLERANCE = 0.15


# ---------------------------------------------------------------------------
# بخشِ ۱ — ریاضیاتِ خالصِ مدل (بدونِ دیتابیس، مستقیماً تست‌پذیر)
# ---------------------------------------------------------------------------

def classify_bias(calibration_factor):
    """
    برچسبِ قابل‌فهمِ سوگیریِ تخمینِ کاربر از رویِ ضریبِ کالیبراسیون.

    مقدارهای خروجی عمداً «ماشین‌خوان»ند (برایِ API و فرانت‌اند)؛ معادلِ
    فارسی/انگلیسیِ نمایشی در i18n.js فرانت‌اند نگاشت می‌شود (نکته‌ی ۶.۱۴
    AI_CONTEXT: رشته‌ی جدیدِ UI باید در دیکشنریِ static/i18n.js بیاید).
    """
    if calibration_factor is None:
        return 'unknown'
    if calibration_factor > 1 + BIAS_TOLERANCE:
        # کاربر کمتر از واقع تخمین می‌زند (بیشتر از طرحش مطالعه کرده)
        return 'underestimates'
    if calibration_factor < 1 - BIAS_TOLERANCE:
        # کاربر بیشتر از واقع تخمین می‌زند (کمتر از طرحش کافی بوده)
        return 'overestimates'
    return 'accurate'


def fit_calibration_model(samples, prior_strength=PRIOR_STRENGTH):
    """
    مدلِ کالیبراسیون را از نمونه‌هایِ (planned, actual) می‌آموزد.

    ورودی: لیستی از دیکشنری‌های {"planned": x > 0, "actual": y ≥ 0} —
    نمونه‌هایِ planned نامعتبر (۰ یا منفی) بی‌صدا کنار گذاشته می‌شوند
    (برازشِ از مبدأ رویِ x=۰ اصلاً تعریف ندارد).

    خروجی: دیکشنریِ مدل:
        status              'ok' | 'no_history'
        raw_factor          β خامِ کمینه‌ی مربعات (یا None اگر نمونه نبود)
        calibration_factor  β نهایی پس از انقباض و مهار — همان که پیش‌بینی
                            می‌کند (بدونِ تاریخچه = ۱٫۰ یعنی «تخمینِ دستی را
                            قبول کن»)
        sample_count        تعدادِ نمونه‌هایِ معتبر
        confidence          n / (n + prior_strength) ∈ [۰,۱) — سهمِ وزنیِ
                            داده‌ی واقعی در برابرِ پیشینِ خنثی
        bias                خروجیِ classify_bias روی β نهایی

    این تابع کاملاً خالص است: هیچ global/DB/زمانی در کار نیست و برایِ
    داده‌ی یکسان، خروجیِ یکسان می‌دهد.
    """
    # نمونه‌هایِ معتبر: فقط planned مثبت (actual منفی هم در دنیایِ این
    # مدل معنا ندارد؛ برایِ مقاومت، همان‌قدر کنار گذاشته می‌شود).
    valid = [
        s for s in samples
        if s.get('planned', 0) > 0 and s.get('actual', 0) >= 0
    ]
    n = len(valid)

    # بدونِ تاریخچه: «مدلِ بی‌طرف» — تخمینِ دستیِ کاربر را بدونِ تغییر
    # قبول می‌کنیم (پیش‌بینیِ ساعت = همان مقدارِ اعلام‌شده).
    if n == 0:
        return {
            'status': 'no_history',
            'raw_factor': None,
            'calibration_factor': 1.0,
            'sample_count': 0,
            'confidence': 0.0,
            'bias': classify_bias(None),
        }

    # کمینه‌ی مربعاتِ «از مبدأ»: β = Σ(x·y) / Σ(x²)
    # (مخرج فقط وقتی صفر می‌شود که همه‌ی plannedها صفر باشند — که با
    # فیلترِ بالا ناممکن است؛ گارد برایِ خوانایی ماند.)
    sum_xy = sum(s['planned'] * s['actual'] for s in valid)
    sum_xx = sum(s['planned'] ** 2 for s in valid)
    raw_factor = (sum_xy / sum_xx) if sum_xx > 0 else 1.0

    # انقباضِ بیزی به‌سمتِ ۱ (پیشینِ خنثی): میانگینِ وزنیِ «نظرِ داده» و
    # «نظرِ پیشین». با n کوچک، پیشین حاکم است؛ با n بزرگ، داده.
    shrunk = (n * raw_factor + prior_strength * 1.0) / (n + prior_strength)

    # مهارِ نهایی در بازه‌ی مجاز (سپرِ داده‌ی خراب/آزمایشی)
    calibration_factor = min(max(shrunk, FACTOR_MIN), FACTOR_MAX)

    return {
        'status': 'ok',
        'raw_factor': raw_factor,
        'calibration_factor': calibration_factor,
        'sample_count': n,
        'confidence': n / (n + prior_strength),
        'bias': classify_bias(calibration_factor),
    }


def predict_hours(model, planned_hours):
    """
    ساعتِ «واقعیِ» موردنیاز را از ساعتِ «اعلام‌شده»ی کاربر پیش‌بینی می‌کند:
    predicted = β نهایی × planned (گرد به یک رقمِ اعشار — عرفِ پروژه).

    پارامترِ model همان دیکشنریِ خروجیِ fit_calibration_model است؛ اگر
    مقدارِ تاریخچه نداشته باشد (β=۱) خروجی دقیقاً خودِ planned است.
    """
    factor = model.get('calibration_factor', 1.0) if model else 1.0
    if planned_hours is None or planned_hours < 0:
        planned_hours = 0.0
    return round(factor * planned_hours, 1)


def assess_exam_risk(predicted_hours, days_left, daily_available_hours):
    """
    ریسکِ «عقب‌افتادن از برنامه» برای یک امتحانِ آینده را می‌سنجد.

    منطق (بر مبنایِ ساعتِ آزادِ روزانه‌ی کاربر از StudyPlan):
      نیازِ روزانه = ساعتِ پیش‌بینی‌شده / روزهایِ باقی‌مانده
      high   : نیازِ روزانه ≥ کلِ ساعتِ آزادِ روزانه (حتی وقف‌کردنِ همه‌ی
               وقتِ آزاد کافی نیست)
      medium : نیازِ روزانه ≥ ۷۵٪ ساعتِ آزاد (تنگ است؛ باقیِ درس‌ها و
               زندگیِ روزمره تحتِ فشار می‌روند)
      low    : کمتر از آن

    نکته‌ها: امتحانِ «امروز» (days_left=۰) برای ریاضیات یک روزِ باقی‌مانده
    فرض می‌شود (max(days_left, 1)) و مقدارِ خامِ days_left برایِ نمایش
    دست‌نخورده در پاسخِ API می‌ماند. سقفِ معقولِ «هر چیزی» به‌عنوانِ ورودی
    پذیرفته می‌شود؛ اعدادِ نامعتبر (منفی/تهی) به‌صورتِ امن نرمال می‌شوند.
    """
    if days_left is None or days_left < 0:
        days_left = 0
    days = max(days_left, 1)

    if predicted_hours is None or predicted_hours <= 0:
        return {'risk': 'low', 'required_daily_hours': 0.0}

    if daily_available_hours is None or daily_available_hours < 0:
        daily_available_hours = 0.0

    required = predicted_hours / days
    if required >= daily_available_hours:
        # حتی اختصاصِ ۱۰۰٪ وقتِ آزادِ روزانه کافی نیست (یا دقیقاً مرزی است)
        risk = 'high'
    elif required >= 0.75 * daily_available_hours:
        risk = 'medium'
    else:
        risk = 'low'

    return {'risk': risk, 'required_daily_hours': round(required, 2)}


# ---------------------------------------------------------------------------
# بخشِ ۲ — اتصال به داده (ORM) — تنها بخشِ غیرخالصِ این ماژول
# ---------------------------------------------------------------------------

def build_training_samples(user, today=None):
    """
    نمونه‌هایِ آموزشیِ (planned, actual) کاربر را از تاریخچه‌اش می‌سازد.

    تعریفِ «امتحانِ تمام‌شده»: exam_date < today و حداقل یک StudyLog دارد.
    (امتحانِ امروز/آینده در آموزش نیست — مدل نباید از آینده‌ای که هنوز
    رخ نداده چیزی «بیندوزد»؛ این همان نظمِ زمانیِ آموزشِ واقعی است.)

    برای هر چنین امتحانی:
      planned = study_hours_remaining فعلی + Σ hours_deducted
                (= بازسازیِ تخمینِ اولیه‌ی کاربر: آنچه مانده + آنچه واقعاً
                از همان تخمین مصرف شده)
      actual  = Σ hours_studied
                (= همه‌ی ساعتی که واقعاً ثبت شده — حتی بیش از طرح، چون
                «مطالعه‌ی اضافه» دقیقاً همان سیگنالِ دست‌کم‌گیری است)

    کارایی: دو کوئری در کل (یک aggregate رویِ StudyLog + یک in_bulk) —
    بدونِ N+1. جداسازی کاربر: هم رویِ user خودِ گزارش‌ها و هم رویِ
    مالکِ درسِ امتحان فیلتر می‌کنیم (لایه‌ی دفاعیِ دوم).
    """
    from django.db.models import Sum  # import داخلِ بدنه (الگوی utils.py)
    from .models import Exam, StudyLog

    if today is None:
        today = date.today()

    # یک ردیف به‌ازای هر امتحانِ گذشته‌ای که گزارش دارد + جمع‌هایِ aggregate
    rows = (
        StudyLog.objects
        .filter(user=user, exam__subject__user=user, exam__exam_date__lt=today)
        .values('exam_id')
        .annotate(
            actual_sum=Sum('hours_studied'),
            deducted_sum=Sum('hours_deducted'),
        )
    )

    exams = Exam.objects.in_bulk([row['exam_id'] for row in rows])

    samples = []
    for row in rows:
        exam = exams.get(row['exam_id'])
        if exam is None:
            continue
        planned = float(exam.study_hours_remaining or 0) + float(row['deducted_sum'] or 0)
        if planned <= 0:
            # تخمینِ اولیه‌ی صفر = هیچ اطلاعاتی درباره‌ی کالیبراسیون نمی‌دهد
            continue
        samples.append({
            'planned': planned,
            'actual': float(row['actual_sum'] or 0),
        })
    return samples


def get_prediction_report(user, daily_available_hours, today=None):
    """
    گزارشِ کاملِ ML را برایِ API می‌سازد (مدل + پیش‌بینیِ امتحان‌هایِ آینده
    + خلاصه). ورودیِ ساعتِ آزادِ روزانه از تنظیماتِ StudyPlan کاربر توسطِ
    ویو تأمین می‌شود (همان منبعی که الگوریتمِ برنامه‌ریزی استفاده می‌کند —
    یک منبعِ حقیقت، نه دو).

    خروجی (شکلِ ثابت برایِ فرانت‌اند — نکته‌ی مشابهِ dashboard):
      {
        "model": {status, calibration_factor, raw_factor, sample_count,
                  confidence, bias, method},
        "predictions": [ {exam_id, subject, exam_date, days_left,
                           planned_hours, predicted_hours,
                           required_daily_hours, risk}, ... ],
        "summary": {exam_count, high_risk, medium_risk, low_risk,
                    total_predicted_hours}
      }
    """
    from .models import Exam  # import داخلِ بدنه (الگوی utils.py)

    if today is None:
        today = date.today()

    samples = build_training_samples(user, today)
    model = fit_calibration_model(samples)

    # امتحان‌هایِ آینده‌ای که هنوز ساعتی برایشان مانده — همان جمعیتی که
    # الگوریتمِ برنامه‌ریزی هم برایشان برنامه می‌سازد (امروز = جزوِ آینده).
    upcoming = (
        Exam.objects
        .filter(subject__user=user, exam_date__gte=today, study_hours_remaining__gt=0)
        .select_related('subject')
        .order_by('exam_date')
    )

    predictions = []
    risk_counts = {'high': 0, 'medium': 0, 'low': 0}
    total_predicted = 0.0

    for exam in upcoming:
        days_left = (exam.exam_date - today).days
        predicted = predict_hours(model, exam.study_hours_remaining)
        assessed = assess_exam_risk(predicted, days_left, daily_available_hours)

        risk_counts[assessed['risk']] += 1
        total_predicted += predicted

        predictions.append({
            'exam_id': exam.pk,
            'subject': exam.subject.name,
            'exam_date': exam.exam_date.isoformat(),
            'days_left': days_left,
            'planned_hours': round(float(exam.study_hours_remaining), 1),
            'predicted_hours': predicted,
            'required_daily_hours': assessed['required_daily_hours'],
            'risk': assessed['risk'],
        })

    # نمایشِ عمومیِ مدل (اعداد گردِ خوانا؛ دقتِ کامل داخلِ تابع‌ها ماند)
    model_public = {
        'status': model['status'],
        'calibration_factor': round(model['calibration_factor'], 2),
        'raw_factor': round(model['raw_factor'], 2) if model['raw_factor'] is not None else None,
        'sample_count': model['sample_count'],
        'confidence': round(model['confidence'], 2),
        'bias': model['bias'],
        'method': 'least-squares-through-origin+shrinkage',
    }

    return {
        'model': model_public,
        'predictions': predictions,
        'summary': {
            'exam_count': len(predictions),
            'high_risk': risk_counts['high'],
            'medium_risk': risk_counts['medium'],
            'low_risk': risk_counts['low'],
            'total_predicted_hours': round(total_predicted, 1),
        },
    }
