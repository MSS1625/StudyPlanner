from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    # پنل مدیریتِ آماده‌ی جنگو (برای دیدنِ مستقیم داده‌ها در دیتابیس)
    path('admin/', admin.site.urls),
    # تمام مسیرهای اپلیکیشن planner زیرمجموعه api/ قرار می‌گیرند
    # یعنی مثلاً /subjects/ داخل planner/urls.py در عمل روی
    # آدرسِ /api/subjects/ در دسترس خواهد بود.
    path('api/', include('planner.urls')),
]
