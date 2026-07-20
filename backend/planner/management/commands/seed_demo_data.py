# planner/management/commands/seed_demo_data.py
"""
دستور کمکی برای تست: برای یک کاربر مشخص چند درس و امتحانِ نمونه با
تاریخ‌های *آینده* می‌سازد تا بشه داشبورد (تقویم مطالعه، هشدارها،
تقسیم‌زمان پیشنهادی) و صفحه‌ی برنامه‌ مطالعه را با داده‌ی واقعی دید.

اجرا:
    python manage.py seed_demo_data ali_test_115
    python manage.py seed_demo_data ali_test_115 --reset   # پاک کردن داده‌ی قبلی همین کاربر
"""

from datetime import date, timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from planner.models import Subject, Exam, StudyLog


class Command(BaseCommand):
    help = (
        "برای یک کاربر مشخص، چند درس و امتحانِ نمونه با تاریخ‌های آینده می‌سازد "
        "تا بتوان داشبورد و برنامه‌ریز مطالعه را با داده‌ی واقعی تست کرد."
    )

    def add_arguments(self, parser):
        parser.add_argument("username", type=str, help="نام کاربری‌ای که باید براش داده‌ی نمونه ساخته شود")
        parser.add_argument(
            "--reset",
            action="store_true",
            help="قبل از ساخت داده‌ی جدید، تمام درس‌ها و امتحان‌های قبلیِ همین کاربر حذف شود",
        )

    def handle(self, *args, **options):
        username = options["username"]
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError(f'کاربری با نام کاربری "{username}" پیدا نشد.')

        if options["reset"]:
            deleted, _ = Subject.objects.filter(user=user).delete()
            self.stdout.write(self.style.WARNING(f"{deleted} رکورد قدیمی (درس/امتحان/لاگ) این کاربر پاک شد."))

        # اگر این درس‌ها از قبل برای کاربر وجود داشته باشند (با همین نام)،
        # get_or_create همان رکورد موجود را برمی‌گرداند و چیزی تکراری ساخته نمی‌شود.
        sample_data = [
            {"name": "مهندسی اینترنت", "difficulty": 4, "target_grade": 18, "days_ahead": 3, "hours": 12, "chapters": 4},
            {"name": "پایگاه داده", "difficulty": 3, "target_grade": 17, "days_ahead": 6, "hours": 8, "chapters": 3},
            {"name": "ساختار داده", "difficulty": 5, "target_grade": 19, "days_ahead": 10, "hours": 16, "chapters": 6},
            {"name": "معماری کامپیوتر", "difficulty": 2, "target_grade": 16, "days_ahead": 18, "hours": 6, "chapters": 2},
        ]

        today = date.today()
        created_subjects = 0
        created_exams = 0

        for index, item in enumerate(sample_data):
            subject, created = Subject.objects.get_or_create(
                user=user,
                name=item["name"],
                defaults={"difficulty": item["difficulty"], "target_grade": item["target_grade"]},
            )
            if created:
                created_subjects += 1

            # اگر این درس همین الان یک امتحانِ آینده دارد، دست‌نخورده رهایش می‌کنیم
            if subject.exams.filter(exam_date__gte=today).exists():
                continue

            exam = Exam.objects.create(
                subject=subject,
                exam_date=today + timedelta(days=item["days_ahead"]),
                chapters_remaining=item["chapters"],
                study_hours_remaining=item["hours"],
            )
            created_exams += 1

            # روی اولین درس، کمی «مطالعه‌ی انجام‌شده» هم ثبت می‌کنیم تا نوار
            # پیشرفت در داشبورد صفر نباشد (تست منطق StudyLog هم همین‌جا انجام می‌شود).
            if index == 0:
                StudyLog.objects.create(
                    user=user,
                    exam=exam,
                    date=today - timedelta(days=1),
                    hours_studied=round(item["hours"] * 0.3, 1),
                    notes="لاگ نمونه (تولیدشده توسط seed_demo_data)",
                )

        self.stdout.write(self.style.SUCCESS(
            f'انجام شد: {created_subjects} درسِ جدید و {created_exams} امتحانِ جدید برای «{username}» ساخته شد.'
        ))
        self.stdout.write("حالا صفحه‌ی داشبورد و برنامه‌ مطالعه را در مرورگر رفرش کن.")
