# planner/models.py
# ----------------------------------------------------------------------------
# این فایل «مدل‌های داده» (Data Models) اپلیکیشن را تعریف می‌کند.
# هر کلاس در این فایل معادل یک جدول در دیتابیس است (به کمک ORM جنگو) و
# فیلدهای کلاس، همان ستون‌های آن جدول هستند. رابطه‌ی بین جدول‌ها (کلید خارجی/
# ForeignKey) هم همین‌جا تعریف می‌شود.
#
# ترتیب منطقی مدل‌ها: هر کاربر (User) چند «درس» (Subject) دارد؛ هر درس چند
# «امتحان» (Exam) دارد؛ برای هر امتحان، کاربر می‌تواند چند «گزارش مطالعه»
# (StudyLog) ثبت کند؛ و هر کاربر یک رکورد «تنظیمات برنامه‌ی مطالعه»
# (StudyPlan) دارد.
# ----------------------------------------------------------------------------

from django.db import models
# User: مدل آماده‌ی جنگو برای کاربر (شامل username، password هش‌شده و...)
from django.contrib.auth.models import User
# اعتبارسنجی مقادیر عددی (مثلاً سختی درس نباید بیشتر از ۵ باشد)
from django.core.validators import MinValueValidator, MaxValueValidator
# برای گرفتن تاریخ/زمان جاری (به‌عنوان مقدار پیش‌فرض فیلد تاریخ)
from django.utils import timezone


class Subject(models.Model):
    """
    یک «درس» که کاربر برای مطالعه ثبت کرده است.
    هر کاربر می‌تواند چند درس داشته باشد (رابطه‌ی یک‌به‌چند از طریق ForeignKey).
    """
    # ForeignKey یعنی هر درس دقیقاً به یک کاربر متعلق است.
    # on_delete=CASCADE یعنی اگر آن کاربر حذف شود، درس‌هایش هم حذف می‌شوند.
    # related_name='subjects' یعنی از سمت User می‌توان با user.subjects.all()
    # به همه‌ی درس‌های آن کاربر دسترسی پیدا کرد.
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='subjects')

    # نام درس (مثلاً «ریاضی عمومی»)
    name = models.CharField(max_length=200)

    # سختی درس به‌صورت عددی بین ۱ (خیلی آسان) تا ۵ (خیلی سخت).
    # این عدد مستقیماً در فرمول الگوریتم برنامه‌ریزی (utils.py) ضرب می‌شود.
    difficulty = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="سختی درس از 1 تا 5",
        default=3
    )

    # هدف نمره‌ی دلخواه کاربر برای این درس؛ اختیاری است (می‌تواند خالی بماند)
    # null=True یعنی در دیتابیس مقدار NULL مجاز است
    # blank=True یعنی در فرم/سریالایزر، خالی‌گذاشتنش خطا نمی‌دهد
    target_grade = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(20)],
        help_text="هدف نمره (اختیاری)"
    )

    # یادداشت کوتاهِ اختیاری درباره‌ی درس (مثلاً «نصف نمره از تمرین‌ها می‌آید»).
    # این فیلد قبلاً در فرمِ subjects.html جمع‌آوری می‌شد ولی در مدل وجود نداشت
    # (فیلد یتیم — رفع شد)؛ الگوی آن از StudyLog.notes گرفته شده است:
    # null=True در سطح دیتابیس + blank=True در سطح فرم/سریالایزر.
    notes = models.TextField(
        blank=True,
        null=True,
        help_text="یادداشت کوتاه درباره‌ی درس (اختیاری)"
    )

    # زمان ایجاد رکورد؛ فقط یک‌بار و به‌صورت خودکار هنگام ساخت پر می‌شود
    created_at = models.DateTimeField(auto_now_add=True)
    # زمان آخرین ویرایش؛ هر بار save() صدا زده شود، خودکار به‌روز می‌شود
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # جدیدترین درس‌ها اول نمایش داده شوند
        ordering = ['-created_at']
        # هیچ کاربری نمی‌تواند دو درس هم‌نام داشته باشد
        # (این محدودیت در سطح خودِ دیتابیس اعمال می‌شود، نه فقط در کد پایتون)
        unique_together = ['user', 'name']

    def __str__(self):
        # این متد تعیین می‌کند وقتی یک Subject را چاپ کنیم یا در پنل ادمین
        # ببینیم، چه متنی نمایش داده شود.
        return f"{self.name} ({self.user.username})"


class Exam(models.Model):
    """
    یک «امتحان» که به یک درس مشخص تعلق دارد.
    یک درس می‌تواند چند امتحان داشته باشد (مثلاً میان‌ترم و پایان‌ترم).
    """
    # هر امتحان دقیقاً به یک درس وصل است.
    # related_name='exams' یعنی subject.exams.all() همه‌ی امتحان‌های آن درس را می‌دهد.
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='exams')

    # تاریخ برگزاری امتحان؛ الگوریتم برنامه‌ریزی بر مبنای همین فیلد،
    # «چند روز تا امتحان مانده» را حساب می‌کند.
    exam_date = models.DateField(help_text="تاریخ امتحان")

    # تعداد فصل‌های باقی‌مانده (فعلاً بیشتر جنبه‌ی اطلاعاتی دارد و در فرمول
    # اصلیِ الگوریتم مستقیماً استفاده نمی‌شود؛ study_hours_remaining معیار اصلی است)
    chapters_remaining = models.IntegerField(
        validators=[MinValueValidator(0)], default=0,
        help_text="تعداد فصل‌های باقی‌مانده"
    )

    # مهم‌ترین فیلد این مدل: چند ساعت مطالعه تا رسیدن به آمادگیِ کامل باقی مانده.
    # این مقدار هر بار که کاربر یک StudyLog جدید ثبت می‌کند، خودکار کم می‌شود
    # (نگاه کنید به متد StudyLog.save() در پایین همین فایل).
    study_hours_remaining = models.FloatField(
        validators=[MinValueValidator(0)],default=0.0,
        help_text="ساعت مطالعه باقی‌مانده"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # امتحان‌ها بر اساس تاریخ (نزدیک‌ترین اول) مرتب می‌شوند
        ordering = ['exam_date']

    def __str__(self):
        return f"{self.subject.name} - {self.exam_date}"


class StudyPlan(models.Model):
    """
    این مدل نقشِ «تنظیمات برنامه‌ی مطالعه‌ی هر کاربر» را دارد: این‌که کاربر
    روزانه چند ساعت زمان آزاد برای مطالعه دارد، و آخرین برنامه‌ی محاسبه‌شده
    (برای کش/مرجع) در فیلد plan_data ذخیره می‌شود.

    نکته: در views.py با الگوی get_or_create از این مدل استفاده می‌شود، یعنی
    عملاً هر کاربر یک رکورد (تنظیمات) دارد، نه چند رکورد جداگانه.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='study_plans')

    # چند ساعت در روز، کاربر برای مطالعه وقت آزاد دارد؛ این عدد مستقیماً در
    # فرمول تخصیصِ روزانه‌ی الگوریتم (generate_study_plan) ضرب می‌شود.
    daily_available_hours = models.FloatField(
        validators=[MinValueValidator(0)],
        help_text="ساعت آزاد روزانه برای مطالعه"
    )

    # آخرین خروجیِ الگوریتم (دیکشنری تاریخ -> لیست تسک‌ها) به‌صورت JSON خام
    # ذخیره می‌شود. این فیلد بیشتر جنبه‌ی مرجع/تاریخچه دارد؛ چون در عمل هر
    # بار که کاربر صفحه‌ی برنامه را باز می‌کند، برنامه از نو (زنده) محاسبه
    # می‌شود، نه این‌که از همین فیلد خوانده شود.
    plan_data = models.JSONField(
        default=dict,
        help_text="برنامه مطالعه روزانه به صورت JSON"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"برنامه {self.user.username}"


class StudyLog(models.Model):
    """
    یک «گزارش مطالعه»: ثبتِ این‌که کاربر در یک تاریخ مشخص، چند ساعت روی
    یک امتحانِ خاص کار کرده است. این مدل حلقه‌ی بازخورد سیستم را می‌بندد:
    هرچه کاربر بیشتر مطالعه را ثبت کند، هم ساعتِ باقی‌مانده‌ی امتحان کم
    می‌شود و هم درصد پیشرفتِ درس (که در serializers.py محاسبه می‌شود) بالا می‌رود.
    """
    # چه کسی این گزارش را ثبت کرده (برای فیلتر کردنِ داده‌ی هر کاربر در API)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='study_logs')
    # این مطالعه برای کدام امتحان بوده است
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='study_logs')
    # تاریخ انجام مطالعه (پیش‌فرض: امروز)
    date = models.DateField(default=timezone.now)
    # چند ساعت مطالعه شده (حداقل ۰.۱ ساعت، یعنی مقدار صفر یا منفی مجاز نیست)
    hours_studied = models.FloatField(validators=[MinValueValidator(0.1)])
    notes = models.TextField(blank=True, null=True) # توضیحات اختیاری

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # جدیدترین گزارش‌ها اول نمایش داده شوند
        ordering = ['-date', '-created_at']

    def save(self, *args, **kwargs):
        """
        این متد رفتار پیش‌فرضِ ذخیره‌سازی جنگو را «گسترش» می‌دهد (Override):
        علاوه بر ذخیره‌ی خودِ گزارش مطالعه، به‌صورت خودکار ساعتِ باقی‌مانده‌ی
        امتحانِ مربوطه را هم به‌روزرسانی می‌کند. این یعنی سازنده‌ی این پروژه
        مجبور نیست هر بار در views.py دستی این کار را انجام دهد؛ منطق درست
        در همان جایی نگه‌داری می‌شود که به آن مربوط است (مدل خودِ داده).
        """
        # بررسی می‌کنیم که آیا این یک رکورد جدید است یا داریم رکورد قبلی را ویرایش می‌کنیم؟
        # اگر pk (کلید اصلی/شناسه) هنوز مقداری ندارد، یعنی این رکورد تازه ساخته می‌شود.
        is_new = self.pk is None

        # ابتدا خود گزارش مطالعه را در دیتابیس ذخیره می‌کنیم
        # (super().save() یعنی رفتار اصلیِ ذخیره‌سازیِ جنگو را همچنان اجرا کن)
        super().save(*args, **kwargs)

        # اگر رکورد جدید بود، ساعات مطالعه را از امتحان مربوطه کم می‌کنیم
        # (برای رکوردهای ویرایش‌شده این کار تکرار نمی‌شود، تا کسر شدن دوباره
        # هنگام هر ذخیره‌ی مجدد رخ ندهد)
        if is_new:
            if self.exam.study_hours_remaining > 0:
                self.exam.study_hours_remaining -= self.hours_studied
                # برای جلوگیری از منفی شدن ساعات باقی‌مانده
                if self.exam.study_hours_remaining < 0:
                    self.exam.study_hours_remaining = 0
                self.exam.save()

    def __str__(self):
        return f"{self.user.username} - {self.exam.subject.name} - {self.hours_studied} hours"
