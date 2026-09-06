# planner/tests.py
# ----------------------------------------------------------------------------
# تست‌های خودکارِ پروژه (Django + DRF).
#
# ساختار:
#   - BaseAPITestCase ......... کلاسِ پایه‌ی مشترک (دو کاربرِ نمونه + کلاینتِ JWT)
#   - AuthAPITests ............ ثبت‌نام/ورود و جریانِ توکن JWT
#   - SubjectAPITests ......... CRUD درس + یکتاییِ نام + جداسازی کاربران
#   - ExamAPITests ............ CRUD امتحان + ویرایش (PATCH) + سناریوهای امنیتی
#   - StudyLogAPITests ........ ثبتِ گزارش + کسرِ ساعتِ امتحان + جداسازی
#   - StudyPlanAPITests ....... endpoint برنامه‌ی مطالعه + اعتبارسنجیِ ورودی
#   - DashboardAPITests ....... شکلِ پاسخ، شمارش‌ها و انواعِ هشدار
#   - StudyPlanAlgorithmTests . تستِ واحدِ توابعِ خالصِ utils.py
#
# اجرا (از پوشه‌ی backend):
#   python manage.py test planner -v 2
#
# نکته‌ها:
#   - همه‌ی تاریخ‌ها به‌صورتِ نسبی از date.today() ساخته می‌شوند تا تست‌ها
#     هرگز با گذشتِ زمان کهنه/خراب نشوند.
#   - احراز هویت با همان سازوکارِ واقعیِ پروژه (SimpleJWT) انجام می‌شود،
#     نه force_authenticate، تا مسیرِ واقعیِ درخواست هم تست شود.
#   - هر تستی که رگرسیونِ یک رفعِ باگِ مشخص است، با کامنتِ «رگرسیون» علامت
#     خورده تا هدفش مستند بماند.
# ----------------------------------------------------------------------------

from datetime import date, timedelta

from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Subject, Exam, StudyLog, StudyPlan
from .utils import (
    compute_subject_progress,
    generate_study_plan,
    format_plan_for_frontend,
    build_subject_distribution,
)


# ---------------------------------------------------------------------------
# کلاسِ پایه‌ی مشترک
# ---------------------------------------------------------------------------

class BaseAPITestCase(APITestCase):
    """
    زیرساختِ مشترکِ همه‌ی کلاس‌های تست:

    - دو کاربرِ نمونه (alice مالکِ داده، bob کاربرِ بیگانه برای تست‌های امنیتی)
    - متدِ client_as(user): کلاینتِ احراز‌هویت‌شده با JWT برای هر کاربر
    - متدهای کمکیِ ساختِ درس/امتحان مستقیماً از مدل (سریع‌تر از API و
      مستقل از درستیِ خودِ API — برای آماده‌سازیِ «زمینِ» تست)
    """

    def setUp(self):
        self.alice = User.objects.create_user(username='alice', password='pw-12345678')
        self.bob = User.objects.create_user(username='bob', password='pw-12345678')

    # --- کمکی‌ها -----------------------------------------------------------

    def client_as(self, user):
        """کلاینتِ APIClient با هدرِ Bearer برای کاربرِ داده‌شده."""
        client = APIClient()
        token = str(RefreshToken.for_user(user).access_token)
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        return client

    @staticmethod
    def future_date(days):
        """تاریخِ «N روزِ دیگر» به‌صورتِ رشته‌ی ISO (مثل '2026-09-10')."""
        return (date.today() + timedelta(days=days)).isoformat()

    @staticmethod
    def create_subject(user, name, difficulty=3, **kwargs):
        return Subject.objects.create(user=user, name=name, difficulty=difficulty, **kwargs)

    @staticmethod
    def create_exam(subject, days_ahead=10, hours=10.0, chapters=3, **kwargs):
        return Exam.objects.create(
            subject=subject,
            exam_date=date.today() + timedelta(days=days_ahead),
            study_hours_remaining=hours,
            chapters_remaining=chapters,
            **kwargs,
        )


# ---------------------------------------------------------------------------
# ۱) احراز هویت
# ---------------------------------------------------------------------------

class AuthAPITests(BaseAPITestCase):
    """جریانِ ثبت‌نام/ورود و صدورِ توکنِ JWT."""

    def test_register_creates_user_and_returns_tokens(self):
        """ثبت‌نامِ موفق: 201 + آبجکتِ کاربر + جفتِ توکنِ access/refresh."""
        payload = {'username': 'newuser', 'email': 'new@example.com', 'password': 'strong-pass-123'}
        response = self.client.post('/api/auth/register/', payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = response.json()
        self.assertIn('access', body)
        self.assertIn('refresh', body)
        self.assertEqual(body['user']['username'], 'newuser')
        self.assertTrue(User.objects.filter(username='newuser').exists())

    def test_register_password_not_in_response(self):
        """رمز عبور write_only است و هرگز در پاسخِ API برنمی‌گردد."""
        payload = {'username': 'newuser', 'password': 'strong-pass-123'}
        response = self.client.post('/api/auth/register/', payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertNotIn('password', response.json()['user'])
        self.assertNotIn('password', response.json())

    def test_register_duplicate_username_rejected(self):
        """نامِ کاربریِ تکراری باید 400 برگرداند (نه 500)."""
        response = self.client.post(
            '/api/auth/register/',
            {'username': 'alice', 'password': 'another-pass-456'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_returns_tokens(self):
        """ورودِ درست: 200 + توکن‌ها."""
        response = self.client.post(
            '/api/auth/login/',
            {'username': 'alice', 'password': 'pw-12345678'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.assertIn('access', body)
        self.assertIn('refresh', body)

    def test_login_wrong_password_rejected(self):
        """رمزِ غلط: 401 بدون هیچ توکنی."""
        response = self.client.post(
            '/api/auth/login/',
            {'username': 'alice', 'password': 'wrong-password'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertNotIn('access', response.json())

    def test_login_unknown_user_rejected(self):
        """کاربرِ ناموجود: 401."""
        response = self.client.post(
            '/api/auth/login/',
            {'username': 'ghost', 'password': 'whatever'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_endpoints_require_authentication(self):
        """بدونِ توکن، endpointهای محافظت‌شده باید 401 بدهند (نه خطای دیگر)."""
        for url in ('/api/subjects/', '/api/exams/', '/api/study-logs/', '/api/study-plan/', '/api/dashboard/'):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


# ---------------------------------------------------------------------------
# ۲) درس‌ها (Subject)
# ---------------------------------------------------------------------------

class SubjectAPITests(BaseAPITestCase):
    """CRUD درس، فیلدِ notes، یکتاییِ نام و جداسازیِ داده بین کاربران."""

    def test_create_subject(self):
        """ثبتِ درسِ جدید: 201 + برگشتنِ مقادیر در پاسخ."""
        response = self.client_as(self.alice).post(
            '/api/subjects/',
            {'name': 'ریاضی عمومی', 'difficulty': 4},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = response.json()
        self.assertEqual(body['name'], 'ریاضی عمومی')
        self.assertEqual(body['difficulty'], 4)

    def test_create_subject_with_notes(self):
        """رگرسیون (رفعِ 2026-08-25): فیلد notes واقعاً ذخیره و برگردانده می‌شود."""
        response = self.client_as(self.alice).post(
            '/api/subjects/',
            {'name': 'شیمی آلی', 'difficulty': 5, 'notes': 'نصف نمره از تمرین‌ها می‌آید'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json()['notes'], 'نصف نمره از تمرین‌ها می‌آید')
        # تأییدِ ذخیره‌شدنِ واقعی در دیتابیس (نه فقط در پاسخ)
        subject = Subject.objects.get(user=self.alice, name='شیمی آلی')
        self.assertEqual(subject.notes, 'نصف نمره از تمرین‌ها می‌آید')

    def test_create_subject_with_target_score_alias(self):
        """فیلدِ نمایشیِ target_score روی target_grade مدل نگاشت می‌شود."""
        response = self.client_as(self.alice).post(
            '/api/subjects/',
            {'name': 'فیزیک ۲', 'difficulty': 3, 'target_score': 18.5},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json()['target_score'], 18.5)
        self.assertEqual(Subject.objects.get(name='فیزیک ۲').target_grade, 18.5)

    def test_subject_response_includes_progress_fields(self):
        """پاسخِ درس شاملِ فیلدهای محاسباتیِ پیشرفت است (حتی وقتی صفرند)."""
        self.create_subject(self.alice, 'ادبیات')
        response = self.client_as(self.alice).get('/api/subjects/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.assertEqual(len(body), 1)
        for key in ('completed_hours', 'total_hours', 'remaining_hours', 'progress_percent'):
            self.assertIn(key, body[0])

    def test_duplicate_subject_name_rejected(self):
        """رگرسیون (رفعِ 2026-08-29): نامِ تکراری برای همان کاربر 400 می‌دهد، نه 500."""
        first = self.client_as(self.alice).post(
            '/api/subjects/', {'name': 'ریاضی', 'difficulty': 3}, format='json'
        )
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)

        second = self.client_as(self.alice).post(
            '/api/subjects/', {'name': 'ریاضی', 'difficulty': 4}, format='json'
        )
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        # فقط یک رکورد در DB مانده است (درخواستِ دوم ذخیره نشده)
        self.assertEqual(Subject.objects.filter(user=self.alice, name='ریاضی').count(), 1)

    def test_rename_subject_to_existing_name_rejected(self):
        """ویرایشِ نامِ درس به نامِ درسِ دیگرِ همان کاربر هم باید 400 بدهد."""
        self.create_subject(self.alice, 'ریاضی')
        other = self.create_subject(self.alice, 'فیزیک')

        response = self.client_as(self.alice).patch(
            f'/api/subjects/{other.pk}/', {'name': 'ریاضی'}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        other.refresh_from_db()
        self.assertEqual(other.name, 'فیزیک')  # نام تغییر نکرده است

    def test_same_name_different_users_allowed(self):
        """دو کاربرِ مختلف می‌توانند درسِ هم‌نام داشته باشند (یکتایی به ازای کاربر است)."""
        self.create_subject(self.alice, 'ریاضی')
        response = self.client_as(self.bob).post(
            '/api/subjects/', {'name': 'ریاضی', 'difficulty': 2}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_list_subjects_isolated(self):
        """هر کاربر فقط درس‌های خودش را می‌بیند."""
        self.create_subject(self.alice, 'ریاضی')
        self.create_subject(self.alice, 'فیزیک')
        self.create_subject(self.bob, 'شیمی')

        body_alice = self.client_as(self.alice).get('/api/subjects/').json()
        body_bob = self.client_as(self.bob).get('/api/subjects/').json()

        self.assertEqual(sorted(s['name'] for s in body_alice), ['ریاضی', 'فیزیک'])
        self.assertEqual([s['name'] for s in body_bob], ['شیمی'])

    def test_update_subject(self):
        """PATCH: تغییرِ سختی و یادداشت."""
        subject = self.create_subject(self.alice, 'ریاضی')
        response = self.client_as(self.alice).patch(
            f'/api/subjects/{subject.pk}/',
            {'difficulty': 5, 'notes': 'فصل ۷ را دو بار بخوان'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        subject.refresh_from_db()
        self.assertEqual(subject.difficulty, 5)
        self.assertEqual(subject.notes, 'فصل ۷ را دو بار بخوان')

    def test_delete_subject(self):
        """DELETE: 204 و حذفِ واقعی + آبشاری‌بودنِ امتحان‌هایش."""
        subject = self.create_subject(self.alice, 'ریاضی')
        exam = self.create_exam(subject)

        response = self.client_as(self.alice).delete(f'/api/subjects/{subject.pk}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Subject.objects.filter(pk=subject.pk).exists())
        # on_delete=CASCADE: امتحانِ وابسته هم باید حذف شده باشد
        self.assertFalse(Exam.objects.filter(pk=exam.pk).exists())

    def test_cannot_create_subject_for_another_user(self):
        """فیلدِ user در ورودی نادیده گرفته می‌شود؛ درس همیشه برای خودِ کاربر ساخته می‌شود."""
        response = self.client_as(self.alice).post(
            '/api/subjects/', {'name': 'درسِ فرضی', 'user': self.bob.pk}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Subject.objects.get(name='درسِ فرضی').user, self.alice)


# ---------------------------------------------------------------------------
# ۳) امتحان‌ها (Exam) — شاملِ قابلیتِ ویرایش و سناریوهای امنیتی
# ---------------------------------------------------------------------------

class ExamAPITests(BaseAPITestCase):
    """CRUD امتحان، فیلدِ notes، ویرایشِ PATCH/PUT و مالکیتِ داده."""

    def setUp(self):
        super().setUp()
        # درس‌های زمینِ تست: دو درس برای alice و یکی برای bob
        self.math = self.create_subject(self.alice, 'ریاضی', difficulty=4)
        self.physics = self.create_subject(self.alice, 'فیزیک', difficulty=3)
        self.bob_subject = self.create_subject(self.bob, 'شیمی', difficulty=2)

    def _create_payload(self, subject_pk, **extra):
        """payload استانداردِ ساختِ امتحان (تاریخِ ۱۰ روزِ دیگر)."""
        payload = {
            'subject': subject_pk,
            'exam_date': self.future_date(10),
            'chapters_remaining': 5,
            'study_hours_remaining': 20,
        }
        payload.update(extra)
        return payload

    def test_create_exam(self):
        """ثبتِ امتحان: 201 + subject_nameِ محاسبه‌شده برای فرانت‌اند."""
        response = self.client_as(self.alice).post(
            '/api/exams/', self._create_payload(self.math.pk), format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = response.json()
        self.assertEqual(body['subject'], self.math.pk)
        self.assertEqual(body['subject_name'], 'ریاضی')

    def test_create_exam_with_notes(self):
        """رگرسیون (رفعِ 2026-08-29): فیلدِ یتیمِ note حالا واقعاً ذخیره می‌شود."""
        response = self.client_as(self.alice).post(
            '/api/exams/',
            self._create_payload(self.math.pk, notes='میان‌ترم؛ سالن ۲؛ فصل‌های ۱ تا ۵'),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json()['notes'], 'میان‌ترم؛ سالن ۲؛ فصل‌های ۱ تا ۵')
        self.assertEqual(
            Exam.objects.get(pk=response.json()['id']).notes,
            'میان‌ترم؛ سالن ۲؛ فصل‌های ۱ تا ۵',
        )

    def test_create_exam_without_notes_optional(self):
        """notes اختیاری است: بدونِ آن هم 201 می‌گیریم (سازگاری به عقب)."""
        response = self.client_as(self.alice).post(
            '/api/exams/', self._create_payload(self.math.pk), format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn(response.json()['notes'], ('', None))

    def test_create_exam_for_foreign_subject_forbidden(self):
        """امنیت: ساختِ امتحان برای درسِ کاربرِ دیگر → 403 (نه 201)."""
        response = self.client_as(self.alice).post(
            '/api/exams/', self._create_payload(self.bob_subject.pk), format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Exam.objects.filter(subject=self.bob_subject).exists())

    def test_create_exam_missing_date_rejected(self):
        """اعتبارسنجی: بدونِ exam_date نمی‌توان امتحان ساخت."""
        response = self.client_as(self.alice).post(
            '/api/exams/',
            {'subject': self.math.pk, 'chapters_remaining': 2, 'study_hours_remaining': 8},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_exam_negative_hours_rejected(self):
        """اعتبارسنجی: ساعتِ منفی از سمتِ validator مدل رد می‌شود."""
        payload = self._create_payload(self.math.pk, study_hours_remaining=-5)
        response = self.client_as(self.alice).post('/api/exams/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_exams_isolated(self):
        """هر کاربر فقط امتحان‌هایِ درس‌های خودش را می‌بیند."""
        self.create_exam(self.math)
        self.create_exam(self.bob_subject)

        body_alice = self.client_as(self.alice).get('/api/exams/').json()
        body_bob = self.client_as(self.bob).get('/api/exams/').json()

        self.assertEqual(len(body_alice), 1)
        self.assertEqual(body_alice[0]['subject_name'], 'ریاضی')
        self.assertEqual(len(body_bob), 1)
        self.assertEqual(body_bob[0]['subject_name'], 'شیمی')

    def test_edit_exam_patch(self):
        """قابلیتِ ویرایش (2026-08-29): PATCH همه‌ی فیلدهایِ قابلِ ویرایش را در DB ذخیره می‌کند."""
        exam = self.create_exam(self.math, days_ahead=10, hours=20, chapters=5)

        response = self.client_as(self.alice).patch(
            f'/api/exams/{exam.pk}/',
            {
                'exam_date': self.future_date(15),
                'chapters_remaining': 3,
                'study_hours_remaining': 12.5,
                'notes': 'تاریخ عوض شد',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.assertEqual(body['exam_date'], self.future_date(15))
        self.assertEqual(body['chapters_remaining'], 3)
        self.assertEqual(body['study_hours_remaining'], 12.5)
        self.assertEqual(body['notes'], 'تاریخ عوض شد')

        # تأییدِ ذخیره‌شدنِ واقعی در دیتابیس (نه فقط پاسخِ سریالایزر)
        exam.refresh_from_db()
        self.assertEqual(exam.exam_date.isoformat(), self.future_date(15))
        self.assertEqual(exam.notes, 'تاریخ عوض شد')

    def test_edit_exam_change_subject_to_own_other_subject(self):
        """ویرایشِ درسِ امتحان به درسِ دیگرِ «خودِ کاربر» مجاز است."""
        exam = self.create_exam(self.math)
        response = self.client_as(self.alice).patch(
            f'/api/exams/{exam.pk}/', {'subject': self.physics.pk}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['subject'], self.physics.pk)
        self.assertEqual(response.json()['subject_name'], 'فیزیک')

    def test_edit_exam_change_subject_to_foreign_subject_forbidden(self):
        """امنیت (رفعِ 2026-08-29): تغییرِ درس به درسِ کاربرِ دیگر → 403 و بدونِ تغییر در DB."""
        exam = self.create_exam(self.math)
        response = self.client_as(self.alice).patch(
            f'/api/exams/{exam.pk}/', {'subject': self.bob_subject.pk}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        exam.refresh_from_db()
        self.assertEqual(exam.subject, self.math)  # درس تغییر نکرده است

    def test_edit_foreign_exam_not_found(self):
        """امنیت: ویرایشِ امتحانِ کاربرِ دیگر حتی کشف هم نمی‌شود → 404."""
        exam = self.create_exam(self.math, notes='اصلی')
        response = self.client_as(self.bob).patch(
            f'/api/exams/{exam.pk}/', {'notes': 'هک!'}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        exam.refresh_from_db()
        self.assertEqual(exam.notes, 'اصلی')  # داده دست‌نخورده ماند

    def test_full_update_with_put(self):
        """PUT (به‌روزرسانیِ کامل) هم مانند PATCH مسیرِ امنیتیِ همان را طی می‌کند."""
        exam = self.create_exam(self.math, days_ahead=10, hours=20, chapters=5)
        response = self.client_as(self.alice).put(
            f'/api/exams/{exam.pk}/',
            self._create_payload(self.math.pk, notes='PUT', study_hours_remaining=4, chapters_remaining=1),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['notes'], 'PUT')
        self.assertEqual(response.json()['study_hours_remaining'], 4)

    def test_delete_exam(self):
        """DELETE: 204 و حذفِ واقعی."""
        exam = self.create_exam(self.math)
        response = self.client_as(self.alice).delete(f'/api/exams/{exam.pk}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Exam.objects.filter(pk=exam.pk).exists())

    def test_delete_foreign_exam_not_found(self):
        """امنیت: حذفِ امتحانِ کاربرِ دیگر → 404 و بدونِ حذف."""
        exam = self.create_exam(self.math)
        response = self.client_as(self.bob).delete(f'/api/exams/{exam.pk}/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Exam.objects.filter(pk=exam.pk).exists())


# ---------------------------------------------------------------------------
# ۴) گزارش‌های مطالعه (StudyLog)
# ---------------------------------------------------------------------------

class StudyLogAPITests(BaseAPITestCase):
    """ثبتِ گزارش، کسرِ خودکارِ ساعتِ امتحان و مالکیتِ داده."""

    def setUp(self):
        super().setUp()
        self.subject = self.create_subject(self.alice, 'ریاضی', difficulty=4)
        self.exam = self.create_exam(self.subject, days_ahead=10, hours=10)
        # داده‌ی بیگانه برای تست‌های امنیتی
        self.bob_subject = self.create_subject(self.bob, 'شیمی')
        self.bob_exam = self.create_exam(self.bob_subject, days_ahead=8, hours=6)

    def _log_payload(self, exam_pk, hours=3, **extra):
        payload = {'exam': exam_pk, 'date': date.today().isoformat(), 'hours_studied': hours}
        payload.update(extra)
        return payload

    def test_create_log_deducts_exam_hours(self):
        """منطقِ کلیدیِ StudyLog.save(): ثبتِ ۳ ساعت، از امتحان ۳ ساعت کم می‌کند."""
        response = self.client_as(self.alice).post(
            '/api/study-logs/', self._log_payload(self.exam.pk, hours=3), format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.exam.refresh_from_db()
        self.assertEqual(self.exam.study_hours_remaining, 7)  # 10 - 3

    def test_log_hours_never_negative(self):
        """کسرِ ساعت هرگز منفی نمی‌شود: ۱۵ ساعت رویِ امتحانِ ۱۰ ساعته → صفر."""
        self.client_as(self.alice).post(
            '/api/study-logs/', self._log_payload(self.exam.pk, hours=15), format='json'
        )
        self.exam.refresh_from_db()
        self.assertEqual(self.exam.study_hours_remaining, 0)
        # ساعاتِ ثبت‌شده‌ی خودِ گزارش، همان ۱۵ ساعت باقی می‌ماند
        self.assertEqual(StudyLog.objects.get().hours_studied, 15)

    def test_create_log_for_foreign_exam_forbidden(self):
        """امنیت: ثبتِ گزارش برای امتحانِ کاربرِ دیگر → 403."""
        response = self.client_as(self.alice).post(
            '/api/study-logs/', self._log_payload(self.bob_exam.pk), format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(StudyLog.objects.filter(exam=self.bob_exam).exists())

    def test_list_logs_isolated(self):
        """هر کاربر فقط گزارش‌های خودش را می‌بیند."""
        StudyLog.objects.create(user=self.alice, exam=self.exam, hours_studied=1)
        StudyLog.objects.create(user=self.bob, exam=self.bob_exam, hours_studied=2)

        body_alice = self.client_as(self.alice).get('/api/study-logs/').json()
        body_bob = self.client_as(self.bob).get('/api/study-logs/').json()

        self.assertEqual(len(body_alice), 1)
        self.assertEqual(body_alice[0]['exam_name'], 'ریاضی')
        self.assertEqual(len(body_bob), 1)
        self.assertEqual(body_bob[0]['exam_name'], 'شیمی')

    def test_log_response_includes_exam_name(self):
        """فیلدِ محاسباتیِ exam_name (درس ← امتحان) در پاسخ هست."""
        response = self.client_as(self.alice).post(
            '/api/study-logs/', self._log_payload(self.exam.pk), format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json()['exam_name'], 'ریاضی')

    def test_log_with_notes(self):
        """فیلدِ اختیاریِ notes ذخیره و برگردانده می‌شود."""
        response = self.client_as(self.alice).post(
            '/api/study-logs/',
            self._log_payload(self.exam.pk, notes='تمرین‌های فصل ۳'),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json()['notes'], 'تمرین‌های فصل ۳')

    def test_log_zero_hours_rejected(self):
        """اعتبارسنجی: صفر ساعت (زیرِ حداقلِ 0.1) رد می‌شود."""
        response = self.client_as(self.alice).post(
            '/api/study-logs/', self._log_payload(self.exam.pk, hours=0), format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_progress_percent_reflects_logged_hours(self):
        """حلقه‌ی بازخورد: بعد از ۲.۵ ساعت مطالعه از ۱۰ ساعت، پیشرفتِ درس ۲۵٪ است."""
        self.client_as(self.alice).post(
            '/api/study-logs/', self._log_payload(self.exam.pk, hours=2.5), format='json'
        )
        body = self.client_as(self.alice).get('/api/subjects/').json()
        subject_data = next(s for s in body if s['name'] == 'ریاضی')

        self.assertEqual(subject_data['completed_hours'], 2.5)
        self.assertEqual(subject_data['total_hours'], 10)
        self.assertEqual(subject_data['progress_percent'], 25.0)

    def test_delete_log(self):
        """حذفِ گزارش: 204 و حذفِ واقعی (رفتارِ بازگرداندنِ ساعت در تست‌های
        اختصاصیِ پایین‌تر به‌تفصیل پوشش داده می‌شود)."""
        log = StudyLog.objects.create(user=self.alice, exam=self.exam, hours_studied=1)
        response = self.client_as(self.alice).delete(f'/api/study-logs/{log.pk}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(StudyLog.objects.filter(pk=log.pk).exists())

    def test_delete_log_restores_exam_hours(self):
        """بازگرداندنِ ساعت (آیتمِ TODO): حذفِ گزارشِ ۳ ساعته، همان ۳ ساعتِ
        کسرشده را به امتحان برمی‌گرداند و امتحان به حالتِ اولیه برمی‌گردد."""
        log = StudyLog.objects.create(user=self.alice, exam=self.exam, hours_studied=3)
        self.exam.refresh_from_db()
        self.assertEqual(self.exam.study_hours_remaining, 7)  # 10 - 3

        response = self.client_as(self.alice).delete(f'/api/study-logs/{log.pk}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.exam.refresh_from_db()
        self.assertEqual(self.exam.study_hours_remaining, 10)  # برگشتِ کامل

    def test_delete_clamped_log_restores_exact_deduction(self):
        """حالتِ کسرِ محدود (Clamp): امتحان ۲ ساعت مانده، گزارشِ ۵ ساعت
        ثبت شده → فقط ۲ ساعت کسر شده است؛ حذفِ گزارش باید دقیقاً ۲ ساعت
        برگرداند، نه ۵ (وگرنه ساعتِ امتحان از مقدارِ اولیه‌اش بیشتر می‌شد)."""
        self.exam.study_hours_remaining = 2
        self.exam.save()
        log = StudyLog.objects.create(user=self.alice, exam=self.exam, hours_studied=5)

        self.exam.refresh_from_db()
        self.assertEqual(self.exam.study_hours_remaining, 0)  # کسرِ محدودشده
        self.assertEqual(StudyLog.objects.get(pk=log.pk).hours_deducted, 2)

        self.client_as(self.alice).delete(f'/api/study-logs/{log.pk}/')
        self.exam.refresh_from_db()
        self.assertEqual(self.exam.study_hours_remaining, 2)  # نه ۵!

    def test_delete_log_when_nothing_was_deducted(self):
        """امتحانِ کامل‌شده (۰ ساعت مانده): گزارش بدونِ هیچ کسری ثبت می‌شود؛
        حذفش هم چیزی برنمی‌گرداند (ساعت نباید از هیچ‌جا ظاهر شود)."""
        self.exam.study_hours_remaining = 0
        self.exam.save()
        log = StudyLog.objects.create(user=self.alice, exam=self.exam, hours_studied=4)

        self.exam.refresh_from_db()
        self.assertEqual(self.exam.study_hours_remaining, 0)
        self.assertEqual(StudyLog.objects.get(pk=log.pk).hours_deducted, 0)

        self.client_as(self.alice).delete(f'/api/study-logs/{log.pk}/')
        self.exam.refresh_from_db()
        self.assertEqual(self.exam.study_hours_remaining, 0)

    def test_delete_one_of_multiple_logs(self):
        """با چند گزارش رویِ یک امتحان، حذفِ هر گزارش فقط ساعتِ همان را
        برمی‌گرداند؛ ساعتِ بقیه‌ی گزارش‌ها کسرشده باقی می‌ماند."""
        log1 = StudyLog.objects.create(user=self.alice, exam=self.exam, hours_studied=2)
        log2 = StudyLog.objects.create(user=self.alice, exam=self.exam, hours_studied=3)
        self.exam.refresh_from_db()
        self.assertEqual(self.exam.study_hours_remaining, 5)  # 10 - 2 - 3

        self.client_as(self.alice).delete(f'/api/study-logs/{log1.pk}/')
        self.exam.refresh_from_db()
        self.assertEqual(self.exam.study_hours_remaining, 7)  # 5 + 2

        self.client_as(self.alice).delete(f'/api/study-logs/{log2.pk}/')
        self.exam.refresh_from_db()
        self.assertEqual(self.exam.study_hours_remaining, 10)  # 7 + 3

    def test_cascade_exam_delete_is_safe(self):
        """حذفِ خودِ امتحان (که گزارش‌هایش را آبشاری حذف می‌کند) نباید خطا
        بدهد: بازگرداندنِ ساعت فقط در حذفِ مستقیمِ گزارش معنا دارد — اینجا
        امتحانی باقی نمی‌ماند که ساعتی به آن برگردد."""
        StudyLog.objects.create(user=self.alice, exam=self.exam, hours_studied=2)
        self.exam.delete()  # حذفِ آبشاری: گزارش‌ها هم باید حذف شوند
        self.assertFalse(StudyLog.objects.exists())
        self.assertFalse(Exam.objects.filter(pk=self.exam.pk).exists())


# ---------------------------------------------------------------------------
# ۵) برنامه‌ی مطالعه (StudyPlan)
# ---------------------------------------------------------------------------

class StudyPlanAPITests(BaseAPITestCase):
    """endpoint برنامه‌ی مطالعه: نمایِ زنده، تنظیمِ ساعتِ روزانه و اعتبارسنجیِ ورودی."""

    def test_get_plan_creates_default_settings(self):
        """اولین GET بدونِ رکوردِ تنظیمات: مقدارِ پیش‌فرضِ ۲ ساعت ساخته و برگردانده می‌شود."""
        response = self.client_as(self.alice).get('/api/study-plan/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['daily_available_hours'], 2.0)
        # رکوردِ تنظیمات هم واقعاً در DB ساخته شده است
        self.assertTrue(StudyPlan.objects.filter(user=self.alice).exists())

    def test_get_plan_response_shape(self):
        """پاسخِ همیشگی شکلِ ثابتی دارد که فرانت‌اند به آن تکیه می‌کند."""
        response = self.client_as(self.alice).get('/api/study-plan/')
        body = response.json()
        for key in ('schedule', 'totals', 'daily_available_hours'):
            self.assertIn(key, body)
        for key in ('recommended_hours', 'average_daily', 'top_subjects'):
            self.assertIn(key, body['totals'])

    def test_plan_schedule_has_tasks_for_future_exam(self):
        """با وجودِ امتحانِ آینده، نمایِ روزانه باید تسک داشته باشد (خالی نیست)."""
        subject = self.create_subject(self.alice, 'ریاضی')
        self.create_exam(subject, days_ahead=5, hours=10)

        body = self.client_as(self.alice).get('/api/study-plan/').json()
        self.assertNotEqual(body['schedule'], [])
        self.assertGreater(len(body['schedule'][0]['tasks']), 0)
        self.assertEqual(body['schedule'][0]['days_covered'], 1)

    def test_plan_empty_without_future_exams(self):
        """بدونِ هیچ امتحانِ آینده‌ای: schedule خالی + پیامِ توضیحی برای کاربر."""
        body = self.client_as(self.alice).get('/api/study-plan/').json()
        self.assertEqual(body['schedule'], [])
        self.assertIn('message', body)

    def test_generate_with_valid_hours(self):
        """ثبتِ ساعتِ روزانه‌ی جدید: 200 + به‌روزرسانیِ تنظیمات در DB."""
        subject = self.create_subject(self.alice, 'ریاضی')
        self.create_exam(subject, days_ahead=7, hours=14)

        response = self.client_as(self.alice).post(
            '/api/study-plan/generate/', {'daily_available_hours': 3.5}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['daily_available_hours'], 3.5)
        settings_obj = StudyPlan.objects.get(user=self.alice)
        self.assertEqual(settings_obj.daily_available_hours, 3.5)
        # برنامه‌ی ساخته‌شده هم در plan_data ذخیره شده است (نه فقط پیام)
        self.assertNotEqual(settings_obj.plan_data, {})

    def test_generate_missing_hours_rejected(self):
        """بدونِ daily_available_hours → 400 با پیامِ خطا."""
        response = self.client_as(self.alice).post('/api/study-plan/generate/', {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.json())

    def test_generate_invalid_hours_rejected(self):
        """مقادیرِ نامعتبر (صفر/منفی/بیشتر از ۲۴/غیرعددی) → 400."""
        for bad_value in (0, -2, 25, 'abc'):
            with self.subTest(value=bad_value):
                response = self.client_as(self.alice).post(
                    '/api/study-plan/generate/',
                    {'daily_available_hours': bad_value},
                    format='json',
                )
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_generate_settings_shared_between_calls(self):
        """چند بار generate نکند چند رکوردِ تنظیمات بسازد (الگوی get_or_create)."""
        client = self.client_as(self.alice)
        client.post('/api/study-plan/generate/', {'daily_available_hours': 2}, format='json')
        client.post('/api/study-plan/generate/', {'daily_available_hours': 4}, format='json')

        self.assertEqual(StudyPlan.objects.filter(user=self.alice).count(), 1)
        self.assertEqual(StudyPlan.objects.get(user=self.alice).daily_available_hours, 4)


# ---------------------------------------------------------------------------
# ۶) داشبورد
# ---------------------------------------------------------------------------

class DashboardAPITests(BaseAPITestCase):
    """شکلِ پاسخِ داشبورد، شمارش‌ها و منطقِ انواعِ هشدار (danger/warning/info)."""

    def test_dashboard_response_shape(self):
        """پاسخِ داشبورد همه‌ی کلیدهایی را دارد که renderDashboard انتظار دارد."""
        response = self.client_as(self.alice).get('/api/dashboard/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        for key in (
            'total_subjects', 'total_exams', 'average_progress', 'alerts',
            'urgent_alerts_count', 'subjects_progress', 'upcoming_exams',
            'study_distribution',
        ):
            self.assertIn(key, body)

    def test_dashboard_counts_subjects_and_upcoming_exams(self):
        """شمارش‌ها: فقط امتحان‌های «امروز به بعد» جزوِ upcoming هستند."""
        subject = self.create_subject(self.alice, 'ریاضی')
        self.create_exam(subject, days_ahead=5)    # آینده: شمرده می‌شود
        self.create_exam(subject, days_ahead=-1)   # گذشته: شمرده نمی‌شود
        self.create_subject(self.bob, 'شیمی')       # درسِ کاربرِ دیگر

        body = self.client_as(self.alice).get('/api/dashboard/').json()
        self.assertEqual(body['total_subjects'], 1)
        self.assertEqual(body['total_exams'], 1)
        self.assertEqual(len(body['subjects_progress']), 1)

    def test_dashboard_danger_alert_for_close_exam(self):
        """امتحانِ ۲ روزِ دیگرِ ناخوانده → هشدارِ danger + شمارشِ فوری ≥ ۱."""
        subject = self.create_subject(self.alice, 'ریاضی')
        self.create_exam(subject, days_ahead=2, hours=8)

        body = self.client_as(self.alice).get('/api/dashboard/').json()
        alert_types = [alert['type'] for alert in body['alerts']]
        self.assertIn('danger', alert_types)
        self.assertGreaterEqual(body['urgent_alerts_count'], 1)

    def test_dashboard_warning_alert_for_medium_range_exam(self):
        """امتحانِ ۵ روزِ دیگر → هشدارِ warning (زرد)، بدونِ danger."""
        subject = self.create_subject(self.alice, 'ریاضی')
        self.create_exam(subject, days_ahead=5, hours=8)

        body = self.client_as(self.alice).get('/api/dashboard/').json()
        alert_types = [alert['type'] for alert in body['alerts']]
        self.assertIn('warning', alert_types)
        self.assertNotIn('danger', alert_types)
        self.assertEqual(body['urgent_alerts_count'], 0)

    def test_dashboard_info_alert_mentions_today_plan(self):
        """وقتی برنامه‌ی امروز تسک دارد، هشدارِ خنثیِ info هم وجود دارد."""
        subject = self.create_subject(self.alice, 'ریاضی')
        self.create_exam(subject, days_ahead=4, hours=6)

        body = self.client_as(self.alice).get('/api/dashboard/').json()
        info_alerts = [a for a in body['alerts'] if a['type'] == 'info']
        self.assertTrue(info_alerts)
        self.assertIn('ریاضی', info_alerts[0]['message'])

    def test_dashboard_study_distribution_labels(self):
        """نمودارِ تقسیم‌زمان: لیبلِ درسِ دارایِ برنامه‌ی آینده برمی‌گردد."""
        subject = self.create_subject(self.alice, 'ریاضی')
        self.create_exam(subject, days_ahead=6, hours=9)

        body = self.client_as(self.alice).get('/api/dashboard/').json()
        self.assertTrue(body['study_distribution'])
        self.assertEqual(body['study_distribution'][0]['label'], 'ریاضی')
        # درسِ تنها: نرمال‌سازی نسبت به خودش → ۱۰۰٪
        self.assertEqual(body['study_distribution'][0]['percent'], 100)


# ---------------------------------------------------------------------------
# ۷) تست‌های واحدِ الگوریتم (utils.py)
# ---------------------------------------------------------------------------

class StudyPlanAlgorithmTests(BaseAPITestCase):
    """
    تستِ مستقیمِ توابعِ (نسبتاً) خالصِ utils.py — همان نقطه‌ی شروعی که
    TODO.md پیشنهاد داده بود؛ چون این توابع ورودی/خروجیِ ساده دارند،
    بدونِ عبور از API و فقط با مدل‌های ساخته‌شده تست می‌شوند.
    """

    def test_compute_subject_progress_without_exams(self):
        """درسِ بدونِ امتحان: (۰ ساعت، ۰ ساعت، ۰٪) — بدونِ خطای تقسیم بر صفر."""
        subject = self.create_subject(self.alice, 'درسِ بی‌امتحان')
        self.assertEqual(compute_subject_progress(subject), (0, 0, 0))

    def test_compute_subject_progress_after_logging(self):
        """امتحانِ ۱۰ ساعته + ۲.۵ ساعت مطالعه → مجموع ۱۰، انجام‌شده ۲.۵، ۲۵٪."""
        subject = self.create_subject(self.alice, 'ریاضی')
        exam = self.create_exam(subject, days_ahead=9, hours=10)
        StudyLog.objects.create(user=self.alice, exam=exam, hours_studied=2.5)
        # (کسرِ خودکار در save انجام شده و exam الان 7.5 ساعت باقی دارد)

        completed, total, percent = compute_subject_progress(subject)
        self.assertEqual(completed, 2.5)
        self.assertEqual(total, 10)  # 7.5 باقی‌مانده + 2.5 لاگ‌شده
        self.assertEqual(percent, 25.0)

    def test_generate_plan_without_future_exams_returns_message(self):
        """بدونِ امتحانِ آینده: فقط پیامِ توضیحی، بدونِ هیچ برنامه‌ای."""
        self.create_subject(self.alice, 'ریاضی')
        plan = generate_study_plan(self.alice, 2)
        self.assertIn('message', plan)

    def test_generate_plan_allocates_full_daily_hours(self):
        """جمعِ سهمِ درس‌های هر روز برابرِ ساعتِ آزادِ روزانه است (نه کمتر)."""
        math = self.create_subject(self.alice, 'ریاضی', difficulty=4)
        physics = self.create_subject(self.alice, 'فیزیک', difficulty=2)
        self.create_exam(math, days_ahead=10, hours=20)
        self.create_exam(physics, days_ahead=10, hours=10)

        plan = generate_study_plan(self.alice, 3)
        today_key = date.today().isoformat()
        today_tasks = plan[today_key]
        # دو درس فعال؛ جمعِ سهم‌ها باید «کلِ» ۳ ساعت را پوشش دهد
        # (تلورانسِ 0.1 برای گردشدنِ هر سهم به یک رقم اعشار)
        self.assertEqual(len(today_tasks), 2)
        self.assertAlmostEqual(sum(t['hours'] for t in today_tasks), 3.0, delta=0.1)

    def test_format_plan_daily_shows_single_day(self):
        """نمایِ روزانه فقط یک بلوک با days_covered=1 دارد."""
        subject = self.create_subject(self.alice, 'ریاضی')
        self.create_exam(subject, days_ahead=10, hours=10)

        payload = format_plan_for_frontend(generate_study_plan(self.alice, 2), 'daily')
        self.assertEqual(len(payload['schedule']), 1)
        self.assertEqual(payload['schedule'][0]['days_covered'], 1)

    def test_format_plan_weekly_merges_identical_days(self):
        """نمایِ هفتگی: روزهایِ پیاپیِ هم‌برنامه در یک بلوک ادغام می‌شوند.

        با یک امتحانِ ۱۰ روزِ بعد، هر ۷ روزِ پنجره‌ی هفتگی دقیقاً یکسان‌اند؛
        پس باید فقط «یک» بلوکِ ۷ روزه برگردد (نه هفت بلوکِ تکراری).
        """
        subject = self.create_subject(self.alice, 'ریاضی')
        self.create_exam(subject, days_ahead=10, hours=10)

        payload = format_plan_for_frontend(generate_study_plan(self.alice, 2), 'weekly')
        self.assertEqual(len(payload['schedule']), 1)
        self.assertEqual(payload['schedule'][0]['days_covered'], 7)

    def test_build_subject_distribution_normalized_to_top(self):
        """نرمال‌سازی نمودار: پرکارترین درس ۱۰۰٪؛ بقیه نسبت به آن."""
        math = self.create_subject(self.alice, 'ریاضی', difficulty=5)
        physics = self.create_subject(self.alice, 'فیزیک', difficulty=1)
        self.create_exam(math, days_ahead=10, hours=20)
        self.create_exam(physics, days_ahead=10, hours=20)

        distribution = build_subject_distribution(
            generate_study_plan(self.alice, 4), days=7, top_n=6
        )
        self.assertEqual(len(distribution), 2)
        # درسِ سخت‌تر (ریاضی با وزنِ ۵) سهمِ بیشتری گرفته و ۱۰۰٪ است
        self.assertEqual(distribution[0]['label'], 'ریاضی')
        self.assertEqual(distribution[0]['percent'], 100)
        self.assertLess(distribution[1]['percent'], 100)
