# planner/admin.py
# ----------------------------------------------------------------------------
# این فایل مدل‌ها را در «پنل مدیریتِ» آماده و خودکارِ جنگو (Django Admin)
# ثبت می‌کند. با ثبتِ هر مدل، جنگو به‌صورت خودکار یک صفحه‌ی وب برای مشاهده،
# جست‌وجو و ویرایشِ دستیِ آن جدول در آدرسِ /admin/ می‌سازد؛ بدون این‌که
# لازم باشد خودمان HTML یا View بنویسیم.
# ----------------------------------------------------------------------------

from django.contrib import admin
from .models import Subject, Exam, StudyPlan, StudyLog


# دکوریتورِ admin.register(Subject) یعنی: «این کلاس، تنظیماتِ نمایشِ مدلِ
# Subject در پنل ادمین است».
@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    # list_display: کدام ستون‌ها در جدولِ فهرست نمایش داده شوند
    list_display = ['id', 'name', 'difficulty',
                    'target_grade', 'user', 'created_at']
    # list_filter: امکانِ فیلترکردن از نوار کناریِ پنل ادمین
    list_filter = ['difficulty', 'created_at']
    # search_fields: کدام فیلدها با جعبه‌ی جست‌وجو قابل‌جست‌وجو باشند
    search_fields = ['name', 'user__username']


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ['id', 'subject', 'exam_date',
                    'chapters_remaining', 'study_hours_remaining', 'created_at']
    list_filter = ['exam_date', 'created_at']
    search_fields = ['subject__name']


@admin.register(StudyPlan)
class StudyPlanAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'daily_available_hours', 'created_at', 'updated_at']
    list_filter = ['created_at', 'updated_at']
    search_fields = ['user__username']


@admin.register(StudyLog)
class StudyLogAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'exam', 'date', 'hours_studied', 'created_at']
    list_filter = ['date', 'created_at']
    # نکته: exam__subject__name یعنی از روی رابطه‌ی StudyLog -> Exam -> Subject
    # عبور کن و روی فیلدِ name جست‌وجو کن (جست‌وجوی چندپله‌ای در جنگو).
    search_fields = ['user__username', 'exam__subject__name']
