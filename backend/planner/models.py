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

from django.db import models, transaction
# User: مدل آماده‌ی جنگو برای کاربر (شامل username، password هش‌شده و...)
from django.contrib.auth.models import User
# اعتبارسنجی مقادیر عددی (مثلاً سختی درس نباید بیشتر از ۵ باشد)
from django.core.validators import MinValueValidator, MaxValueValidator
# برای گرفتن تاریخ/زمان جاری (به‌عنوان مقدار پیش‌فرض فیلد تاریخ)
from django.utils import timezone
# برچسب‌های نوعِ رویدادِ امنیتی تا زمانِ رندر ترجمه‌نشده می‌مانند و با
# زبانِ درخواست (Accept-Language) ترجمه می‌شوند (همان الگوی WEEKDAY_FA).
from django.utils.translation import gettext_lazy


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

    # یادداشتِ اختیاری درباره‌ی امتحان (مثلاً «میان‌ترم، سالنِ ۲، chapters 1-5»).
    # (فیلدِ یتیمِ فرم — رفع شد): فرمِ امتحان در exams.html از قبل یک textarea
    # یادداشت داشت که مقدارش بی‌صدا دور ریخته می‌شد؛ الگوی آن از Subject.notes
    # و StudyLog.notes گرفته شده است. با قابلیتِ «ویرایشِ امتحان» کامل شد.
    notes = models.TextField(
        blank=True, null=True, help_text="یادداشت اختیاری درباره‌ی امتحان"
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
    (از مایگریشنِ 0008 این یکتایی در سطحِ خودِ دیتابیس هم با قیدِ
    UNIQUE روی ستونِ user_id تضمین می‌شود؛ پیش از اعمالِ قید، رکورد‌های
    تکراریِ احتمالی در خودِ مایگریشن پاکسازی می‌شوند.)
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='study_plans',
        # OneToOneField = ForeignKey با قیدِ یکتاییِ داخلی: هر کاربر
        # حداکثر یک رکوردِ «تنظیماتِ برنامه» دارد. این قید از مایگریشنِ
        # 0008 در خودِ دیتابیس اعمال می‌شود و الگوی get_or_create در
        # views.py را در برابرِ درخواست‌هایِ هم‌زمان (Race
        # Condition) مصون می‌کند.
    )

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
    # چند ساعت از «ساعتِ باقی‌مانده‌ی» امتحانِ مربوطه، در لحظه‌ی ثبتِ همین
    # گزارش «واقعاً» کم شده است (مبنای بازگرداندنِ ساعت در delete() پایین).
    # چرا این فیلد لازم است؟ چون کسرِ ساعت در save() به مقدارِ موجودِ امتحان
    # محدود است و هرگز منفی نمی‌شود؛ مثلاً اگر فقط ۲ ساعت مانده باشد و کاربر
    # ۵ ساعت مطالعه ثبت کند، دقیقاً ۲ ساعت کسر می‌شود (نه ۵). پس هنگامِ حذفِ
    # گزارش هم باید دقیقاً «همان ۲ ساعت» برگردد، نه ۵ ساعت — این فیلد همان
    # عددِ دقیق را به ازای هر گزارش نگه می‌دارد (از Migration 0007 به بعد).
    hours_deducted = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0)],
        help_text="ساعتِ واقعاً کسرشده از امتحان (مبنای بازگرداندن هنگام حذف)"
    )
    notes = models.TextField(blank=True, null=True) # توضیحات اختیاری

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # جدیدترین گزارش‌ها اول نمایش داده شوند
        ordering = ['-date', '-created_at']

    def save(self, *args, **kwargs):
        """
        این متد رفتار پیش‌فرضِ ذخیره‌سازیِ جنگو را «گسترش» می‌دهد (Override):
        علاوه بر ذخیره‌ی خودِ گزارش مطالعه، به‌صورتِ خودکار ساعتِ باقی‌مانده‌ی
        امتحانِ مربوطه را هم کم می‌کند — و برخلافِ گذشته، کلِ این عملیات
        داخلِ یک تراکنشِ اتمیک انجام می‌شود (یا هر دو، یا هیچ‌کدام).

        قفلِ هم‌زمانی (2026-09-09): پیش از هر خواندن/نوشتنِ «ساعتِ باقی‌مانده»،
        سطرِ امتحان با select_for_update() قفل و از دیتابیس «تازه» خوانده
        می‌شود؛ پس مبنایِ محاسبه‌ی کسر، مقدارِ لحظه‌ایِ دیتابیس است، نه
        snapshotِ ممکن‌الوقوعِ در حافظه — دو درخواستِ هم‌زمان دیگر نمی‌توانند
        کسرِ یکدیگر را «از دست بدهند» (Lost Update).
        (SQLite قفلِ FOR UPDATE را بی‌صدا نادیده می‌گیرد؛ «خواندنِ تازه»
        به‌تنهایی بخشِ عمده‌یِ آثارِ Lost Update را از بین می‌برد و قفلِ
        واقعیِ سطر در PostgreSQL/MySQL فعال می‌شود — پیش‌نیازِ چندکاربره.)
        """
        # بررسی می‌کنیم که آیا این یک رکورد جدید است یا داریم رکورد قبلی را ویرایش می‌کنیم؟
        # اگر pk (کلید اصلی/شناسه) هنوز مقداری ندارد، یعنی این رکورد تازه ساخته می‌شود.
        is_new = self.pk is None

        # کلِ عملیاتِ «قفل + ذخیره‌ی گزارش + کسرِ ساعتِ امتحان» یکپارچه و اتمیک
        # است: اگر قدمِ آخر شکست بخورد، هیچ‌کدام commit نمی‌شوند و گزارشی
        # نیمه‌کاره (بدونِ کسرِ ساعت) باقی نمی‌ماند.
        with transaction.atomic():
            locked_exam = None
            if is_new:
                # سطرِ امتحان را قفل و «تازه» می‌خوانیم. عمداً self.exam_id
                # (نه self.exam) تا از snapshotِ حافظه استفاده نشود؛ اگر
                # امتحانِ مربوطه هم‌اکنون در دیتابیس موجود نباشد (حذفِ
                # هم‌زمان)، همین‌جا خطایِ DoesNotExist می‌گیریم و هیچ رکوردِ
                # نیمه‌کاره‌ای ذخیره نمی‌شود.
                locked_exam = Exam.objects.select_for_update().get(
                    pk=self.exam_id
                )

                # «ساعتِ واقعاً کسرشده» را رویِ مقدارِ تازه‌ی دیتابیس حساب
                # می‌کنیم تا همراهِ همان INSERT در دیتابیس بنشیند (مبنای
                # بازگرداندنِ ساعت در delete() پایین). عددِ کسرشده = کمینه‌ی
                # «ساعتِ مطالعه» و «ساعتِ موجودِ امتحان»؛ یعنی اگر فقط ۲ ساعت
                # مانده باشد و کاربر ۵ ساعت ثبت کند، دقیقاً ۲ ساعت کسر می‌شود
                # (نه بیشتر).
                if locked_exam.study_hours_remaining > 0:
                    self.hours_deducted = min(
                        self.hours_studied, locked_exam.study_hours_remaining
                    )
                else:
                    self.hours_deducted = 0.0

            super().save(*args, **kwargs)

            # اگر رکورد جدید بود، ساعتِ کسرشده را از همان نمونه‌یِ قفل‌شده و
            # تازه‌خوانده‌شده کم می‌کنیم (برای رکوردهای ویرایش‌شده این کار
            # تکرار نمی‌شود، تا کسرِ دوباره هنگامِ هر ذخیره‌یِ مجدد رخ ندهد)
            if is_new and self.hours_deducted > 0:
                locked_exam.study_hours_remaining -= self.hours_deducted
                # محافظِ خطاهای گردکردنِ اعدادِ اعشاری (هرگز منفی نمی‌شود)
                if locked_exam.study_hours_remaining < 0:
                    locked_exam.study_hours_remaining = 0
                locked_exam.save()

    def delete(self, *args, **kwargs):
        """
        قرینه‌ی save() برای حذف: وقتی یک گزارشِ مطالعه حذف می‌شود، ساعت‌هایی
        که در لحظه‌ی ثبتِ همین گزارش از امتحان کم شده بودند (فیلدِ
        hours_deducted) دقیقاً به همان امتحان برمی‌گردند — نه بیشتر، نه کمتر.
        (بستنِ آیتمِ Medium Priorityِ TODO.md، 2026-09-03؛ قفلِ هم‌زمانی و
        خواندنِ تازه در 2026-09-09 به آن اضافه شد.)

        نکته‌ی فنی: این متد فقط در حذفِ «مستقیمِ» یک نمونه صدا زده می‌شود؛
        مسیرِ API حذفِ گزارش (perform_destroy در views.py) هم دقیقاً از
        همین‌جا می‌گذرد. اما حذفِ آبشاری (مثلاً حذفِ خودِ امتحان که
        گزارش‌هایش را هم می‌برد) یا حذفِ دسته‌ایِ QuerySet، از مسیرِ
        BulkDeleteِ سریعِ جنگو می‌گذرند و این متد را صدا نمی‌زنند — که
        رفتارِ درستی هم هست، چون در حذفِ آبشاری، امتحانی باقی نمی‌ماند
        که ساعتی به آن برگردد.
        """
        # مبلغِ بازگشتی را قبل از حذف در متغیر می‌گیریم؛ بعد از
        # super().delete() دیگر نمی‌خواهیم به رابطه‌های رکوردِ در حالِ حذف
        # تکیه کنیم.
        refund = self.hours_deducted or 0.0

        # حذفِ گزارش و بازگرداندنِ ساعت، هم‌اتمیک‌اند: یا هر دو، یا هیچ‌کدام.
        # ترتیبِ قفل‌ها با save() یکسان است (اول امتحان، بعد گزارش) تا در
        # دیتابیس‌های چندکاربره بن‌بست (Deadlock) بینِ این دو متد رخ ندهد.
        with transaction.atomic():
            locked_exam = None
            if self.exam_id is not None and refund > 0:
                # مثلِ save(): سطرِ امتحان را قفل و «تازه» می‌خوانیم تا
                # بازگرداندنِ ساعت رویِ مقدارِ لحظه‌ایِ دیتابیس جمع شود، نه
                # رویِ snapshotِ ممکن‌الوقوعِ حافظه (مثلاً کپیِِ کش‌شده‌یِ
                # select_related از ابتدایِ درخواست).
                try:
                    locked_exam = Exam.objects.select_for_update().get(
                        pk=self.exam_id
                    )
                except Exam.DoesNotExist:
                    # امتحانِ مربوطه دیگر وجود ندارد (رکوردِ یتیم با کلیدِ
                    # خارجیِ شکسته): فقط خودِ گزارش حذف می‌شود — بدونِ خطا،
                    # بدونِ «بازگرداندنِ ساعتی به هیچ‌جا» و بدونِ زنده‌کردنِ
                    # دوباره‌یِ امتحانِ حذف‌شده (رفتارِ defensiveِ قبلی حفظ
                    # شد؛ فقط با یک SELECT کمتر و بدونِ خطرِ resurrection).
                    locked_exam = None

            super().delete(*args, **kwargs)

            if locked_exam is not None:
                locked_exam.study_hours_remaining += refund
                locked_exam.save()

    def __str__(self):
        return f"{self.user.username} - {self.exam.subject.name} - {self.hours_studied} hours"


# ----------------------------------------------------------------------------
# امنیتِ حسابِ کاربری (از 2026-09-10)
# ----------------------------------------------------------------------------

class UserSecurityProfile(models.Model):
    """
    «پروفایلِ امنیتیِ» هر کاربر — در حالِ حاضر فقط یک وظیفه دارد: نگه‌داشتنِ
    لحظه‌ی آخرینِ تغییرِ رمز عبور (password_changed_at) تا لایه‌ی احرازِ هویتِ
    JWT (planner/authentication.py) بتواند توکن‌هایِ دسترسیِ صادرشده «قبل ازِ»
    تغییرِ رمز را رد کند.

    نکته‌های طراحی:

    - چرا مدلِ جدا به‌جایِ فیلد رویِ خودِ User؟ مدلِ User متعلق به
      django.contrib.auth است و افزودنِ فیلد به آن نیازمندِ مدلِ کاربرِ سفارشیِ
      (AUTH_USER_MODEL) است که در میانه‌ی عمرِ پروژه مهاجرتِ خطرناکی دارد؛
      جدولِ جانبیِ یک‌به‌یکِ همان اطلاعات را با یک مایگریشنِ کوچک و امن می‌دهد.
    - رکورد «فقط برای کسانی ساخته می‌شود که رمزشان را عوض کرده‌اند» — نه در
      ثبت‌نام. یعنی برایِ کاربرانِ عادیِ قدیمی هیچ سطرِ اضافه‌ای وجود ندارد و
      رفتارِ احرازِ هویتِ آن‌ها ذره‌ای عوض نمی‌شود (همان اصلِ dev-safeِ پروژه).
    - حذفِ کاربر → حذفِ این رکورد هم (CASCADE) — منطقی است چون رکورد بدونِ
      کاربر بی‌معناست.
    """

    # یک‌به‌یک: هر کاربر حداکثر یک پروفایلِ امنیتی (قیدِ UNIQUE در سطحِ
    # دیتابیس — همان الگویِ StudyPlan.user در 0008).
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='security_profile',
    )

    # لحظه‌ی آخرینِ تغییرِ رمزِ موفقِ این کاربر (timezone-aware — USE_TZ روشن
    # است). معیارِ مقایسه در authentication.py: هر توکنِ JWT ادعایِ iat
    # («صادرشده در») دارد؛ اگر iat < این لحظه باشد یعنی توکن مالِ «قبل ازِ
    # تغییرِ رمز» است و رد می‌شود.
    password_changed_at = models.DateTimeField(
        default=timezone.now,
    )

    # -----------------------------------------------------------------
    # ورودِ دومرحله‌ای / TOTP (از 2026-09-14) — جزئیاتِ الگوریتم در
    # planner/totp.py؛ این‌جا فقط «وضعیتِ» کاربر نگه داشته می‌شود.
    # -----------------------------------------------------------------

    # کلیدِ مشترکِ base32 (۳۲ نویسه برایِ ۲۰ بایت) — هم برایِ «در انتظارِ
    # تأیید» (بعد از setup، قبل از confirm) و هم برایِ «فعال» (بعد از
    # confirm) همین فیلد است؛ تمایزشان با totp_confirmed_at ساخته می‌شود.
    # طولِ ۶۴ برایِ کلیدهایِ بلندترِ آینده (۳۲ بایت = ۵۲ نویسه) هم کافی است.
    totp_secret = models.CharField(
        max_length=64, null=True, blank=True,
        help_text='کلیدِ TOTP به base32 (فقط وقتی معتبر است که confirmed پر باشد)',
    )

    # لحظه‌ی تأییدِ کلید با اولین کدِ درست (setup هنوز کامل نشده = NULL).
    # «فعال‌بودنِ» 2FA یعنی: totp_secret پر باشد و این فیلد NULL نباشد —
    # دو فیلد جدا تا جریانِ «ساختم ولی تأیید نکردم» حالتِ میانیِ امنِ خودش
    # باشد (کلیدِ تأییدنشده در ورود هیچ اثری ندارد).
    totp_confirmed_at = models.DateTimeField(
        null=True, blank=True,
        help_text='لحظه‌ی فعال‌سازیِ 2FA (NULL = هنوز تأییدنشده/خاموش)',
    )

    # شماره‌ی آخرینِ گامِ زمانیِ ۳۰ثانیه‌ای که کدش یک‌بار پذیرفته شد —
    # «ضدِ پخشِ مجدد» (همان کد دوباره کار نمی‌کند؛ RFC 6238 §5.2).
    # NULL یعنی هنوز هیچ کدی مصرف نشده است. صریحاً «گام» ذخیره می‌شود
    # (نه خودِ کد) تا با چرخشِ گام‌ها مقایسه‌ی مرتبی بماند.
    last_used_totp_step = models.BigIntegerField(
        null=True, blank=True,
        help_text='آخرینِ گامِ زمانیِ مصرف‌شده (ضدِ replay)',
    )

    @property
    def two_factor_enabled(self):
        """«فعال» یعنی کلید هست «و» با کدِ درست تأیید شده (confirmed پر).

        property ساده برایِ خواناییِ ویوها؛ در پرس‌وجوها شرطِ معادل باید
        صریح نوشته شود (totp_secret__isnull=False + totp_confirmed_at__isnull=False).
        """
        return bool(self.totp_secret) and self.totp_confirmed_at is not None

    def __str__(self):
        return f"{self.user.username} - password changed at {self.password_changed_at:%Y-%m-%d %H:%M}"


# ----------------------------------------------------------------------------
# لاگِ رویدادهایِ امنیتی (از 2026-09-12)
# ----------------------------------------------------------------------------

class SecurityEvent(models.Model):
    """
    یک «رویدادِ امنیتی» در تاریخچه‌ی حسابِ کاربر — چیزی که کاربر خودش بعداً
    می‌تواند ببیند: ورودِ موفق، تلاشِ ناموفقِ ورود، تغییرِ رمز، درخواستِ
    بازیابی و بازنشانیِ رمز و فعال/خاموش‌شدنِ ورودِ دومرحله‌ای. (ایده‌ی
    ثبت‌شده در TODO.md — «لاگِ رویدادهایِ امنیتی / audit log».)

    نکته‌های طراحی:

    - این لاگ «خصوصی» است، نه عمومی: تنها مسیرِ خواندنش GET /api/auth/
      security/events/ است که فقط با توکنِ خودِ کاربر جواب می‌دهد (جداسازی
      کامل مثل درس/امتحان/گزارش). داده‌اش هم داخلی است — ضبطِ رویداد
      هیچ اثری در «پاسخِ» مسیرهای بی‌لاگین نمی‌گذارد (قراردادِ ضدِ کشفِ
      حسابِ بازیابیِ رمز دست‌نخورده می‌ماند).
    - IPِ ثبت‌شده همان «هویتی» است که محدودسازِ نرخ (throttles.py) شمرده
      می‌شود (AuthBurstThrottle().get_ident) — یعنی لاگ و throttle همیشه
      یک تعریف از «این درخواست از کجا آمد» دارند.
    - نگه‌داریِ محدود (RETENTION_LIMIT): هر ثبت، رویدادهای قدیمی‌تر از
      سقفِ هر کاربر را همان‌جا هرس می‌کند — جدولِ لاگ هرگز بی‌سقف رشد
      نمی‌کند و نیازی به jobِ زمان‌بندی‌شده‌ی جدا ندارد.
    - حذفِ کاربر → حذفِ رویدادهایش هم (CASCADE) — منطقی است چون تاریخچه‌ی
      امنیتیِ کاربرِ حذف‌شده دیگر مخاطبی ندارد.
    """

    class EventType(models.TextChoices):
        """انواعِ رویدادِ امنیتی — مقدار = کلیدِ ماشین‌خوانِ ثابت در API؛ برچسب =
        متنِ قابل‌ترجمه (gettext_lazy) برای نمایش (serializer آن را با
        get_event_type_display و زبانِ درخواست برمی‌گرداند)."""
        LOGIN_SUCCESS = 'login_success', gettext_lazy('ورود موفق')
        LOGIN_FAILED = 'login_failed', gettext_lazy('تلاشِ ناموفقِ ورود')
        PASSWORD_CHANGED = 'password_changed', gettext_lazy('تغییر رمز عبور')
        PASSWORD_RESET_REQUESTED = (
            'password_reset_requested',
            gettext_lazy('درخواستِ بازیابیِ رمزِ عبور'),
        )
        PASSWORD_RESET_COMPLETED = (
            'password_reset_completed',
            gettext_lazy('بازنشانیِ رمزِ عبور'),
        )
        # ورودِ دومرحله‌ای (از 2026-09-14): فعال/خاموش‌شدنِ لایه‌ی دوم و
        # کدِ نامعتبری که با رمزِ درست آمده بود (رمز لو رفته ولی مهاجم
        # از لایه‌ی دوم رد نشد — برایِ صاحبِ حساب، دانستنِ همین تلاش
        # ارزشِ امنیتیِ جدی دارد).
        TWO_FACTOR_ENABLED = 'two_factor_enabled', gettext_lazy('فعال‌سازیِ ورودِ دومرحله‌ای')
        TWO_FACTOR_DISABLED = 'two_factor_disabled', gettext_lazy('خاموش‌شدنِ ورودِ دومرحله‌ای')
        LOGIN_2FA_FAILED = 'login_2fa_failed', gettext_lazy('کدِ نامعتبرِ ورودِ دومرحله‌ای')
        # هشدارِ ورود از نشانیِ جدید (از 2026-09-16): ورودِ موفق از نشانی‌ای
        # که حسابِ این کاربر قبلاً ندیده بود — رویدادی که مالکِ حساب باید
        # همان لحظه (ایمیل) و بعداً (این لاگ) ببیند؛ ایده‌ی ثبت‌شده در
        # TODO.md/HANDOFF («هشدارِ ایمیلِ ورود از نشانیِ جدید»).
        LOGIN_NEW_ADDRESS = 'login_new_address', gettext_lazy('ورود از نشانیِ جدید')

    # سقفِ نگه‌داریِ رویدادها به‌ازایِ هر کاربر — عددِ ثابتِ کلاس (نه متغیرِ
    # محیطی) چون رفتارِ امنیتی است نه تنظیمِ استقرار؛ تست‌ها برای سناریویِ
    # هرس موقتاً همین عدد را کوچک می‌کنند (patch.object).
    RETENTION_LIMIT = 200

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='security_events',
        # db_index پیش‌فرضِ ForeignKey است؛ Meta.indexes نمایِ ترکیبیِ «کاربر +
        # زمان» را برای پرس‌وجویِ اصلی (تازه‌ترینِ رویدادهایِ این کاربر)
        # اضافه می‌کند — تنها الگویِ خواندنِ این جدول.
    )

    # نوعِ رویداد (کلیدِ ماشین‌خوان — ثابت در API؛ کلاینت هیچ‌وقت متنِ فارسیِ
    # داخلی را نمی‌بیند بلکه labelِ ترجمه‌شده را می‌گیرد).
    event_type = models.CharField(max_length=40, choices=EventType.choices)

    # لحظه‌ی ثبت (auto_now_add — فقط یک‌بار)؛ ترتیبِ نمایش و مرجعِ هرس است.
    created_at = models.DateTimeField(auto_now_add=True)

    # نشانیِ IP فرستنده‌ی درخواست — همان هویتی که throttle می‌شمارد؛ ممکن است
    # None باشد (فراخوانیِ بدونِ request، مثل برخی تست‌ها).
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    # عاملِ کاربر (User-Agent) — بریده به ۳۰۰ نویسه تا رکوردهایِ حجیم در
    # جدول نمی‌نشینند (UAهایِ واقعی طولانی‌اند ولی سرِنوشتشان همین
    # بریدگیِ صادقانه است).
    user_agent = models.CharField(max_length=300, blank=True, default='')

    class Meta:
        # تازه‌ترین رویداد اول؛ -id برای قطعیتِ ترتیبِ رویدادهایِ هم‌ثانیه
        # (auto_now_add رزولوشنِ میکروثانیه دارد ولی هرس و صفحه‌بندی باید
        # حتی در فرضِ بدترین حالت (هم‌میکروثانیه) پایدار بمانند).
        ordering = ['-created_at', '-id']
        indexes = [
            models.Index(fields=['user', '-created_at'], name='sec_event_user_idx'),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.event_type} at {self.created_at:%Y-%m-%d %H:%M}"

    # ---------------------------------------------------------------------
    # ضبطِ اتمیک + هرس
    # ---------------------------------------------------------------------

    @classmethod
    def record(cls, *, user, event_type, request=None):
        """یک رویداد را «اتمیک» ثبت و رویدادهای فراتر از سقف را هرس می‌کند.

        تنها نقطه‌ی ورودِ نوشتن به این جدول است — همه‌ی نقاطِ ضبط
        (login موفق/ناموفق، تغییر رمز، درخواست/تأییدِ بازیابی، 2FA) از همین یک
        متد می‌گذرند تا رفتار (IP/UA/هرس/ترتیب) همه‌جا یکسان بماند.

        - تراکنش: ثبت + هرس یا هر دو یا هیچ — اگر فراخواننده خودش داخلِ
          transaction.atomic() باشد، این تراکنش به savepoint تبدیل می‌شود
          (رفتارِ استانداردِ جنگو؛ تغییری لازم نیست).
        - idempotence نیست (هر فراخوانی = یک رویداد — لاگِ تکراری با معنا
          است: دو ورودِ موفقِ پشت‌سرِهم دو رویدادند)؛ ولی بی‌خطر است چون
          هرس سقفِ رشد را نگه می‌دارد.
        """
        # هویتِ شبکه‌ای و عاملِ کاربر از خودِ درخواست — مستقیم از DRF (همان
        # منطقِ throttle؛ پشتِ پروکسیِ Nginx = X-Forwarded-For، وگرنه
        # REMOTE_ADDR). request ممکن است نباشد (فراخوانیِ برنامه‌ای).
        ip_address = None
        user_agent = ''
        if request is not None:
            # import داخلی تا وابستگیِ مدل → throttle در زمانِ import برقرار
            # نشود (throttles.py ماژولِ لایه‌ی API است؛ این‌جا فقط یک متدِ
            # کمکیِ دیده‌بانی‌شده را قرض می‌گیریم).
            from .throttles import AuthBurstThrottle
            ident = AuthBurstThrottle().get_ident(request)
            ip_address = ident or None
            user_agent = (request.META.get('HTTP_USER_AGENT') or '')[:300]

        with transaction.atomic():
            event = cls.objects.create(
                user=user,
                event_type=event_type,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            # هرسِ همان‌جا: تازه‌ترینِ RETENTION_LIMIT رویدادِ این کاربر
            # می‌مانند و بقیه حذف می‌شوند. orderingِ Meta (-created_at, -id)
            # مرتب‌سازی را تضمین می‌کند؛ values_list بدونِ کشِ مدل = سبک.
            # وقتی شمارِ رویدادها <= سقف است، exclude هیچ‌چیز نمی‌گیرد و این
            # پرس‌وجو عملاً یک شمارشِ ارزان است.
            keep_ids = list(
                cls.objects.filter(user=user).values_list('pk', flat=True)[
                    : cls.RETENTION_LIMIT
                ]
            )
            cls.objects.filter(user=user).exclude(pk__in=keep_ids).delete()

        return event


class KnownLoginAddress(models.Model):
    """
    نشانیِ شبکه‌ایِ «شناخته‌شده»ی هر کاربر — مبنایِ هشدارِ ورود از نشانیِ
    جدید (از 2026-09-16؛ ایده‌ی ثبت‌شده در TODO.md/HANDOFF).

    نکته‌های طراحی:

    - چرا جدولِ جدا و NOT همان SecurityEvent؟ لاگِ رویدادها هرس می‌شود
      (RETENTION_LIMIT = ۲۰۰) و «شناخته‌شده‌بودنِ» یک نشانی نباید با هرسِ لاگ
      گم شود — وگرنه کاربر برایِ گوشیِ همیشگیِ خودش، هشدارِ تکراری می‌گیرد.
      این جدول «آخرین وضعیت» را نگه می‌دارد، نه تاریخچه.
    - IPِ ثبت‌شده همان هویتی است که محدودسازِ نرخ و SecurityEvent می‌شمارند
      (AuthBurstThrottle().get_ident) — همه یک تعریف از «این درخواست از کجا
      آمد» دارند.
    - نگه‌داریِ محدود (RETENTION_LIMIT): تازه‌ترینِ نشانی‌ها بر اساسِ
      last_seen_at می‌مانند؛ نشانیِ کهنِ کنارگذاشته‌شده «فراموش» می‌شود و
      بازگشتش دوباره «جدید» است — مصالحه‌ی صادقانه‌ی رشدِ کراندار بدونِ
      jobِ زمان‌بندی (همان فلسفه‌ی هرسِ SecurityEvent).
    - ALERT_DAILY_LIMIT: سقفِ ایمیل‌هایِ هشدار در پنجره‌ی ۲۴ساعته‌ی لغزان —
      دفاعِ «حسابِ درست، صندوقِ سالم» در برابرِ مهاجمِ رمزدار با شبکه‌ی
      بزرگ (botnet): رویدادها همیشه ثبت می‌شوند ولی ایمیل‌ها زیرِ سقف
      می‌مانند. عددِ ثابتِ کلاس چون رفتارِ امنیتی است نه تنظیمِ استقرار.
    - حذفِ کاربر → حذفِ نشانی‌هایش (CASCADE) — نشانیِ «شناخته‌شده» بدونِ
      صاحبِ حساب بی‌معناست.
    """

    # سقفِ نگه‌داریِ نشانی‌ها به‌ازایِ هر کاربر — تست‌ها برایِ سناریویِ هرس
    # موقتاً همین عدد را کوچک می‌کنند (patch.object؛ الگوی RETENTION_LIMITِ
    # SecurityEvent).
    RETENTION_LIMIT = 30

    # حداکثر ایمیلِ «نشانیِ جدید» در هر پنجره‌ی ۲۴ساعته‌ی لغزان به‌ازایِ
    # کاربر — شمارش روی alert_sent_at (ایمیل‌هایِ واقعاً فرستاده‌شده) است؛
    # تست‌ها برایِ سناریویِ سقف موقتاً کوچکش می‌کنند.
    ALERT_DAILY_LIMIT = 5

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='known_login_addresses',
    )

    # نشانیِ شبکه‌ای — GenericIPAddressField هم IPv4 هم IPv6 را اعتبارسنجی
    # می‌کند (طولِ حداکثرِ متنیِ IPv6 = ۳۹ + بازنماییِ IPv4-نگاشته).
    ip_address = models.GenericIPAddressField()

    # اولین و آخرین باری که این نشانی دیده شد — first_seen مرزِ «جدید» است
    # و last_seen مرجعِ هرس (نشانیِ همیشه‌درِاستفاده هرگز هرس نمی‌شود).
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(default=timezone.now)

    # آخرین عاملِ کاربری که از این نشانی آمد (بریده به ۳۰۰ نویسه — هم‌قدِ
    # SecurityEvent.user_agent) — فقط برایِ نمایش در ایمیلِ هشدار.
    last_user_agent = models.CharField(max_length=300, blank=True, default='')

    # لحظه‌ی فرستاده‌شدنِ ایمیلِ هشدار برایِ «اولین‌بارِ» این نشانی — مبنایِ
    # شمارشِ سقفِ ۲۴ساعته (برایِ نشانی‌هایِ بعدی که زیرِ سقف رد شدند خالی
    # می‌ماند). «تلاشِ ارسال» ثبت می‌شود نه «موفقیتِ قطعی» — شکستِ پایدارِ
    # SMTP نباید سهمیه را دور بزند و صندوق را درِ ثانیه‌یِ بعدی غرق کند.
    alert_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        # تازه‌ترین استفاده اول — همان ترتیبی که هرس رویش پایدار است.
        ordering = ['-last_seen_at', '-id']
        # هر کاربر هر نشانی را فقط یک‌بار دارد — در سطحِ خودِ دیتابیس
        # (قیدِ یکتایی؛ رقابتِ دو ورودِ هم‌زمان از یک IP با get_or_create
        # + IntegrityError-خوارِ خودِ جنگو حل می‌شود).
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'ip_address'],
                name='known_addr_user_ip_uniq',
            ),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.ip_address} (last seen {self.last_seen_at:%Y-%m-%d %H:%M})"

    # ---------------------------------------------------------------------
    # ثبتِ اتمیک + هرس — تنها نقطه‌ی ورودِ نوشتن (الگوی SecurityEvent.record)
    # ---------------------------------------------------------------------

    @classmethod
    def register(cls, *, user, request=None):
        """نشانیِ «این ورود» را ثبت/به‌روزرسانی می‌کند — اتمیک + هرس.

        خروجی: (address, is_new, is_first)
          - (None, False, False): هویتِ شبکه‌ای در دسترس نبود (request نبود
            یا ident خالی) — هیچ ردیفی ساخته/لمس نمی‌شود؛ هشداری هم نیست.
          - is_first=True: کاربر تا حالا هیچ نشانی‌ای نداشت و این «مبناگذاریِ
            اول» است — ثبت می‌شود ولی هشدار ندارد (چه چیزی برای مقایسه
            بوده است؟ اولین ورودِ هر کاربرِ تازه نباید ایمیلِ ترسناک بگیرد).
          - is_new=True: کاربر مبنا دارد و این نشانی برایِ اولین‌بار دیده
            شد — مستحقِ رویدادِ login_new_address و ایمیلِ هشدار است.

        نکته‌ی تراکنش: ثبتِ ردیف + به‌روزرسانیِ last_seen + هرس یا همه یا
        هیچ. نکته‌ی idempotence: دوباره‌صداکردن با همان نشانی فقط last_seen
        را تازه می‌کند و دیگر «جدید» نیست (هشدارِ تکراری وجود ندارد).
        """
        ip_address = None
        user_agent = ''
        if request is not None:
            # همان قرضِ دیده‌بانی‌شده‌ی SecurityEvent.record — هویتِ شبکه‌ای
            # از نگاهِ throttle، تا لاگ/هشدار/محدودسازی یک زبان حرف بزنند.
            from .throttles import AuthBurstThrottle
            ident = AuthBurstThrottle().get_ident(request)
            ip_address = ident or None
            user_agent = (request.META.get('HTTP_USER_AGENT') or '')[:300]

        if ip_address is None:
            return None, False, False

        with transaction.atomic():
            # «مبنا دارد؟» باید «قبل از» get_or_create سنجیده شود — بعد از
            # ساختِ اولین ردیف، جوابِ همیشه‌بله است.
            had_addresses = cls.objects.filter(user=user).exists()
            address, created = cls.objects.get_or_create(
                user=user,
                ip_address=ip_address,
                defaults={'last_user_agent': user_agent},
            )
            if not created:
                # نشانیِ شناخته‌شده: فقط «آخرین دیدار» را تازه کن (و UA را —
                # مرورگرِ همان IP هم عوض می‌شود).
                address.last_seen_at = timezone.now()
                address.last_user_agent = user_agent
                address.save(update_fields=['last_seen_at', 'last_user_agent'])
            # هرسِ همان‌جا: تازه‌ترینِ RETENTION_LIMIT نشانیِ این کاربر بر
            # اساسِ last_seen_at می‌مانند؛ orderingِ Meta ترتیب را تضمین
            # می‌کند و وقتی شمار ≤ سقف است، exclude هیچ نمی‌گیرد.
            keep_ids = list(
                cls.objects.filter(user=user).values_list('pk', flat=True)[
                    : cls.RETENTION_LIMIT
                ]
            )
            cls.objects.filter(user=user).exclude(pk__in=keep_ids).delete()

        is_first = created and not had_addresses
        is_new = created and had_addresses
        return address, is_new, is_first
