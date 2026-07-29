# StudyPlanner/backend/planner/urls.py
# ----------------------------------------------------------------------------
# این فایل «نقشه‌ی مسیرها»ی اپلیکیشن planner است: تعیین می‌کند هر آدرسِ URL
# (بعد از پیشوندِ /api/ که در backend/urls.py اضافه می‌شود) به کدام View
# در views.py وصل شود.
# ----------------------------------------------------------------------------

from django.urls import path, include
# DefaultRouter: به‌جای نوشتنِ دستیِ ۵ مسیر برای هر ViewSet (list/create/
# retrieve/update/delete)، با یک خط register این مسیرها را خودکار می‌سازد.
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
# هرکدام از این خط‌ها یعنی: «برای این پیشوند، این ViewSet را مسئول کن».
# مثلاً router.register(r'subjects', ...) خودش مسیرهای زیر را می‌سازد:
#   GET/POST      /subjects/
#   GET/PUT/PATCH/DELETE  /subjects/{id}/
router.register(r'subjects', views.SubjectViewSet, basename='subject')
router.register(r'exams', views.ExamViewSet, basename='exam')
router.register(r'study-plan', views.StudyPlanViewSet, basename='study-plan')
router.register(r'study-logs', views.StudyLogViewSet, basename='studylog')

# نکته‌ی مهم: router.register باید همیشه قبل از include(router.urls) انجام شود،
# چون router.urls در همان لحظه‌ای که فراخوانی می‌شود، لیست URLها را از روی
# ویوست‌های *فعلاً ثبت‌شده* می‌سازد. اگر بعد از include() چیزی register شود،
# اصلاً به urlpatterns اضافه نمی‌شود (این باگ قبلی همین‌جا بود).

urlpatterns = [
    # include(router.urls) یعنی: همه‌ی مسیرهایی که بالاتر با register ساختیم،
    # همین‌جا (زیرِ همین پیشوند) اضافه شوند.
    path('', include(router.urls)),
    # این سه مسیر، توابعِ ساده (نه ViewSet) هستند، پس دستی تعریف می‌شوند.
    path('auth/register/', views.register, name='register'),
    path('auth/login/', views.login, name='login'),
    path('dashboard/', views.dashboard, name='dashboard'),
]
