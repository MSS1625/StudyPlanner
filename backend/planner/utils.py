# StudyPlanner/backend/planner/utils.py
"""
منطق «هوشمند» برنامه‌ریز مطالعه.

سه تابع اصلی این ماژول:
1. compute_subject_progress   -> درصد پیشرفت یک درس را حساب می‌کند (برای صفحه درس‌ها و داشبورد)
2. generate_study_plan        -> الگوریتم تخصیص ساعت روزانه به تفکیک تاریخ (خام)
3. format_plan_for_frontend   -> خروجی خام بالا را به شکلی که فرانت‌اند نمایش می‌دهد تبدیل می‌کند

هیچ سرویس خارجی‌ای استفاده نمی‌شود؛ همه‌چیز با پایتون خالص و بر پایه‌ی
«سختی درس»، «روزهای باقی‌مانده» و «ساعات باقی‌مانده» محاسبه می‌شود.

نکته‌ی طراحی مهم: توابع این فایل تا حد امکان «خالص» (Pure Function) نوشته
شده‌اند، یعنی به‌جای گرفتنِ مستقیمِ کوئری‌ست از دیتابیس، ورودی و خروجیِ آن‌ها
عمدتاً دیکشنری/لیست‌های ساده‌ی پایتون است. همین ویژگی باعث می‌شود بشود این
توابع را بدون بالا آوردنِ کل جنگو، جداگانه تست کرد (نگاه کنید به توضیحات
README.md، بخش «کارهای آینده»).
"""

from datetime import date, timedelta

# نام روزهای هفته به ترتیب استاندارد پایتون (دوشنبه = 0 ... یکشنبه = 6)
# این دیکشنری برای ساختِ عنوانِ فارسیِ هر بلوکِ برنامه (مثل «سه‌شنبه») استفاده می‌شود.
WEEKDAY_FA = {
    0: "دوشنبه",
    1: "سه‌شنبه",
    2: "چهارشنبه",
    3: "پنج‌شنبه",
    4: "جمعه",
    5: "شنبه",
    6: "یکشنبه",
}


def compute_subject_progress(subject):
    """
    درصد پیشرفت یک درس را بر مبنای گزارش‌های مطالعه (StudyLog) محاسبه می‌کند.

    ایده: هر امتحانِ یک درس، مقداری «ساعت باقی‌مانده» دارد که با ثبت هر
    StudyLog کم می‌شود (این کار در متد save() مدل StudyLog انجام می‌شود).
    پس همیشه داریم:
        کل ساعتِ آن امتحان = ساعت باقی‌مانده‌ی فعلی + مجموع ساعات لاگ‌شده

    با جمع این مقدار روی همه‌ی امتحان‌های یک درس، پیشرفت کل درس به دست می‌آید.

    نکته‌ی کارایی: برای جلوگیری از N+1 query، بهتر است در ویو از
    prefetch_related('exams__study_logs') استفاده شود.

    خروجی: تاپل (ساعات مطالعه‌شده, کل ساعات, درصد پیشرفت)
    """
    total_hours = 0.0
    completed_hours = 0.0

    # روی همه‌ی امتحان‌های این درس حلقه می‌زنیم (ممکن است یک درس چند
    # امتحان داشته باشد، مثلاً میان‌ترم و پایان‌ترم)
    for exam in subject.exams.all():
        # مجموع ساعاتی که تا الان برای این امتحانِ خاص لاگ (ثبت) شده
        logged = sum(log.hours_studied for log in exam.study_logs.all())
        # کل حجمِ این امتحان = آنچه هنوز مانده + آنچه از قبل مطالعه شده
        total_hours += exam.study_hours_remaining + logged
        completed_hours += logged

    # اگر اصلاً امتحانی وجود ندارد (یا حجمِ کل صفر است)، تقسیم بر صفر رخ
    # ندهد؛ پیشرفت را صفر برمی‌گردانیم.
    if total_hours <= 0:
        return round(completed_hours, 1), round(total_hours, 1), 0

    progress_percent = round((completed_hours / total_hours) * 100, 1)
    return round(completed_hours, 1), round(total_hours, 1), progress_percent


def generate_study_plan(user, daily_available_hours):
    """
    یک برنامه مطالعه روزانه بر اساس امتحانات آینده، سختی آن‌ها و زمان باقی‌مانده می‌سازد.

    الگوریتم (وزن‌دهی ساده و قابل توضیح - بدون هیچ API خارجی):
        نیاز روزانه‌ی خام یک امتحان = ساعات باقی‌مانده / روزهای باقی‌مانده
        نیاز وزنی = نیاز روزانه‌ی خام × سختی درس (۱ تا ۵)
        سهم هر درس از ساعات آزاد روزانه = نیاز وزنی آن / مجموع نیازهای وزنیِ روزِ جاری

    خروجی: دیکشنری {"YYYY-MM-DD": [{"subject":.., "exam_id":.., "hours":..}, ...]}
    یا در صورت نبود داده‌ی کافی: {"message": "..."}
    """
    # import در همین‌جا (نه بالای فایل) نوشته شده تا از import چرخه‌ای بین
    # utils.py و models.py جلوگیری شود (چون models از جای دیگری utils را
    # صدا نمی‌زند، ولی برای احتیاط این الگو رعایت شده است).
    from .models import Exam  # جلوگیری از import چرخه‌ای

    today = date.today()
    # فقط امتحان‌هایی که تاریخ‌شان *بعد از* امروز است در نظر گرفته می‌شوند
    # (برای امتحانِ همین امروز، دیگر فرصتی برای برنامه‌ریزی نمانده است).
    exams = Exam.objects.filter(subject__user=user, exam_date__gt=today).select_related("subject").order_by("exam_date")

    # اگر اصلاً امتحانِ آینده‌ای ثبت نشده، برنامه‌ای هم برای ساختن نیست.
    if not exams.exists():
        return {"message": "هیچ امتحان آینده‌ای برای برنامه‌ریزی وجود ندارد."}

    # مرحله ۱: محاسبه‌ی «نیاز وزنی» ثابت برای هر امتحان
    # (این مقدار در طول روزهای مختلف تغییر نمی‌کند؛ فقط با گذشتن تاریخِ
    # امتحان از محاسبات بعدی کنار گذاشته می‌شود)
    exam_needs = []
    total_weighted_need = 0.0

    for exam in exams:
        days_left = (exam.exam_date - today).days
        # اگر امتحان امروز/گذشته باشد یا دیگر ساعتی برایش نمانده، رد شو
        if days_left <= 0 or exam.study_hours_remaining <= 0:
            continue

        # نیاز خام روزانه: اگر همین امروز بخواهیم به‌طور یکنواخت تا امتحان
        # درس بخوانیم، روزی چند ساعت لازم است؟
        daily_hours_needed = exam.study_hours_remaining / days_left
        # ضرب در سختیِ درس: درسِ سخت‌تر حتی با نیازِ خامِ یکسان، وزنِ بیشتری می‌گیرد
        weighted_need = daily_hours_needed * exam.subject.difficulty

        exam_needs.append({"exam": exam, "weighted_need": weighted_need})
        total_weighted_need += weighted_need

    # اگر بعد از فیلتر بالا هیچ امتحانِ «فعالی» نماند (مثلاً همه پوشش داده شده‌اند)
    if total_weighted_need == 0:
        return {"message": "تمام امتحانات پوشش داده شده‌اند یا ساعت مطالعه باقی‌مانده ندارند."}

    # مرحله ۲: ساخت برنامه برای تک‌تک روزها تا آخرین امتحان
    # سقف ۶۰ روز می‌گذاریم: چون در نهایت فقط «امروز» یا «۷ روز آینده» به
    # کاربر نمایش داده می‌شود، نیازی به ساختن صدها روزِ برنامه برای
    # امتحان‌هایی که خیلی دور هستند نیست (هم کارایی بهتر، هم داده‌ی کمتر).
    plan = {}
    last_exam_date = exams.last().exam_date
    num_days_to_plan = min((last_exam_date - today).days + 1, 60)

    # حلقه‌ی اصلی: برای هرکدام از روزهای آینده (امروز تا حداکثر ۶۰ روز بعد)
    for i in range(num_days_to_plan):
        current_date = today + timedelta(days=i)
        day_str = current_date.isoformat()  # تبدیل به رشته مثل "2026-07-20" برای استفاده به‌عنوان کلید دیکشنری
        plan[day_str] = []

        # کل ساعتِ آزادِ کاربر که باید بین درس‌های امروز تقسیم شود
        hours_to_allocate_today = float(daily_available_hours)

        # نیاز وزنیِ باقی‌مانده در روز جاری (فقط امتحان‌هایی که هنوز برگزار نشده‌اند)
        # یعنی امتحان‌هایی که تاریخ‌شان از امروز گذشته، از این جمع کنار گذاشته می‌شوند.
        current_total_weighted_need = sum(
            need["weighted_need"] for need in exam_needs if need["exam"].exam_date >= current_date
        )

        # اگر هیچ امتحانِ فعالی برای این روز نمانده (یعنی همه گذشته‌اند)، این
        # روز را خالی رها کن و برو سراغ روز بعد.
        if current_total_weighted_need == 0:
            continue

        # مرحله ۳: توزیع نسبیِ ساعات آزاد امروز بین امتحان‌های باقی‌مانده
        for need in exam_needs:
            exam = need["exam"]
            # این امتحان که تاریخش گذشته را نادیده بگیر
            if exam.exam_date < current_date:
                continue

            # سهمِ این درس از کلِ نیازِ وزنیِ امروز (عددی بین صفر و یک)
            proportion = need["weighted_need"] / current_total_weighted_need
            # همان سهم را در ساعتِ آزادِ کاربر ضرب می‌کنیم تا ساعتِ واقعی به دست بیاید
            allocated_hours = round(proportion * hours_to_allocate_today, 1)

            # فقط اگر مقدارِ معناداری (بیشتر از صفر) به این درس تعلق گرفت، ثبتش کن
            if allocated_hours > 0:
                plan[day_str].append({
                    "subject": exam.subject.name,
                    "exam_id": exam.id,
                    "hours": allocated_hours,
                })

    return plan


def format_plan_for_frontend(raw_plan, range_type="daily"):
    """
    خروجیِ خامِ generate_study_plan را به ساختاری تبدیل می‌کند که صفحه‌ی
    «برنامه مطالعه» در فرانت‌اند مستقیماً می‌تواند رندر کند:

        {
          "schedule": [
              {"title": "...", "total_hours": 3.5, "hours_badge": "3.5 ساعت",
               "days_covered": 1, "tasks": [{"subject": "..", "hours": 1.5}, ...]},
              ...
          ],
          "totals": {
              "recommended_hours": 7.0,
              "average_daily": 3.5,
              "top_subjects": ["ریاضی", "فیزیک"]
          }
        }

    range_type:
        "daily"  -> فقط امروز
        "weekly" -> ۷ روز آینده

    نکته‌ی طراحی: تا وقتی تاریخ هیچ امتحانی نگذرد، الگوریتم دقیقاً همان
    ترکیبِ درس/ساعت را برای روزهای پیاپی پیشنهاد می‌دهد (چون هیچ‌کدام از
    وزن‌ها تغییر نکرده). نمایش چند بلوکِ کاملاً یکسان زیر هم در نمای هفتگی
    تکراری و بی‌فایده به‌نظر می‌رسد؛ برای همین روزهای پیاپیِ هم‌برنامه را در
    یک «بازه» ادغام می‌کنیم (مثلاً «امروز تا پنج‌شنبه»).
    """
    # اگر generate_study_plan اصلاً برنامه‌ای نساخته (فقط یک پیامِ توضیحی
    # برگردانده)، همان پیام را با ساختارِ خالی به فرانت‌اند پاس می‌دهیم.
    if "message" in raw_plan:
        return {
            "schedule": [],
            "totals": {"recommended_hours": 0, "average_daily": 0, "top_subjects": []},
            "message": raw_plan["message"],
        }

    # کلیدهای دیکشنری (تاریخ‌ها) را مرتب می‌کنیم تا روزها به ترتیب زمانی باشند
    sorted_days = sorted(raw_plan.keys())
    # بسته به این‌که کاربر «روزانه» یا «هفتگی» خواسته، فقط ۱ یا ۷ روزِ اول را برمی‌داریم
    days_to_show = sorted_days[:7] if range_type == "weekly" else sorted_days[:1]
    today_str = date.today().isoformat()

    # مرحله ۱: فقط روزهایی که کاری برایشان هست را نگه می‌داریم
    day_entries = []
    for day_str in days_to_show:
        tasks = raw_plan.get(day_str, [])
        if not tasks:
            continue
        day_entries.append({
            "date": date.fromisoformat(day_str),
            "tasks": [{"subject": task["subject"], "hours": task["hours"]} for task in tasks],
        })

    # مرحله ۲: روزهای پیاپی با ترکیب دقیقاً یکسان را در یک گروه ادغام می‌کنیم
    # (تابعِ داخلیِ کوچک زیر، یک «امضا»/شناسه از ترکیبِ درس‌ها و ساعت‌های هر
    # روز می‌سازد؛ اگر دو روزِ پشت‌سرهم امضای یکسانی داشته باشند، یعنی برنامه‌شان
    # کاملاً یکی است و می‌شود آن‌ها را یک بازه در نظر گرفت.)
    def _signature(tasks):
        return tuple(sorted((task["subject"], task["hours"]) for task in tasks))

    groups = []
    for entry in day_entries:
        sig = _signature(entry["tasks"])
        # اگر امضای این روز با امضای آخرین گروهِ ساخته‌شده یکی بود، فقط
        # تاریخِ پایانِ آن گروه را جلو می‌بریم (بدون ساختنِ گروهِ جدید)
        if groups and groups[-1]["signature"] == sig:
            groups[-1]["end_date"] = entry["date"]
        else:
            # وگرنه یک گروهِ تازه (با شروع و پایانِ یکسان، فعلاً فقط همین یک روز) می‌سازیم
            groups.append({
                "start_date": entry["date"],
                "end_date": entry["date"],
                "tasks": entry["tasks"],
                "signature": sig,
            })

    # مرحله ۳: از هر گروه، یک بلوکِ نمایشی برای فرانت‌اند می‌سازیم
    schedule = []
    subject_totals = {}

    for group in groups:
        start, end = group["start_date"], group["end_date"]
        # چند روزِ تقویمی این گروه پوشش می‌دهد (اگر تک‌روزه باشد، ۱ می‌شود)
        span_days = (end - start).days + 1
        per_day_total = round(sum(task["hours"] for task in group["tasks"]), 1)
        is_today_start = start.isoformat() == today_str

        if span_days == 1:
            # حالت ساده: فقط یک روز؛ عنوان یا «امروز» است یا نامِ روزِ هفته
            title = (
                f"امروز - {start.strftime('%Y/%m/%d')}"
                if is_today_start
                else f"{WEEKDAY_FA[start.weekday()]} - {start.strftime('%Y/%m/%d')}"
            )
            hours_badge = f"{per_day_total} ساعت"
        else:
            # حالتِ ادغام‌شده: عنوان به‌صورت «از روزِ شروع تا روزِ پایان» ساخته می‌شود
            start_label = "امروز" if is_today_start else WEEKDAY_FA[start.weekday()]
            title = f"{start_label} تا {WEEKDAY_FA[end.weekday()]} ({start.strftime('%Y/%m/%d')} تا {end.strftime('%Y/%m/%d')})"
            hours_badge = f"{per_day_total} ساعت در روز"

        schedule.append({
            "title": title,
            "total_hours": per_day_total,
            "hours_badge": hours_badge,
            "days_covered": span_days,
            "tasks": group["tasks"],
        })

        # برای محاسبه‌ی «پرکارترین درس‌ها»ی کلِ بازه، سهمِ هر درس را در تعداد
        # روزهایی که این گروه پوشش می‌دهد ضرب می‌کنیم (چون این ساعت، ساعتِ
        # *هر روزِ* آن گروه است، نه فقط یک روز).
        for task in group["tasks"]:
            subject_totals[task["subject"]] = subject_totals.get(task["subject"], 0) + task["hours"] * span_days

    # مجموعِ واقعیِ روزهایی که برایشان برنامه ساخته شده (برای محاسبه‌ی میانگین)
    total_days_with_plan = len(day_entries)
    recommended_hours = round(sum(subject_totals.values()), 1)
    average_daily = round(recommended_hours / total_days_with_plan, 1) if total_days_with_plan else 0
    # سه درسی که بیشترین ساعت را در این بازه گرفته‌اند (برای نمایش خلاصه در فرانت‌اند)
    top_subjects = sorted(subject_totals, key=subject_totals.get, reverse=True)[:3]

    result = {
        "schedule": schedule,
        "totals": {
            "recommended_hours": recommended_hours,
            "average_daily": average_daily,
            "top_subjects": top_subjects,
        },
    }
    # اگر بعد از همه‌ی این پردازش، هیچ بلوکی باقی نماند، یک پیامِ توضیحی اضافه کن
    if not schedule:
        result["message"] = "برای بازه‌ی انتخاب‌شده، برنامه‌ای برای نمایش وجود ندارد."
    return result


def build_subject_distribution(raw_plan, days=7, top_n=6):
    """
    داده‌ی نمودار میله‌ای «تقسیم‌زمان پیشنهادی» را می‌سازد.

    نکته‌ی مهم: چون الگوریتم هر روز کل «ساعت آزاد روزانه» را به‌طور کامل بین
    درس‌های فعال تقسیم می‌کند، مجموعِ ساعتِ هر روز تقریباً همیشه با روزِ بعدی
    یکسان است (چون جمعِ سهم‌ها همیشه برابر با همان عدد ثابت است) — پس نموداری
    که بر مبنای «روز» باشد عملاً صاف و بی‌معنی از آب درمی‌آید.

    چیزی که واقعاً بین روزها فرق می‌کند «سهم هر درس» از این ساعات است (چون
    سختی و فوریتِ امتحان هر درس متفاوت است). پس این تابع، ساعات هرکدام از
    درس‌ها را در طول `days` روز آینده جمع می‌زند و نسبت به پرکارترین درس
    نرمال می‌کند.
    """
    if "message" in raw_plan:
        return []

    # فقط N روزِ اول (پیش‌فرض ۷ روز) را در نظر می‌گیریم
    sorted_days = sorted(raw_plan.keys())[:days]
    subject_totals = {}
    for day_str in sorted_days:
        for task in raw_plan.get(day_str, []):
            # جمع‌زدنِ ساعاتِ هر درس در طولِ کل بازه
            subject_totals[task["subject"]] = subject_totals.get(task["subject"], 0) + task["hours"]

    if not subject_totals:
        return []

    # فقط پرکارترین درس‌ها (حداکثر top_n تا) را برای نمودار نگه می‌داریم
    top_items = sorted(subject_totals.items(), key=lambda item: item[1], reverse=True)[:top_n]
    # پرکارترین درس، مبنای نرمال‌سازی (۱۰۰٪) قرار می‌گیرد؛ بقیه نسبت به آن سنجیده می‌شوند
    max_hours = max(hours for _, hours in top_items) or 1

    return [
        {
            "label": name,
            "hours": round(hours, 1),
            "percent": round((hours / max_hours) * 100),
        }
        for name, hours in top_items
    ]
