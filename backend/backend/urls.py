from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    # تمام مسیرهای اپلیکیشن planner زیرمجموعه api/ قرار می‌گیرند
    path('api/', include('planner.urls')),
]
