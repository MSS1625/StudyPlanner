# StudyPlanner/backend/planner/utils.py
"""
منطق «هوشمند» برنامه‌ریز مطالعه.

سه تابع اصلی این ماژول:
1. compute_subject_progress   -> درصد پیشرفت یک درس را حساب می‌کند (برای صفحه درس‌ها و داشبورد)
2. generate_study_plan        -> الگوریتم تخصیص ساعت روزانه به تفکیک تاریخ (خام)
3. format_plan_for_frontend   -> خروجی خام بالا را به شکلی که فرانت‌اند نمایش می‌دهد تبدیل می‌کند

هیچ سرویس خارجی‌ای استفاده نمی‌شود؛ همه‌چیز با پایتون خالص و بر پایه‌ی
«سختی درس»، «روزهای باقی‌مانده» و «ساعات باقی‌مانده» محاسبه می‌شود.
"""

from datetime import date, timedelta

# نام روزهای هفته به ترتیب استاندارد پایتون (دوشنبه = 0 ... یکشنبه = 6)
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

    for exam in subject.exams.all():
        logged = sum(log.hours_studied for log in exam.study_logs.all())
        total_hours += exam.study_hours_remaining + logged
        completed_hours += logged

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
    from .models import Exam  # جلوگیری از import چرخه‌ای

    today = date.today()
    exams = Exam.objects.filter(subject__user=user, exam_date__gt=today).select_related("subject").order_by("exam_date")

    if not exams.exists():
        return {"message": "هیچ امتحان آینده‌ای برای برنامه‌ریزی وجود ندارد."}

    # مرحله ۱: محاسبه‌ی «نیاز وزنی» ثابت برای هر امتحان
    exam_needs = []
    total_weighted_need = 0.0

    for exam in exams:
        days_left = (exam.exam_date - today).days
        if days_left <= 0 or exam.study_hours_remaining <= 0:
            continue

        daily_hours_needed = exam.study_hours_remaining / days_left
        weighted_need = daily_hours_needed * exam.subject.difficulty

        exam_needs.append({"exam": exam, "weighted_need": weighted_need})
        total_weighted_need += weighted_need

    if total_weighted_need == 0:
        return {"message": "تمام امتحانات پوشش داده شده‌اند یا ساعت مطالعه باقی‌مانده ندارند."}

    # مرحله ۲: ساخت برنامه برای تک‌تک روزها تا آخرین امتحان
    # سقف ۶۰ روز می‌گذاریم: چون در نهایت فقط «امروز» یا «۷ روز آینده» به
    # کاربر نمایش داده می‌شود، نیازی به ساختن صدها روزِ برنامه برای
    # امتحان‌هایی که خیلی دور هستند نیست (هم کارایی بهتر، هم داده‌ی کمتر).
    plan = {}
    last_exam_date = exams.last().exam_date
    num_days_to_plan = min((last_exam_date - today).days + 1, 60)

    for i in range(num_days_to_plan):
        current_date = today + timedelta(days=i)
        day_str = current_date.isoformat()
        plan[day_str] = []

        hours_to_allocate_today = float(daily_available_hours)

        # نیاز وزنیِ باقی‌مانده در روز جاری (فقط امتحان‌هایی که هنوز برگزار نشده‌اند)
        current_total_weighted_need = sum(
            need["weighted_need"] for need in exam_needs if need["exam"].exam_date >= current_date
        )

        if current_total_weighted_need == 0:
            continue

        # مرحله ۳: توزیع نسبیِ ساعات آزاد امروز بین امتحان‌های باقی‌مانده
        for need in exam_needs:
            exam = need["exam"]
            if exam.exam_date < current_date:
                continue

            proportion = need["weighted_need"] / current_total_weighted_need
            allocated_hours = round(proportion * hours_to_allocate_today, 1)

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
    if "message" in raw_plan:
        return {
            "schedule": [],
            "totals": {"recommended_hours": 0, "average_daily": 0, "top_subjects": []},
            "message": raw_plan["message"],
        }

    sorted_days = sorted(raw_plan.keys())
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
    def _signature(tasks):
        return tuple(sorted((task["subject"], task["hours"]) for task in tasks))

    groups = []
    for entry in day_entries:
        sig = _signature(entry["tasks"])
        if groups and groups[-1]["signature"] == sig:
            groups[-1]["end_date"] = entry["date"]
        else:
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
        span_days = (end - start).days + 1
        per_day_total = round(sum(task["hours"] for task in group["tasks"]), 1)
        is_today_start = start.isoformat() == today_str

        if span_days == 1:
            title = (
                f"امروز - {start.strftime('%Y/%m/%d')}"
                if is_today_start
                else f"{WEEKDAY_FA[start.weekday()]} - {start.strftime('%Y/%m/%d')}"
            )
            hours_badge = f"{per_day_total} ساعت"
        else:
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

        for task in group["tasks"]:
            subject_totals[task["subject"]] = subject_totals.get(task["subject"], 0) + task["hours"] * span_days

    total_days_with_plan = len(day_entries)
    recommended_hours = round(sum(subject_totals.values()), 1)
    average_daily = round(recommended_hours / total_days_with_plan, 1) if total_days_with_plan else 0
    top_subjects = sorted(subject_totals, key=subject_totals.get, reverse=True)[:3]

    result = {
        "schedule": schedule,
        "totals": {
            "recommended_hours": recommended_hours,
            "average_daily": average_daily,
            "top_subjects": top_subjects,
        },
    }
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

    sorted_days = sorted(raw_plan.keys())[:days]
    subject_totals = {}
    for day_str in sorted_days:
        for task in raw_plan.get(day_str, []):
            subject_totals[task["subject"]] = subject_totals.get(task["subject"], 0) + task["hours"]

    if not subject_totals:
        return []

    top_items = sorted(subject_totals.items(), key=lambda item: item[1], reverse=True)[:top_n]
    max_hours = max(hours for _, hours in top_items) or 1

    return [
        {
            "label": name,
            "hours": round(hours, 1),
            "percent": round((hours / max_hours) * 100),
        }
        for name, hours in top_items
    ]
