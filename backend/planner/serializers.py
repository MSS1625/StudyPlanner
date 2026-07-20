from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from django.contrib.auth.models import User
from .models import Subject, Exam, StudyPlan, StudyLog
from .utils import compute_subject_progress


class UserSerializer(serializers.ModelSerializer):
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
        extra_kwargs = {'password': {'write_only': True}}

    def create(self, validated_data):
        # اگر ایمیل خالی بود، کلا از دیکشنری حذفش کن که تکراری بودن رشته‌های خالی خطا ندهد
        if validated_data.get('email') == '':
            validated_data.pop('email')

        user = User.objects.create_user(**validated_data)
        return user


class SubjectSerializer(serializers.ModelSerializer):
    # فیلد نمایشی سازگار با فرانت‌اند (name="target_score" در فرم‌ها)
    # روی همان فیلد مدل target_grade نگاشت می‌شود، هم برای خواندن هم نوشتن.
    target_score = serializers.FloatField(source='target_grade', required=False, allow_null=True)

    class Meta:
        model = Subject
        fields = ['id', 'name', 'difficulty', 'target_score']

    def to_representation(self, instance):
        """
        فیلدهای محاسباتی (پیشرفت، ساعات مطالعه‌شده/باقی‌مانده) را یک‌جا و با
        یک بار فراخوانی compute_subject_progress اضافه می‌کنیم تا کوئری
        تکراری نداشته باشیم.
        """
        data = super().to_representation(instance)
        completed_hours, total_hours, progress_percent = compute_subject_progress(instance)
        data['completed_hours'] = completed_hours
        data['total_hours'] = total_hours
        data['remaining_hours'] = round(total_hours - completed_hours, 1)
        data['progress_percent'] = progress_percent
        return data


class ExamSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source='subject.name', read_only=True)

    class Meta:
        model = Exam
        fields = ['id', 'subject', 'subject_name', 'exam_date', 'chapters_remaining',
                  'study_hours_remaining', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']


class StudyPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudyPlan
        fields = ['id', 'daily_available_hours', 'plan_data', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']


class StudyLogSerializer(serializers.ModelSerializer):
    user = serializers.ReadOnlyField(source='user.username')
    exam_name = serializers.ReadOnlyField(source='exam.subject.name')

    class Meta:
        model = StudyLog
        fields = ['id', 'user', 'exam', 'exam_name', 'date', 'hours_studied', 'notes']
