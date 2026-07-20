# StudyPlanner/backend/planner/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'subjects', views.SubjectViewSet, basename='subject')
router.register(r'exams', views.ExamViewSet, basename='exam')
router.register(r'study-plan', views.StudyPlanViewSet, basename='study-plan')
router.register(r'study-logs', views.StudyLogViewSet, basename='studylog')

# نکته‌ی مهم: router.register باید همیشه قبل از include(router.urls) انجام شود،
# چون router.urls در همان لحظه‌ای که فراخوانی می‌شود، لیست URLها را از روی
# ویوست‌های *فعلاً ثبت‌شده* می‌سازد. اگر بعد از include() چیزی register شود،
# اصلاً به urlpatterns اضافه نمی‌شود (این باگ قبلی همین‌جا بود).

urlpatterns = [
    path('', include(router.urls)),
    path('auth/register/', views.register, name='register'),
    path('auth/login/', views.login, name='login'),
    path('dashboard/', views.dashboard, name='dashboard'),
]
