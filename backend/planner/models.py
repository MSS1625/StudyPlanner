from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone


class Subject(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='subjects')
    name = models.CharField(max_length=200)
    difficulty = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="سختی درس از 1 تا 5",
        default=3
    )
    target_grade = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(20)],
        help_text="هدف نمره (اختیاری)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ['user', 'name']

    def __str__(self):
        return f"{self.name} ({self.user.username})"


class Exam(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='exams')
    exam_date = models.DateField(help_text="تاریخ امتحان")
    chapters_remaining = models.IntegerField(
        validators=[MinValueValidator(0)], default=0,
        help_text="تعداد فصل‌های باقی‌مانده"
    )
    study_hours_remaining = models.FloatField(
        validators=[MinValueValidator(0)],default=0.0,
        help_text="ساعت مطالعه باقی‌مانده"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['exam_date']

    def __str__(self):
        return f"{self.subject.name} - {self.exam_date}"


class StudyPlan(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='study_plans')
    daily_available_hours = models.FloatField(
        validators=[MinValueValidator(0)],
        help_text="ساعت آزاد روزانه برای مطالعه"
    )
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
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='study_logs')
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='study_logs')
    date = models.DateField(default=timezone.now)
    hours_studied = models.FloatField(validators=[MinValueValidator(0.1)])
    notes = models.TextField(blank=True, null=True) # توضیحات اختیاری
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def save(self, *args, **kwargs):
        # بررسی می‌کنیم که آیا این یک رکورد جدید است یا داریم رکورد قبلی را ویرایش می‌کنیم؟
        is_new = self.pk is None 
        
        # ابتدا خود گزارش مطالعه را در دیتابیس ذخیره می‌کنیم
        super().save(*args, **kwargs)

        # اگر رکورد جدید بود، ساعات مطالعه را از امتحان مربوطه کم می‌کنیم
        if is_new:
            if self.exam.study_hours_remaining > 0:
                self.exam.study_hours_remaining -= self.hours_studied
                # برای جلوگیری از منفی شدن ساعات باقی‌مانده
                if self.exam.study_hours_remaining < 0:
                    self.exam.study_hours_remaining = 0
                self.exam.save()

    def __str__(self):
        return f"{self.user.username} - {self.exam.subject.name} - {self.hours_studied} hours"