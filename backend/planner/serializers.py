# planner/serializers.py
# ----------------------------------------------------------------------------
# «سریالایزر» (Serializer) در Django REST Framework دو وظیفه‌ی اصلی دارد:
#   ۱) تبدیل آبجکت‌های پایتونی/مدل‌های جنگو به JSON برای ارسال به فرانت‌اند
#      (Serialization)
#   ۲) اعتبارسنجیِ داده‌ی JSON دریافتی از فرانت‌اند و تبدیل آن به داده‌ی
#      قابل‌ذخیره در مدل (Deserialization / Validation)
#
# این فایل یک سریالایزر برای هرکدام از مدل‌های اصلی پروژه دارد.
# ----------------------------------------------------------------------------

from rest_framework import serializers
# UniqueValidator: برای اطمینان از یکتا بودنِ یک مقدار (مثل نام کاربری) در دیتابیس
from rest_framework.validators import UniqueValidator
from django.contrib.auth.models import User
from .models import Subject, Exam, StudyPlan, StudyLog
# تابع کمکی که درصد پیشرفتِ یک درس را حساب می‌کند (تعریف‌شده در utils.py)
from .utils import compute_subject_progress


class UserSerializer(serializers.ModelSerializer):
    """
    سریالایزرِ ثبت‌نام کاربر. هم برای اعتبارسنجیِ ورودیِ فرمِ ثبت‌نام استفاده
    می‌شود (چک کردنِ یکتا بودنِ username/email) و هم برای ساختِ کاربر جدید.
    """
    # به‌صورت پیش‌فرض، ModelSerializer یکتا بودنِ username را چک نمی‌کند مگر
    # این‌که خودمان یک UniqueValidator با پیامِ خطای دلخواه اضافه کنیم.
    username = serializers.CharField(
        validators=[UniqueValidator(queryset=User.objects.all(), message="این نام کاربری قبلاً ثبت شده است.")]
    )
    email = serializers.EmailField(
        required=False,
        allow_blank=True,  # این خط حتماً باید اضافه شود
        validators=[UniqueValidator(queryset=User.objects.all(), message="این ایمیل قبلاً ثبت شده است.")]
    )

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'password']
        # write_only یعنی رمز عبور هرگز در پاسخِ API برگردانده نمی‌شود،
        # فقط برای ورودی (هنگام ثبت‌نام) قابل‌استفاده است.
        extra_kwargs = {'password': {'write_only': True}}

    def create(self, validated_data):
        # اگر ایمیل خالی بود، کلا از دیکشنری حذفش کن که تکراری بودن رشته‌های خالی خطا ندهد
        if validated_data.get('email') == '':
            validated_data.pop('email')

        # create_user (نه create ساده) استفاده می‌شود چون این متد به‌صورت
        # خودکار رمز عبور را قبل از ذخیره در دیتابیس Hash می‌کند.
        user = User.objects.create_user(**validated_data)
        return user


class SubjectSerializer(serializers.ModelSerializer):
    """
    سریالایزرِ درس. نکته‌ی مهم: فیلدهایی مثل درصد پیشرفت در مدل ذخیره
    نشده‌اند (چون مشتق‌شده‌اند)، بلکه در متد to_representation پایین همین
    کلاس، در لحظه محاسبه و به خروجی اضافه می‌شوند.
    """
    # فیلد نمایشی سازگار با فرانت‌اند (name="target_score" در فرم‌ها)
    # روی همان فیلد مدل target_grade نگاشت می‌شود، هم برای خواندن هم نوشتن.
    target_score = serializers.FloatField(source='target_grade', required=False, allow_null=True)

    class Meta:
        model = Subject
        # این‌ها فیلدهایی هستند که مستقیماً از مدل خوانده/نوشته می‌شوند؛
        # فیلدهای محاسباتی (progress_percent و...) پایین‌تر جداگانه اضافه می‌شوند.
        # notes از این پس یک فیلد واقعیِ مدل است (قبلاً فرم می‌فرستاد ولی نادیده
        # گرفته می‌شد — رفعِ فیلد یتیم).
        fields = ['id', 'name', 'difficulty', 'target_score', 'notes']

    def validate_name(self, value):
        """
        یکتاییِ نامِ درس به ازای هر کاربر، در سطحِ API (کد 400 تمیز، نه خطای 500).

        چرا این اعتبارسنجی لازم است؟ محدودیتِ یکتاییِ ('user', 'name') فقط در
        سطحِ دیتابیس وجود دارد (Meta.unique_together). DRF فقط وقتی می‌تواند
        به‌صورت خودکار UniqueTogetherValidator بسازد که «هر دو» فیلدِ آن
        محدودیت در سریالایزر حضور داشته باشند؛ ولی فیلد user عمداً اینجا
        نیست (کاربر از روی توکنِ درخواست تعیین می‌شود، نه ورودیِ فرم).
        نتیجه‌ی نبودِ این متد: IntegrityErrorِ خامِ دیتابیس که به‌صورت
        خطای 500 به کلاینت می‌رسید (کشف‌شده هنگام نوشتنِ تست‌ها، 2026-08-29).
        """
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        # فقط وقتی کاربرِ احراز‌هویت‌شده در دسترس است این بررسی معنا دارد
        if user is not None and user.is_authenticated:
            qs = Subject.objects.filter(user=user, name=value)
            # در حالتِ ویرایش (update)، خودِ رکوردِ فعلی نباید با خودش مقایسه شود
            if self.instance is not None:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError('شما قبلاً درسی با این نام ثبت کرده‌اید.')
        return value

    def to_representation(self, instance):
        """
        فیلدهای محاسباتی (پیشرفت، ساعات مطالعه‌شده/باقی‌مانده) را یک‌جا و با
        یک بار فراخوانی compute_subject_progress اضافه می‌کنیم تا کوئری
        تکراری نداشته باشیم.
        """
        # ابتدا خروجیِ استانداردِ سریالایزر (همان فیلدهای بالا) را می‌گیریم...
        data = super().to_representation(instance)
        # ...سپس با یک بار محاسبه (نه چهار بار جداگانه)، هر چهار مقدارِ
        # مرتبط با پیشرفت را همزمان به دست می‌آوریم:
        completed_hours, total_hours, progress_percent = compute_subject_progress(instance)
        data['completed_hours'] = completed_hours
        data['total_hours'] = total_hours
        data['remaining_hours'] = round(total_hours - completed_hours, 1)
        data['progress_percent'] = progress_percent
        return data


class ExamSerializer(serializers.ModelSerializer):
    """سریالایزرِ امتحان؛ نام درسِ مربوطه را هم برای راحتیِ فرانت‌اند اضافه می‌کند."""
    # subject_name یک فیلدِ فقط-خواندنی است که مستقیماً از روی رابطه‌ی
    # ForeignKey (exam.subject.name) خوانده می‌شود، تا فرانت‌اند مجبور نباشد
    # برای نمایش نام درس، یک درخواست جداگانه بزند.
    subject_name = serializers.CharField(source='subject.name', read_only=True)

    class Meta:
        model = Exam
        # notes از این پس یک فیلدِ واقعیِ مدل است (رفعِ فیلدِ یتیمِ فرمِ امتحان).
        fields = ['id', 'subject', 'subject_name', 'exam_date', 'chapters_remaining',
                  'study_hours_remaining', 'notes', 'created_at', 'updated_at']
        # این دو فیلد را کاربر نمی‌تواند مستقیم تغییر بدهد؛ جنگو خودش پرشان می‌کند.
        read_only_fields = ['created_at', 'updated_at']


class StudyPlanSerializer(serializers.ModelSerializer):
    """
    سریالایزرِ خامِ مدل StudyPlan (تنظیمات کاربر).
    توجه: این سریالایزر برای مسیر پیش‌فرضِ create/retrieve استفاده می‌شود؛
    خروجیِ اصلیِ صفحه‌ی «برنامه مطالعه» (که فرمت متفاوتی دارد) در views.py
    و با تابع format_plan_for_frontend ساخته می‌شود، نه از طریق این سریالایزر.
    """
    class Meta:
        model = StudyPlan
        fields = ['id', 'daily_available_hours', 'plan_data', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']


class StudyLogSerializer(serializers.ModelSerializer):
    """سریالایزرِ گزارش مطالعه؛ نام کاربر و نام درس را هم برای نمایش راحت‌تر اضافه می‌کند."""
    # ReadOnlyField یعنی این مقدار فقط برای خروجی (نمایش) است و کاربر
    # نمی‌تواند هنگام ثبت، مستقیماً آن را ست کند.
    user = serializers.ReadOnlyField(source='user.username')
    # از دو پله‌ی رابطه عبور می‌کند: StudyLog -> Exam -> Subject -> name
    exam_name = serializers.ReadOnlyField(source='exam.subject.name')

    class Meta:
        model = StudyLog
        fields = ['id', 'user', 'exam', 'exam_name', 'date', 'hours_studied', 'notes']
