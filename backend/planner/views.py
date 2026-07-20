from datetime import date

from rest_framework import viewsets, status, permissions
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate

from .models import Subject, Exam, StudyPlan, StudyLog
from .serializers import UserSerializer, SubjectSerializer, ExamSerializer, StudyPlanSerializer, StudyLogSerializer
from .utils import generate_study_plan, format_plan_for_frontend, build_subject_distribution, compute_subject_progress


# ---------------------------------------------------------------------------
# احراز هویت
# ---------------------------------------------------------------------------

@api_view(['POST'])
@permission_classes([AllowAny])
def register(request):
    serializer = UserSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response({
            'user': serializer.data,
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])
def login(request):
    username = request.data.get('username')
    password = request.data.get('password')
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
    serializer_class = SubjectSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # prefetch_related جلوی N+1 کوئری را می‌گیرد چون هر Subject برای
        # محاسبه‌ی پیشرفت باید امتحان‌ها و لاگ‌های مطالعه‌اش را بخواند.
        return (
            Subject.objects.filter(user=self.request.user)
            .select_related('user')
            .prefetch_related('exams__study_logs')
        )

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class ExamViewSet(viewsets.ModelViewSet):
    serializer_class = ExamSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Exam.objects.filter(subject__user=self.request.user).select_related('subject', 'subject__user')

    def perform_create(self, serializer):
        subject = serializer.validated_data['subject']
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
        serializer.save(user=self.request.user)


# ---------------------------------------------------------------------------
# برنامه‌ریز مطالعه‌ی هوشمند
# ---------------------------------------------------------------------------

def _get_or_create_plan_settings(user):
    """
    هر کاربر یک رکورد «تنظیمات برنامه» دارد (ساعت آزاد روزانه + آخرین
    برنامه‌ی تولیدشده). اگر هنوز نساخته، با مقدار پیش‌فرض ۲ ساعت می‌سازیم.
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
        نیاز دارد برمی‌گردانیم.
        """
        range_type = request.query_params.get('range', 'daily')
        if range_type not in ('daily', 'weekly'):
            range_type = 'daily'

        settings_obj = _get_or_create_plan_settings(request.user)
        raw_plan = generate_study_plan(request.user, settings_obj.daily_available_hours)
        payload = format_plan_for_frontend(raw_plan, range_type)
        payload['daily_available_hours'] = settings_obj.daily_available_hours
        return Response(payload)

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

    average_progress = round(sum(progress_values) / len(progress_values), 1) if progress_values else 0

    # --- برنامه‌ی زنده‌ی مطالعه (هم برای یادآوری امروز، هم برای نمودار تقسیم‌زمان) ---
    settings_obj = _get_or_create_plan_settings(user)
    raw_plan = generate_study_plan(user, settings_obj.daily_available_hours)

    # --- امتحان‌های پیشِ‌رو و هشدارها ---
    upcoming_exams_data = []
    alerts = []
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
    today_tasks = raw_plan.get(today.isoformat(), [])
    if today_tasks:
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
