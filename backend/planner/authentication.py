# planner/authentication.py
# ----------------------------------------------------------------------------
# لایه‌ی احرازِ هویتِ سفارشیِ JWT (از 2026-09-10).
#
# مسئله: توکنِ دسترسیِ JWT «بی‌حالت» است — اعتبارش فقط با امضایِ سرور و
# تاریخِ انقضا (ACCESS_TOKEN_LIFETIME = ۱ روز) چک می‌شود، نه با دیتابیس.
# یعنی اگر کاربر رمزش را عوض کند یا حسابش لو برود، توکن‌هایِ دسترسیِ
# صادرشده‌یِ قبلی تا پایانِ عمرشان معتبر می‌مانند — «ابطالِ لیستِ سیاهِ
# توکنِ Refresh» (2026-09-08) فقط مسیرِ تمدید را می‌بندد، نه خودِ توکنِ
# دسترسی را.
#
# راه‌حلِ این‌جا: هر توکنِ JWT ادعایِ استانداردِ iat («issued at» = لحظه‌ی
# صدور، ثانیه‌ی یونیکس) دارد و هر تغییرِ رمزِ موفق لحظه‌اش در
# UserSecurityProfile.password_changed_at ثبت می‌شود. این کلاس بعد ازِ
# اعتبارسنجیِ امضا و کاربر، این دو را مقایسه می‌کند: توکنی که «قبل ازِ
# آخرینِ تغییرِ رمز» صادر شده باشد رد می‌شود — یعنی تغییرِ رمز، همه‌ی
# نشست‌ها (حتی توکن‌هایِ دسترسیِ زنده) را در سرِ همان لحظه باطل می‌کند.
#
# هزینه: فقط برایِ کاربرانی که رکوردِ پروفایل دارند یک SELECT کوچک اضافه
# می‌شود (کاربرانِ عادی — که هرگز رمز عوض نکرده‌اند — رکورد ندارند و دقیقاً
# همان مسیرِ اجراییِ قبلی را می‌روند؛ اصلِ dev-safe).
#
# مرزِ شناخته‌شده (صادقانه): iat با رزولوشنِ ثانیه است؛ توکنی که در «همانِ
# ثانیه‌ی» تغییرِ رمز صادر شده باشد معتبر می‌ماند (پنجره‌ی حداکثرِ یک
# ثانیه). توکنِ تازه‌ای که بلافاصله بعد ازِ تغییرِ رمز صادر می‌شود (خودِ
# پاسخِ تغییرِ رمز) iat >= لحظه‌ی تغییر دارد و مشکلی ندارد.
# ----------------------------------------------------------------------------

from django.utils.translation import gettext as _
from rest_framework import exceptions
from rest_framework_simplejwt.authentication import JWTAuthentication

from .models import UserSecurityProfile


class SessionInvalidatingJWTAuthentication(JWTAuthentication):
    """
    همانِ JWTAuthenticationِ استانداردِ SimpleJWT + یک قدم اضافه در get_user:
    ردِ توکن‌هایِ دسترسیِ صادرشده «قبل ازِ آخرینِ تغییرِ رمزِ» کاربر.

    JWTAuthentication.authenticate() با این ترتیب کار می‌کند: خواندنِ هدر →
    اعتبارسنجیِ امضا/انقضا (get_validated_token) → یافتنِ کاربر (get_user).
    قدمِ اضافه در get_user می‌نشیند چون کاربر باید از قبل حل‌شده باشد و
    ردِ توکن باید «AuthenticationFailed» باشد تا DRF همان ۴۰۱ استانداردِ
    (با هدرِ WWW-Authenticate) را برگرداند که فرانت‌اند از قبل برای‌ش
    استراتژی دارد (تمدیدِ بی‌صدا و در صورتِ شکست، هدایت به صفحه‌ی ورود).
    """

    def get_user(self, validated_token):
        user = super().get_user(validated_token)

        # فقط برایِ کاربرانی که تا به حال رمزشان را عوض کرده‌اند رکورد وجود
        # دارد؛ filter().first() به‌جایِ user.security_profile تا نبودِ رکورد
        # (کاربرانِ عادی) با exception نپرد و همانِ None برگردد.
        profile = UserSecurityProfile.objects.filter(user_id=user.pk).first()
        if profile is None:
            return user

        # iat لحظه‌ی صدورِ توکن (ثانیه‌ی یونیکس) است؛ password_changed_at
        # timezone-aware است و USE_TZ روشن است، پس timestamp() مقایسه‌ی
        # درستی می‌دهد. int() برایِ مقایسه‌ی ثانیه‌به‌ثانیه (متنِ docstringِ
        # کلاس: توکنِ «همان ثانیه» معتبر می‌ماند).
        issued_at = validated_token.payload.get('iat') or 0
        changed_at = int(profile.password_changed_at.timestamp())
        if issued_at < changed_at:
            # code='password_changed' برایِ این که تست/مانیتورینگ بتواند
            # این ۴۰۱ را از ۴۰۱ِ «امضای خراب/انقضا» تشخیص دهد.
            raise exceptions.AuthenticationFailed(
                _('رمز عبور این حساب تغییر کرده است؛ لطفاً دوباره وارد شوید.'),
                code='password_changed',
            )

        return user
