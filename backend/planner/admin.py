from django.contrib import admin
from .models import Subject, Exam, StudyPlan, StudyLog


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'difficulty',
                    'target_grade', 'user', 'created_at']
    list_filter = ['difficulty', 'created_at']
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
    search_fields = ['user__username', 'exam__subject__name']
