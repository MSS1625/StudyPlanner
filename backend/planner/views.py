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

from rest_framework import viewsets, status, permissions
# api_view: تبدیل یک تابعِ ساده‌ی پایتون به یک View قابل‌فهم برای DRF
# permission_classes: تعیینِ این‌که چه کسی اجازه‌ی صدا زدنِ این View را دارد
# action: برای اضافه‌کردنِ یک مسیرِ سفارشی (غیر از CRUD معمولی) به یک ViewSet
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
# RefreshToken: برای ساختنِ توکن‌های JWT (دسترسی + تمدید) هنگام ثبت‌نام/ورود
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate

from .models import Subject, Exam, StudyPlan, StudyLog
from .serializers import UserSerializer, SubjectSerializer, ExamSerializer, StudyPlanSerializer, StudyLogSerializer
from .utils import generate_study_plan, format_plan_for_frontend, build_subject_distribution, compute_subject_progress


# ---------------------------------------------------------------------------
# احراز هویت
# ---------------------------------------------------------------------------

@api_view(['POST'])
# AllowAny یعنی این مسیر برخلاف بقیه‌ی مسیرهای پروژه، نیازی به لاگین‌بودن ندارد
# (طبیعی است؛ کسی که می‌خواهد ثبت‌نام کند، هنوز حسابی ندارد!)
@permission_classes([AllowAny])
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
def login(request):
    username = request.data.get('username')
    password = request.data.get('password')
    # authenticate یک تابعِ آماده‌ی جنگو است: رمزِ واردشده را دوباره Hash
    # می‌کند و با مقدارِ ذخیره‌شده در دیتابیس مقایسه می‌کند؛ اگر مطابقت
    # داشت، آبجکتِ کاربر را برمی‌گرداند، وگرنه None
    user = authenticate(username=username, password=password)
    if user:
        refresh = RefreshToken.for_user(user)
        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        })
    return Response({'error': 'نام کاربری یا رمز عبور اشتباه است'}, status=status.HTTP_401_UNAUTHORIZED)


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

    def get_queryset(self):
        # فیلتر بر مبنای subject__user یعنی: فقط امتحان‌هایی که به یک
        # درسِ متعلق به همین کاربر وصل هستند
        return Exam.objects.filter(subject__user=self.request.user).select_related('subject', 'subject__user')

    def perform_create(self, serializer):
        subject = serializer.validated_data['subject']
        # بررسیِ امنیتیِ اضافه: حتی اگر کاربر شناسه‌ی یک درسِ متعلق به
        # کاربرِ دیگر را در بدنه‌ی درخواست بفرستد، اینجا رد می‌شود.
        if subject.user != self.request.user:
            raise PermissionDenied("شما مجاز به ایجاد امتحان برای این درس نیستید")
        serializer.save()


class StudyLogViewSet(viewsets.ModelViewSet):
    serializer_class = StudyLogSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # کاربر فقط گزارش‌های مطالعه خودش را می‌بیند
        return StudyLog.objects.filter(user=self.request.user).select_related('exam', 'exam__subject')

    def perform_create(self, serializer):
        exam = serializer.validated_data['exam']
        if exam.subject.user != self.request.user:
            raise PermissionDenied("شما مجاز به ثبت گزارش مطالعه برای این امتحان نیستید")
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
        serializer.save(user=self.request.user)

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
            return Response({"error": "ساعت مطالعه روزانه الزامی است."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            daily_hours = float(daily_hours)
            if daily_hours <= 0 or daily_hours > 24:
                raise ValueError
        except (TypeError, ValueError):
            return Response({"error": "ساعت مطالعه باید عددی بین ۰ تا ۲۴ باشد."}, status=status.HTTP_400_BAD_REQUEST)

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
                'message': f"فقط {max(days_left, 0)} روز تا امتحان {exam.subject.name} مانده و {exam.study_hours_remaining} ساعت مطالعه باقی است!",
                'subject': exam.subject.name,
            })
        elif days_left <= 7:
            alerts.append({
                'type': 'warning',
                'message': f"{days_left} روز تا امتحان {exam.subject.name} باقی مانده. برنامه‌ات را جدی بگیر.",
                'subject': exam.subject.name,
            })

    # --- یادآوریِ برنامه‌ی امروز (نوع خنثی/info، جدا از هشدارهای فوری) ---
    # از همان raw_plan که بالاتر ساختیم، فقط تسک‌های «امروز» را برمی‌داریم
    today_tasks = raw_plan.get(today.isoformat(), [])
    if today_tasks:
        # یک جمله‌ی طبیعی و خوانا از لیستِ تسک‌های امروز می‌سازیم
        tasks_text = "، ".join(f"{task['subject']} ({task['hours']} ساعت)" for task in today_tasks)
        alerts.append({
            'type': 'info',
            'message': f"طبق برنامه‌ی امروز، پیشنهاد می‌شود روی {tasks_text} کار کنی.",
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
