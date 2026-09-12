# planner/views.py
# ----------------------------------------------------------------------------
# این فایل «ویوها» (Views) را تعریف می‌کند: کدی که واقعاً به هر درخواستِ HTTP
# پاسخ می‌دهد. دو نوع View در این پروژه استفاده شده:
#   ۱) توابعِ ساده با دکوریتورِ @api_view (برای register/login/dashboard که
#      عملیاتِ CRUD معمولی نیستند)
#   ۲) کلاس‌های ViewSet (برای Subject/Exam/StudyLog/StudyPlan که عملیاتِ
#      استاندارد CRUD دارند و DRF می‌تواند مسیرهایشان را خودکار بسازد)
# ----------------------------------------------------------------------------

from datetime import date

from rest_framework import viewsets, status, permissions, pagination
# api_view: تبدیل یک تابعِ ساده‌ی پایتون به یک View قابل‌فهم برای DRF
# permission_classes: تعیینِ این‌که چه کسی اجازه‌ی صدا زدنِ این View را دارد
# action: برای اضافه‌کردنِ یک مسیرِ سفارشی (غیر از CRUD معمولی) به یک ViewSet
# throttle_classes: تعیینِ کلاس‌هایِ محدودسازیِ نرخِ درخواستِ این View
# (از 2026-09-10 — روی register/login برای دفاعِ brute-force)
from rest_framework.decorators import api_view, permission_classes, action, throttle_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, ValidationError
# RefreshToken: برای ساختنِ توکن‌های JWT (دسترسی + تمدید) هنگام ثبت‌نام/ورود
from rest_framework_simplejwt.tokens import RefreshToken
# جداولِ «توکن‌هایِ صادرشده» و «لیستِ سیاه» (از 2026-09-10 برایِ تغییرِ رمز):
# هنگامِ تغییرِ رمز، همه‌ی توکن‌هایِ Refreshِ برجسته‌یِ کاربر یک‌جا باطل می‌شوند
# (خروجِ تک‌توکنیِ /api/auth/logout/ فقط یکی را می‌بندد).
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
# سیاستِ رمزِ عبور (از 2026-09-10): اعتبارسنج‌هایِ AUTH_PASSWORD_VALIDATORS
# روی رمزِ جدیدِ تغییرِ رمز هم اجرا می‌شوند (پیام‌ها مالِ جنگو — ترجمه‌ی fa/en
# خودکار). خطای جنگو با نامِ مستعارِ جدا تا با ValidationErrorِ DRF اشتباه نشود.
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
# timezone.now (از 2026-09-10): مهرِ زمانِ تغییرِ رمز در UserSecurityProfile
from django.utils import timezone
# gettext (از 2026-09-09): پیام‌هایِ API با زبانِ درخواست (Accept-Language)
# ترجمه می‌شوند؛ متنِ اصلی فارسی است و کاتالوگِ en ترجمه‌ی انگلیسی را می‌دهد.
from django.utils.translation import gettext as _
# بازیابیِ رمز (از 2026-09-12): uid امنِ base64 (بدون افشای pk خام در URL) و
# مولدِ توکنِ امضاشده‌ی جنگو — جزئیات در password_reset_request پایین‌تر.
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.db import IntegrityError, transaction
from django.db.models import Q
# لاگِ سرور-محورِ مشترک (از 2026-09-12): اطلاع‌رسانیِ امنیتیِ ایمیل و شکستِ
# ارسالِ آن (مثلِ بازیابیِ رمز) — یک logger در سطحِ ماژول، الگویِ استانداردِ جنگو.
import logging
# پایشِ سلامت (از 2026-09-10): اتصالِ زندهٔ دیتابیس برای endpointِ health و
# تنظیماتِ جاری (نمایشِ DEBUG) — هر دو فقط «خواندن» هستند.
from django.db import connection
from django.conf import settings

from .models import Subject, Exam, StudyPlan, StudyLog, UserSecurityProfile, SecurityEvent
from .serializers import UserSerializer, SubjectSerializer, ExamSerializer, StudyPlanSerializer, StudyLogSerializer, SecurityEventSerializer
from .utils import generate_study_plan, format_plan_for_frontend, build_subject_distribution, compute_subject_progress
# مؤلفه‌ی یادگیریِ آماری (از 2026-09-09): مدلِ کالیبراسیونِ «تخمینِ ساعتیِ
# کاربر ↔ واقعیتِ ثبت‌شده» + پیش‌بینیِ ساعتِ واقعیِ موردنیاز و ریسکِ
# عقب‌افتادن — جزئیات و محدودیت‌های مدل در planner/ml.py.
from .ml import get_prediction_report
# محدودسازیِ نرخِ درخواست روی مسیرهایِ احرازِ هویت (از 2026-09-10): جلوگیری از
# حمله‌ی حدسِ رمز (brute-force) — نرخ از متغیرِ محیطیِ DJANGO_AUTH_THROTTLE_RATE.
from .throttles import AuthBurstThrottle

# لاگرِ ماژول — همه‌ی رشته‌هایِ «خطای زیرساختی که نباید به پاسخِ HTTP بریزد»
# از این‌جا می‌گذرند (شکستِ SMTP در اطلاع‌رسانیِ امنیتی/بازیابی).
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# احراز هویت
# ---------------------------------------------------------------------------

@api_view(['POST'])
# AllowAny یعنی این مسیر برخلاف بقیه‌ی مسیرهای پروژه، نیازی به لاگین‌بودن ندارد
# (طبیعی است؛ کسی که می‌خواهد ثبت‌نام کند، هنوز حسابی ندارد!)
@permission_classes([AllowAny])
# محدودسازیِ نرخِ ویژهٔ احرازِ هویت (از 2026-09-10): بدونِ متغیرِ محیطی،
# نرخِ پیش‌فرض 10000/min = مؤثراً نامحدود است (رفتارِ توسعه دست‌نخورده)؛
# در Production با DJANGO_AUTH_THROTTLE_RATE مثل '20/min' فعال می‌شود.
@throttle_classes([AuthBurstThrottle])
def register(request):
    # داده‌ی خام درخواست (JSON) را به سریالایزر می‌دهیم تا هم اعتبارسنجی
    # شود (یکتا بودنِ username/email) و هم بعداً برای ساختِ کاربر استفاده شود
    serializer = UserSerializer(data=request.data)
    if serializer.is_valid():
        # serializer.save() در پس‌زمینه متد create() خودِ سریالایزر را صدا
        # می‌زند که در آن create_user (با هش‌کردنِ خودکارِ رمز) فراخوانی می‌شود
        user = serializer.save()
        # بلافاصله بعد از ثبت‌نام، یک جفت توکن (دسترسی + تمدید) هم صادر
        # می‌کنیم تا کاربر مجبور نباشد بلافاصله دوباره وارد شود
        refresh = RefreshToken.for_user(user)
        return Response({
            'user': serializer.data,
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }, status=status.HTTP_201_CREATED)
    # اگر اعتبارسنجی شکست خورد (مثلاً نام کاربری تکراری بود)، خطاها را برگردان
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])
# همین محدودیتِ نرخِ احرازِ هویت روی login — هدفِ اصلیِ دفاعِ brute-force
# اینجاست (حدسِ رمزِ عبور).
@throttle_classes([AuthBurstThrottle])
def login(request):
    username = request.data.get('username')
    password = request.data.get('password')
    # authenticate یک تابعِ آماده‌ی جنگو است: رمزِ واردشده را دوباره Hash
    # می‌کند و با مقدارِ ذخیره‌شده در دیتابیس مقایسه می‌کند؛ اگر مطابقت
    # داشت، آبجکتِ کاربر را برمی‌گرداند، وگرنه None
    user = authenticate(username=username, password=password)
    if user:
        # لاگِ رویدادهایِ امنیتی (از 2026-09-12): هر ورودِ موفق در تاریخچه‌ی
        # حسابِ خودِ کاربر ثبت می‌شود (IP + User-Agent) — کاربر می‌تواند از
        # GET /api/auth/security/events/ ببیند «چه وقلی از کجا» وارد شده است.
        SecurityEvent.record(
            user=user,
            event_type=SecurityEvent.EventType.LOGIN_SUCCESS,
            request=request,
        )
        refresh = RefreshToken.for_user(user)
        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        })
    # تلاشِ ناموفق — فقط برای «کاربرِ موجودِ فعال» ثبت می‌شود (کاربرِ ناموجود
    # که رویدادی ندارد که به آن بچسبد؛ کاربرِ غیرفعال هم که لاگین نمی‌بیند).
    # iexact عمداً: جابه‌جاییِ حروفِ بزرگ/کوچکِ نامِ کاربری هم برایِ مالکِ واقعی
    # قابل‌مشاهده باشد — این داده فقط با توکنِ خودِ کاربر خوانده می‌شود و
    # هیچ اثری در «پاسخِ» این مسیر نمی‌گذارد (پیامِ خطا برایِ موجود/ناموجود
    # یکسان باقی می‌ماند).
    if username:
        attempted_user = User.objects.filter(
            username__iexact=username, is_active=True,
        ).first()
        if attempted_user is not None:
            SecurityEvent.record(
                user=attempted_user,
                event_type=SecurityEvent.EventType.LOGIN_FAILED,
                request=request,
            )
    return Response({'error': _('نام کاربری یا رمز عبور اشتباه است')}, status=status.HTTP_401_UNAUTHORIZED)


# ---------------------------------------------------------------------------
# کمکیِ مشترکِ «ابطالِ همه‌ی نشست‌ها» (از 2026-09-12 از دلِ change_password
# استخراج شد چون بازیابیِ رمز هم دقیقاً همان کار را لازم دارد)
# ---------------------------------------------------------------------------

def _invalidate_all_sessions(user):
    """همه‌ی نشست‌هایِ کاربر را باطل می‌کند — دو مسیرِ هم‌زمان:

    ۱) همه‌ی توکن‌هایِ Refreshِ برجسته لیست‌سیاه می‌شوند (مسیرِ «تمدید»
       بسته می‌شود — توکنِ دزدیده‌شده دیگر قابلِ نوسازی نیست).
    ۲) UserSecurityProfile.password_changed_at ثبت می‌شود تا لایه‌ی
       planner/authentication.py توکن‌هایِ «دسترسیِ» صادرشده قبل از این
       لحظه را هم رد کند (توکنِ JWT بی‌حالت است و مگر با این پیچِ دولایه
       تا پایانِ عمرش زنده می‌ماند).

    نکته‌ی تراکنش: فراخواننده باید این را داخلِ transaction.atomic() صدا
    بزند تا با set_password یا هر تغییرِ دیگری اتمیک بماند (الگویِ «یا
    همه، یا هیچ» — هر دو مسیرِ ابطال با هم اعمال می‌شوند).

    نکته‌ی idempotence: دوباره‌صدا‌کردنش بی‌خطر است — update_or_create فقط
    لحظه را تازه می‌کند و get_or_create فقط رد می‌شود (بعضی توکن‌ها ممکن
    است از قبل باطل باشند، مثلاً با logout یا چرخش).
    """
    UserSecurityProfile.objects.update_or_create(
        user=user,
        defaults={'password_changed_at': timezone.now()},
    )
    for outstanding in OutstandingToken.objects.filter(user=user):
        BlacklistedToken.objects.get_or_create(token=outstanding)


def _send_password_notification(user, event):
    """ایمیلِ اطلاع‌رسانیِ امنیتی بعد از تغییر/بازنشانیِ رمز (از 2026-09-12).

    روی «رویدادهایِ پُرسیگنال» فرستاده می‌شود — تغییرِ رمز (توسطِ خودِ کاربر)
    و بازنشانیِ رمز (با لینکِ بازیابی) — نه روی هر ورود/تلاشِ ورود (سروصدای
    بی‌فایده و ابزارِ بمبارانِ صندوقِ کاربر با لاگین‌هایِ ناموفق).

    قواعد:
    - بدونِ ایمیلِ ثبت‌شده → هیچ کاری نمی‌کند (بی‌صدا و بی‌خطا).
    - شکستِ SMTP → ثبت در لاگِ سرور و بلعیده می‌شود (logger.exception) —
      اطلاع‌رسانیِ «لطفاً» نباید مسیرِ اصلی (خودِ تغییر/بازنشانی) را ۵۰۰ کند.
      الگویِ همانِ views.password_reset_request.
    - متن‌ها gettext هستند (fa/en با Accept-Language در لحظه‌ی درخواست).
    - ایمیلِ رخدادِ بازنشانی به‌علاوه توصیه‌ی «اگر شما نبودید» دارد چون
      نشانه‌ی جدیِ تلاشِ موفق مهاجم است؛ تغییرِ رمز هم همین توصیه را دارد.

    ورودیِ event = رکوردِ SecurityEventِ همین لحظه — برایِ متنِ ایمیل (نوعِ
    رویداد + IPِ فرستنده) استفاده می‌شود.
    """
    if not user.email:
        return

    is_reset = event.event_type == SecurityEvent.EventType.PASSWORD_RESET_COMPLETED
    if is_reset:
        subject = _('بازنشانیِ رمزِ عبور — برنامه‌ریزِ هوشمندِ مطالعه')
        body = _(
            'سلام %(username)s،\n\n'
            'رمزِ عبورِ حسابِ شما با لینکِ بازیابی بازنشانی شد و همه‌ی '
            'نشست‌هایِ قبلی باطل شدند.\n'
            'نشانیِ فرستنده: %(ip)s\n\n'
            'اگر این کار را شما کرده‌اید، با رمزِ جدید وارد شوید.\n'
            'اگر شما این کار را نکرده‌اید، همین حالا از صفحه‌ی ورود با '
            '«رمز را فراموش کرده‌اید؟» دوباره رمز را بازنشانی کنید.'
        ) % {
            'username': user.get_username(),
            'ip': event.ip_address or _('نامشخص'),
        }
    else:
        subject = _('تغییرِ رمزِ عبور — برنامه‌ریزِ هوشمندِ مطالعه')
        body = _(
            'سلام %(username)s،\n\n'
            'رمزِ عبورِ حسابِ شما تغییر کرد و همه‌ی نشست‌هایِ دیگر باطل شدند.\n'
            'نشانیِ فرستنده: %(ip)s\n\n'
            'اگر این تغییر را شما انجام داده‌اید، نیازی به هیچ کاری نیست.\n'
            'اگر شما این تغییر را نکرده‌اید، همین حالا از صفحه‌ی ورود با '
            '«رمز را فراموش کرده‌اید؟» رمز را بازنشانی کنید.'
        ) % {
            'username': user.get_username(),
            'ip': event.ip_address or _('نامشخص'),
        }

    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [user.email])
    except Exception:  # noqa: BLE001 — نیتِ صریح: پنهان‌سازی از پاسخِ HTTP
        logger.exception(
            'security notification email failed for user pk=%s event=%s',
            user.pk, event.event_type,
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def change_password(request):
    """تغییرِ رمزِ عبورِ حسابِ خودِ کاربر (از 2026-09-10) — POST /api/auth/password/

    ورودی: {"current_password": "...", "new_password": "..."}
    خروجیِ موفق: ۲۰۰ + {"detail": ..., "refresh": ..., "access": ...} — جفتِ
    توکنِ تازه همان‌جا صادر می‌شود تا نشستِ «همین دستگاهِ» فعلی بی‌وقفه ادامه
    پیدا کند؛ همه‌ی نشست‌هایِ دیگر (توکن‌هایِ Refreshِ برجسته + توکن‌هایِ دسترسیِ
    قبل ازِ تغییر) باطل می‌شوند.

    دفاعِ سه‌لایه:
      ۱) رمزِ فعلی باید درست باشد (۴۰۰ با پیامِ ترجمه‌شده — جلویِ تغییرِ رمز
         توسطِ نشستِ لو‌رفته‌ای صرفاً توکن‌دار).
      ۲) رمزِ جدید باید از AUTH_PASSWORD_VALIDATORS عبور کند (۴۰۰ با
         پیام‌هایِ سیاست — همان‌هایِ ثبت‌نام).
      ۳) بعد ازِ تغییر: همه‌ی OutstandingTokenهایِ کاربر لیست‌سیاه +
         UserSecurityProfile.password_changed_at ثبت می‌شود تا توکن‌هایِ
         دسترسیِ قبل ازِ تغییر هم ۴۰۱ بگیرند (planner/authentication.py).

    محدودسازیِ نرخ: پیش‌فرضِ سراسری (scopeِ 'user' — نرخِ هر کاربر)؛ برخلافِ
    register/login که AuthBurstThrottle دارند، این مسیر فقط برایِ کاربرِ لاگین‌شده
    معنا دارد و تلاشِ حدسی رویش ممکن نیست (رمزِ فعلی لازم است).
    """
    current_password = request.data.get('current_password') or ''
    new_password = request.data.get('new_password') or ''

    # لایه‌ی ۱: رمزِ فعلی. چکِ صریح (نه authenticate) چون username لازم نیست
    # و کاربر از قبل با توکنِ معتبر شناخته‌شده است.
    if not request.user.check_password(current_password):
        return Response(
            {'current_password': [_('رمز عبور فعلی اشتباه است.')]},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # لایه‌ی ۲: سیاستِ رمزِ جدید. این‌جا transient user لازم نیست — خودِ
    # request.user برایِ مقایسه‌ی شباهت (UserAttributeSimilarity) از دیتابیس
    # حل‌شده است.
    try:
        validate_password(new_password, request.user)
    except DjangoValidationError as error:
        return Response(
            {'new_password': list(error.messages)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # لایه‌ی ۳: اعمالِ اتمیک. set_password رمز را هش می‌کند (هرگز رمزِ خام
    # ذخیره نمی‌شود)؛ سپس همه‌ی توکن‌هایِ Refreshِ برجسته باطل و لحظه‌ی تغییر
    # ثبت می‌شود. ترتیب داخلِ transaction: یا همه، یا هیچ (از 2026-09-12
    # بدنه‌ی مشترک در _invalidate_all_sessions زندگی می‌کند). ضبطِ رویدادِ
    # امنیتی (password_changed) هم داخلِ همین تراکنش است تا «رمز عوض شد» و
    # «رویدادش ثبت شد» جدایی‌ناپذیر باشند.
    with transaction.atomic():
        request.user.set_password(new_password)
        request.user.save(update_fields=['password'])
        _invalidate_all_sessions(request.user)
        event = SecurityEvent.record(
            user=request.user,
            event_type=SecurityEvent.EventType.PASSWORD_CHANGED,
            request=request,
        )

    # اطلاع‌رسانیِ ایمیلیِ امنیتی — بعد از commit (ایمیل داخلِ تراکنشِ DB
    # نمی‌نشیند)؛ شکستِ ارسالِ آن مسیرِ اصلی را خراب نمی‌کند.
    _send_password_notification(request.user, event)

    # جفتِ توکنِ تازه «بعد ازِ» سیاه‌کردنِ قدیمی‌ها صادر می‌شود تا خودش
    # در لیستِ سیاه نیفتد؛ iat آن >= لحظه‌ی تغییر است (مرزِ همان‌ثانیه در
    # docstringِ authentication.py) و فرانت‌اند هر دو را ذخیره می‌کند.
    refresh = RefreshToken.for_user(request.user)
    return Response({
        'detail': _('رمز عبور با موفقیت تغییر کرد؛ همه‌ی نشست‌هایِ دیگر باطل شدند.'),
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    })


@api_view(['POST'])
@permission_classes([AllowAny])
# همان محدودیتِ نرخِ register/login (scopeِ 'auth'، به‌ازایِ IP): این مسیر
# بدونِ لاگین صدا زده می‌شود و بدونِ سقف، می‌توان با آن صدها ایمیل (یا
# صدها پروبِ «آیا این نامِ کاربری وجود دارد؟») تولید کرد.
@throttle_classes([AuthBurstThrottle])
def password_reset_request(request):
    """درخواستِ لینکِ بازیابیِ رمز (از 2026-09-12) — POST /api/auth/password/reset/

    ورودی: {"identifier": "نام کاربری یا ایمیل"} (یکی کافی است؛ backend هر
    دو را امتحان می‌کند). خروجی: ۲۰۰ با پیامِ عمومی — همیشه.

    اصلِ ضدِ کشفِ حساب (anti-enumeration): پاسخِ «حسابِ موجود» و «حسابِ
    ناموجود» بایت‌به‌بایت یکسان است؛ نه status فرق دارد نه بدنه. کسی که
    می‌خواهد فهرستِ نام‌هایِ کاربریِ ثبت‌شده را دربیاورد، از اینجا هیچ
    اطلاعاتی نمی‌گیرد (این پاسخِ یکسان، «قراردادِ» این endpoint است —
    نکته‌ی ۶.۱۸ AI_CONTEXT؛ تغییرش یعنی بازکردنِ کانالِ نشت).

    سه حالتِ «بی‌ایمیل» (حسابِ ناموجود / حسابِ بدونِ ایمیلِ ثبت‌شده / حسابِ
    غیرفعال) هیچ فرقی در پاسخ ندارند و فقط ایمیل فرستاده نمی‌شود. اگر
    حسابِ موجود و ایمیل‌دار باشد، لینکِ یک‌بارمصرف به آن آدرس می‌رود.

    موتورِ ایمیل: EMAIL_BACKEND — در توسعه console (لینک در stdoutِ
    runserver) و در Production SMTP (05_deployment.md). خطایِ ارسالِ SMTP
    عمداً «ثبت و بلعیده» می‌شود (logger.exception) تا شکستِ سرویسِ ایمیل
    همان کانالِ نشت را باز نکند (۵۰۰ برایِ موجود و ۲۰۰ برایِ ناموجود =
    oracle) — ادمین آن را در لاگ می‌بیند.
    """
    identifier = (request.data.get('identifier') or '').strip()
    if not identifier:
        return Response(
            {'detail': _('نام کاربری یا ایمیل را وارد کنید.')},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # __iexact برایِ هر دو: ایمیل در ثبت‌نام اختیاری است و کاربر ممکن است
    # با هر کدام باشد. مرزیِ شناخته‌شده: دو حسابِ «A@x» و «a@x» (که فقط در
    # حروفِ بزرگ/کوچکِ ایمیل فرق دارند) از ثبت‌نامِ امروزِ پروژه می‌گذرند
    # (یکتاییِ ستونِ email حساسِبه‌حروف است) — .first() یکی را برمی‌دارد؛
    # ایده‌آل: نرمال‌سازیِ ایمیل هنگامِ ثبت‌نام (وظیفه‌ی آینده، نه این Task).
    user = User.objects.filter(
        Q(email__iexact=identifier) | Q(username__iexact=identifier),
        is_active=True,
    ).first()

    # لاگِ رویدادهایِ امنیتی (از 2026-09-12): درخواستِ بازیابی برایِ حسابِ
    # موجودِ فعال ثبت می‌شود — کاربر بعداً می‌بیند که «درخواستِ بازیابی برایِ
    # حسابِ من ثبت شد» (حتی اگر ایمیلِ ثبت‌شده نداشته باشد و لینکی نرفته
    # باشد — خودِ دانستنِ این تلاش، ارزشِ امنیتی دارد).
    # قراردادِ ضدِ کشفِ حسابِ همین docstring دست‌نخورده می‌ماند: این ثبتِ داخلی
    # هیچ اثری در «پاسخِ» HTTP نمی‌گذارد (بدنه/وضعیت یکسان)؛ تفاوتِ زمانِ
    # اجرا (یک INSERT) هم در برابرِ تفاوتِ زمانِ ارسالِ SMTP که از قبل
    # وجود داشت، ناچیز و غیرقابل‌تشخیص است.
    if user is not None:
        SecurityEvent.record(
            user=user,
            event_type=SecurityEvent.EventType.PASSWORD_RESET_REQUESTED,
            request=request,
        )

    # فقط برایِ حسابِ موجودِ ایمیل‌دار ایمیل می‌رود — بقیه‌ی حالت‌ها به همین
    # جمله‌ی عمومیِ پایین می‌رسند و فرقشان فقط «ایمیل نرفتن» است.
    if user is not None and user.email:
        uid = urlsafe_base64_encode(str(user.pk).encode())
        token = default_token_generator.make_token(user)
        link = (
            f'{settings.FRONTEND_BASE_URL}/static/reset-password.html'
            f'?uid={uid}&token={token}'
        )
        # عمرِ لینک به دقیقه (برایِ جمله‌ی صادقانه‌ی داخلِ ایمیل) — از همان
        # تنظیمِ واحدِِ رفتارِ سرور (PASSWORD_RESET_TIMEOUT) خوانده می‌شود.
        minutes = max(1, settings.PASSWORD_RESET_TIMEOUT // 60)
        subject = _('بازیابیِ رمزِ عبور — برنامه‌ریزِ هوشمندِ مطالعه')
        # gettext پیام را ترجمه می‌کند و % مقادیر را داخلش می‌گذارد (الگویِ
        # استانداردِ جنگو برایِ placeholderهایِ نامی — ترتیب در msgstr آزاد است).
        body = _(
            'سلام %(username)s،\n\n'
            'برایِ تعیینِ رمزِ عبورِ جدید، این لینک را در مرورگر باز کنید:\n\n'
            '%(link)s\n\n'
            'این لینک %(minutes)s دقیقه اعتبار دارد و فقط یک‌بار قابلِ استفاده است. '
            'اگر شما این درخواست را نداده‌اید، این ایمیل را نادیده بگیرید؛ '
            'رمزِ عبورِ شما تغییری نمی‌کند.'
        ) % {
            'username': user.get_username(),
            'link': link,
            'minutes': minutes,
        }
        try:
            send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [user.email])
        except Exception:  # noqa: BLE001 — نیتِ صریح: پنهان‌سازی از پاسخِ HTTP
            # شکستِ SMTP نباید به کاربرِ بی‌اطلاع ۵۰۰ بدهد (کانالِ نشتِ
            # موجود/ناموجود)؛ در لاگِ سرور با سطحِ ERROR باقی می‌ماند.
            logger.exception(
                'password reset email delivery failed for user pk=%s', user.pk
            )

    # پاسخِ واحدِ همه‌ی حالت‌ها — همین متن، همین status، همین کلیدها.
    return Response({
        'detail': _(
            'اگر این حساب وجود داشته باشد، لینکِ بازیابی به ایمیلِ شما ارسال شد.'
        ),
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def password_reset_confirm(request):
    """تعیینِ رمزِ جدید با لینکِ بازیابی (از 2026-09-12) — POST /api/auth/password/reset/confirm/

    ورودی: {"uid": "...", "token": "...", "new_password": "..."} — uid و token
    همان چیزی است که در لینکِ ایمیل آمده. خروجیِ موفق: ۲۰۰ + پیامِ ترجمه‌شده؛
    خروجیِ ناموفق: ۴۰۰ با پیامِ واحدِ «نامعتبر یا منقضی».

    چرا توکنِ «امضاشده‌ی» جنگو و نه جدولِ رمزِ یک‌بارمصرف در دیتابیس؟
    PasswordResetTokenGenerator همان الگویِ «امضا با SECRET_KEY + هشِ وضعیتِ
    کاربر» است: بدونِ ذخیره‌ی چیزی در دیتابیس، یک‌بارمصرف است (بعد از تغییرِ
    رمز، هشِ کاربر عوض می‌شود و توکن مرد)، زمان‌دار است (PASSWORD_RESET_TIMEOUT)
    و جعلش بدونِ SECRET_KEY ممکن نیست. یعنی بدونِ مایگریشنِ جدید.

    نکته‌ی امنیتیِ مهم: بعد از موفقیت، عمداً هیچ توکنی صادر نمی‌شود — بازیابیِ
    رمز یعنی «ورودِ تازه‌ی ثابت‌شده با ایمیل» لازم است، نه ورودِ خودکار. رمزِ
    جدید + همه‌ی نشست‌هایِ قبلی هم همان‌ لحظه باطل می‌شوند (_invalidate_all_sessions)
    تا اگر رمزِ قبلی لو رفته بوده و برای همین بازیابی شده، مهاجمِ توکن‌دار
    بیرون بیفتد (همان تضمینِ تغییرِ رمز از 2026-09-10).

    محدودسازیِ نرخ: throttle پیش‌فرضِ سراسری (scopeِ anon به‌ازایِ IP)؛
    کلاسِ auth اینجا عمداً نیست چون توکنِ امضاشده خودش «رازِ» این مسیر است و
    حدسِش عملاً ممکن نیست — سقفِ anon برایِ جلوگیری از فشارِ خودکار کافی است.
    """
    uid = request.data.get('uid') or ''
    token = request.data.get('token') or ''
    new_password = request.data.get('new_password') or ''

    if not uid or not token or not new_password:
        return Response(
            {'detail': _('هر سه فیلد uid، token و new_password لازمند.')},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # برگرداندنِ uid به کاربر: base64 امن برایِ URL است (کاراکترهایِ +/ به -_
    # تبدیل می‌شوند). هر خطایِ دیکد/جست‌وجو = همان پیامِ واحدِ «نامعتبر» (بدونِ
    # افشایِ این‌که کاربر وجود داشت یا نه).
    try:
        user = User.objects.get(pk=urlsafe_base64_decode(uid).decode(), is_active=True)
    except (TypeError, ValueError, UnicodeDecodeError, OverflowError, User.DoesNotExist):
        return Response(
            {'detail': _('لینکِ بازیابی نامعتبر یا منقضی شده است.')},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not default_token_generator.check_token(user, token):
        return Response(
            {'detail': _('لینکِ بازیابی نامعتبر یا منقضی شده است.')},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # سیاستِ رمزِ جدید — همان اعتبارسنج‌هایِ ثبت‌نام/تغییرِ رمز (پیام‌هایِ
    # خودِ جنگو، ترجمه‌ی fa/en خودکار). user واقعی لازم است چون
    # UserAttributeSimilarity نامِ کاربری را هم می‌سنجد.
    try:
        validate_password(new_password, user)
    except DjangoValidationError as error:
        return Response(
            {'new_password': list(error.messages)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # اعمالِ اتمیک — و آن‌قدر مهم که دوباره گفته شود: set_password هش
    # می‌کند (رمزِ خام هرگز ذخیره نمی‌شود) و _invalidate_all_sessions همه‌ی
    # نشست‌هایِ قدیمی (Refresh + دسترسی) را می‌کشد. توکنِ بازیابی هم با
    # همین تغییر مرد (هشِ رمز در توکن است) — یعنی یک‌بارمصرف. ضبطِ رویدادِ
    # امنیتی (password_reset_completed) هم داخلِ همین تراکنش است تا با
    # خودِ بازنشانی جدایی‌ناپذیر بماند.
    with transaction.atomic():
        user.set_password(new_password)
        user.save(update_fields=['password'])
        _invalidate_all_sessions(user)
        event = SecurityEvent.record(
            user=user,
            event_type=SecurityEvent.EventType.PASSWORD_RESET_COMPLETED,
            request=request,
        )

    # اطلاع‌رسانیِ ایمیلیِ امنیتی — بعد از commit؛ شکستِ ارسالِ آن مسیرِ
    # اصلی (خودِ بازنشانی) را خراب نمی‌کند (قواعد در _send_password_notification).
    _send_password_notification(user, event)

    return Response({
        'detail': _('رمز عبور با موفقیت بازنشانی شد؛ لطفاً با رمزِ جدید وارد شوید.'),
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def security_events(request):
    """تاریخچه‌ی رویدادهایِ امنیتیِ حسابِ خودِ کاربر (از 2026-09-12) — GET /api/auth/security/events/

    فقط با توکنِ خودِ کاربر جواب می‌دهد (جداسازی کامل — کاربر هیچ راهی
    برایِ دیدنِ رویدادهایِ کاربرِ دیگر ندارد؛ رکوردها در خودِ دیتابیس به
    user قید شده‌اند و فیلترِ پرس‌وجو هم رویِ request.user است، پس حتی
    حدسِ id یا دستکاریِ پارامتر راهی نمی‌بازد).

    خروجی: آرایه‌ی JSON از تازه‌ترین رویدادها (نوبتِ Meta.ordering)؛ هر
    آیتم شکلِ SecurityEventSerializer را دارد: type (کلیدِ ثابت) + label
    (ترجمه‌شده با Accept-Language) + created_at (ISO) + ip + user_agent.

    پارامترِ اختیاریِ ?limit=N (۱ تا ۲۰۰؛ پیش‌فرضِ ۵۰) — مقدارهایِ خارج از
    بازه/غیرعددی به همان پیش‌فرض/مرز برمی‌گردند (رفتارِ همیشه‌معلوم، نه
    خطا: یک پارامترِ «تعدادِ نمایش» نباید درخواست را خراب کند).

    محدودسازیِ نرخ: پیش‌فرضِ سراسریِ scopeِ 'user' (به‌ازایِ کاربرِ لاگین‌شده)
    — این مسیر فقط خواندنی و سبک است و سقفِ عام کافی است.
    """
    raw_limit = request.query_params.get('limit')
    limit = 50
    if raw_limit is not None:
        try:
            limit = int(raw_limit)
        except (TypeError, ValueError):
            limit = 50
    # مهارِ مرزها: کمتر از ۱ → ۱؛ بیشتر از ۲۰۰ → ۲۰۰ (سقفِِ نگه‌داری هم
    # ۲۰۰ است — نمی‌شود بیشتر از چیزی که نگه می‌داریم خواست).
    limit = max(1, min(limit, 200))

    events = SecurityEvent.objects.filter(user=request.user)[:limit]
    serializer = SecurityEventSerializer(events, many=True)
    return Response(serializer.data)


# ---------------------------------------------------------------------------
# صفحه‌بندیِ اختیاریِ لیست‌ها
# ---------------------------------------------------------------------------

class OptionalPageNumberPagination(pagination.PageNumberPagination):
    """
    صفحه‌بندیِ «اختیاری» برای endpointهای لیستی (درس/امتحان/گزارشِ مطالعه).

    قاعده‌ی سازگاری: تا وقتی کلاینت نه ?page= فرستاده و نه ?page_size=،
    get_page_size مقدارِ None برمی‌گرداند؛ DRF در این حالت صفحه‌بندی را
    کاملاً غیرفعال می‌کند و پاسخ دقیقاً همان «لیستِ کاملِ JSON» قبل است —
    یعنی فرانت‌اندِ فعلیِ پروژه (app.js هیچ‌کدام از این پارامترها را
    نمی‌فرستد) هیچ تغییری حس نمی‌کند.

    به‌محضِ فرستادنِ هرکدام از دو پارامتر، شکلِ پاسخ به قالبِ استانداردِ
    DRF تبدیل می‌شود:
        {"count": 27, "next": "...?page=2", "previous": null, "results": [...]}
    """

    page_query_param = 'page'
    page_size_query_param = 'page_size'
    # سقفِ اندازه‌ی صفحه: حتی اگر کلاینت ۱۰۰۰ بفرستد، سرور در یک پاسخ
    # بیش از ۱۰۰ رکورد نمی‌فرستد (محافظتِ کارایی و پهنای‌باند).
    max_page_size = 100
    # اندازه‌ی صفحه وقتی کلاینت فقط ?page= فرستاده (بدونِ page_size)
    default_page_size = 20

    def get_page_size(self, request):
        # ۱) page_size صریح: همان مقدار (مثبت و با سقفِ max_page_size).
        #    مقدارِ نامعتبر/غیرمثبت به‌خودی‌خود صفحه‌بندی را روشن نمی‌کند:
        #    اگر ?page= هم هست به اندازه‌ی پیش‌فرض می‌افتیم، وگرنه پاسخ
        #    همان لیستِ کامل می‌ماند (رفتارِ همیشه‌معلوم، نه حالتِ پنهانی).
        if self.page_size_query_param in request.query_params:
            try:
                size = int(request.query_params[self.page_size_query_param])
                if size <= 0:
                    raise ValueError
                return min(size, self.max_page_size)
            except (TypeError, ValueError):
                pass
        # ۲) فقط ?page= : اندازه‌ی پیش‌فرضِ پروژه
        if self.page_query_param in request.query_params:
            return self.default_page_size
        # ۳) هیچ پارامتری نیست → None = صفحه‌بندیِ غیرفعال (لیستِ کامل)
        return None


# ---------------------------------------------------------------------------
# درس‌ها و امتحان‌ها
# ---------------------------------------------------------------------------

class SubjectViewSet(viewsets.ModelViewSet):
    """
    ModelViewSet به‌صورت خودکار پنج عملیاتِ CRUD (list, create, retrieve,
    update, destroy) را پیاده می‌کند؛ فقط کافی است بگوییم از کدام سریالایزر
    و کدام queryset استفاده کند (پایین‌تر).
    """
    serializer_class = SubjectSerializer
    # هیچ‌کس بدونِ لاگین نمی‌تواند این ویوست را صدا بزند
    permission_classes = [IsAuthenticated]
    # صفحه‌بندیِ اختیاری (فقط با ?page= / ?page_size= فعال می‌شود؛
    # بدونِ این پارامترها پاسخ همان لیستِ کاملِ قبلی است — سازگار با
    # فرانت‌اندِ فعلی). مرتب‌سازیِ قطعیِ Meta.ordering مدل (جدیدترین
    # درس اول) پایداریِ صفحه‌ها را تضمین می‌کند.
    pagination_class = OptionalPageNumberPagination

    def get_queryset(self):
        # prefetch_related جلوی N+1 کوئری را می‌گیرد چون هر Subject برای
        # محاسبه‌ی پیشرفت باید امتحان‌ها و لاگ‌های مطالعه‌اش را بخواند.
        # نکته‌ی امنیتی مهم: با filter(user=self.request.user) تضمین می‌کنیم
        # هر کاربر فقط درس‌های خودش را می‌بیند، نه درس‌های کاربرِ دیگر.
        return (
            Subject.objects.filter(user=self.request.user)
            .select_related('user')
            .prefetch_related('exams__study_logs')
        )

    def perform_create(self, serializer):
        # هنگام ساختِ یک درسِ جدید، فیلدِ user را از روی کاربرِ لاگین‌کرده
        # (نه از ورودیِ کاربر) پر می‌کنیم؛ یعنی کسی نمی‌تواند برای کاربر
        # دیگری درس بسازد.
        serializer.save(user=self.request.user)


class ExamViewSet(viewsets.ModelViewSet):
    serializer_class = ExamSerializer
    permission_classes = [IsAuthenticated]
    # صفحه‌بندیِ اختیاری — همان کلاسِ مشترکِ درس‌ها (Meta.ordering مدل:
    # امتحانِ نزدیک‌تر اول، پایداریِ صفحه‌ها)
    pagination_class = OptionalPageNumberPagination

    def get_queryset(self):
        # فیلتر بر مبنای subject__user یعنی: فقط امتحان‌هایی که به یک
        # درسِ متعلق به همین کاربر وصل هستند
        return Exam.objects.filter(subject__user=self.request.user).select_related('subject', 'subject__user')

    def perform_create(self, serializer):
        subject = serializer.validated_data['subject']
        # بررسیِ امنیتیِ اضافه: حتی اگر کاربر شناسه‌ی یک درسِ متعلق به
        # کاربرِ دیگر را در بدنه‌ی درخواست بفرستد، اینجا رد می‌شود.
        if subject.user != self.request.user:
            raise PermissionDenied(_("شما مجاز به ایجاد امتحان برای این درس نیستید"))
        serializer.save()

    def perform_update(self, serializer):
        # همان بررسیِ امنیتیِ perform_create، این‌بار برای ویرایش: اگر کاربر
        # در ویرایشِ امتحان، درسِ آن را به درسی از کاربرِ دیگری تغییر دهد،
        # اینجا رد می‌شود (بدونِ این بررسی، ModelViewSet در update استاندارد
        # مالکیتِ «درسِ جدید» را کنترل نمی‌کرد و مهاجم می‌توانست امتحانش را
        # به درسِ دیگری قفل کند). توجه: get_queryset خودِ امتحان را از قبل
        # به امتحان‌های همین کاربر محدود می‌کند.
        subject = serializer.validated_data.get(
            'subject', serializer.instance.subject
        )
        if subject.user != self.request.user:
            raise PermissionDenied(_("شما مجاز به تغییرِ درسِ این امتحان نیستید"))
        serializer.save()


class StudyLogViewSet(viewsets.ModelViewSet):
    serializer_class = StudyLogSerializer
    permission_classes = [permissions.IsAuthenticated]
    # صفحه‌بندیِ اختیاری — همان کلاسِ مشترکِ درس/امتحان (Meta.ordering
    # مدل: گزارشِ جدیدتر اول)
    pagination_class = OptionalPageNumberPagination

    def get_queryset(self):
        # کاربر فقط گزارش‌های مطالعه خودش را می‌بیند
        return StudyLog.objects.filter(user=self.request.user).select_related('exam', 'exam__subject')

    def perform_create(self, serializer):
        exam = serializer.validated_data['exam']
        if exam.subject.user != self.request.user:
            raise PermissionDenied(_("شما مجاز به ثبت گزارش مطالعه برای این امتحان نیستید"))
        # هنگام ذخیره، به صورت خودکار کاربر فعلی را به لاگ وصل می‌کنیم
        # (توجه: خودِ متد save() مدل StudyLog، به‌صورت خودکار ساعتِ باقی‌مانده‌ی
        # امتحانِ مربوطه را هم کم می‌کند؛ اینجا فقط رکوردِ لاگ ذخیره می‌شود)
        serializer.save(user=self.request.user)


# ---------------------------------------------------------------------------
# برنامه‌ریز مطالعه‌ی هوشمند
# ---------------------------------------------------------------------------

def _get_or_create_plan_settings(user):
    """
    هر کاربر یک رکورد «تنظیمات برنامه» دارد (ساعت آزاد روزانه + آخرین
    برنامه‌ی تولیدشده). اگر هنوز نساخته، با مقدار پیش‌فرض ۲ ساعت می‌سازیم.
    این تابع در چند جای این فایل (هم در StudyPlanViewSet، هم در dashboard)
    استفاده می‌شود تا این منطق فقط یک‌بار نوشته شود (اصل DRY).
    """
    settings_obj, _ = StudyPlan.objects.get_or_create(
        user=user,
        defaults={'daily_available_hours': 2.0, 'plan_data': {}},
    )
    return settings_obj


class StudyPlanViewSet(viewsets.ModelViewSet):
    """
    /api/study-plan/            GET   -> برنامه‌ی زنده و فرمت‌شده (?range=daily|weekly)
    /api/study-plan/generate/   POST  -> ثبت ساعت آزاد روزانه‌ی جدید و ساخت مجدد برنامه
    """
    serializer_class = StudyPlanSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return StudyPlan.objects.filter(user=self.request.user).order_by('-created_at')

    def perform_create(self, serializer):
        # رگرسیونِ یکتایی (مایگریشنِ 0008): فیلدِ user از این پس در
        # سطحِ دیتابیس یکتاست؛ یک POST مستقیم به /api/study-plan/ برای
        # بارِ دوم دیگر نباید رکوردِ تکراری بسازد. این چکِ پیشینی +
        # گرفتنِ IntegrityError، خطایِ 500 خام را به پاسخِ 400 خوانا
        # تبدیل می‌کند (همان الگویِ نامِ درسِ تکراری در SubjectViewSet).
        if StudyPlan.objects.filter(user=self.request.user).exists():
            raise ValidationError({
                'detail': _('تنظیماتِ برنامه‌یِ مطالعه برای این کاربر از قبل موجود است؛ '
                            'برای تغییر، از generate یا PATCH استفاده کنید.')
            })
        try:
            serializer.save(user=self.request.user)
        except IntegrityError:
            # حالتِ نادرِ Race: رکورد در فاصله‌یِ بینِ چکِ بالا و INSERT
            # ساخته شد؛ قیدِ DB آن را بلاک کرد و اینجا به 400 خوانا
            # تبدیل می‌شود.
            raise ValidationError({
                'detail': _('تنظیماتِ برنامه‌یِ مطالعه برای این کاربر از قبل موجود است؛ '
                            'برای تغییر، از generate یا PATCH استفاده کنید.')
            })

    def list(self, request, *args, **kwargs):
        """
        به‌جای فهرست خام رکوردهای StudyPlan، برنامه را همیشه به‌صورت زنده
        (بر اساس امتحان‌های فعلی) محاسبه و در قالبی که صفحه‌ی «برنامه مطالعه»
        نیاز دارد برمی‌گردانیم. این یعنی متد پیش‌فرضِ list() جنگو را عمداً
        بازنویسی (Override) کرده‌ایم تا رفتارِ متفاوتی داشته باشد.
        """
        # کاربر با پارامترِ ?range=daily یا ?range=weekly در URL مشخص می‌کند
        # چه نمایی از برنامه می‌خواهد؛ اگر چیزِ دیگری/نامعتبری فرستاد،
        # پیش‌فرض را «روزانه» می‌گذاریم.
        range_type = request.query_params.get('range', 'daily')
        if range_type not in ('daily', 'weekly'):
            range_type = 'daily'

        settings_obj = _get_or_create_plan_settings(request.user)
        # برنامه را از نو (بر مبنای وضعیتِ فعلیِ درس/امتحان‌ها) محاسبه می‌کنیم؛
        # هیچ نسخه‌ی کش‌شده‌ای خوانده نمی‌شود.
        raw_plan = generate_study_plan(request.user, settings_obj.daily_available_hours)
        payload = format_plan_for_frontend(raw_plan, range_type)
        payload['daily_available_hours'] = settings_obj.daily_available_hours
        return Response(payload)

    # این دکوریتور یک مسیرِ اضافی (غیر از CRUD معمولیِ ViewSet) می‌سازد:
    # detail=False یعنی این مسیر روی کلِ Collection است، نه یک آیتم خاص
    # (یعنی آدرسش می‌شود /api/study-plan/generate/ نه /api/study-plan/{id}/generate/)
    @action(detail=False, methods=['post'], url_path='generate')
    def generate(self, request):
        daily_hours = request.data.get('daily_available_hours')

        if daily_hours is None:
            return Response({"error": _("ساعت مطالعه روزانه الزامی است.")}, status=status.HTTP_400_BAD_REQUEST)

        try:
            daily_hours = float(daily_hours)
            if daily_hours <= 0 or daily_hours > 24:
                raise ValueError
        except (TypeError, ValueError):
            return Response({"error": _("ساعت مطالعه باید عددی بین ۰ تا ۲۴ باشد.")}, status=status.HTTP_400_BAD_REQUEST)

        settings_obj = _get_or_create_plan_settings(request.user)
        settings_obj.daily_available_hours = daily_hours

        raw_plan = generate_study_plan(request.user, daily_hours)
        # فقط وقتی برنامه‌ی واقعی ساخته شد آن را ذخیره کن (نه پیام خطا/راهنما)
        if "message" not in raw_plan:
            settings_obj.plan_data = raw_plan
        settings_obj.save()

        range_type = request.query_params.get('range', 'daily')
        if range_type not in ('daily', 'weekly'):
            range_type = 'daily'

        payload = format_plan_for_frontend(raw_plan, range_type)
        payload['daily_available_hours'] = daily_hours
        return Response(payload, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# داشبورد
# ---------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard(request):
    """
    یک تصویر کلی از وضعیت درس‌ها، امتحان‌های پیشِ‌رو، هشدارها و تقسیم‌زمان
    پیشنهادی می‌سازد. دقیقاً همان ساختاری که صفحه‌ی داشبورد در فرانت‌اند
    (renderDashboard در app.js) انتظار دارد.
    """
    user = request.user
    today = date.today()

    # همه‌ی درس‌های همین کاربر، همراه با پیش‌بارگذاریِ امتحان‌ها/لاگ‌ها
    # (برای این‌که compute_subject_progress پایین‌تر کوئریِ اضافه نزند)
    subjects = Subject.objects.filter(user=user).prefetch_related('exams__study_logs')
    total_subjects = subjects.count()

    upcoming_exams_qs = (
        Exam.objects.filter(subject__user=user, exam_date__gte=today)
        .select_related('subject')
        .order_by('exam_date')
    )
    total_exams = upcoming_exams_qs.count()

    # --- پیشرفت درس‌ها ---
    subjects_progress = []
    progress_values = []
    for subject in subjects:
        completed_hours, total_hours, progress_percent = compute_subject_progress(subject)
        progress_values.append(progress_percent)
        subjects_progress.append({
            'name': subject.name,
            'difficulty': subject.difficulty,
            'completed_hours': completed_hours,
            'total_hours': total_hours,
            'progress_percent': progress_percent,
        })

    # میانگینِ ساده‌ی درصدِ پیشرفتِ همه‌ی درس‌ها؛ اگر اصلاً درسی نبود، صفر برگردان
    average_progress = round(sum(progress_values) / len(progress_values), 1) if progress_values else 0

    # --- برنامه‌ی زنده‌ی مطالعه (هم برای یادآوری امروز، هم برای نمودار تقسیم‌زمان) ---
    settings_obj = _get_or_create_plan_settings(user)
    raw_plan = generate_study_plan(user, settings_obj.daily_available_hours)

    # --- امتحان‌های پیشِ‌رو و هشدارها ---
    upcoming_exams_data = []
    alerts = []
    # فقط ۸ امتحانِ نزدیک‌تر را نشان می‌دهیم تا داشبورد شلوغ نشود
    for exam in upcoming_exams_qs[:8]:
        days_left = (exam.exam_date - today).days
        upcoming_exams_data.append({
            'subject_name': exam.subject.name,
            'exam_date': exam.exam_date,
            'remaining_days': days_left,
            'remaining_hours': exam.study_hours_remaining,
        })

        if exam.study_hours_remaining <= 0:
            continue  # این امتحان کاملاً پوشش داده شده، نیازی به هشدار نیست

        # هرچه امتحان نزدیک‌تر باشد، هشدار جدی‌تر (قرمز) است
        if days_left <= 3:
            alerts.append({
                'type': 'danger',
                'message': _("فقط %(days)s روز تا امتحان %(exam)s مانده و %(hours)s ساعت مطالعه باقی است!") % {
                    'days': max(days_left, 0),
                    'exam': exam.subject.name,
                    'hours': exam.study_hours_remaining,
                },
                'subject': exam.subject.name,
            })
        elif days_left <= 7:
            alerts.append({
                'type': 'warning',
                'message': _("%(days)s روز تا امتحان %(exam)s باقی مانده. برنامه‌ات را جدی بگیر.") % {
                    'days': days_left,
                    'exam': exam.subject.name,
                },
                'subject': exam.subject.name,
            })

    # --- یادآوریِ برنامه‌ی امروز (نوع خنثی/info، جدا از هشدارهای فوری) ---
    # از همان raw_plan که بالاتر ساختیم، فقط تسک‌های «امروز» را برمی‌داریم
    today_tasks = raw_plan.get(today.isoformat(), [])
    if today_tasks:
        # یک جمله‌ی طبیعی و خوانا از لیستِ تسک‌های امروز می‌سازیم
        tasks_text = _("، ").join(
            _("%(subject)s (%(hours)s ساعت)") % task for task in today_tasks
        )
        alerts.append({
            'type': 'info',
            'message': _("طبق برنامه‌ی امروز، پیشنهاد می‌شود روی %(tasks)s کار کنی.") % {'tasks': tasks_text},
            'subject': None,
        })

    # --- تقسیم‌زمان پیشنهادی (سهم هر درس از ساعات هفته‌ی آینده) ---
    study_distribution = build_subject_distribution(raw_plan, days=7, top_n=6)

    # کارت «هشدارهای فوری» فقط هشدارهای قرمز (۳ روز یا کمتر) را می‌شمارد؛
    # پنل «هشدارها و یادآوری‌ها» همه‌ی هشدارها/یادآوری‌ها (قرمز + زرد + آبی) را نشان می‌دهد.
    urgent_alerts_count = sum(1 for alert in alerts if alert['type'] == 'danger')

    # در نهایت همه‌ی این داده‌ها را در یک JSON واحد به فرانت‌اند برمی‌گردانیم
    return Response({
        'total_subjects': total_subjects,
        'total_exams': total_exams,
        'average_progress': average_progress,
        'alerts': alerts,
        'urgent_alerts_count': urgent_alerts_count,
        'subjects_progress': subjects_progress,
        'upcoming_exams': upcoming_exams_data,
        'study_distribution': study_distribution,
    })


# ---------------------------------------------------------------------------
# پیش‌بینیِ هوشمند (مؤلفه‌ی یادگیریِ آماری — 2026-09-09)
# ---------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def predictions(request):
    """
    GET /api/predictions/ — پیش‌بینیِ «ساعتِ واقعیِ موردنیاز» برایِ امتحان‌هایِ
    آینده + ریسکِ عقب‌افتادن از برنامه.

    پاسخ سه بخش دارد (شکلِ ثابت، مشابهِ dashboard):
      model       وضعیتِ مدلِ کالیبراسیونِ کاربر: ضریبِ β (نسبتِ واقعیت به
                 تخمین)، تعدادِ نمونه‌ها، اعتماد و سوگیری — بدونِ تاریخچه،
                 β=۱ است یعنی «تخمینِ دستی بی‌طرفانه قبول می‌شود».
      predictions به‌ازای هر امتحانِ آینده‌ی دارایِ ساعتِ باقی‌مانده:
                 ساعتِ اعلام‌شده، ساعتِ پیش‌بینی‌شده، نیازِ روزانه و ریسک.
      summary     شمارشِ امتحان‌ها به تفکیکِ ریسک + جمعِ ساعتِ پیش‌بینی‌شده.

    ساعتِ آزادِ روزانه از همان تنظیماتِ StudyPlan خوانده می‌شود که الگوریتمِ
    برنامه‌ریزی هم استفاده می‌کند (یک منبعِ حقیقت)؛ اگر کاربر هنوز تنظیماتی
    نساخته باشد با پیش‌فرضِ ۲ ساعت ساخته می‌شود.

    نکته: پیام‌های این پاسخ عمداً ماشین‌خوانند (risk: high/medium/low و
    bias: underestimates/...)؛ متنِ نمایشی در فرانت‌اند با i18n.js ترجمه
    می‌شود (نکته‌ی ۶.۱۴ AI_CONTEXT) — پس این endpoint رشته‌ی gettextِ
    جدیدی اضافه نمی‌کند و کاتالوگِ locale/en دست‌نخورده می‌ماند.
    """
    settings_obj = _get_or_create_plan_settings(request.user)
    report = get_prediction_report(request.user, settings_obj.daily_available_hours)
    return Response(report)


# ---------------------------------------------------------------------------
# پایشِ سلامت (Health Check — 2026-09-10)
# ---------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([AllowAny])
# مسیرِ پایش باید همیشه در دسترس باشد — حتی وقتیِ همه‌چیز زیرِ فشار/محدودیت
# است؛ اگر خودِ health محدود شود، «فشارِ پایش» می‌تواند سیستمِ سالم را
# «بیمار» گزارش کند. لیستِ خالی یعنی هیچ کلاسِ throttleای روی این ویو نمی‌نشیند.
@throttle_classes([])
def health(request):
    """
    GET /api/health/ — سلامتِ سرویس برای مانیتورینگ/Load Balancer.

    پاسخ ۲۰۰ یعنی فرایندِ پایتون زنده است «و» دیتابیس به یک کوئریِ ارزانِ
    ``SELECT 1`` جواب می‌دهد؛ هر خطایِ دیتابیس → ۵۰۳. بارِ پاسخ (payload)
    عمداً ماشین‌خوان و بدونِ gettext است (مثلِ predictions — نکتهٔ ۶.۱۴):

        {"status": "ok", "database": "ok", "engine": "sqlite", "debug": false}

    - engine: نامِ موتورِ فعال از connection.vendor (بدونِ ساختِ اتصالِ جدید).
    - debug: حالتِ DEBUG فعلی — برای تشخیصِ سریعِ این‌که کدام «محیط» جواب
      می‌دهد (dev/staging/prod)؛ اطلاعاتِ حساسی فاش نمی‌کند.
    - این endpoint هیچ مدلِ ORM را لمس نمی‌کند تا خرابیِ یک جدول، گزارشِ
      سلامتِ فرایند را خراب نکند — فقط اتصالِ دیتابیس چک می‌شود.
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
        database_status = 'ok'
        http_status = status.HTTP_200_OK
    except Exception:
        # هر نوعِ خطایِ اتصال/اجرا = ناسالم؛ سلامتِ سرویس نباید به نوعِ
        # استثنا وابسته باشد (OperationalError، InterfaceError، ...).
        database_status = 'error'
        http_status = status.HTTP_503_SERVICE_UNAVAILABLE
    return Response(
        {
            'status': 'ok' if database_status == 'ok' else 'error',
            'database': database_status,
            'engine': connection.vendor,
            'debug': settings.DEBUG,
        },
        status=http_status,
    )
