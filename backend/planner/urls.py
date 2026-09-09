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
# TokenRefreshView: ویوی آماده‌ی SimpleJWT برای «تمدیدِ توکنِ دسترسی» —
# بدنه‌ی {"refresh": "..."} می‌گیرد و توکنِ دسترسیِ تازه برمی‌گرداند.
# TokenBlacklistView: ویوی آماده‌ی SimpleJWT برای «ابطالِ توکنِ Refresh» —
# بدنه‌ی {"refresh": "..."} می‌گیرد و آن توکن را در لیستِ سیاه ثبت می‌کند
# (لازمه‌ی فعال‌بودنش: اپِ rest_framework_simplejwt.token_blacklist در
# INSTALLED_APPS — از 2026-09-08 فعال است).
from rest_framework_simplejwt.views import TokenBlacklistView, TokenRefreshView
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
    # تمدیدِ توکنِ دسترسی: فرانت‌اند وقتی پاسخِ 401 می‌گیرد، توکنِ Refreshِ ذخیره‌شده را
    # به این مسیر می‌فرستد و توکنِ دسترسیِ تازه می‌گیرد (و اگر خودِ توکنِ Refresh هم
    # منقضی/بی‌اعتبار باشد، همین مسیر 401 می‌دهد و فرانت‌اند کاربر را به صفحه‌ی ورود
    # هدایت می‌کند). این ویو مثلِ register/login بدونِ هدرِ Authorization در دسترس است
    # (خودِ توکنِ Refresh اثباتِ هویت است، نه هدر).
    path('auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    # خروجِ سرور-محور (از 2026-09-08): فرانت‌اند موقعِ خروج، توکنِ Refreshِ
    # ذخیره‌شده را به این مسیر می‌فرستد تا رویِ سرور باطل شود؛ بعد از این،
    # حتی اگر کسی localStorage را دزدیده باشد، آن توکن دیگر قابلِ تمدید نیست
    # (تا ۷ روزِ قبل از این تغییر، توکنِ خروج‌شده تا پایانِ عمرش معتبر می‌ماند).
    # این ویو هم مثلِ refresh بدونِ هدرِ Authorization در دسترس است.
    path('auth/logout/', TokenBlacklistView.as_view(), name='token_blacklist'),
    path('dashboard/', views.dashboard, name='dashboard'),
    # پیش‌بینیِ هوشمند (از 2026-09-09): GET /api/predictions/ — مؤلفه‌ی
    # یادگیریِ آماری (کالیبراسیونِ تخمین‌هایِ ساعتیِ کاربر رویِ تاریخچه‌ی
    # StudyLogها + ریسکِ عقب‌افتادن برایِ امتحان‌هایِ آینده). مثلِ dashboard
    # فقط با لاگین در دسترس است و رشته‌هایش ماشین‌خوانند (ترجمه در فرانت‌اند).
    path('predictions/', views.predictions, name='predictions'),
]
