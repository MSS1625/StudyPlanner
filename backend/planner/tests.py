# planner/tests.py
# ----------------------------------------------------------------------------
# تست‌های خودکارِ پروژه (Django + DRF).
#
# ساختار:
#   - BaseAPITestCase ......... کلاسِ پایه‌ی مشترک (دو کاربرِ نمونه + کلاینتِ JWT)
#   - AuthAPITests ............ ثبت‌نام/ورود و جریانِ توکن JWT
#   - JWTTokenRotationBlacklistTests ‌چرخشِ توکنِ Refresh + لیستِ سیاه + خروجِ سرور-محور (2026-09-08)
#   - SubjectAPITests ......... CRUD درس + یکتاییِ نام + جداسازی کاربران
#   - ExamAPITests ............ CRUD امتحان + ویرایش (PATCH) + سناریوهای امنیتی
#   - StudyLogAPITests ........ ثبتِ گزارش + کسرِ ساعتِ امتحان + جداسازی
#   - StudyLogConcurrencyLockTests  قفلِ select_for_update و خواندنِ تازه در ذخیره/حذفِ گزارش (2026-09-09)
#   - StudyLogOrphanDeleteTests  حذفِ گزارشِ یتیم (کلیدِ خارجیِ شکسته؛ TransactionTestCase)
#   - StudyPlanAPITests ....... endpoint برنامه‌ی مطالعه + اعتبارسنجیِ ورودی
#   - StudyPlanUniqueConstraintTests ‌یکتاییِ StudyPlan.user در سطحِ DB (مایگریشنِ 0008، با TransactionTestCase)
#   - DashboardAPITests ....... شکلِ پاسخ، شمارش‌ها و انواعِ هشدار
#   - StudyPlanAlgorithmTests . تستِ واحدِ توابعِ خالصِ utils.py
#   - PaginationAPITests ...... صفحه‌بندیِ اختیاریِ endpointهای لیستی (?page/?page_size)
#   - SettingsEnvVarsTests .... تنظیماتِ محیطیِ Production (بوتِ مفسرِ جدا؛ بدونِ DB)
#   - DatabaseUrlSettingsTests  دیتابیس از متغیرِ DATABASE_URL — PostgreSQL + پیش‌فرضِ امنِ SQLite (2026-09-09)
#   - PostgresForUpdateTests ... رگرسیونِ FOR UPDATE در SQL — فقط وقتی موتورِ فعال PostgreSQL است
#   - I18nAcceptLanguageTests . ترجمه‌ی پیام‌هایِ API با هدرِ Accept-Language (2026-09-09)
#   - I18nCatalogIntegrityTests  سلامتِ کاتالوگِ locale/en + تنظیماتِ چندزبانی (2026-09-09)
#   - MLCalibrationMathTests . ریاضیاتِ خالصِ مدلِ کالیبراسیون (LSQ از مبدأ + انقباض + مهار) (2026-09-09)
#   - MLTrainingDataTests ... ساختِ نمونه‌هایِ (planned, actual) از تاریخچه‌ی StudyLog (2026-09-09)
#   - MLPredictionsAPITests .. GET /api/predictions/ — مدل + پیش‌بینی‌ها + ریسک + جداسازیِ کاربر (2026-09-09)
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

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from django.conf import settings as django_settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.db import IntegrityError, OperationalError, connection, transaction
from django.db.models.query import QuerySet
from django.test import SimpleTestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from rest_framework.throttling import SimpleRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)

from backend.settings import (
    BASE_DIR,
    _env_bool,
    _env_list,
    _env_int,
    _env_proxy_ssl_header,
    _env_throttle_rate,
    _resolve_database,
)
from .models import Subject, Exam, StudyLog, StudyPlan, UserSecurityProfile
from .utils import (
    compute_subject_progress,
    generate_study_plan,
    format_plan_for_frontend,
    build_subject_distribution,
)
from .ml import (
    fit_calibration_model,
    classify_bias,
    predict_hours,
    assess_exam_risk,
    build_training_samples,
    get_prediction_report,
    PRIOR_STRENGTH,
    FACTOR_MIN,
    FACTOR_MAX,
    BIAS_TOLERANCE,
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

    def tearDown(self):
        # شمارنده‌هایِ محدودسازیِ نرخ (throttle) در cacheِ مشترکِ locmem
        # می‌مانند و کلیدشان مستقل از نرخ است؛ بدونِ پاک‌سازی، تست‌ها به
        # ترتیبِ اجرا وابسته می‌شوند (آلودگیِ بین‌کلاسی). پاک‌سازیِ ارزان است
        # و هیچ stateِ معناداری را از بین نمی‌برد.
        cache.clear()
        super().tearDown()

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

    def test_refresh_returns_new_working_access_token(self):
        """رگرسیونِ انقضای توکن (2026-09-06): توکنِ Refreshِ معتبر → توکنِ دسترسیِ تازه که واقعاً کار می‌کند."""
        login_body = self.client.post(
            '/api/auth/login/',
            {'username': 'alice', 'password': 'pw-12345678'},
            format='json',
        ).json()

        response = self.client.post(
            '/api/auth/refresh/',
            {'refresh': login_body['refresh']},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        new_access = response.json()['access']
        self.assertTrue(new_access)  # توکنِ خالی نیست
        # توکنِ تازه باید رویِ endpointهای محافظت‌شده واقعاً کار کند (ادغامِ کاملِ مسیر)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {new_access}')
        self.assertEqual(client.get('/api/subjects/').status_code, status.HTTP_200_OK)

    def test_refresh_with_garbage_token_rejected(self):
        """توکنِ Refreshِ بی‌اعتبار: 401 (این همان سیگنالی است که فرانت‌اند را به صفحه‌ی ورود می‌فرستد)."""
        response = self.client.post(
            '/api/auth/refresh/',
            {'refresh': 'garbage-token-not-a-jwt'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertNotIn('access', response.json())

    def test_refresh_endpoint_needs_no_auth_header(self):
        """مسیرِ تمدید مثلِ ورود/ثبت‌نام عمومی است؛ نبودِ هدرِ Authorization نباید 403 بدهد."""
        # APIClientِ خالی = هیچ هدری فرستاده نمی‌شود؛ پاسخِ درست اینجا 401/400 است نه 403
        response = APIClient().post(
            '/api/auth/refresh/', {'refresh': 'x'}, format='json'
        )

        self.assertNotEqual(response.status_code, status.HTTP_403_FORBIDDEN)

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
# ۱-ب) چرخش و لیستِ سیاهِ توکنِ Refresh (ROTATE/BLACKLIST — از 2026-09-08)
# ---------------------------------------------------------------------------

class JWTTokenRotationBlacklistTests(BaseAPITestCase):
    """
    پوششِ رفتارِ پس از فعال‌شدنِ ROTATE_REFRESH_TOKENS و BLACKLIST_AFTER_ROTATION
    (به‌همراه‌ی اپِ token_blacklist در INSTALLED_APPS):

    - هر تمدید، توکنِ Refreshِ تازه صادر می‌کند و توکنِ قبلی باطل می‌شود
      (هر توکنِ تمدید فقط یک‌بار قابلِ استفاده است — مهاجمی که توکن را دزدیده
      باشد، با اولین تمدیدِ مالکِ واقعی از بازی خارج می‌شود).
    - خروجِ سرور-محور: POST /api/auth/logout/ (TokenBlacklistView) توکنِ
      Refreshِ داده‌شده را در لیستِ سیاه ثبت می‌کند.

    فرانت‌اند از قبل با این رفتار سازگار است: refreshAccessToken در app.js
    توکنِ تازه را ذخیره می‌کند و logout پیش از پاک‌کردنِ localStorage، توکن
    را به /api/auth/logout/ می‌فرستد.
    """

    # --- کمکی‌ها -----------------------------------------------------------

    def _login_refresh(self, username='alice'):
        """ورودِ واقعی از API و برگرداندنِ توکنِ Refreshِ صادرشده."""
        body = self.client.post(
            '/api/auth/login/',
            {'username': username, 'password': 'pw-12345678'},
            format='json',
        ).json()
        return body['refresh']

    def _rotate(self, refresh):
        """POST به مسیرِ تمدید با توکنِ Refreshِ داده‌شده."""
        return self.client.post(
            '/api/auth/refresh/', {'refresh': refresh}, format='json'
        )

    # --- چرخش --------------------------------------------------------------

    def test_refresh_returns_new_refresh_token(self):
        """چرخش: پاسخِ تمدید حالا توکنِ Refreshِ تازه هم دارد (متفاوت از قبلی)."""
        old_refresh = self._login_refresh()

        response = self._rotate(old_refresh)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.assertIn('refresh', body)
        self.assertTrue(body['refresh'])
        self.assertNotEqual(body['refresh'], old_refresh)

    def test_old_refresh_token_rejected_after_rotation(self):
        """رگرسیونِ امنیتی: توکنِ Refreshِ قبلی بعد از چرخش باطل است (۴۰۱)."""
        old_refresh = self._login_refresh()
        self._rotate(old_refresh)  # چرخشِ اول: توکنِ قبلی واردِ لیستِ سیاه شد

        response = self._rotate(old_refresh)  # استفاده‌ی مجدد از توکنِ مرده

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_rotation_chain_continues(self):
        """زنجیره‌ی تمدید ادامه دارد: توکنِ تازه هم می‌چرخد؛ نسل‌های قبلی همه مرده‌اند."""
        r1 = self._login_refresh()
        r2 = self._rotate(r1).json()['refresh']

        r3 = self._rotate(r2)

        self.assertEqual(r3.status_code, status.HTTP_200_OK)
        r3 = r3.json()['refresh']
        self.assertNotEqual(r3, r2)
        # هر دو نسلِ قبلی باید باطل باشند (توکنِ هر نسل فقط یک‌بار)
        self.assertEqual(self._rotate(r1).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self._rotate(r2).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_rotated_access_token_works(self):
        """توکنِ دسترسیِ صادرشده در چرخش، رویِ endpointهای محافظت‌شده واقعاً کار می‌کند
        (ابطالِ توکنِ Refreshِ قبلی، این توکنِ دسترسی را از کار نمی‌اندازد — عمرش مستقل است)."""
        old_refresh = self._login_refresh()

        body = self._rotate(old_refresh).json()

        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {body['access']}")
        self.assertEqual(client.get('/api/subjects/').status_code, status.HTTP_200_OK)

    # --- خروجِ سرور-محور (TokenBlacklistView) -------------------------------

    def test_logout_blacklists_refresh_token(self):
        """خروجِ سرور-محور: POST /api/auth/logout/ توکن را باطل می‌کند؛ تمدیدِ بعدی ۴۰۱."""
        refresh = self._login_refresh()

        response = self.client.post(
            '/api/auth/logout/', {'refresh': refresh}, format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            self._rotate(refresh).status_code, status.HTTP_401_UNAUTHORIZED
        )

    def test_logout_with_garbage_token_rejected(self):
        """توکنِ بی‌اعتبار در خروج: ۴۰۱ (نه ۵۰۰/خطایِ دیگر)."""
        response = self.client.post(
            '/api/auth/logout/', {'refresh': 'garbage-token-not-a-jwt'}, format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_blacklists_only_that_token(self):
        """ابطالِ توکنِ یک نشست، توکنِ نشستِ دیگر (کاربرِ دیگر) را نمی‌کشد."""
        alice_refresh = self._login_refresh('alice')
        bob_refresh = self._login_refresh('bob')

        self.client.post(
            '/api/auth/logout/', {'refresh': alice_refresh}, format='json'
        )

        self.assertEqual(
            self._rotate(alice_refresh).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
        self.assertEqual(self._rotate(bob_refresh).status_code, status.HTTP_200_OK)


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
# ۴-ب) قفلِ هم‌زمانیِ گزارشِ مطالعه (select_for_update) — 2026-09-09
# ---------------------------------------------------------------------------

class StudyLogConcurrencyLockTests(BaseAPITestCase):
    """
    قفلِ هم‌زمانیِ StudyLog.save()/delete() (آیتمِ Lowِ TODO، 2026-09-09):
    سطرِ امتحان پیش از کسر/بازگشتِ ساعت با select_for_update() قفل و
    «تازه» خوانده می‌شود؛ پس مبنایِ محاسبه، مقدارِ لحظه‌ایِ دیتابیس است نه
    snapshotِ حافظه — و Lost Update ممکن نیست (دو تستِ اول رفتارِ قدیمی را
    قطعی‌آور شکست می‌دهند؛ بقیه قفل‌بودنِ مسیر و رفتارهایِ حاشیه‌ای را
    تضمین می‌کنند).
    """

    def setUp(self):
        super().setUp()
        self.subject = self.create_subject(self.alice, 'فیزیک')
        self.exam = self.create_exam(self.subject, hours=5)

    def _spy_on_queryset_get(self, calls):
        """
        جاسوس روی QuerySet.get: هر خواندنِ امتحان را همراهِ این‌که کوئری‌اش
        select_for_update داشت یا نه ثبت می‌کند — راهِ قطعی‌آورِ اثباتِ
        قفل‌بودنِ مسیر در SQLite (که FOR UPDATE را بی‌صدا نادیده می‌گیرد و
        در SQL دیده نمی‌شود).
        """
        original_get = QuerySet.get

        def spy_get(self_qs, *args, **kwargs):
            calls.append(
                bool(getattr(self_qs.query, 'select_for_update', False))
            )
            return original_get(self_qs, *args, **kwargs)

        return patch('django.db.models.query.QuerySet.get', spy_get)

    def test_save_deducts_from_fresh_db_value_not_stale_instance(self):
        """رگرسیونِ Lost Update (رفعِ 2026-09-09): مبنایِ کسر، مقدارِ تازه‌ی
        دیتابیس است نه snapshotِ حافظه. امتحان ۵ ساعته → گزارشِ اول ۳ ساعت
        می‌گیرد (باقی‌مانده: ۲)؛ گزارشِ دوم که در حافظه به کپیِ قدیمیِ
        ۵ ساعته اشاره می‌کند ۴ ساعت ثبت می‌کند. کدِ درست: فقط ۲ ساعت
        (باقی‌مانده‌یِ واقعی) کسر و حاصل صفر می‌شود؛ کدِ قدیمی با مبنایِ
        کهنه ۴ ساعت کسر و عددِ ۱ را می‌نوشت (کسرِ گزارشِ اول له می‌شد)."""
        stale_exam = Exam.objects.get(pk=self.exam.pk)  # snapshot: ۵ ساعت
        StudyLog.objects.create(user=self.alice, exam=self.exam, hours_studied=3)
        self.exam.refresh_from_db()
        self.assertEqual(self.exam.study_hours_remaining, 2)  # 5 - 3

        # گزارشِ دوم با مرجعِ کهنه (در حافظه هنوز ۵ ساعت می‌بیند):
        second_log = StudyLog(user=self.alice, exam=stale_exam, hours_studied=4)
        second_log.save()

        self.exam.refresh_from_db()
        self.assertEqual(self.exam.study_hours_remaining, 0)  # نه ۱ (کدِ قدیمی)
        self.assertEqual(second_log.hours_deducted, 2)  # فقط باقی‌مانده‌یِ واقعی

        # بازگشتِ دقیق: حذفِ گزارشِ دوم فقط همان ۲ ساعتِ واقعاً کسرشده را
        # برمی‌گرداند (کدِ قدیمی ۴ ساعت «از هیچ» می‌ساخت).
        second_log.delete()
        self.exam.refresh_from_db()
        self.assertEqual(self.exam.study_hours_remaining, 2)

    def test_delete_refunds_into_fresh_db_value(self):
        """قرینه‌یِ تستِ بالا در delete(): بازگشتِ ساعت رویِ مقدارِ لحظه‌ایِ
        دیتابیس جمع می‌شود، نه رویِ کپیِ کش‌شده‌یِ ابتدایِ درخواست. بعد از
        گزارشِ ۳ ساعته (باقی‌مانده: ۲)، به‌روزرسانیِ هم‌زمانِ باقی‌مانده را
        به ۱۰ می‌برد؛ حذفِ گزارش باید ۱۳ بگذارد (کدِ قدیمی با snapshotِ
        کهنه ۵ می‌نوشت و به‌روزرسانیِ هم‌زمان را له می‌کرد)."""
        log = StudyLog.objects.create(user=self.alice, exam=self.exam, hours_studied=3)
        self.exam.refresh_from_db()
        self.assertEqual(self.exam.study_hours_remaining, 2)

        # گزارش با examِ کش‌شده (مثلِ select_relatedِ ابتدایِ درخواست):
        log = StudyLog.objects.select_related('exam').get(pk=log.pk)
        # به‌روزرسانیِ هم‌زمان (مستقل از نمونه‌هایِ در حافظه):
        Exam.objects.filter(pk=self.exam.pk).update(study_hours_remaining=10)

        log.delete()
        self.exam.refresh_from_db()
        self.assertEqual(self.exam.study_hours_remaining, 13)  # 10 + 3

    def test_save_locks_exam_row_with_select_for_update(self):
        """مسیرِ save() باید امتحان را با کوئریِ select_for_update بخواند
        (در SQLite در SQL ظاهر نمی‌شود؛ پرچمِ کوئری را با جاسوس چک می‌کنیم)."""
        calls = []
        with self._spy_on_queryset_get(calls):
            StudyLog.objects.create(user=self.alice, exam=self.exam, hours_studied=1)
        self.assertIn(True, calls)  # حداقل یک خواندنِ قفل‌شده

    def test_delete_locks_exam_row_with_select_for_update(self):
        """مسیرِ delete() (با بازگشتِ ساعت) هم امتحان را قفل می‌کند."""
        log = StudyLog.objects.create(user=self.alice, exam=self.exam, hours_studied=2)
        calls = []
        with self._spy_on_queryset_get(calls):
            log.delete()
        self.assertIn(True, calls)

    def test_edit_log_skips_lock_and_deduction(self):
        """ویرایشِ گزارش (pk دارد) نه قفل می‌گیرد (اتلاف نداریم) و نه دوباره
        ساعت کسر می‌کند — دست‌نخوردگیِ رفتارِ قبلی."""
        log = StudyLog.objects.create(user=self.alice, exam=self.exam, hours_studied=2)
        self.exam.refresh_from_db()
        self.assertEqual(self.exam.study_hours_remaining, 3)  # 5 - 2

        log.hours_studied = 5  # ویرایش
        calls = []
        with self._spy_on_queryset_get(calls):
            log.save()

        self.assertNotIn(True, calls)  # بدونِ قفل
        self.exam.refresh_from_db()
        self.assertEqual(self.exam.study_hours_remaining, 3)  # بدونِ کسرِ مجدد
        log.refresh_from_db()
        self.assertEqual(log.hours_studied, 5)
        self.assertEqual(log.hours_deducted, 2)  # کسرِ اصلی دست‌نخورده

    def test_save_with_deleted_exam_fails_cleanly(self):
        """اگر امتحانِ گزارشِ تازه قبل از ذخیره حذف شده باشد: خطایِ روشنِ
        DoesNotExist (نه رکوردِ یتیمِ نیمه‌کاره) و هیچ گزارشی ذخیره نمی‌شود."""
        log = StudyLog(user=self.alice, exam=self.exam, hours_studied=1)
        self.exam.delete()
        with self.assertRaises(Exam.DoesNotExist):
            log.save()
        self.assertFalse(StudyLog.objects.exists())


@unittest.skipUnless(
    connection.vendor == 'sqlite',
    'ساختِ یتیمِ واقعی با PRAGMA foreign_keys فقط در SQLite ممکن است؛'
    ' در PostgreSQL همین تست با skip رد می‌شود (رفتارِ حذفِ یتیم توسط'
    ' رگرسیون‌های Lost Update در StudyLogConcurrencyLockTests پوشش داده'
    ' می‌شود).',
)
class StudyLogOrphanDeleteTests(TransactionTestCase):
    """
    حذفِ مستقیمِ گزارشِ «یتیم» (کلیدِ خارجیِ شکسته) — رفتارِ defensive:
    فقط خودِ گزارش حذف می‌شود، بدونِ خطا و بدونِ زنده‌کردنِ امتحانِ حذف‌شده.
    (TransactionTestCase لازم است چون ساختِ یتیمِ واقعی فقط بیرونِ تراکنشِ
    تست و با خاموش‌کردنِ موقتِ کلیدِ خارجیِ SQLite ممکن است.)
    """

    def test_delete_orphan_log_just_deletes_without_refund(self):
        user = User.objects.create_user(username='carol', password='pw-12345678')
        subject = Subject.objects.create(user=user, name='شیمی', difficulty=3)
        exam = Exam.objects.create(
            subject=subject,
            exam_date=date.today() + timedelta(days=10),
            study_hours_remaining=5,
            chapters_remaining=3,
        )
        log = StudyLog.objects.create(user=user, exam=exam, hours_studied=2)

        # شبیه‌سازیِ کلیدِ خارجیِ شکسته: حذفِ خامِ سطرِ امتحان (بدونِ آبشار)
        with connection.cursor() as cursor:
            cursor.execute('PRAGMA foreign_keys = OFF')
            cursor.execute('DELETE FROM planner_exam WHERE id = %s', [exam.pk])
            cursor.execute('PRAGMA foreign_keys = ON')
        self.assertTrue(StudyLog.objects.filter(pk=log.pk).exists())  # یتیم ماند

        log.delete()  # نباید خطا بدهد و نباید امتحان را «زنده» کند

        self.assertFalse(StudyLog.objects.filter(pk=log.pk).exists())
        self.assertFalse(Exam.objects.filter(pk=exam.pk).exists())  # نه resurrection


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


    def test_direct_post_second_settings_rejected(self):
        """رگرسیون (0008): POST مستقیم به /api/study-plan/ فقط یک‌بار می‌سازد؛
        بارِ دوم پاسخِ 400 خوانا می‌گیرد (نه خطایِ 500 خامِ دیتابیس) و رکوردِ دومی ساخته نمی‌شود."""
        client = self.client_as(self.alice)
        first = client.post('/api/study-plan/', {'daily_available_hours': 5.0}, format='json')
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        second = client.post('/api/study-plan/', {'daily_available_hours': 6.0}, format='json')
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('detail', second.json())
        self.assertEqual(StudyPlan.objects.filter(user=self.alice).count(), 1)


# ---------------------------------------------------------------------------
# ۵-ب) قیدِ یکتاییِ StudyPlan.user در سطحِ دیتابیس
# ---------------------------------------------------------------------------

class StudyPlanUniqueConstraintTests(TransactionTestCase):
    """یکتاییِ StudyPlan.user در خودِ دیتابیس (مایگریشنِ 0008).
    TransactionTestCase لازم است چون IntegrityError تراکنشِ TestCase را
    می‌شکند و بعد از آن هیچ کوئریِ دیگری در همان تست ممکن نیست."""

    def test_db_rejects_second_row_for_same_user(self):
        """دو CREATE خامِ ORM برای یک کاربر → IntegrityError؛ قیدِ UNIQUE واقعاً در DB نشسته است."""
        user = User.objects.create_user('plandupe', password='Strong-Pass-123')
        StudyPlan.objects.create(user=user, daily_available_hours=2.0)
        with self.assertRaises(IntegrityError):
            StudyPlan.objects.create(user=user, daily_available_hours=3.0)
        self.assertEqual(StudyPlan.objects.filter(user=user).count(), 1)

    def test_get_or_create_remains_idempotent_under_constraint(self):
        """الگوی get_or_create (مسیرِ اصلیِ views.py) با وجودِ قید، رفتارِ پیشین را دارد."""
        user = User.objects.create_user('planatomic', password='Strong-Pass-123')
        obj, created = StudyPlan.objects.get_or_create(
            user=user, defaults={'daily_available_hours': 2.0}
        )
        self.assertTrue(created)
        obj2, created2 = StudyPlan.objects.get_or_create(
            user=user, defaults={'daily_available_hours': 4.0}
        )
        self.assertFalse(created2)
        self.assertEqual(obj.pk, obj2.pk)
        # مقدارِ موجود (2.0) دست‌نخورده می‌ماند؛ defaults فقط موقعِ ساخت اعمال می‌شود
        self.assertEqual(obj2.daily_available_hours, 2.0)


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


# ---------------------------------------------------------------------------
# ۸) صفحه‌بندیِ اختیاریِ لیست‌ها
# ---------------------------------------------------------------------------

class PaginationAPITests(BaseAPITestCase):
    """
    صفحه‌بندیِ اختیاریِ endpointهای لیستی (?page= و ?page_size=).

    مهم‌ترین رگرسیون: درخواستِ بدونِ پارامتر باید دقیقاً همان «لیستِ کاملِ
    JSON» قبل از این قابلیت را بدهد — فرانت‌اندِ فعلیِ پروژه (app.js)
    هیچ‌کدام از این پارامترها را نمی‌فرستد و نباید چیزی حس کند.
    """

    def setUp(self):
        super().setUp()
        # ۵ درس برای alice؛ ۳ امتحان روی سه درسِ اول؛ ۳ گزارش روی امتحانِ اول
        self.subjects = [self.create_subject(self.alice, f'درس{i}') for i in range(1, 6)]
        self.exams = [self.create_exam(subject) for subject in self.subjects[:3]]
        for _ in range(3):
            StudyLog.objects.create(user=self.alice, exam=self.exams[0], hours_studied=1)
        # داده‌ی کاربرِ بیگانه: نباید در هیچ صفحه/شمارشی دیده شود
        self.create_subject(self.bob, 'درسِ باب')
        self.create_exam(self.create_subject(self.bob, 'شیمیِ باب'))

    # --- سازگاری با فرانت‌اندِ فعلی ---------------------------------------

    def test_no_params_returns_plain_list(self):
        """رگرسیون: بدونِ ?page/?page_size پاسخ همان لیستِ کامل است (نه dict)."""
        expected_counts = {
            '/api/subjects/': 5,
            '/api/exams/': 3,
            '/api/study-logs/': 3,
        }
        for url, expected in expected_counts.items():
            with self.subTest(url=url):
                body = self.client_as(self.alice).get(url).json()
                self.assertIsInstance(body, list)
                self.assertEqual(len(body), expected)

    def test_invalid_page_size_alone_returns_plain_list(self):
        """page_size نامعتبر/غیرمثبت بدونِ page → صفحه‌بندی فعال نمی‌شود."""
        for query in ('?page_size=abc', '?page_size=0', '?page_size=-3'):
            with self.subTest(query=query):
                body = self.client_as(self.alice).get(f'/api/subjects/{query}').json()
                self.assertIsInstance(body, list)
                self.assertEqual(len(body), 5)

    # --- شکلِ پاسخِ صفحه‌بندی‌شده -------------------------------------------

    def test_page_size_returns_paginated_shape(self):
        """?page_size=2 → قالبِ استانداردِ {count,next,previous,results} + جداسازی."""
        body = self.client_as(self.alice).get('/api/subjects/?page_size=2').json()

        self.assertIsInstance(body, dict)
        self.assertEqual(set(body.keys()), {'count', 'next', 'previous', 'results'})
        # count فقط درس‌هایِ alice را می‌شمارد (درسِ باب نه)
        self.assertEqual(body['count'], 5)
        self.assertEqual(len(body['results']), 2)
        self.assertIsNone(body['previous'])
        self.assertIsNotNone(body['next'])
        self.assertIn('page=2', body['next'])
        self.assertNotIn('درسِ باب', [s['name'] for s in body['results']])

    def test_page_only_uses_default_page_size(self):
        """?page= به‌تنهایی → صفحه‌بندی فعال با اندازه‌ی پیش‌فرض (۲۰ ≥ ۵ → همه)."""
        body = self.client_as(self.alice).get('/api/subjects/?page=1').json()

        self.assertIsInstance(body, dict)
        self.assertEqual(body['count'], 5)
        self.assertEqual(len(body['results']), 5)
        self.assertIsNone(body['next'])
        self.assertIsNone(body['previous'])

    def test_exams_and_study_logs_paginate_the_same_way(self):
        """امتحان‌ها و گزارش‌ها هم با همان کلاسِ مشترک صفحه‌بندی می‌شوند."""
        for url, total in (('/api/exams/', 3), ('/api/study-logs/', 3)):
            with self.subTest(url=url):
                body = self.client_as(self.alice).get(f'{url}?page_size=2').json()

                self.assertEqual(body['count'], total)
                self.assertEqual(len(body['results']), 2)
                self.assertIn('page=2', body['next'])

    # --- صحتِ پیمایشِ صفحه‌ها -----------------------------------------------

    def test_all_pages_cover_every_record_exactly_once(self):
        """صفحه‌هایِ ۱..۳ با page_size=2 → اجتماعِ نتایج = هر ۵ درس، بدونِ هم‌پوشانی."""
        seen_ids = []
        for page_number in (1, 2, 3):
            body = self.client_as(self.alice).get(
                f'/api/subjects/?page={page_number}&page_size=2'
            ).json()
            seen_ids.extend(subject['id'] for subject in body['results'])

        # اگر رکوردی دو بار می‌آمد یا جایی می‌ماند، این مقایسه می‌شکست
        self.assertEqual(sorted(seen_ids), sorted(s.id for s in self.subjects))

    def test_last_page_has_null_next_link(self):
        """آخرین صفحه: next=null و previous مقدار دارد."""
        body = self.client_as(self.alice).get('/api/subjects/?page=3&page_size=2').json()

        self.assertEqual(len(body['results']), 1)
        self.assertIsNone(body['next'])
        self.assertIsNotNone(body['previous'])

    def test_out_of_range_or_invalid_page_returns_404(self):
        """صفحه‌ی نامعتبر/خارج از محدوده → 404 استانداردِ DRF (نه 500)."""
        for query in ('?page=abc', '?page=99', '?page=abc&page_size=2'):
            with self.subTest(query=query):
                response = self.client_as(self.alice).get(f'/api/subjects/{query}')
                self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # --- تستِ واحدِ خودِ کلاسِ صفحه‌بندی --------------------------------------

    def test_pagination_class_size_rules(self):
        """قواعدِ get_page_size: پیش‌فرض، سقفِ ۱۰۰، غیرفعال‌بودنِ بدونِ پارامتر."""
        from rest_framework.request import Request
        from rest_framework.test import APIRequestFactory

        from .views import OptionalPageNumberPagination

        factory = APIRequestFactory()

        def size_for(params):
            # factory درخواستِ خامِ Django می‌سازد؛ query_params (که DRF
            # می‌فهمد) فقط رویِ Requestِ DRF وجود دارد، پس می‌پیچیمش.
            request = Request(factory.get('/api/subjects/', params))
            return OptionalPageNumberPagination().get_page_size(request)

        self.assertIsNone(size_for({}))                       # هیچ پارامتری
        self.assertEqual(size_for({'page': '2'}), 20)          # فقط page → پیش‌فرض
        self.assertEqual(size_for({'page_size': '5'}), 5)      # صریح
        self.assertEqual(size_for({'page_size': '999'}), 100)  # سقفِ max_page_size
        self.assertIsNone(size_for({'page_size': 'abc'}))      # نامعتبر
        self.assertIsNone(size_for({'page_size': '0'}))        # غیرمثبت
        # نامعتبر همراه با page → به اندازه‌ی پیش‌فرض می‌افتد
        self.assertEqual(size_for({'page': '2', 'page_size': 'abc'}), 20)


# ---------------------------------------------------------------------------
# تنظیماتِ محیطیِ Production (از 2026-09-06 — بستنِ آیتمِ Medium TODO)
# ---------------------------------------------------------------------------

class SettingsEnvVarsTests(SimpleTestCase):
    """
    متغیرهایِ محیطیِ `settings.py` — دو لایه:

    ۱) تستِ واحدِ توابعِ کمکیِ `_env_bool`/`_env_list` (بدونِ دیتابیس).
    ۲) «بوتِ واقعی»: هر تست یک مفسرِ پایتونِ تازه spawn می‌کند
       (``python -c "import django; django.setup()"``) با متغیرهایِ دلخواه،
       تا تنظیماتِ همانِ محیطِ ساختگی — نه محیطِ همین فرایندِ تست —
       واقعاً بارگذاری و ارزیابی شود (شاملِ سپرِ راه‌اندازیِ Production).
    """

    _ENV_KEYS = (
        'DJANGO_SECRET_KEY', 'DJANGO_DEBUG', 'DJANGO_ALLOWED_HOSTS',
        'DJANGO_CORS_ALLOW_ALL', 'DJANGO_ALLOWED_ORIGINS',
    )

    def _boot(self, extra_env, code):
        """مفسرِ تازه‌ای با متغیرهایِ داده‌شده بالا می‌آورد و نتیجه را برمی‌گرداند."""
        env = os.environ.copy()
        env['DJANGO_SETTINGS_MODULE'] = 'backend.settings'
        for key in self._ENV_KEYS:
            env.pop(key, None)          # نشتِ محیطِ تست به نتیجه نداشته باشد
        env.update(extra_env)
        return subprocess.run(
            [sys.executable, '-c', code],
            capture_output=True, text=True, env=env,
            cwd=str(Path(__file__).resolve().parents[1]),   # پوشه‌ی backend/
            timeout=90,
        )

    # ---- ۱) توابعِ کمکی ------------------------------------------------------

    def test_env_bool_parsing(self):
        """رگرسیون: فقط 1/true/yes/on مثبت‌اند؛ هر چیزِ دیگر منفی؛ بی‌مقدار → default."""
        for raw in ('1', 'true', 'TRUE', 'True', 'yes', 'YES', 'on', 'ON', ' 1 ', ' true '):
            with patch.dict(os.environ, {'DJANGO_TEST_BOOL': raw}):
                self.assertIs(_env_bool('DJANGO_TEST_BOOL'), True, msg=raw)
        for raw in ('0', 'false', 'FALSE', 'no', 'off', 'OFF', '', '   ', 'banana', '2', '01'):
            with patch.dict(os.environ, {'DJANGO_TEST_BOOL': raw}):
                self.assertIs(_env_bool('DJANGO_TEST_BOOL'), False, msg=raw)
        # بی‌مقدار → مقدارِ پیش‌فرض (در هر دو جهت)
        os.environ.pop('DJANGO_TEST_BOOL', None)
        self.assertIs(_env_bool('DJANGO_TEST_BOOL', default=True), True)
        self.assertIs(_env_bool('DJANGO_TEST_BOOL', default=False), False)

    def test_env_list_parsing(self):
        """رگرسیون: جداکننده‌ی کاما + چشم‌پوشی از فاصله‌ها و خانه‌های خالی."""
        with patch.dict(os.environ, {'DJANGO_TEST_LIST': 'a, b ,, c ,'}):
            self.assertEqual(_env_list('DJANGO_TEST_LIST'), ['a', 'b', 'c'])
        with patch.dict(os.environ, {'DJANGO_TEST_LIST': ''}):
            self.assertEqual(_env_list('DJANGO_TEST_LIST'), [])
        os.environ.pop('DJANGO_TEST_LIST', None)
        self.assertEqual(_env_list('DJANGO_TEST_LIST'), [])

    # ---- ۲) بوتِ واقعی با تنظیماتِ تازه ---------------------------------------

    def test_boot_dev_defaults_unchanged(self):
        """بدونِ هیچ متغیری: دقیقاً همان رفتارِ توسعه‌ی قبل — بوت می‌شود."""
        code = (
            'import django; django.setup(); from django.conf import settings; '
            'assert settings.DEBUG is True, "DEBUG"; '
            'assert settings.CORS_ALLOW_ALL_ORIGINS is True, "CORS"; '
            'assert settings.SECRET_KEY, "KEY"; '
            'assert settings.ALLOWED_HOSTS == [], "HOSTS"; '
            'print("dev-ok")'
        )
        result = self._boot({}, code)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn('dev-ok', result.stdout)

    def test_prod_without_secret_key_refuses_to_boot(self):
        """سپر: DEBUG=false با کلیدِ توسعه از همانِ بوت متوقف می‌شود."""
        result = self._boot({'DJANGO_DEBUG': 'false'}, 'import django; django.setup()')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('DJANGO_SECRET_KEY', result.stderr)

    def test_prod_without_allowed_hosts_refuses_to_boot(self):
        """سپر: DEBUG=false بدونِ DJANGO_ALLOWED_HOSTS هم متوقف می‌شود."""
        result = self._boot(
            {'DJANGO_DEBUG': 'false', 'DJANGO_SECRET_KEY': 'p' * 64},
            'import django; django.setup()',
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('DJANGO_ALLOWED_HOSTS', result.stderr)

    def test_prod_with_env_boots_with_production_values(self):
        """ترکیبِ کاملِ متغیرها: بوتِ سالم با مقادیرِ Production."""
        key = 'p' * 64
        code = (
            'import django; django.setup(); from django.conf import settings; '
            'assert settings.DEBUG is False, "DEBUG"; '
            "assert settings.SECRET_KEY == '{0}', 'KEY'; "
            "assert settings.ALLOWED_HOSTS == ['example.com', 'www.example.com'], 'HOSTS'; "
            'print("prod-ok")'
        ).format(key)
        result = self._boot(
            {'DJANGO_DEBUG': 'false', 'DJANGO_SECRET_KEY': key,
             'DJANGO_ALLOWED_HOSTS': 'example.com, www.example.com'},
            code,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn('prod-ok', result.stdout)

    def test_cors_env_overrides(self):
        """CORS: خاموش‌کردنِ allow-all + فهرستِ مبدأهایِ مجاز از متغیر."""
        code = (
            'import django; django.setup(); from django.conf import settings; '
            'assert settings.CORS_ALLOW_ALL_ORIGINS is False, "ALL"; '
            "assert settings.CORS_ALLOWED_ORIGINS == "
            "['https://a.com', 'https://b.com'], 'ORIG'; "
            'print("cors-ok")'
        )
        result = self._boot(
            {'DJANGO_CORS_ALLOW_ALL': 'false',
             'DJANGO_ALLOWED_ORIGINS': 'https://a.com,https://b.com'},
            code,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn('cors-ok', result.stdout)


# ---------------------------------------------------------------------------
# ۱۵) دیتابیس از متغیرِ محیطیِ DATABASE_URL — پشتیبانیِ PostgreSQL
# (پیش‌فرضِ امنِ توسعه: بدونِ متغیر، همان SQLiteِ قبل)
# ---------------------------------------------------------------------------

try:
    import psycopg  # noqa: F401 — فقط برای تشخیصِ نصب‌بودنِ درایور
    _HAS_PSYCOPG = True
except ImportError:
    _HAS_PSYCOPG = False


def _fake_import(name):
    """شبیه‌سازیِ «psycopg نصب نیست» — همیشه ImportError می‌دهد."""
    raise ImportError(f'No module named {name!r} (simulated)')


class DatabaseUrlSettingsTests(SimpleTestCase):
    """
    متغیرِ DATABASE_URL — سه لایه، مثلِ SettingsEnvVarsTests:

    ۱) تستِ واحدِ تابعِ `_resolve_database` (بدونِ دیتابیس؛ محیط و
       درایورِ ساختگی تزریق می‌شود تا نتیجه همه‌جا قطعی باشد).
    ۲) «بوتِ واقعی»: مفسرِ تازه با DATABASE_URL دلخواه بالا می‌آید.
    ۳) نبودِ درایور: یک ماژولِ سایه‌ی psycopg در PYTHONPATH جلوتر از
       site-packages می‌نشیند و import با خطا می‌شکند — این تست حتی
       روی ماشینِ نصب‌شده هم همانِ روزِ اول را بازسازی می‌کند.
    """

    _ENV_KEYS = SettingsEnvVarsTests._ENV_KEYS + ('DATABASE_URL',)

    def _boot(self, extra_env, code, extra_pythonpath=''):
        """مفسرِ تازه با متغیرهایِ داده‌شده (DATABASE_URL همیشه پاک می‌شود)."""
        env = os.environ.copy()
        env['DJANGO_SETTINGS_MODULE'] = 'backend.settings'
        for key in self._ENV_KEYS:
            env.pop(key, None)          # نشتِ محیطِ تست به نتیجه نداشته باشد
        env.update(extra_env)
        if extra_pythonpath:
            env['PYTHONPATH'] = (
                extra_pythonpath + os.pathsep + env.get('PYTHONPATH', '')
            )
        return subprocess.run(
            [sys.executable, '-c', code],
            capture_output=True, text=True, env=env,
            cwd=str(Path(__file__).resolve().parents[1]),   # پوشه‌ی backend/
            timeout=90,
        )

    # ---- ۱) تستِ واحدِ `_resolve_database` -----------------------------------

    def test_default_without_url_returns_sqlite(self):
        """رگرسیون: بدونِ DATABASE_URL دقیقاً همان SQLiteِ قبل — هیچ تغییری نه."""
        self.assertEqual(
            _resolve_database({}),
            {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': BASE_DIR / 'db.sqlite3',
            },
        )
        # مقدارِ خالی/فاصله‌ای هم مثلِ نبودِ متغیر رفتار می‌کند:
        self.assertEqual(
            _resolve_database({'DATABASE_URL': '   '})['ENGINE'],
            'django.db.backends.sqlite3',
        )

    @unittest.skipUnless(_HAS_PSYCOPG, 'psycopg نصب نیست (pip install -r requirements.txt)')
    def test_postgres_url_full_components(self):
        """URL کامل: user/pass (با URL-decode)، host، port و نامِ دیتابیس."""
        database = _resolve_database(
            {'DATABASE_URL': 'postgres://study:p%40ss@db.example.com:5433/plannerdb'}
        )
        self.assertEqual(database['ENGINE'], 'django.db.backends.postgresql')
        self.assertEqual(database['USER'], 'study')
        self.assertEqual(database['PASSWORD'], 'p@ss')      # %40 → @
        self.assertEqual(database['HOST'], 'db.example.com')
        self.assertEqual(database['PORT'], '5433')
        self.assertEqual(database['NAME'], 'plannerdb')
        self.assertNotIn('OPTIONS', database)               # بدونِ query → بدونِ OPTIONS
        self.assertNotIn('CONN_MAX_AGE', database)

    @unittest.skipUnless(_HAS_PSYCOPG, 'psycopg نصب نیست (pip install -r requirements.txt)')
    def test_postgres_url_query_params(self):
        """پارامترهایِ اختیاری: ?host= (سوکت)، ?sslmode=، ?conn_max_age=."""
        database = _resolve_database(
            {'DATABASE_URL': (
                'postgresql://u:pw@ignored-host:5432/plannerdb'
                '?host=/var/run/postgresql&sslmode=require&conn_max_age=60'
            )}
        )
        # ?host= بر hostnameِ داخلِ URL اولویت دارد (الگویِ هاستِ ابری):
        self.assertEqual(database['HOST'], '/var/run/postgresql')
        self.assertEqual(database['OPTIONS'], {'sslmode': 'require'})
        self.assertEqual(database['CONN_MAX_AGE'], 60)
        # schemeِ postgresql هم مثلِ postgres پذیرفته می‌شود:
        self.assertEqual(database['ENGINE'], 'django.db.backends.postgresql')

    def test_rejects_unsupported_scheme(self):
        """scheme غیر از postgres/postgresql → ImproperlyConfiguredِ راهنما."""
        with self.assertRaises(ImproperlyConfigured) as ctx:
            _resolve_database({'DATABASE_URL': 'mysql://user:pass@localhost/db'})
        self.assertIn('postgres', str(ctx.exception))
        self.assertIn('mysql', str(ctx.exception))

    def test_rejects_invalid_port(self):
        """پورتِ غیر عددی → ImproperlyConfigured (نه عددِ بی‌معنا)."""
        with self.assertRaises(ImproperlyConfigured) as ctx:
            _resolve_database(
                {'DATABASE_URL': 'postgres://u:p@localhost:abc/plannerdb'}
            )
        self.assertIn('port', str(ctx.exception))

    def test_rejects_missing_database_name(self):
        """URL بدونِ نامِ دیتابیس → ImproperlyConfigured با مثالِ درست."""
        with self.assertRaises(ImproperlyConfigured) as ctx:
            _resolve_database({'DATABASE_URL': 'postgres://u:p@localhost:5432'})
        self.assertIn('database name', str(ctx.exception))

    def test_rejects_non_integer_conn_max_age(self):
        """conn_max_age= غیر عددی → ImproperlyConfigured، نه ValueErrorِ خام."""
        with self.assertRaises(ImproperlyConfigured) as ctx:
            _resolve_database(
                {'DATABASE_URL': 'postgres://u:p@localhost/db?conn_max_age=hour'}
            )
        self.assertIn('integer', str(ctx.exception))

    def test_missing_psycopg_driver_message(self):
        """درایورِ غایب → ImproperlyConfigured با دستورِ نصبِ psycopg."""
        with self.assertRaises(ImproperlyConfigured) as ctx:
            _resolve_database(
                {'DATABASE_URL': 'postgres://u:p@localhost:5432/db'},
                import_module=_fake_import,
            )
        message = str(ctx.exception)
        self.assertIn('psycopg', message)
        self.assertIn('pip install', message)

    # ---- ۲) بوتِ واقعی با DATABASE_URL ----------------------------------------

    def test_boot_without_url_keeps_sqlite_default(self):
        """بدونِ متغیر: بوتِ سالم روی همانِ SQLiteِ توسعه (رفتارِ قبل)."""
        code = (
            'import django; django.setup(); from django.conf import settings; '
            "assert settings.DATABASES['default']['ENGINE'] "
            "== 'django.db.backends.sqlite3', 'ENGINE'; "
            "assert str(settings.DATABASES['default']['NAME']).endswith"
            "('db.sqlite3'), 'NAME'; "
            'print("db-default-ok")'
        )
        result = self._boot({}, code)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn('db-default-ok', result.stdout)

    def test_boot_postgres_without_psycopg_refuses_to_boot(self):
        """نبودِ درایور: بوت با ImproperlyConfiguredِ psycopg متوقف می‌شود."""
        with tempfile.TemporaryDirectory() as tmp:
            # ماژولِ سایه: import psycopg درونِ همین مفسر با خطا می‌شکند و
            # جلوتر از site-packages واقعی پیدا می‌شود (PYTHONPATH اولویت دارد).
            (Path(tmp) / 'psycopg.py').write_text(
                'raise ImportError("simulated: psycopg is not installed")\n',
                encoding='utf-8',
            )
            result = self._boot(
                {'DATABASE_URL': 'postgres://u:p@localhost:5432/db'},
                'import django; django.setup()',
                extra_pythonpath=tmp,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('psycopg', result.stderr)
        self.assertIn('pip install', result.stderr)

    @unittest.skipUnless(_HAS_PSYCOPG, 'psycopg نصب نیست (pip install -r requirements.txt)')
    def test_boot_postgres_url_resolves_engine(self):
        """بوتِ سالم با URL کامل: مقادیرِ PostgreSQL دقیقاً از URL می‌آیند."""
        code = (
            'import django; django.setup(); from django.conf import settings; '
            "db = settings.DATABASES['default']; "
            "assert db['ENGINE'] == 'django.db.backends.postgresql', 'ENGINE'; "
            "assert db['USER'] == 'study', 'USER'; "
            "assert db['PASSWORD'] == 'p@ss', 'PASSWORD'; "
            "assert db['HOST'] == 'db.example.com', 'HOST'; "
            "assert db['PORT'] == '5433', 'PORT'; "
            "assert db['NAME'] == 'plannerdb', 'NAME'; "
            "assert db['CONN_MAX_AGE'] == 45, 'CONN'; "
            'print("pg-resolve-ok")'
        )
        result = self._boot(
            {'DATABASE_URL': (
                'postgres://study:p%40ss@db.example.com:5433/plannerdb'
                '?conn_max_age=45'
            )},
            code,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn('pg-resolve-ok', result.stdout)

    def test_boot_prod_mode_on_sqlite_prints_warning(self):
        """DEBUG=false بدونِ DATABASE_URL: هشدارِ SQLite روی stderr، بوتِ سالم."""
        key = 'p' * 64
        result = self._boot(
            {'DJANGO_DEBUG': 'false', 'DJANGO_SECRET_KEY': key,
             'DJANGO_ALLOWED_HOSTS': 'example.com'},
            'import django; django.setup(); print("prod-sqlite-ok")',
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn('prod-sqlite-ok', result.stdout)
        self.assertIn('SQLite', result.stderr)          # هشدارِ یک‌خطی


# ---------------------------------------------------------------------------
# ۱۶) قفلِ FOR UPDATE — فقط وقتی موتورِ فعال PostgreSQL است
# (در SQLite قفلِ FOR UPDATE به SQL ترجمه نمی‌شود — تستِ اسپایِ
# StudyLogConcurrencyLockTests همان‌جا رفتار را پوشش می‌دهد)
# ---------------------------------------------------------------------------

@unittest.skipUnless(
    connection.vendor == 'postgresql',
    'FOR UPDATE فقط در SQLِ PostgreSQL دیده می‌شود؛'
    ' در SQLite این تست skip می‌شود (پوششِ رفتاری در کلاس‌های قبل است).',
)
class PostgresForUpdateTests(TransactionTestCase):
    """
    رگرسیونِ موتور: رویِ PostgreSQL، عبارتِ select_for_update باید واقعاً
    «FOR UPDATE» در SQL تولید کند — همان قفلی که Lost Update را در
    چندکاربره بسته می‌کند (ادغامِ منطقیِ Taskهای ۲۴ و ۲۵).
    """

    def test_lock_emits_for_update_sql(self):
        user = User.objects.create_user(username='dave', password='pw-12345678')
        subject = Subject.objects.create(user=user, name='زیست', difficulty=3)
        exam = Exam.objects.create(
            subject=subject,
            exam_date=date.today() + timedelta(days=10),
            study_hours_remaining=5,
            chapters_remaining=3,
        )

        with transaction.atomic():          # select_for_update فقط داخلِ تراکنش
            with CaptureQueriesContext(connection) as ctx:
                Exam.objects.select_for_update().get(pk=exam.pk)

        self.assertTrue(
            any('FOR UPDATE' in q['sql'] for q in ctx.captured_queries),
            msg=[q['sql'] for q in ctx.captured_queries],
        )


# ---------------------------------------------------------------------------
# ۱۲) چندزبانی (i18n) — مذاکره‌ی Accept-Language + کاتالوگِ en (2026-09-09)
# ---------------------------------------------------------------------------

class I18nAcceptLanguageTests(BaseAPITestCase):
    """
    پیام‌هایِ API با زبانِ فعالِ درخواست ترجمه می‌شوند:

    - بدونِ هدرِ Accept-Language → پیش‌فرضِ fa → همان متنِ فارسیِ اصلی
      (رفتارِ دقیقاً همانِ قبل از چندزبانی‌شدن).
    - Accept-Language: en → ترجمه‌ی انگلیسی از کاتالوگِ locale/en.
    - زبانِ پشتیبانی‌نشده → fallback به fa.

    مبنایِ کار: LocaleMiddleware + gettext در views/serializers/utils و
    هدری که app.js برایِ هر درخواست می‌فرستد (Accept-Language).
    """

    LOGIN = '/api/auth/login/'

    def _login_error(self, client=None, **headers):
        """ورودِ ناموفق با هدرهایِ دلخواه؛ متنِ خطا را برمی‌گرداند."""
        response = (client or self.client).post(
            self.LOGIN,
            {'username': 'alice', 'password': 'wrong-pass'},
            format='json',
            **headers,
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        return response.json()['error']

    def test_no_header_keeps_persian_default(self):
        """بدونِ Accept-Language: پیامِ خطا همانِ متنِ فارسیِ اصلی است (پیش‌فرضِ fa)."""
        self.assertEqual(self._login_error(), 'نام کاربری یا رمز عبور اشتباه است')

    def test_english_header_translates_error(self):
        """Accept-Language: en → ترجمه‌ی انگلیسی از کاتالوگِ پروژه."""
        self.assertEqual(
            self._login_error(HTTP_ACCEPT_LANGUAGE='en'),
            'Incorrect username or password.',
        )

    def test_persian_header_keeps_original(self):
        """Accept-Language: fa → متنِ اصلی (fa کاتالوگی در پروژه ندارد)."""
        self.assertEqual(
            self._login_error(HTTP_ACCEPT_LANGUAGE='fa'),
            'نام کاربری یا رمز عبور اشتباه است',
        )

    def test_unsupported_language_falls_back_to_default(self):
        """زبانِ پشتیبانی‌نشده (de) → fallback به fa → متنِ فارسی."""
        self.assertEqual(
            self._login_error(HTTP_ACCEPT_LANGUAGE='de'),
            'نام کاربری یا رمز عبور اشتباه است',
        )

    def test_realistic_browser_header_selects_english(self):
        """هدرِ واقعیِ مرورگر (en-US,en;q=0.9,fa;q=0.8) → en انتخاب می‌شود."""
        self.assertEqual(
            self._login_error(HTTP_ACCEPT_LANGUAGE='en-US,en;q=0.9,fa;q=0.8'),
            'Incorrect username or password.',
        )

    def test_english_duplicate_subject_message(self):
        """پیامِ اعتبارسنجیِ سریالایزر (gettext_lazy) هم با en ترجمه می‌شود."""
        self.create_subject(self.alice, 'ریاضی')
        response = self.client_as(self.alice).post(
            '/api/subjects/', {'name': 'ریاضی', 'difficulty': 3}, format='json',
            HTTP_ACCEPT_LANGUAGE='en',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body_text = json.dumps(response.json(), ensure_ascii=False)
        self.assertIn('You have already registered a subject with this name.', body_text)
        self.assertNotIn('شما قبلاً', body_text)

    def test_english_generate_validation_errors(self):
        """خطاهایِ generate با en: هم «الزامی» هم «بازه‌ی ۰ تا ۲۴»."""
        client = self.client_as(self.alice)
        missing = client.post(
            '/api/study-plan/generate/', {}, format='json', HTTP_ACCEPT_LANGUAGE='en',
        )
        self.assertEqual(missing.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(missing.json()['error'], 'Daily study hours is required.')

        bad = client.post(
            '/api/study-plan/generate/',
            {'daily_available_hours': 30},
            format='json',
            HTTP_ACCEPT_LANGUAGE='en',
        )
        self.assertEqual(bad.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(bad.json()['error'], 'Study hours must be a number between 0 and 24.')

    def test_english_plan_title_and_badge(self):
        """خروجیِ برنامه با en: عنوانِ «Today - تاریخ» و نشانِ «N hours» (interpolation)."""
        subject = self.create_subject(self.alice, 'ریاضی')
        self.create_exam(subject, days_ahead=3, hours=6)

        body = self.client_as(self.alice).get(
            '/api/study-plan/', HTTP_ACCEPT_LANGUAGE='en'
        ).json()
        self.assertNotEqual(body['schedule'], [])
        first = body['schedule'][0]
        self.assertTrue(first['title'].startswith('Today - '), first['title'])
        self.assertTrue(first['hours_badge'].endswith(' hours'), first['hours_badge'])

    def test_english_dashboard_alert(self):
        """هشدارِ danger داشبورد با en: جمله‌ی کاملِ ترجمه‌شده با پارامترها."""
        subject = self.create_subject(self.alice, 'ریاضی')
        self.create_exam(subject, days_ahead=2, hours=8)

        body = self.client_as(self.alice).get(
            '/api/dashboard/', HTTP_ACCEPT_LANGUAGE='en'
        ).json()
        danger = [a for a in body['alerts'] if a['type'] == 'danger']
        self.assertTrue(danger)
        self.assertTrue(danger[0]['message'].startswith('Only 2 days left'), danger[0]['message'])
        self.assertIn('hours of study remaining', danger[0]['message'])
        # نامِ درس «داده» است نه رشته‌ی رابط — ترجمه نمی‌شود
        self.assertIn('ریاضی', danger[0]['message'])


class I18nCatalogIntegrityTests(SimpleTestCase):
    """
    سلامتِ کاتالوگِ locale/en و تنظیماتِ چندزبانی:

    - فایلِ django.mo موجود است و gettext پایتونی (همان مسیرِ جنگو) می‌خواندش
      — رگرسیونِ کامپایل: ترجمه‌ها نباید «خودِ کلید» باشند (باگِ msgstr==msgid).
    - همه‌ی ورودی‌هایِ .po ترجمه‌ی غیرخالیِ متفاوت از کلید دارند.
    - کلیدِ ناموجود → همانِ متنِ اصلی (fallback).
    - WEEKDAY_FA با gettext_lazy تا زمانِ رندر ترجمه‌نشده می‌ماند.
    - تنظیمات: fa پیش‌فرض، fa/en پشتیبانی‌شده، LOCALE_PATHS، ترتیبِ LocaleMiddleware.
    """

    LOCALE_DIR = BASE_DIR / 'locale'
    PO_FILE = LOCALE_DIR / 'en' / 'LC_MESSAGES' / 'django.po'
    MO_FILE = LOCALE_DIR / 'en' / 'LC_MESSAGES' / 'django.mo'

    def _load_catalog(self):
        """کاتالوگ را با gettext پایتونی می‌خواند (دقیقاً مثل جنگو)."""
        import gettext as pygettext
        return pygettext.translation('django', localedir=str(self.LOCALE_DIR), languages=['en'])

    def test_mo_file_exists_and_loads(self):
        """django.mo در ریپو هست (msgfmt روی ویندوز لازم نیست) و خوانا است."""
        self.assertTrue(self.MO_FILE.exists(), 'django.mo باید commit شده باشد')
        tr = self._load_catalog()
        self.assertEqual(
            tr.gettext('نام کاربری یا رمز عبور اشتباه است'), 'Incorrect username or password.',
        )

    def test_po_entries_all_have_distinct_translations(self):
        """رگرسیونِ کامپایل: هیچ ورودیِ .po ترجمه‌ی خالی یا «برابرِ کلید» ندارد."""
        entries = []
        msgid = msgstr = None
        for line in self.PO_FILE.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if line.startswith('msgid '):
                if msgid is not None:
                    entries.append((msgid, msgstr))
                msgid, msgstr = line[6:].strip().strip('"'), ''
            elif line.startswith('msgstr '):
                msgstr = line[7:].strip().strip('"')
        if msgid is not None:
            entries.append((msgid, msgstr))

        real = [(k, v) for k, v in entries if k]  # هدر (msgid خالی) کنار می‌رود
        self.assertGreaterEqual(len(real), 25)
        for key, value in real:
            self.assertTrue(value, f'msgstr خالی برای: {key[:50]}')
            self.assertNotEqual(key, value, f'ترجمه همانِ کلید است: {key[:50]}')

    def test_unknown_key_falls_back_to_original(self):
        """کلیدِ خارج از کاتالوگ → همانِ متن (سپرِ gettext)."""
        tr = self._load_catalog()
        self.assertEqual(tr.gettext('کلیدی که در کاتالوگ نیست'), 'کلیدی که در کاتالوگ نیست')

    def test_weekday_fa_is_lazily_translated(self):
        """WEEKDAY_FA تا زمانِ رندر ترجمه‌نشده می‌ماند و با زبانِ فعال عوض می‌شود."""
        from django.utils import translation
        from planner.utils import WEEKDAY_FA
        try:
            translation.activate('en')
            self.assertEqual(str(WEEKDAY_FA[0]), 'Monday')
            translation.activate('fa')
            self.assertEqual(str(WEEKDAY_FA[0]), 'دوشنبه')
        finally:
            translation.deactivate()

    def test_language_settings_shape(self):
        """fa پیش‌فرض؛ fa+en پشتیبانی‌شده؛ LOCALE_PATHS به backend/locale اشاره می‌کند."""
        from django.conf import settings
        self.assertEqual(settings.LANGUAGE_CODE, 'fa')
        self.assertEqual({code for code, _ in settings.LANGUAGES}, {'fa', 'en'})
        self.assertEqual(list(settings.LOCALE_PATHS), [BASE_DIR / 'locale'])

    def test_locale_middleware_position(self):
        """LocaleMiddleware بعد از SessionMiddleware و قبل از CommonMiddleware است
        (ترتیبِ لازمِ مستندِ جنگو)."""
        from django.conf import settings
        mw = list(settings.MIDDLEWARE)
        session = mw.index('django.contrib.sessions.middleware.SessionMiddleware')
        locale_mw = mw.index('django.middleware.locale.LocaleMiddleware')
        common = mw.index('django.middleware.common.CommonMiddleware')
        self.assertLess(session, locale_mw)
        self.assertLess(locale_mw, common)


# ---------------------------------------------------------------------------
# ۱۸) مؤلفه‌ی یادگیریِ آماری — ریاضیاتِ خالصِ مدل (planner/ml.py)
# ---------------------------------------------------------------------------

class MLCalibrationMathTests(SimpleTestCase):
    """
    تستِ واحدِ توابعِ خالصِ planner/ml.py — بدونِ دیتابیس، بدونِ ORM؛
    فقط ریاضیاتِ «کالیبراسیونِ تخمینِ ساعتیِ کاربر»:

    - رگرسیونِ کمینه‌ی مربعاتِ از مبدأ: β = Σxy / Σx² (خالی، دقیق)
    - انقباضِ بیزی به‌سمتِ ۱ (PRIOR_STRENGTH نمونه‌ی فرضیِ خنثی)
    - مهارِ نهاییِ β در بازه‌ی [FACTOR_MIN, FACTOR_MAX]
    - برچسبِ سوگیری، سنجشِ ریسک و اعمالِ β در پیش‌بینی
    """

    def test_exact_least_squares_slope_and_shrinkage(self):
        """β خامِ LSQ از مبدأ + انقباض — اعدادِ دستیِ قابل‌ردیابی.

        نمونه‌ها: (2,3), (4,5), (6,9) → Σxy=80 و Σx²=56 → β=1.4286؛
        با n=3 و پیشینِ ۴: β_eff = (3×1.4286 + 4) / 7 = 1.1837؛
        اعتماد = 3/7 = 0.4286.
        """
        model = fit_calibration_model([
            {'planned': 2, 'actual': 3},
            {'planned': 4, 'actual': 5},
            {'planned': 6, 'actual': 9},
        ])
        self.assertEqual(model['status'], 'ok')
        self.assertAlmostEqual(model['raw_factor'], 80 / 56, places=4)
        self.assertAlmostEqual(model['calibration_factor'], (3 * (80 / 56) + 4) / 7, places=4)
        self.assertAlmostEqual(model['confidence'], 3 / 7, places=4)
        self.assertEqual(model['sample_count'], 3)

    def test_empty_samples_trust_manual_estimate(self):
        """بدونِ تاریخچه: مدلِ «بی‌طرف» — β=۱ یعنی تخمینِ دستی بدونِ تغییر."""
        model = fit_calibration_model([])
        self.assertEqual(model['status'], 'no_history')
        self.assertIsNone(model['raw_factor'])
        self.assertEqual(model['calibration_factor'], 1.0)
        self.assertEqual(model['sample_count'], 0)
        self.assertEqual(model['confidence'], 0.0)
        self.assertEqual(model['bias'], 'unknown')

    def test_invalid_planned_samples_are_ignored(self):
        """نمونه‌هایِ planned نامعتبر (۰) کنار می‌روند ولی نمونه‌ی معتبر می‌ماند.

        (0,5) و (0,3) هیچ اطلاعاتی درباره‌ی «نسبتِ واقعیت به تخمین» نمی‌دهند؛
        (4,6) باید به‌تنهایی مدل را بسازد: β=1.5 → β_eff=(1×1.5+4)/5=1.1
        """
        model = fit_calibration_model([
            {'planned': 0, 'actual': 5},
            {'planned': 0, 'actual': 3},
            {'planned': 4, 'actual': 6},
        ])
        self.assertEqual(model['status'], 'ok')
        self.assertEqual(model['sample_count'], 1)
        self.assertAlmostEqual(model['raw_factor'], 1.5, places=4)
        self.assertAlmostEqual(model['calibration_factor'], 1.1, places=4)

    def test_shrinkage_damps_small_sample_extremes(self):
        """یک نمونه‌ی افراطی (β خام=۱۰) نباید مدل را افراطی کند.

        n=1 و پیشینِ ۴ → β_eff = (10+4)/5 = 2.8 — دامپ‌شده ولی جهتِ سوگیری
        حفظ شده (کاربر دست‌کم می‌گیرد).
        """
        model = fit_calibration_model([{'planned': 1, 'actual': 10}])
        self.assertEqual(model['status'], 'ok')
        self.assertAlmostEqual(model['raw_factor'], 10.0, places=4)
        self.assertAlmostEqual(model['calibration_factor'], 2.8, places=4)
        self.assertAlmostEqual(model['confidence'], 0.2, places=4)
        self.assertEqual(model['bias'], 'underestimates')
        self.assertLess(model['calibration_factor'], model['raw_factor'])

    def test_clamping_upper_bound(self):
        """داده‌ی خراب/آزمایشی (۱۰ نمونه‌ی β=۱۰۰) → مهار در سقفِ FACTOR_MAX."""
        samples = [{'planned': 1, 'actual': 100}] * 10
        model = fit_calibration_model(samples)
        self.assertAlmostEqual(model['raw_factor'], 100.0, places=4)
        self.assertEqual(model['calibration_factor'], FACTOR_MAX)

    def test_clamping_lower_bound(self):
        """بیست نمونه‌ی «هیچ مطالعه‌ای نشد» (β خام=۰) → مهار در کفِ FACTOR_MIN."""
        samples = [{'planned': 10, 'actual': 0}] * 20
        model = fit_calibration_model(samples)
        self.assertAlmostEqual(model['raw_factor'], 0.0, places=4)
        self.assertEqual(model['calibration_factor'], FACTOR_MIN)

    def test_bias_classification_thresholds(self):
        """برچسبِ سوگیری با تلورانسِ ±۱۵٪: دقیق / دست‌کم‌گیر / زیادرو."""
        self.assertEqual(classify_bias(1.2), 'underestimates')
        self.assertEqual(classify_bias(0.8), 'overestimates')
        self.assertEqual(classify_bias(1.07), 'accurate')
        self.assertEqual(classify_bias(0.9), 'accurate')
        self.assertEqual(classify_bias(None), 'unknown')
        # مرزهای دقیقِ تلورانس (تستِ ثابت‌ها برای جلوگیری از تغییرِ ناخواسته)
        self.assertEqual(classify_bias(1 + BIAS_TOLERANCE + 0.001), 'underestimates')
        self.assertEqual(classify_bias(1 - BIAS_TOLERANCE - 0.001), 'overestimates')

    def test_assess_risk_thresholds(self):
        """ریسک نسبتِ نیازِ روزانه به ساعتِ آزادِ روزانه (با مرزها)."""
        # نیاز روزانه = 10/5 = 2.0 == کلِ ساعتِ آزاد → حتی ۱۰۰٪ وقت کافی نیست
        self.assertEqual(assess_exam_risk(10.0, 5, 2.0)['risk'], 'high')
        # 8/5 = 1.6 → بینِ ۷۵٪ (1.5) و ۱۰۰٪ (2.0) → تنگ
        self.assertEqual(assess_exam_risk(8.0, 5, 2.0)['risk'], 'medium')
        # 5/5 = 1.0 → راحت
        self.assertEqual(assess_exam_risk(5.0, 5, 2.0)['risk'], 'low')
        # امتحانِ امروز (days_left=0): برای ریاضیات یک روز فرض می‌شود
        result = assess_exam_risk(10.0, 0, 5.0)
        self.assertEqual(result['risk'], 'high')
        self.assertEqual(result['required_daily_hours'], 10.0)
        # بدونِ ساعتِ پیش‌بینی‌شده → خطا/ریسکی نیست
        self.assertEqual(assess_exam_risk(0.0, 5, 2.0), {'risk': 'low', 'required_daily_hours': 0.0})
        # گردشدنِ نیازِ روزانه به دو رقمِ اعشار
        self.assertEqual(assess_exam_risk(10.0, 3, 10.0)['required_daily_hours'], 3.33)

    def test_predict_hours_applies_calibration(self):
        """پیش‌بینی = β نهایی × ساعتِ اعلام‌شده (گرد به یک رقمِ اعشار).

        دو نمونه‌ی (4,8): β=2 خام → β_eff=4/3 → predict(6) = 8.0؛
        و مدلِ بی‌تاریخچه همان مقدارِ اعلام‌شده را برمی‌گرداند (β=1).
        """
        learned = fit_calibration_model([
            {'planned': 4, 'actual': 8},
            {'planned': 4, 'actual': 8},
        ])
        self.assertAlmostEqual(learned['calibration_factor'], 4 / 3, places=4)
        self.assertEqual(predict_hours(learned, 6.0), 8.0)

        neutral = fit_calibration_model([])
        self.assertEqual(predict_hours(neutral, 6.0), 6.0)


# ---------------------------------------------------------------------------
# ۱۹) مؤلفه‌ی ML — ساختِ نمونه‌هایِ آموزشی از تاریخچه‌ی StudyLog
# ---------------------------------------------------------------------------

class MLTrainingDataTests(BaseAPITestCase):
    """
    آزمونِ «استخراجِ داده» — پلِ بینِ ORM و مدلِ خالص:

    - فقط امتحان‌هایِ «تمام‌شده» (تاریخِ گذشته + حداقل یک گزارش) نمونه می‌شوند
    - planned = باقی‌مانده‌ی فعلی + جمعِ hours_deducted (بازسازیِ تخمینِ اولیه)
    - actual = جمعِ hours_studied (مطالعه‌ی فراتر از طرح = سیگنالِ دست‌کم‌گیری)
    - مرزِ «امروز»: در آموزش نیست (جلوگیری از نشتِ آینده) ولی در پیش‌بینی هست
    - جداسازیِ کاربران
    """

    def test_only_past_exams_with_logs_become_samples(self):
        """امتحانِ آینده (حتی با گزارش) و امتحانِ گذشتهِ بی‌گزارش، آموزش نیستند."""
        subject = self.create_subject(self.alice, 'ریاضی')
        # گذشته + گزارش → نمونه می‌شود
        past = self.create_exam(subject, days_ahead=-10, hours=10)
        StudyLog.objects.create(user=self.alice, exam=past, hours_studied=2.5)
        # آینده + گزارش → نباید در آموزش باشد (داده‌ی آینده به گذشته نشت نکند)
        future = self.create_exam(subject, days_ahead=10, hours=10)
        StudyLog.objects.create(user=self.alice, exam=future, hours_studied=3)
        # گذشته بدونِ گزارش → چیزی برای یادگیری ندارد
        self.create_exam(subject, days_ahead=-15, hours=8)

        samples = build_training_samples(self.alice)
        self.assertEqual(len(samples), 1)
        self.assertEqual(samples[0], {'planned': 10.0, 'actual': 2.5})

    def test_planned_is_reconstructed_from_deductions(self):
        """بازسازیِ تخمینِ اولیه: باقی‌مانده + جمعِ کسرشده‌ها.

        امتحانِ ۱۰ ساعته + دو گزارشِ ۲ و ۳ ساعته → باقی‌مانده ۵، کسرشده ۵ →
        planned=10 (همان تخمینِ اولیه) و actual=5.
        """
        subject = self.create_subject(self.alice, 'فیزیک')
        exam = self.create_exam(subject, days_ahead=-10, hours=10)
        StudyLog.objects.create(user=self.alice, exam=exam, hours_studied=2)
        StudyLog.objects.create(user=self.alice, exam=exam, hours_studied=3)

        exam.refresh_from_db()
        self.assertEqual(exam.study_hours_remaining, 5)  # کسرِ خودکار در save()

        samples = build_training_samples(self.alice)
        self.assertEqual(samples, [{'planned': 10.0, 'actual': 5.0}])

    def test_zero_planned_exam_is_skipped(self):
        """امتحانی که از اول ۰ ساعتِ باقی‌مانده داشت، چیزی به کالیبراسیون نمی‌گوید
        (کسر هم از صفر اتفاق نیفتاده — planned بازسازی‌شده صفر می‌ماند)."""
        subject = self.create_subject(self.alice, 'شیمی')
        exam = self.create_exam(subject, days_ahead=-10, hours=0)
        StudyLog.objects.create(user=self.alice, exam=exam, hours_studied=3)

        samples = build_training_samples(self.alice)
        self.assertEqual(samples, [])

    def test_today_is_not_past_but_counts_as_upcoming(self):
        """مرزِ «امروز»: در آموزش نیست ولی در پیش‌بینی هست (قرینه‌ی گتِ dashboard)."""
        subject = self.create_subject(self.alice, 'ادبیات')
        today_exam = self.create_exam(subject, days_ahead=0, hours=6)
        StudyLog.objects.create(user=self.alice, exam=today_exam, hours_studied=2)

        # آموزش: تاریخِ «امروز» هنوز تمام‌نشده محسوب می‌شود (strict less-than)
        self.assertEqual(build_training_samples(self.alice), [])

        # پیش‌بینی: امتحانِ امروز جزوِ آینده است؛ بدونِ تاریخچه β=۱
        # (گزارشِ ۲ ساعته‌ی بالا ۲ ساعت از ۶ ساعتِ باقی‌مانده کسر کرده → ۴)
        report = get_prediction_report(self.alice, daily_available_hours=2.0)
        self.assertEqual(len(report['predictions']), 1)
        item = report['predictions'][0]
        self.assertEqual(item['days_left'], 0)
        self.assertEqual(item['planned_hours'], 4.0)
        self.assertEqual(item['predicted_hours'], 4.0)
        # نیازِ روزانه با فرضِ «یک روزِ باقی‌مانده»: 4 ≥ 2 → ریسکِ بالا
        self.assertEqual(item['risk'], 'high')

    def test_users_are_isolated(self):
        """هر کاربر فقط از تاریخچه‌ی خودش یاد می‌گیرد (قرینه‌ی نکته‌ی ۶.۳)."""
        alice_subject = self.create_subject(self.alice, 'ریاضیِ آلیس')
        alice_past = self.create_exam(alice_subject, days_ahead=-10, hours=10)
        StudyLog.objects.create(user=self.alice, exam=alice_past, hours_studied=2.5)

        bob_subject = self.create_subject(self.bob, 'ریاضیِ باب')
        bob_past = self.create_exam(bob_subject, days_ahead=-10, hours=4)
        StudyLog.objects.create(user=self.bob, exam=bob_past, hours_studied=8)

        self.assertEqual(build_training_samples(self.alice), [{'planned': 10.0, 'actual': 2.5}])
        self.assertEqual(build_training_samples(self.bob), [{'planned': 4.0, 'actual': 8.0}])


# ---------------------------------------------------------------------------
# ۲۰) مؤلفه‌ی ML — GET /api/predictions/
# ---------------------------------------------------------------------------

class MLPredictionsAPITests(BaseAPITestCase):
    """
    رفتارِ endpointِ پیش‌بینی در سطحِ HTTP:

    - فقط با احرازِ هویت (نکته‌ی ۶.۳: داده‌ی هر کاربر فقط مالِ خودش)
    - کاربرِ تازه‌بی‌خبر: β=۱ (تخمینِ دستی بی‌طرفانه) + ریسکِ حساب‌شده
    - تاریخچه‌ی دست‌کم‌گیر: β>۱ → پیش‌بینیِ بزرگ‌تر از تخمینِ دستی
    - فقط امتحان‌هایِ آینده‌ی «فعال» (ساعتِ باقی‌مانده > 0)، مرتب با تاریخ
    - سطح‌هایِ ریسک نسبت به ساعتِ آزادِ روزانه‌ی همان کاربر (StudyPlan)
    """

    def test_authentication_required(self):
        """بدونِ توکن: 401 — مثلِ بقیه‌ی endpointهایِ محافظت‌شده."""
        response = APIClient().get('/api/predictions/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_fresh_user_trusts_manual_estimate(self):
        """کاربرِ بدونِ تاریخچه: status=no_history و β=۱؛ ریسک از تخمینِ خام."""
        subject = self.create_subject(self.alice, 'ریاضی')
        self.create_exam(subject, days_ahead=10, hours=5)

        response = self.client_as(self.alice).get('/api/predictions/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        body = response.json()
        self.assertEqual(body['model']['status'], 'no_history')
        self.assertEqual(body['model']['calibration_factor'], 1.0)
        self.assertEqual(body['model']['sample_count'], 0)
        self.assertEqual(body['model']['bias'], 'unknown')

        self.assertEqual(len(body['predictions']), 1)
        item = body['predictions'][0]
        self.assertEqual(item['subject'], 'ریاضی')
        self.assertEqual(item['days_left'], 10)
        self.assertEqual(item['planned_hours'], 5.0)
        self.assertEqual(item['predicted_hours'], 5.0)
        # 5 ساعت در 10 روز = 0.5 ساعتِ روزانه؛ پیش‌فرضِ ساعتِ آزاد = 2 → کم‌خطر
        self.assertEqual(item['required_daily_hours'], 0.5)
        self.assertEqual(item['risk'], 'low')

        self.assertEqual(body['summary']['exam_count'], 1)
        self.assertEqual(body['summary']['low_risk'], 1)
        self.assertEqual(body['summary']['total_predicted_hours'], 5.0)

    def test_calibration_changes_future_prediction(self):
        """تاریخچه‌ی «دست‌کم‌گیری» → β>۱ → ساعتِ پیش‌بینی‌شده بزرگ‌تر از تخمین.

        دو امتحانِ گذشته‌ی ۴ ساعته که هرکدام ۸ ساعت مطالعه خورته‌اند →
        β خام=2 و با انقباض β_eff=4/3 → برای امتحانِ آینده‌ی ۶ ساعته:
        6×4/3 = 8 ساعتِ واقعی.
        """
        subject = self.create_subject(self.alice, 'زیست')
        for _ in range(2):
            past = self.create_exam(subject, days_ahead=-20, hours=4)
            StudyLog.objects.create(user=self.alice, exam=past, hours_studied=8)

        future = self.create_exam(subject, days_ahead=9, hours=6)

        response = self.client_as(self.alice).get('/api/predictions/')
        body = response.json()

        self.assertEqual(body['model']['status'], 'ok')
        self.assertEqual(body['model']['sample_count'], 2)
        self.assertAlmostEqual(body['model']['calibration_factor'], 1.33, places=2)
        self.assertEqual(body['model']['bias'], 'underestimates')
        self.assertAlmostEqual(body['model']['confidence'], 0.33, places=2)

        item = body['predictions'][0]
        self.assertEqual(item['exam_id'], future.pk)
        self.assertEqual(item['planned_hours'], 6.0)
        self.assertEqual(item['predicted_hours'], 8.0)  # 6 × 4/3
        self.assertNotEqual(item['predicted_hours'], item['planned_hours'])

    def test_predictions_only_include_active_upcoming_exams(self):
        """امتحانِ گذشته و امتحانِ تمام‌شده (۰ ساعتِ باقی‌مانده) پیش‌بینی نمی‌شوند؛
        بقیه مرتب با نزدیک‌ترین تاریخ می‌آیند و شکلِ آیتم‌ها ثابت است."""
        subject = self.create_subject(self.alice, 'شیمی')
        # گذشته → فقط مالِ آموزش است
        past = self.create_exam(subject, days_ahead=-5, hours=10)
        StudyLog.objects.create(user=self.alice, exam=past, hours_studied=2)
        # آینده ولی تمام‌شده → هیچ ساعتی برای پیش‌بینی ندارد
        self.create_exam(subject, days_ahead=15, hours=0)
        # دو امتحانِ آینده‌ی فعال
        near = self.create_exam(subject, days_ahead=3, hours=5)
        far = self.create_exam(subject, days_ahead=8, hours=5)

        response = self.client_as(self.alice).get('/api/predictions/')
        body = response.json()

        self.assertEqual(len(body['predictions']), 2)
        self.assertEqual(body['predictions'][0]['exam_id'], near.pk)
        self.assertEqual(body['predictions'][1]['exam_id'], far.pk)
        # شکلِ ثابتِ هر آیتم (قرارداد با فرانت‌اند — مثلِ dashboard)
        for item in body['predictions']:
            self.assertEqual(
                set(item.keys()),
                {'exam_id', 'subject', 'exam_date', 'days_left', 'planned_hours',
                 'predicted_hours', 'required_daily_hours', 'risk'},
            )

    def test_risk_levels_from_daily_available_hours(self):
        """سه سطحِ ریسک با ساعتِ آزادِ پیش‌فرضِ ۲ (ساختِ خودکارِ تنظیمات).

        نیازِ روزانه: 10/5=2.0 ≥ 2 → بالا؛ 8/5=1.6 → متوسط؛ 5/5=1.0 → کم.
        """
        subject = self.create_subject(self.alice, 'حسابان')
        self.create_exam(subject, days_ahead=5, hours=10)  # required = 2.0
        self.create_exam(subject, days_ahead=5, hours=8)   # required = 1.6
        self.create_exam(subject, days_ahead=5, hours=5)   # required = 1.0

        response = self.client_as(self.alice).get('/api/predictions/')
        body = response.json()

        risks = [item['risk'] for item in body['predictions']]
        self.assertEqual(risks, ['high', 'medium', 'low'])
        self.assertEqual(body['summary']['high_risk'], 1)
        self.assertEqual(body['summary']['medium_risk'], 1)
        self.assertEqual(body['summary']['low_risk'], 1)

    def test_daily_hours_setting_changes_risk(self):
        """همان امتحان با ساعتِ آزادِ ۵ (تنظیمِ خودِ کاربر) کم‌خطر می‌شود —
        ریسک به «ظرفیتِ اعلام‌شده‌ی» کاربر حساس است، نه عددِ ثابتِ سرور."""
        subject = self.create_subject(self.alice, 'فلسفه')
        self.create_exam(subject, days_ahead=5, hours=10)  # نیازِ روزانه = 2.0

        # بدونِ تنظیمات: نخستین فراخوانی، تنظیمات را با پیش‌فرضِ ۲ ساعت
        # می‌سازد (همان الگوی dashboard) → نیازِ روزانه‌ی 2.0 ≥ 2 → ریسکِ بالا
        body_default = self.client_as(self.alice).get('/api/predictions/').json()
        self.assertEqual(body_default['predictions'][0]['risk'], 'high')
        self.assertEqual(StudyPlan.objects.get(user=self.alice).daily_available_hours, 2.0)

        # با تنظیمِ ۵ ساعت: 2.0 < 0.75×5=3.75 → ریسکِ کم (ویرایشِ همان رکوردِ
        # خودکار — قیدِ UNIQUEِ 0008 اجازه‌ی رکوردِ دوم نمی‌دهد)
        plan = StudyPlan.objects.get(user=self.alice)
        plan.daily_available_hours = 5.0
        plan.save()
        body_custom = self.client_as(self.alice).get('/api/predictions/').json()
        self.assertEqual(body_custom['predictions'][0]['risk'], 'low')

    def test_history_is_per_user_not_shared(self):
        """تاریخچه‌ی آلیس مدلِ باب را رنگ نمی‌کند (آموزشِ کاربر-محور)."""
        alice_subject = self.create_subject(self.alice, 'آمار')
        for _ in range(2):
            past = self.create_exam(alice_subject, days_ahead=-20, hours=4)
            StudyLog.objects.create(user=self.alice, exam=past, hours_studied=8)

        bob_subject = self.create_subject(self.bob, 'مبانی')
        self.create_exam(bob_subject, days_ahead=7, hours=6)

        alice_body = self.client_as(self.alice).get('/api/predictions/').json()
        bob_body = self.client_as(self.bob).get('/api/predictions/').json()

        self.assertEqual(alice_body['model']['status'], 'ok')
        self.assertEqual(alice_body['model']['sample_count'], 2)

        # باب: بدونِ تاریخچه → بی‌طرف؛ پیش‌بینی‌اش فقط امتحانِ خودش است
        self.assertEqual(bob_body['model']['status'], 'no_history')
        self.assertEqual(bob_body['model']['calibration_factor'], 1.0)
        self.assertEqual(len(bob_body['predictions']), 1)
        self.assertEqual(bob_body['predictions'][0]['subject'], 'مبانی')
        self.assertEqual(bob_body['predictions'][0]['predicted_hours'], 6.0)


# ---------------------------------------------------------------------------
# پایشِ سلامت: GET /api/health/ (از 2026-09-10 — آمادگیِ استقرار)
# ---------------------------------------------------------------------------

class HealthEndpointTests(BaseAPITestCase):
    """endpoint عمومیِ سلامت — بدونِ لاگین، ماشین‌خوان و معاف از throttle.

    طراحی (وفادار به نکته‌ی ۶.۱۴ AI_CONTEXT): پاسخ عمداً gettext ندارد تا
    کاتالوگِ locale/en دست‌نخورده بماند؛ متنِ نمایشی لازم نیست چون مخاطبِ
    این مسیر مانیتورینگ/Load Balancer است، نه کاربرِ انسانی.
    """

    def test_health_is_public_and_ok(self):
        """بدونِ هیچ هدرِ احرازِ هویت: 200 + status=ok + database=ok."""
        resp = self.client.get('/api/health/')
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body['status'], 'ok')
        self.assertEqual(body['database'], 'ok')

    def test_health_payload_is_machine_readable(self):
        """دقیقاً همین چهار کلید — نه بیشتر (رشته‌ی ترجمه‌شدنی ندارد)."""
        body = self.client.get('/api/health/').json()
        self.assertEqual(set(body.keys()), {'status', 'database', 'engine', 'debug'})

    def test_health_reports_real_engine(self):
        """engine = موتورِ فعالِ همین محیط (sqlite در توسعه؛ postgres در PG)."""
        body = self.client.get('/api/health/').json()
        self.assertEqual(body['engine'], connection.vendor)

    def test_health_reflects_current_debug_flag(self):
        """debug همانِ settings.DEBUG است (تست‌رانِ جنگو آن را False می‌کند)."""
        body = self.client.get('/api/health/').json()
        self.assertEqual(body['debug'], django_settings.DEBUG)

    def test_health_rejects_post(self):
        """فقط GET؛ متدِ دیگر = 405 (بدونِ مصرفِ شمارنده‌ی throttle)."""
        resp = self.client.post('/api/health/', {})
        self.assertEqual(resp.status_code, 405)

    def test_health_is_never_throttled(self):
        """رگرسیون: حتی با نرخِ ۱/دقیقه، health مکرر نباید ۴۲۹ بگیرد.

        مسیرِ پایش معاف است (throttle_classes=[]) تا فشارِ خودِ پایش،
        سرویسِ سالم را «بیمار» گزارش نکند.

        نکته‌ی مکانیکی: THROTTLE_RATES کلاسِ DRF در زمانِ import عکسِ فوری
        (snapshot) از تنظیمات است و override_settings آن را تازه نمی‌کند؛
        پس نرخ را مستقیماً روی خودِ کلاس patch می‌کنیم.
        """
        with patch.object(SimpleRateThrottle, 'THROTTLE_RATES',
                          {'anon': '1/min', 'user': '1/min', 'auth': '1/min'}):
            for _ in range(5):
                resp = self.client.get('/api/health/')
                self.assertEqual(resp.status_code, 200, 'health must stay available')

    def test_health_returns_503_when_db_down(self):
        """رگرسیون: خطایِ اتصالِ دیتابیس → ۵۰۳ِ ساخت‌یافته، نهِ ۵۰۰ِ خام."""
        with patch('django.db.connection.cursor', side_effect=OperationalError('db down')):
            resp = self.client.get('/api/health/')
        self.assertEqual(resp.status_code, 503)
        body = resp.json()
        self.assertEqual(body['status'], 'error')
        self.assertEqual(body['database'], 'error')
        # بقیه‌ی گزارش حتی در خرابی هم معنادار بماند
        self.assertEqual(body['engine'], connection.vendor)


# ---------------------------------------------------------------------------
# محدودسازیِ نرخِ درخواست (از 2026-09-10 — دفاعِ brute-force)
# ---------------------------------------------------------------------------

_THROTTLE_TEST_RATES = {'anon': '2/min', 'user': '2/min', 'auth': '2/min'}


# نکته‌ی مکانیکیِ مهم: SimpleRateThrottle.THROTTLE_RATES در زمانِ importِ DRF
# snapshot از تنظیمات است؛ api_settings.reload() (پاسخِ override_settings)
# آن را تازه نمی‌کند — در Production مشکلی نیست (تنظیمات فقط یک‌بار خوانده
# می‌شوند و همان snapshot معتبر است) اما در تست، نرخ‌ها را مستقیماً روی
# کلاس patch می‌کنیم تا واقعاً کوچک شوند. نگاشتِ env→setting جداگانه در
# ThrottleAndSecuritySettingsTests با «بوتِ واقعی» اثبات شده است.
@patch.object(SimpleRateThrottle, 'THROTTLE_RATES', _THROTTLE_TEST_RATES)
class ThrottlingAPITests(BaseAPITestCase):
    """رفتارِ ۴۲۹ با نرخ‌هایِ عمداً کوچک‌شده ('2/min').

    نکته‌ی جداسازی: شمارنده‌هایِ throttle در cacheِ locmem زندگی می‌کنند و
    BaseAPITestCase.tearDown کلِ cache را بعدِ هر تست پاک می‌کند؛ هر تستِ
    IP-محور هم IP مخصوصِ خودش را می‌فرستد (دفاعِ دولایه).
    """

    def _ghost_login(self, remote_addr=None):
        """login با نامِ کاربریِ ناموجود: همیشه 401 و «بدونِ هشِ رمز» (سریع)."""
        payload = {'username': 'ghost-user', 'password': 'whatever-pass'}
        if remote_addr:
            return self.client.post('/api/auth/login/', payload, format='json', REMOTE_ADDR=remote_addr)
        return self.client.post('/api/auth/login/', payload, format='json')

    def test_login_burst_gets_throttled(self):
        """سه login پشتِ‌سرِ‌هم از یک IP → سومی ۴۲۹ (اولی ۴۰۱)."""
        self.assertEqual(self._ghost_login().status_code, 401)
        self.assertEqual(self._ghost_login().status_code, 401)
        self.assertEqual(self._ghost_login().status_code, 429)

    def test_register_burst_gets_throttled(self):
        """همین سقف روی register — دو ثبت‌نامِ موفق، سومی ۴۲۹."""
        for n in (1, 2):
            resp = self.client.post(
                '/api/auth/register/',
                {'username': f'burst{n}', 'password': 'pw-12345678'},
                format='json',
            )
            self.assertEqual(resp.status_code, 201)
        resp = self.client.post(
            '/api/auth/register/',
            {'username': 'burst3', 'password': 'pw-12345678'},
            format='json',
        )
        self.assertEqual(resp.status_code, 429)

    def test_throttle_is_per_ip(self):
        """IP جدا = شمارنده‌ی جدا (کاربرهایِ مختلف پشتِ NAT/پروکسی)."""
        self._ghost_login(remote_addr='10.99.0.1')
        self._ghost_login(remote_addr='10.99.0.1')
        blocked = self._ghost_login(remote_addr='10.99.0.1')
        other = self._ghost_login(remote_addr='10.99.0.2')
        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(other.status_code, 401)   # محدودیتِ IP اول، IP دوم را قفل نکند

    def test_throttled_response_carries_retry_after(self):
        """پاسخِ ۴۲۹ باید Retry-After بدهد تا کلاینتِ مهربان منتظر بماند."""
        self._ghost_login()
        self._ghost_login()
        resp = self._ghost_login()
        self.assertEqual(resp.status_code, 429)
        self.assertIn('Retry-After', resp)
        self.assertTrue(str(resp['Retry-After']).isdigit())

    def test_user_rate_limits_data_endpoints(self):
        """نرخِ «هر کاربر» روی مسیرهایِ داده: سومین GET همان کاربر ۴۲۹."""
        client = self.client_as(self.alice)
        self.assertEqual(client.get('/api/subjects/').status_code, 200)
        self.assertEqual(client.get('/api/subjects/').status_code, 200)
        self.assertEqual(client.get('/api/subjects/').status_code, 429)

    def test_user_throttle_is_per_user(self):
        """مصرفِ آلیس سهمِ باب را نمی‌سوزاند (کلید = کاربر، نه IP)."""
        alice_client = self.client_as(self.alice)
        self.assertEqual(alice_client.get('/api/subjects/').status_code, 200)
        self.assertEqual(alice_client.get('/api/subjects/').status_code, 200)
        self.assertEqual(alice_client.get('/api/subjects/').status_code, 429)
        # باب از همان «IP» (127.0.0.1) می‌زند و آزاد است
        self.assertEqual(self.client_as(self.bob).get('/api/subjects/').status_code, 200)

    def test_unauthenticated_data_requests_are_401_not_429(self):
        """مسیرهایِ محافظت‌شده قبل از throttle با 401 رد می‌شوند و شمارنده
        scope «auth» را هم مصرف نمی‌کنند — بعد از آن‌ها login آزاد است."""
        for _ in range(3):
            resp = self.client.get('/api/subjects/')
            self.assertEqual(resp.status_code, 401)
        self.assertEqual(self._ghost_login().status_code, 401)   # نهِ 429

    def test_single_login_still_works_under_tight_rates(self):
        """ترافیکِ عادیِ یک انسان (یک login درست) زیرِ نرخِ سخت هم رد نمی‌شود."""
        resp = self.client.post(
            '/api/auth/login/',
            {'username': 'alice', 'password': 'pw-12345678'},
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn('access', resp.json())

    def test_auth_throttle_window_expires(self):
        """محدودیت موقتی است: با نرخِ '2/sec'، پس از گذرِ پنجره آزاد می‌شود."""
        with patch.object(SimpleRateThrottle, 'THROTTLE_RATES',
                          {'anon': '10000/min', 'user': '10000/min', 'auth': '2/sec'}):
            self.assertEqual(self._ghost_login().status_code, 401)
            self.assertEqual(self._ghost_login().status_code, 401)
            self.assertEqual(self._ghost_login().status_code, 429)
            time.sleep(1.3)                     # پنجره‌ی ۱ ثانیه‌ای بگذرد
            self.assertEqual(self._ghost_login().status_code, 401)


class ThrottleDevSafeDefaultsTests(BaseAPITestCase):
    """رگرسیونِ ۶.۱۰ برایِ نرخ‌هایِ محدودسازی: با پیش‌فرضِ توسعه (10000/min)
    هیچ ترافیکیِ معقولِ توسعه/تست نباید ۴۲۹ بگیرد — یعنی «بدونِ ست‌کردنِ هیچ
    متغیری، همانِ رفتارِ قبل» هنوز برقرار است."""

    def test_heavy_dev_traffic_never_throttled(self):
        """۲۵ درخواستِ متوالیِ بی‌احراز + ۱۰ درخواستِ احراز‌شده: همه پاسخِ
        عادی می‌گیرند (400/200)، هیچ‌کدام 429."""
        for _ in range(25):
            resp = self.client.post(
                '/api/auth/register/',
                {'username': 'alice', 'password': 'whatever'},   # تکراری → 400
                format='json',
            )
            self.assertEqual(resp.status_code, 400)
        client = self.client_as(self.alice)
        for _ in range(10):
            self.assertEqual(client.get('/api/subjects/').status_code, 200)


# ---------------------------------------------------------------------------
# متغیرهایِ محیطیِ نرخ‌ها و هدرهایِ امنیتی (از 2026-09-10)
# ---------------------------------------------------------------------------

class ThrottleAndSecuritySettingsTests(SimpleTestCase):
    """متغیرهایِ محیطیِ جدید — هم‌الگویِ SettingsEnvVarsTests، دو لایه:

    ۱) تستِ واحدِ توابعِ کمکیِ _env_throttle_rate/_env_int/_env_proxy_ssl_header.
    ۲) «بوتِ واقعی» با مفسرِ جدا: اعتبارسنجیِ سخت‌گیرانه (fail-fast) و
       مقادیرِ Production از همانِ محیطِ ساختگی.
    """

    _ENV_KEYS = (
        'DJANGO_SECRET_KEY', 'DJANGO_DEBUG', 'DJANGO_ALLOWED_HOSTS',
        'DJANGO_CORS_ALLOW_ALL', 'DJANGO_ALLOWED_ORIGINS', 'DATABASE_URL',
        'DJANGO_ANON_THROTTLE_RATE', 'DJANGO_USER_THROTTLE_RATE',
        'DJANGO_AUTH_THROTTLE_RATE', 'DJANGO_SECURE_SSL_REDIRECT',
        'DJANGO_COOKIES_SECURE', 'DJANGO_HSTS_SECONDS',
        'DJANGO_PROXY_SSL_HEADER',
    )

    def _boot(self, extra_env, code):
        """مفسرِ تازه‌ای با متغیرهایِ داده‌شده بالا می‌آورد و نتیجه را برمی‌گرداند."""
        env = os.environ.copy()
        env['DJANGO_SETTINGS_MODULE'] = 'backend.settings'
        for key in self._ENV_KEYS:
            env.pop(key, None)          # نشتِ محیطِ تست به نتیجه نداشته باشد
        env.update(extra_env)
        return subprocess.run(
            [sys.executable, '-c', code],
            capture_output=True, text=True, env=env,
            cwd=str(Path(__file__).resolve().parents[1]),   # پوشه‌ی backend/
            timeout=90,
        )

    # ---- ۱) توابعِ کمکی ------------------------------------------------------

    def test_env_throttle_rate_parsing(self):
        """قالبِ '<عدد>/<sec|min|hour|day>'؛ فاصله‌ها trimmed؛ غلط = خطا."""
        with patch.dict(os.environ, {'T': '30/min'}):
            self.assertEqual(_env_throttle_rate('T', '10000/min'), '30/min')
        with patch.dict(os.environ, {'T': ' 30/min '}):
            self.assertEqual(_env_throttle_rate('T', '10000/min'), '30/min')
        for bad in ('20/hourly', '20', 'abc', '30/MIN', '/min', '1.5/min', '-5/min'):
            with patch.dict(os.environ, {'T': bad}):
                with self.assertRaises(ImproperlyConfigured, msg=bad):
                    _env_throttle_rate('T', '10000/min')
        os.environ.pop('T', None)
        self.assertEqual(_env_throttle_rate('T', '10000/min'), '10000/min')   # بی‌مقدار → default

    def test_env_int_parsing(self):
        """عددِ صحیحِ خالص؛ فاصله trimmed؛ نامعتبر = خطا؛ بی‌مقدار → default."""
        with patch.dict(os.environ, {'T': '31536000'}):
            self.assertEqual(_env_int('T', 0), 31536000)
        with patch.dict(os.environ, {'T': ' 42 '}):
            self.assertEqual(_env_int('T', 0), 42)
        for bad in ('soon', '12.5', '1e3'):
            with patch.dict(os.environ, {'T': bad}):
                with self.assertRaises(ImproperlyConfigured, msg=bad):
                    _env_int('T', 0)
        os.environ.pop('T', None)
        self.assertEqual(_env_int('T', 0), 0)
        self.assertEqual(_env_int('T', 7), 7)

    def test_env_proxy_ssl_header_parsing(self):
        """'HEADER,value' → تاپل؛ خالی → None؛ قالبِ ناقص = خطا."""
        with patch.dict(os.environ, {'T': 'HTTP_X_FORWARDED_PROTO,https'}):
            self.assertEqual(_env_proxy_ssl_header('T'), ('HTTP_X_FORWARDED_PROTO', 'https'))
        with patch.dict(os.environ, {'T': 'HTTP_X_FORWARDED_PROTO , https'}):
            self.assertEqual(_env_proxy_ssl_header('T'), ('HTTP_X_FORWARDED_PROTO', 'https'))
        for bad in ('X-Proto', 'a,b,c', 'a,', ',b'):
            with patch.dict(os.environ, {'T': bad}):
                with self.assertRaises(ImproperlyConfigured, msg=bad):
                    _env_proxy_ssl_header('T')
        os.environ.pop('T', None)
        self.assertIsNone(_env_proxy_ssl_header('T'))

    # ---- ۲) بوتِ واقعی با تنظیماتِ تازه ---------------------------------------

    def test_boot_dev_defaults_unchanged(self):
        """رگرسیونِ ۶.۱۰: بدونِ هیچ متغیری، نرخ‌ها 10000/min و هدرها خاموش."""
        code = (
            'import django; django.setup(); from django.conf import settings; '
            "assert settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'] == "
            "{'anon': '10000/min', 'user': '10000/min', 'auth': '10000/min'}, 'RATES'; "
            'assert settings.SECURE_SSL_REDIRECT is False, "SSL"; '
            'assert settings.SESSION_COOKIE_SECURE is False, "SESS"; '
            'assert settings.CSRF_COOKIE_SECURE is False, "CSRF"; '
            'assert settings.SECURE_HSTS_SECONDS == 0, "HSTS"; '
            'assert settings.SECURE_PROXY_SSL_HEADER is None, "PROXY"; '
            'print("dev-ok")'
        )
        result = self._boot({}, code)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn('dev-ok', result.stdout)

    def test_boot_prod_warns_on_default_throttle_rates(self):
        """DEBUG=false با نرخ‌هایِ پیش‌فرض: بوت می‌شود ولی روی stderr هشدار."""
        result = self._boot(
            {'DJANGO_DEBUG': 'false', 'DJANGO_SECRET_KEY': 'p' * 64,
             'DJANGO_ALLOWED_HOSTS': 'example.com'},
            'import django; django.setup()',
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn('DJANGO_AUTH_THROTTLE_RATE', result.stderr)

    def test_boot_prod_no_throttle_warning_when_rates_set(self):
        """با ست‌شدنِ هر سه نرخ، همان هشدار دیگر نوشته نمی‌شود."""
        result = self._boot(
            {'DJANGO_DEBUG': 'false', 'DJANGO_SECRET_KEY': 'p' * 64,
             'DJANGO_ALLOWED_HOSTS': 'example.com',
             'DJANGO_ANON_THROTTLE_RATE': '120/min',
             'DJANGO_USER_THROTTLE_RATE': '600/min',
             'DJANGO_AUTH_THROTTLE_RATE': '20/min'},
            'import django; django.setup()',
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertNotIn('throttle rates', result.stderr)

    def test_boot_prod_applies_throttle_and_security_values(self):
        """ترکیبِ کاملِ Production: نرخ‌ها + ریدایرکتِ SSL + کوکی‌هایِ Secure
        + HSTS + هدرِ پروکسی، همه از متغیرها اعمال می‌شوند."""
        key = 'p' * 64
        code = (
            'import django; django.setup(); from django.conf import settings; '
            "assert settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'] == "
            "{'anon': '120/min', 'user': '600/min', 'auth': '20/min'}, 'RATES'; "
            'assert settings.SECURE_SSL_REDIRECT is True, "SSL"; '
            'assert settings.SESSION_COOKIE_SECURE is True, "SESS"; '
            'assert settings.CSRF_COOKIE_SECURE is True, "CSRF"; '
            'assert settings.SECURE_HSTS_SECONDS == 31536000, "HSTS"; '
            "assert settings.SECURE_PROXY_SSL_HEADER == "
            "('HTTP_X_FORWARDED_PROTO', 'https'), 'PROXY'; "
            'print("sec-ok")'
        )
        result = self._boot(
            {'DJANGO_DEBUG': 'false', 'DJANGO_SECRET_KEY': key,
             'DJANGO_ALLOWED_HOSTS': 'example.com',
             'DJANGO_ANON_THROTTLE_RATE': '120/min',
             'DJANGO_USER_THROTTLE_RATE': '600/min',
             'DJANGO_AUTH_THROTTLE_RATE': '20/min',
             'DJANGO_SECURE_SSL_REDIRECT': '1',
             'DJANGO_COOKIES_SECURE': 'on',
             'DJANGO_HSTS_SECONDS': '31536000',
             'DJANGO_PROXY_SSL_HEADER': 'HTTP_X_FORWARDED_PROTO,https'},
            code,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn('sec-ok', result.stdout)

    def test_boot_invalid_throttle_rate_refuses_to_boot(self):
        """نرخِ با قالبِ غلط = fail-fastِ همانِ بوت با پیامِ راهنما."""
        result = self._boot({'DJANGO_AUTH_THROTTLE_RATE': '20/hourly'},
                            'import django; django.setup()')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('DJANGO_AUTH_THROTTLE_RATE', result.stderr)

    def test_boot_invalid_hsts_seconds_refuses_to_boot(self):
        """HSTS غیرعددی یا منفی = بوت متوقف (منفی بی‌معناست)."""
        for bad in ('soon', '-1'):
            result = self._boot({'DJANGO_HSTS_SECONDS': bad},
                                'import django; django.setup()')
            self.assertNotEqual(result.returncode, 0, msg=bad)
            self.assertIn('DJANGO_HSTS_SECONDS', result.stderr)

    def test_boot_invalid_proxy_header_refuses_to_boot(self):
        """هدرِ پروکسیِ ناقص = بوت متوقف با قالبِ درست در پیام."""
        result = self._boot({'DJANGO_PROXY_SSL_HEADER': 'X-Proto'},
                            'import django; django.setup()')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('HEADER,value', result.stderr)


# ---------------------------------------------------------------------------
# هدرهایِ امنیتیِ شرطی در سطحِ پاسخِ HTTP (از 2026-09-10)
# ---------------------------------------------------------------------------

class SecurityHeadersResponseTests(BaseAPITestCase):
    """رفتارِ قابلِ مشاهده: روشن/خاموش‌کردنِ هر تنظیم، هدرِ درست می‌سازد.

    روشن‌کردن‌ها اینجا با override_settings شبیه‌سازی می‌شوند (معادلِ
    ست‌کردنِ متغیرِ محیطی — نگاشتِ env→setting در کلاسِ قبلی تست شده).
    """

    def test_hsts_header_appears_when_enabled(self):
        """پشتِ پروکسیِ TLS (X-Forwarded-Proto: https) + HSTS روشن → هدرِ
        Strict-Transport-Security رویِ پاسخ. جنگو هدرِ HSTS را فقط برای
        درخواستِ امن (is_secure) می‌فرستد — همان چیزی که در Production
        پشتِ Nginx اتفاق می‌افتد (نگاه کنید به 05_deployment.md)."""
        with override_settings(SECURE_HSTS_SECONDS=31536000,
                               SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO', 'https')):
            resp = self.client.get('/api/health/', HTTP_X_FORWARDED_PROTO='https')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp['Strict-Transport-Security'].startswith('max-age=31536000'))

    def test_no_hsts_header_by_default(self):
        """رگرسیونِ ۶.۱۰: پیش‌فرضِ توسعه هیچ هدرِ HSTS نمی‌فرستد."""
        resp = self.client.get('/api/health/')
        self.assertNotIn('Strict-Transport-Security', resp)

    def test_ssl_redirect_when_enabled(self):
        with override_settings(SECURE_SSL_REDIRECT=True):
            resp = self.client.get('/api/health/')
        self.assertEqual(resp.status_code, 301)
        self.assertTrue(resp['Location'].startswith('https://'))

    def test_no_ssl_redirect_by_default(self):
        """رگرسیونِ ۶.۱۰: پیش‌فرضِ توسعه http را به https هُل نمی‌دهد."""
        resp = self.client.get('/api/health/')
        self.assertEqual(resp.status_code, 200)

    def test_csrf_cookie_gets_secure_flag_when_enabled(self):
        with override_settings(CSRF_COOKIE_SECURE=True):
            resp = self.client.get('/admin/login/')
        cookie = resp.cookies.get('csrftoken')
        self.assertIsNotNone(cookie, 'admin login should set a CSRF cookie')
        self.assertTrue(cookie['secure'])

    def test_csrf_cookie_not_secure_by_default(self):
        """رگرسیونِ ۶.۱۰: کوکیِ CSRF در توسعه بدونِ فلگِ Secure می‌ماند
        (وگرنه runserver رویِ http عملاً از کار می‌افتاد)."""
        resp = self.client.get('/admin/login/')
        cookie = resp.cookies.get('csrftoken')
        self.assertIsNotNone(cookie, 'admin login should set a CSRF cookie')
        self.assertFalse(cookie['secure'])


# ---------------------------------------------------------------------------
# امنیتِ حسابِ کاربری: سیاستِ رمز + تغییرِ رمز + ابطالِ کاملِ نشست‌ها
# (از 2026-09-10)
# ---------------------------------------------------------------------------

# رمزِ جدیدِ استانداردِ این بخش — از همه‌ی اعتبارسنج‌ها (طول/رایج/عددی/
# شباهت) عبور می‌کند و در هیچ فهرستِ رمزهای رایج نیست.
_ACCOUNT_NEW_PASSWORD = 'brand-new-pass-77'


class RegisterPasswordPolicyTests(BaseAPITestCase):
    """سیاستِ رمزِ عبور در ثبت‌نام (از 2026-09-10).

    تا این تاریخ، AUTH_PASSWORD_VALIDATORS در settings «تعریف» شده بود ولی
    هیچ‌جا صدا زده نمی‌شد — ثبت‌نام با رمزهایِ «12345678» و «password»
    ممکن بود. حالا UserSerializer.validate قبل ازِ ساختِ کاربر، رمز را با
    همان اعتبارسنج‌هایِ جنگو می‌سنجد.

    پیام‌هایِ خطا مالِ خودِ جنگو هستند (نه کاتالوگِ پروژه) و جنگو کاتالوگِ
    fa و en خودش را دارد — پس ترجمه‌ی پیام با Accept-Language خودکار است.
    """

    def _register(self, username, password):
        return self.client.post(
            '/api/auth/register/',
            {'username': username, 'password': password},
            format='json',
        )

    def test_common_password_rejected(self):
        """رمزِ رایج («12345678») → ۴۰۰ با کلیدِ password و بدونِ ساختِ کاربر."""
        response = self._register('policyuser1', '12345678')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password', response.json())
        self.assertGreater(len(response.json()['password']), 0)
        self.assertFalse(User.objects.filter(username='policyuser1').exists())

    def test_too_short_password_rejected(self):
        """رمزِ کوتاه‌تر از حداقلِ ۸ نویسه → ۴۰۰."""
        response = self._register('policyuser2', 'short')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password', response.json())
        self.assertFalse(User.objects.filter(username='policyuser2').exists())

    def test_numeric_password_rejected(self):
        """رمزِ کاملاً عددی (حتی غیرِ رایج) → ۴۰۰ (NumericPasswordValidator)."""
        response = self._register('policyuser3', '13579246')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password', response.json())

    def test_password_similar_to_username_rejected(self):
        """رمزِ هم‌نام با username → ۴۰۰ (UserAttributeSimilarityValidator)."""
        response = self._register('hamidreza', 'hamidreza')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password', response.json())
        self.assertFalse(User.objects.filter(username='hamidreza').exists())

    def test_strong_password_still_accepted(self):
        """رگرسیون: رمزِ معتبرِ همیشگیِ پروژه ('pw-12345678') → ۲۰۱ + ورود."""
        response = self._register('policyuser4', 'pw-12345678')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        login = self.client.post(
            '/api/auth/login/',
            {'username': 'policyuser4', 'password': 'pw-12345678'},
            format='json',
        )
        self.assertEqual(login.status_code, status.HTTP_200_OK)

    def test_policy_message_translated_per_language(self):
        """پیامِ سیاست با Accept-Language ترجمه می‌شود (fa/en جنگو)."""
        fa_response = self._register('policyuser5', '12345678')
        en_response = self.client.post(
            '/api/auth/register/',
            {'username': 'policyuser5', 'password': '12345678'},
            format='json',
            HTTP_ACCEPT_LANGUAGE='en',
        )
        self.assertEqual(
            fa_response.json()['password'][0], 'این رمز عبور بسیار رایج است.'
        )
        self.assertEqual(
            en_response.json()['password'][0], 'This password is too common.'
        )

    def test_direct_user_creation_not_affected(self):
        """دامنه‌ی سیاست = فقط API ثبت‌نام؛ ساختِ مستقیمِ کاربر (مدیریت/تست)
        هنوز آزاد است — رگرسیونِ پایه‌ی همه‌ی setUpهای این فایل که با
        create_user کاربر می‌سازند."""
        User.objects.create_user('carol', password='weakold')
        login = self.client.post(
            '/api/auth/login/',
            {'username': 'carol', 'password': 'weakold'},
            format='json',
        )
        self.assertEqual(login.status_code, status.HTTP_200_OK)


class ChangePasswordAPITests(BaseAPITestCase):
    """POST /api/auth/password/ — تغییرِ رمز با ابطالِ کاملِ نشست‌ها.

    - رمزِ فعلی لازم است (۴۰۰ با پیامِ ترجمه‌شده در صورتِ خطا).
    - رمزِ جدید از همان سیاستِ ثبت‌نام می‌گذرد.
    - همه‌ی توکن‌هایِ Refreshِ برجسته‌یِ کاربر لیستِ سیاه می‌شوند (نه فقط
      توکنِ همین نشست، مثلِ logout).
    - پاسخِ موفق جفتِ توکنِ تازه می‌دهد تا نشستِ همین دستگاه ادامه یابد.
    """

    def _login_tokens(self, username='alice', password='pw-12345678'):
        body = self.client.post(
            '/api/auth/login/',
            {'username': username, 'password': password},
            format='json',
        ).json()
        return body['access'], body['refresh']

    def _change(self, client, current, new):
        return client.post(
            '/api/auth/password/',
            {'current_password': current, 'new_password': new},
            format='json',
        )

    def test_change_password_success_returns_fresh_token_pair(self):
        """مسیرِ خوش‌بخت: ۲۰۰ + توکن‌هایِ تازه که همان‌جا کار می‌کنند."""
        old_access, old_refresh = self._login_tokens()
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {old_access}')

        response = self._change(client, 'pw-12345678', _ACCOUNT_NEW_PASSWORD)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.assertIn('access', body)
        self.assertIn('refresh', body)
        # توکن‌هایِ تازه همان‌جا معتبرند (iat >= لحظه‌ی تغییر):
        fresh = APIClient()
        fresh.credentials(HTTP_AUTHORIZATION=f"Bearer {body['access']}")
        self.assertEqual(fresh.get('/api/subjects/').status_code, 200)

    def test_old_refresh_blacklisted_after_change(self):
        """رگرسیونِ امنیتی: توکنِ Refreshِ قبل ازِ تغییر، غیرقابلِ تمدید."""
        old_access, old_refresh = self._login_tokens()
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {old_access}')
        self._change(client, 'pw-12345678', _ACCOUNT_NEW_PASSWORD)

        refresh_response = self.client.post(
            '/api/auth/refresh/', {'refresh': old_refresh}, format='json'
        )
        self.assertEqual(refresh_response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_all_outstanding_tokens_blacklisted_not_just_current(self):
        """«همه‌ی» نشست‌ها باطل می‌شوند: چند نشستِ هم‌زمان → همه‌ی Refreshها
        سیاه؛ نه فقط نشستِ تغییردهنده (تفاوتِ کلیدی با logoutِ تک‌توکنی)."""
        # نشست ۱ (مرورگر) و نشست ۲ (گوشی) — دو ورودِ جدا:
        _, refresh_browser = self._login_tokens()
        _, refresh_phone = self._login_tokens()
        client = APIClient()
        access_changer, _ = self._login_tokens()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_changer}')
        self._change(client, 'pw-12345678', _ACCOUNT_NEW_PASSWORD)

        for label, refresh in [('browser', refresh_browser), ('phone', refresh_phone)]:
            with self.subTest(session=label):
                response = self.client.post(
                    '/api/auth/refresh/', {'refresh': refresh}, format='json'
                )
                self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_new_refresh_from_response_still_rotates(self):
        """توکنِ Refreshِ صادرشده در پاسخ، خودش دوباره چرخش می‌کند (۲۰۰)."""
        old_access, _ = self._login_tokens()
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {old_access}')
        body = self._change(client, 'pw-12345678', _ACCOUNT_NEW_PASSWORD).json()

        response = self.client.post(
            '/api/auth/refresh/', {'refresh': body['refresh']}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.json())

    def test_login_with_old_password_fails_after_change(self):
        """بعد ازِ تغییر، ورود با رمزِ قدیمی ۴۰۱ و با رمزِ جدید ۲۰۰ است."""
        old_access, _ = self._login_tokens()
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {old_access}')
        self._change(client, 'pw-12345678', _ACCOUNT_NEW_PASSWORD)

        old_login = self.client.post(
            '/api/auth/login/',
            {'username': 'alice', 'password': 'pw-12345678'},
            format='json',
        )
        new_login = self.client.post(
            '/api/auth/login/',
            {'username': 'alice', 'password': _ACCOUNT_NEW_PASSWORD},
            format='json',
        )
        self.assertEqual(old_login.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(new_login.status_code, status.HTTP_200_OK)

    def test_wrong_current_password_rejected(self):
        """رمزِ فعلیِ غلط → ۴۰۰ + پیامِ ترجمه‌شده + رمز عوض نمی‌شود."""
        client = self.client_as(self.alice)

        response = self._change(client, 'wrong-password', _ACCOUNT_NEW_PASSWORD)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.json()['current_password'][0], 'رمز عبور فعلی اشتباه است.'
        )
        # رمز عوض نشده — ورود با رمزِ اصلی هنوز موفق است و پروفایلی ساخته نشده:
        login = self.client.post(
            '/api/auth/login/',
            {'username': 'alice', 'password': 'pw-12345678'},
            format='json',
        )
        self.assertEqual(login.status_code, status.HTTP_200_OK)
        self.assertFalse(
            UserSecurityProfile.objects.filter(user=self.alice).exists()
        )

    def test_wrong_current_password_message_translated(self):
        client = self.client_as(self.alice)
        response = client.post(
            '/api/auth/password/',
            {'current_password': 'wrong-password', 'new_password': _ACCOUNT_NEW_PASSWORD},
            format='json',
            HTTP_ACCEPT_LANGUAGE='en',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.json()['current_password'][0], 'Current password is incorrect.'
        )

    def test_weak_new_password_rejected(self):
        """رمزِ جدیدِ ضعیف → ۴۰۰ با پیامِ سیاست؛ رمزِ فعلی دست‌نخورده."""
        client = self.client_as(self.alice)

        response = self._change(client, 'pw-12345678', '12345678')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('new_password', response.json())
        login = self.client.post(
            '/api/auth/login/',
            {'username': 'alice', 'password': 'pw-12345678'},
            format='json',
        )
        self.assertEqual(login.status_code, status.HTTP_200_OK)

    def test_new_password_similar_to_username_rejected(self):
        """رمزِ جدیدِ شبیهِ username خودِ کاربر → ۴۰۰ (سنجشِ شباهت با کاربرِ
        واقعیِ حل‌شده از دیتابیس، نه نمونه‌ی گذرا مثلِ ثبت‌نام)."""
        client = self.client_as(self.alice)

        response = self._change(client, 'pw-12345678', 'alice1234')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('new_password', response.json())

    def test_requires_authentication(self):
        """بدونِ توکنِ دسترسی → ۴۰۱ (رمزِ کسی بدونِ احرازِ هویت عوض نمی‌شود)."""
        response = self.client.post(
            '/api/auth/password/',
            {'current_password': 'pw-12345678', 'new_password': _ACCOUNT_NEW_PASSWORD},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_missing_new_password_rejected(self):
        """بدنه‌ی ناقص (فقط رمزِ فعلی) → ۴۰۰ با کلیدِ new_password."""
        client = self.client_as(self.alice)
        response = client.post(
            '/api/auth/password/',
            {'current_password': 'pw-12345678'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('new_password', response.json())

    def test_other_users_sessions_unaffected(self):
        """تغییرِ رمزِ alice نشستِ bob را باطل نمی‌کند (جداسازیِ کاربر-محور)."""
        bob_client = self.client_as(self.bob)
        self.assertEqual(bob_client.get('/api/subjects/').status_code, 200)

        alice_client = self.client_as(self.alice)
        self._change(alice_client, 'pw-12345678', _ACCOUNT_NEW_PASSWORD)

        self.assertEqual(bob_client.get('/api/subjects/').status_code, 200)

    def test_success_message_translated(self):
        old_access, _ = self._login_tokens()
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {old_access}')
        response = client.post(
            '/api/auth/password/',
            {'current_password': 'pw-12345678', 'new_password': _ACCOUNT_NEW_PASSWORD},
            format='json',
            HTTP_ACCEPT_LANGUAGE='en',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.json()['detail'],
            'Password changed successfully; all other sessions were invalidated.',
        )


class StaleAccessTokenInvalidationTests(BaseAPITestCase):
    """ابطالِ توکن‌هایِ دسترسیِ قبل ازِ تغییرِ رمز — planner/authentication.py.

    معیار: iat (لحظه‌ی صدورِ توکن، ثانیه‌یِ یونیکس) < password_changed_at → ۴۰۱.
    برایِ قطعیتِ زمانی (بدونِ sleep)، مهرِ زمانِ پروفایل مستقیماً دستکاری
    می‌شود — سازوکارِ مقایسه همین است و دقیقاً همین را تست می‌کند.
    """

    def test_token_issued_before_change_is_rejected(self):
        """توکنِ صادرشده قبل ازِ تغییرِ رمز → ۴۰۱ روی endpointهایِ عادی."""
        client = self.client_as(self.alice)
        self.assertEqual(client.get('/api/subjects/').status_code, 200)

        # مهرِ زمانِ «تغییرِ رمز» دو ثانیه بعد از صدورِ توکن (آینده):
        UserSecurityProfile.objects.create(
            user=self.alice, password_changed_at=timezone.now() + timedelta(seconds=2)
        )
        response = client.get('/api/subjects/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_token_issued_after_change_is_accepted(self):
        """توکنِ صادرشده «بعد ازِ» تغییرِ رمز معتبر است (پروفایل در گذشته)."""
        UserSecurityProfile.objects.create(
            user=self.alice, password_changed_at=timezone.now() - timedelta(seconds=10)
        )
        client = self.client_as(self.alice)
        self.assertEqual(client.get('/api/subjects/').status_code, 200)

    def test_users_without_profile_completely_unaffected(self):
        """رگرسیونِ ۶.۱۰ (dev-safe): کاربرانِ عادی — که هرگز رمز عوض نکرده‌اند
        و رکوردِ پروفایل ندارند — دقیقاً همانِ مسیرِ اجراییِ قبلی را می‌روند."""
        client = self.client_as(self.alice)
        self.assertFalse(
            UserSecurityProfile.objects.filter(user=self.alice).exists()
        )
        self.assertEqual(client.get('/api/subjects/').status_code, 200)
        self.assertEqual(client.get('/api/dashboard/').status_code, 200)

    def test_same_second_edge_keeps_token_valid(self):
        """مرزِ مستندشده: توکنِ صادرشده در «همانِ ثانیه‌یِ» تغییرِ رمز معتبر
        می‌ماند (رزولوشنِ iat ثانیه است؛ پنجره‌ی حداکثرِ یک ثانیه). این تست
        مرز را قفل می‌کند تا تغییرِ ناخواسته‌یِ علامتِ مقایسه به 'کمتر-یا‌مساوی'
        (که توکن‌هایِ تازه را هم می‌کُشد) در تست‌ها واضوح شود."""
        UserSecurityProfile.objects.create(
            user=self.alice, password_changed_at=timezone.now()
        )
        # توکن «بعد از» ساختِ پروفایل صادر می‌شود → iat >= ثانیه‌یِ مهر:
        client = self.client_as(self.alice)
        self.assertEqual(client.get('/api/subjects/').status_code, 200)

    def test_rejection_message_translated(self):
        """پیامِ ۴۰۱ِ ابطال، ترجمه‌ی خودکار دارد (fa = متنِ اصلی، en = کاتالوگ)."""
        client = self.client_as(self.alice)
        UserSecurityProfile.objects.create(
            user=self.alice, password_changed_at=timezone.now() + timedelta(seconds=2)
        )
        fa_response = client.get('/api/subjects/')
        self.assertEqual(
            fa_response.json()['detail'],
            'رمز عبور این حساب تغییر کرده است؛ لطفاً دوباره وارد شوید.',
        )

        en_client = APIClient()
        token = str(RefreshToken.for_user(self.alice).access_token)
        en_client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        en_response = en_client.get(
            '/api/subjects/', HTTP_ACCEPT_LANGUAGE='en'
        )
        self.assertEqual(
            en_response.json()['detail'],
            'The password of this account has changed; please log in again.',
        )


class UserSecurityProfileModelTests(BaseAPITestCase):
    """مدلِ UserSecurityProfile — قیدها و رفتارِ جدولی (محرکِ ابطالِ نشست)."""

    def test_str_representation_contains_username(self):
        profile = UserSecurityProfile.objects.create(
            user=self.alice, password_changed_at=timezone.now()
        )
        self.assertIn('alice', str(profile))

    def test_one_profile_per_user_enforced(self):
        """قیدِ یک‌به‌یک در سطحِ دیتابیس: رکوردِ دوم → IntegrityError."""
        UserSecurityProfile.objects.create(
            user=self.alice, password_changed_at=timezone.now()
        )
        with self.assertRaises(IntegrityError):
            UserSecurityProfile.objects.create(
                user=self.alice, password_changed_at=timezone.now()
            )

    def test_profile_deleted_with_user(self):
        """CASCADE: حذفِ کاربر، پروفایلِ امنیتیِ او را هم پاک می‌کند."""
        profile = UserSecurityProfile.objects.create(
            user=self.alice, password_changed_at=timezone.now()
        )
        self.alice.delete()
        self.assertFalse(
            UserSecurityProfile.objects.filter(pk=profile.pk).exists()
        )

    def test_update_or_create_keeps_single_row_and_advances_timestamp(self):
        """تغییرِ رمزِ مکرر: همان رکورد به‌روز می‌شود (نه رکوردِ جدید) و مهرِ
        زمانِ جلو می‌رود — همان کاری که change_password می‌کند."""
        first = UserSecurityProfile.objects.update_or_create(
            user=self.alice,
            defaults={'password_changed_at': timezone.now() - timedelta(days=1)},
        )[0]
        later = timezone.now()
        second = UserSecurityProfile.objects.update_or_create(
            user=self.alice, defaults={'password_changed_at': later}
        )[0]
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(UserSecurityProfile.objects.count(), 1)
        self.assertEqual(second.password_changed_at, later)


# ---------------------------------------------------------------------------
# بازیابیِ رمزِ فراموش‌شده (از 2026-09-12)
# ---------------------------------------------------------------------------
# دو endpoint بی‌لاگین: POST /api/auth/password/reset/ (درخواستِ لینک) و
# POST /api/auth/password/reset/confirm/ (تعیینِ رمزِ جدید با uid/token).
# تست‌ها با backend ایمیلِ locmem اجرا می‌شوند (ایمیل‌ها به جایِ ارسال در
# mail.outbox جمع می‌شوند) — «موتورِ» فرستادن جدا از «منطقِ» endpoint تست
# می‌شود؛ خودِ موتورِ console/SMTP در PasswordResetSettingsTests.
# ---------------------------------------------------------------------------

import re as _re
from datetime import datetime
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode

# موتورِ ایمیلِ تست: locmem (بدونِ شبکه) — رفتارِ واقعیِ view مستقل از موتور
_LOCMEM = {'EMAIL_BACKEND': 'django.core.mail.backends.locmem.EmailBackend'}

_RESET_URL = '/api/auth/password/reset/'
_RESET_CONFIRM_URL = '/api/auth/password/reset/confirm/'


def _make_reset_link(user):
    """uid + tokenِ همان لینکی که ایمیل می‌رود — برایِ تستِ مستقیمِ confirm."""
    return (
        urlsafe_base64_encode(str(user.pk).encode()),
        default_token_generator.make_token(user),
    )


def _extract_link_from_email(message):
    """لینکِ بازیابی را از متنِ ایمیل بیرون می‌کشد (فرمتِ دقیقِ ایمیلِ view)."""
    match = _re.search(r'(https?://\S*reset-password\.html\?uid=[^&\s]+&token=\S+)', message.body)
    return match.group(1) if match else None


@override_settings(**_LOCMEM)
class PasswordResetRequestAPITests(BaseAPITestCase):
    """POST /api/auth/password/reset/ — «ایمیل برو» با اصلِ ضدِ کشفِ حساب.

    قراردادِ امنیتیِ این endpoint (نکته‌ی ۶.۱۷ AI_CONTEXT): پاسخِ حسابِ
    موجودِ ایمیل‌دار، حسابِ ناموجود، حسابِ بدونِ ایمیل و حسابِ غیرفعال
    بایت‌به‌بایت یکسان است — تنها تفاوتِ دنیایِ واقعی، «ایمیلِ رفتن» است.
    """

    def setUp(self):
        super().setUp()
        self.alice.email = 'alice@example.com'
        self.alice.save(update_fields=['email'])

    def test_request_by_email_sends_one_email(self):
        """شناسه = ایمیلِ آلیس → ۲۰۰ + دقیقاً یک ایمیل به همان آدرس."""
        resp = self.client.post(_RESET_URL, {'identifier': 'alice@example.com'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('detail', resp.json())
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['alice@example.com'])

    def test_request_by_username_sends_email(self):
        """شناسه = نامِ کاربری هم کار می‌کند (ایمیل در ثبت‌نام اختیاری است)."""
        resp = self.client.post(_RESET_URL, {'identifier': 'alice'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)

    def test_request_is_case_insensitive_for_email(self):
        """حروفِ بزرگ/کوچکِ ایمیل نباید مسیرِ بازیابی را ببندد."""
        resp = self.client.post(_RESET_URL, {'identifier': 'Alice@Example.COM'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)

    def test_unknown_identifier_returns_identical_generic_response(self):
        """اصلِ ضدِ کشفِ حساب: ناموجود و موجود، همان status و همان بدنه."""
        resp_known = self.client.post(_RESET_URL, {'identifier': 'alice@example.com'}, format='json')
        resp_unknown = self.client.post(_RESET_URL, {'identifier': 'nobody@example.com'}, format='json')
        self.assertEqual(resp_known.status_code, resp_unknown.status_code)
        self.assertEqual(resp_known.json(), resp_unknown.json())
        # فقط فرقِ واقعی: برایِ ناموجود هیچ ایمیلی نمی‌رود
        self.assertEqual(len(mail.outbox), 1)

    def test_user_without_email_returns_generic_response_and_sends_nothing(self):
        """باب (بدونِ ایمیلِ ثبت‌شده) → همان پاسخِ عمومی، بدونِ ایمیل."""
        resp = self.client.post(_RESET_URL, {'identifier': 'bob'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json()['detail'],
                         'اگر این حساب وجود داشته باشد، لینکِ بازیابی به ایمیلِ شما ارسال شد.')
        self.assertEqual(len(mail.outbox), 0)

    def test_inactive_user_gets_no_email(self):
        """حسابِ غیرفعالْ لینکِ بازیابی نمی‌گیرد (ولی همان پاسخِ عمومی)."""
        self.alice.is_active = False
        self.alice.save(update_fields=['is_active'])
        resp = self.client.post(_RESET_URL, {'identifier': 'alice@example.com'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 0)

    def test_missing_identifier_returns_400(self):
        """بدونِ شناسه → ۴۰۰ با پیامِ ترجمه‌شده (این خطا فاش‌کننده نیست)."""
        resp = self.client.post(_RESET_URL, {'identifier': '   '}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.json()['detail'], 'نام کاربری یا ایمیل را وارد کنید.')

    def test_email_contains_valid_recovery_link(self):
        """ایمیلِ رفته: لینکِ کامل با uid/tokenِ واقعاً معتبر + مبدأِ پیش‌فرض."""
        self.client.post(_RESET_URL, {'identifier': 'alice@example.com'}, format='json')
        self.assertEqual(len(mail.outbox), 1)
        link = _extract_link_from_email(mail.outbox[0])
        self.assertIsNotNone(link, 'email body must contain the recovery link')
        self.assertIn('/static/reset-password.html?uid=', link)
        # uid باید به همان کاربر برگردد و token باید از سنجشِ مولد رد شود:
        query = link.split('?', 1)[1]
        params = dict(pair.split('=', 1) for pair in query.split('&'))
        user_pk = urlsafe_base64_decode(params['uid']).decode()
        user = User.objects.get(pk=user_pk)
        self.assertEqual(user, self.alice)
        self.assertTrue(default_token_generator.check_token(user, params['token']))

    def test_email_link_respects_frontend_base_url_override(self):
        """مبدأِ لینک از FRONTEND_BASE_URL می‌آید (تنظیمِ سرور، نه حدس)."""
        with override_settings(FRONTEND_BASE_URL='https://planner.example.com'):
            self.client.post(_RESET_URL, {'identifier': 'alice@example.com'}, format='json')
        link = _extract_link_from_email(mail.outbox[0])
        self.assertTrue(link.startswith('https://planner.example.com/static/reset-password.html'))

    def test_english_response_and_email_when_accept_language_en(self):
        """زبانِ درخواست، هم پاسخِ HTTP و هم ایمیلِ رفته را ترجمه می‌کند."""
        resp = self.client.post(_RESET_URL, {'identifier': 'alice@example.com'},
                                format='json', HTTP_ACCEPT_LANGUAGE='en')
        self.assertEqual(resp.json()['detail'],
                         'If this account exists, a recovery link has been sent to your email.')
        self.assertEqual(mail.outbox[0].subject,
                         'Password recovery — Smart Study Planner')
        self.assertIn('Hello alice,', mail.outbox[0].body)
        self.assertIn('valid for 60 minutes', mail.outbox[0].body)

    def test_get_method_not_allowed(self):
        """این endpoint فقط POST است (GET → 405، مکانیکِ @api_view)."""
        resp = self.client.get(_RESET_URL)
        self.assertEqual(resp.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_email_delivery_failure_still_returns_generic_200(self):
        """شکستِ SMTP نباید ۵۰۰ بدهد — وگرنه فرقِ موجود/ناموجود لو می‌رود."""
        with patch('planner.views.send_mail', side_effect=ConnectionError('SMTP down')):
            resp = self.client.post(_RESET_URL, {'identifier': 'alice@example.com'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json()['detail'],
                         'اگر این حساب وجود داشته باشد، لینکِ بازیابی به ایمیلِ شما ارسال شد.')


@patch.object(SimpleRateThrottle, 'THROTTLE_RATES', _THROTTLE_TEST_RATES)
class PasswordResetThrottleTests(BaseAPITestCase):
    """نرخِ درخواستِ بازیابی — همان مکانیکِ ThrottlingAPITests (نرخ‌هایِ
    کوچک‌شده روی کلاس patch می‌شوند چون DRF نرخ‌ها را زمانِ import
    snapshot می‌گیرد؛ نگاشتِ env→نرخ جداگانه اثبات شده)."""

    def setUp(self):
        super().setUp()
        self.alice.email = 'alice@example.com'
        self.alice.save(update_fields=['email'])

    def test_reset_request_burst_gets_throttled(self):
        """بورستِ درخواستِ لینک از یک IP → سومی ۴۲۹ + Retry-After (scope auth)."""
        for _ in range(2):
            resp = self.client.post(_RESET_URL, {'identifier': 'alice@example.com'}, format='json')
            self.assertEqual(resp.status_code, status.HTTP_200_OK)
        resp = self.client.post(_RESET_URL, {'identifier': 'alice@example.com'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertTrue(str(resp['Retry-After']).isdigit())

    def test_confirm_endpoint_is_anon_scoped_not_auth_scoped(self):
        """confirm از scopeِ auth نیست (رازش توکن است) ولی anon سقفش را
        می‌گذارد — سه درخواستِ ردشدهِ پشتِ‌سرِهم، سومی ۴۲۹. توکنِ عمداً
        دستکاری‌شده است تا هر سه درخواستِ «رد» معنادار بمانند (۴۰۰) و سقفِ
        نرخ روی همان مسیر آزموده شود (نخستینِ معتبر ۲۰۰ می‌شد و token را
        مصرف می‌کرد — رشته‌ی ردشدهِِ تکرارپذیرِ پایدارتر است)."""
        uid, _ = _make_reset_link(self.alice)
        payload = {'uid': uid, 'token': 'tampered-token-value', 'new_password': 'pw-12345678'}
        for _ in range(2):
            resp = self.client.post(_RESET_CONFIRM_URL, payload, format='json')
            self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        resp = self.client.post(_RESET_CONFIRM_URL, payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_429_TOO_MANY_REQUESTS)


class PasswordResetConfirmAPITests(BaseAPITestCase):
    """POST /api/auth/password/reset/confirm/ — تعیینِ رمزِ جدید با لینک.

    ماتریسِ رد: فیلدِ غایب / uidِ خراب / tokenِ خراب / tokenِ کاربرِ دیگر /
    tokenِ مصرف‌شده / tokenِ منقضی / حسابِ غیرفعال — همه ۴۰۰ با پیامِ واحدِ
    «نامعتبر یا منقضی» (بدونِ افشایِ اینکه کدام). ماتریسِ پذیرش: رمزِ قوی +
    لینکِ تازه = ۲۰۰ و بدونِ صدورِ توکن (ورودِ تازه لازم است).
    """

    def setUp(self):
        super().setUp()
        self.carol = User.objects.create_user(
            username='carol', email='carol@example.com', password='pw-old-pass-123',
        )

    def _confirm(self, uid, token, new_password='pw-brand-new-456', **client_kwargs):
        """POST confirm — kwargsهای اضافی به‌عنوانِ هدرِ درخواست (مثل
        HTTP_ACCEPT_LANGUAGE) به client.post می‌روند، نه داخلِ بدنه."""
        return self.client.post(
            _RESET_CONFIRM_URL,
            {'uid': uid, 'token': token, 'new_password': new_password},
            format='json',
            **client_kwargs,
        )

    def test_happy_path_resets_password_and_requires_fresh_login(self):
        """مسیرِ کاملِ موفق: ۲۰۰ + رمزِ قدیمی مرد + رمزِ جدید زنده است."""
        uid, token = _make_reset_link(self.carol)
        resp = self._confirm(uid, token)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json()['detail'],
                         'رمز عبور با موفقیت بازنشانی شد؛ لطفاً با رمزِ جدید وارد شوید.')
        # ورودِ تازه با رمزِ قدیمی → 401؛ با رمزِ جدید → 200:
        old_login = self.client.post('/api/auth/login/',
                                     {'username': 'carol', 'password': 'pw-old-pass-123'},
                                     format='json')
        self.assertEqual(old_login.status_code, status.HTTP_401_UNAUTHORIZED)
        new_login = self.client.post('/api/auth/login/',
                                     {'username': 'carol', 'password': 'pw-brand-new-456'},
                                     format='json')
        self.assertEqual(new_login.status_code, status.HTTP_200_OK)

    def test_success_response_issues_no_tokens(self):
        """بازیابیِ موفق عمداً توکن صادر نمی‌کند — ورودِ تازه لازم است (شواهد
        مالکیتِ ایمیل به نشستِ خودکار تبدیل نشود)."""
        uid, token = _make_reset_link(self.carol)
        resp = self._confirm(uid, token)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        body = resp.json()
        self.assertNotIn('access', body)
        self.assertNotIn('refresh', body)

    def test_weak_password_rejected_with_policy_messages(self):
        """رمزِ جدید از همان سیاستِ ثبت‌نام می‌گذرد — پیام‌هایِ جنگو (fa)."""
        uid, token = _make_reset_link(self.carol)
        resp = self._confirm(uid, token, new_password='12345678')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        messages = resp.json()['new_password']
        self.assertTrue(any('رایج' in message for message in messages),
                        msg=messages)

    def test_password_similar_to_username_rejected(self):
        """UserAttributeSimilarity: رمزِ شبیهِ نامِ کاربری رد می‌شود."""
        similar_user = User.objects.create_user(
            username='roberta', email='roberta@example.com', password='pw-old-pass-123',
        )
        uid, token = _make_reset_link(similar_user)
        resp = self._confirm(uid, token, new_password='roberta1234')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('new_password', resp.json())

    def test_missing_fields_returns_400(self):
        """هر سه فیلد لازم‌اند؛ غیبتِ هرکدام → ۴۰۰ با پیامِ راهنما."""
        uid, token = _make_reset_link(self.carol)
        resp = self.client.post(_RESET_CONFIRM_URL, {'uid': uid, 'token': token},
                                format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.json()['detail'],
                         'هر سه فیلد uid، token و new_password لازمند.')

    def test_invalid_uid_returns_400(self):
        """uidِ دست‌کاری‌شده → همان ۴۰۰ واحد (کاربر وجود داشت یا نه، فرقی
        در پاسخ نیست)."""
        resp = self._confirm('not-a-valid-uid', 'whatever-token')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.json()['detail'], 'لینکِ بازیابی نامعتبر یا منقضی شده است.')

    def test_invalid_token_returns_400(self):
        uid, _ = _make_reset_link(self.carol)
        resp = self._confirm(uid, 'tampered-token-value')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.json()['detail'], 'لینکِ بازیابی نامعتبر یا منقضی شده است.')

    def test_token_of_other_user_rejected(self):
        """tokenِ آلیس + uidِ کارول = جعلِ ساده؛ مولد ردش می‌کند (امضا به
        وضعیتِ کاربر وصل است، نه فقط به SECRET_KEY)."""
        uid, _ = _make_reset_link(self.carol)
        _, alice_token = _make_reset_link(self.alice)
        resp = self._confirm(uid, alice_token)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_token_is_single_use(self):
        """بارِ اول موفق، بارِ دوم با همان token → ۴۰۰ و رمز همانِ اول
        می‌ماند (هشِ رمز در توکن است؛ تغییرش توکن را می‌کشد)."""
        uid, token = _make_reset_link(self.carol)
        first = self._confirm(uid, token, new_password='pw-first-reset-1')
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        second = self._confirm(uid, token, new_password='pw-second-reset-2')
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        # رمزِ نهایی همانِ اول است، نه دومی:
        second_login = self.client.post('/api/auth/login/',
                                        {'username': 'carol', 'password': 'pw-second-reset-2'},
                                        format='json')
        self.assertEqual(second_login.status_code, status.HTTP_401_UNAUTHORIZED)
        first_login = self.client.post('/api/auth/login/',
                                       {'username': 'carol', 'password': 'pw-first-reset-1'},
                                       format='json')
        self.assertEqual(first_login.status_code, status.HTTP_200_OK)

    def test_expired_token_rejected(self):
        """tokenِ درست ولی «از آینده» سنجیده می‌شود (PASSWORD_RESET_TIMEOUT
        گذشته) → همان ۴۰۰ِ واحد. _now مولدِ جنگو mock می‌شود (تستِ قطعی،
        بدونِ sleep)."""
        uid, token = _make_reset_link(self.carol)
        future = datetime.now() + timedelta(
            seconds=django_settings.PASSWORD_RESET_TIMEOUT + 5,
        )
        with patch.object(default_token_generator, '_now', return_value=future):
            resp = self._confirm(uid, token)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.json()['detail'], 'لینکِ بازیابی نامعتبر یا منقضی شده است.')

    def test_english_error_messages(self):
        """پیام‌هایِ confirm با Accept-Language: en انگلیسی می‌شوند."""
        uid, _ = _make_reset_link(self.carol)
        resp = self._confirm(uid, 'bad-token', HTTP_ACCEPT_LANGUAGE='en')
        self.assertEqual(resp.json()['detail'],
                         'The recovery link is invalid or has expired.')

    def test_inactive_user_cannot_use_link(self):
        """حسابِ غیرفعالْ حتی با لینکِ معتبر هم بازیابی نمی‌کند (۴۰۰ واحد)."""
        uid, token = _make_reset_link(self.carol)
        self.carol.is_active = False
        self.carol.save(update_fields=['is_active'])
        resp = self._confirm(uid, token)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


@override_settings(**_LOCMEM)
class PasswordResetSessionInvalidationTests(BaseAPITestCase):
    """بازیابیِ موفق = همان تضمینِ تغییرِ رمز (2026-09-10): همه‌ی نشست‌هایِ
    قبلی — Refresh (لیستِ سیاه) و حتی Access زنده (password_changed_at) —
    همان لحظه می‌میرند. مسیرِ کاملِ API: درخواستِ لینک → بازکردنِ ایمیل →
    confirm (بدونِ دستکاریِ مستقیمِ مدل)."""

    def setUp(self):
        super().setUp()
        self.carol = User.objects.create_user(
            username='carol', email='carol@example.com', password='pw-old-pass-123',
        )

    def test_all_old_tokens_die_after_reset(self):
        """ورودِ قبلِ بازیابی (توکن‌هایِ زنده) → بعدِ confirm همه ۴۰۱."""
        # نشستِ قبل از بازیابی (یک login واقعی تا OutstandingToken ساخته شود):
        login = self.client.post('/api/auth/login/',
                                 {'username': 'carol', 'password': 'pw-old-pass-123'},
                                 format='json')
        self.assertEqual(login.status_code, status.HTTP_200_OK)
        old_access = login.json()['access']
        old_refresh = login.json()['refresh']

        # جریانِ بازیابی از خودِ API (درخواست → لینک از ایمیل → تعیینِ رمز):
        self.client.post(_RESET_URL, {'identifier': 'carol@example.com'}, format='json')
        self.assertEqual(len(mail.outbox), 1)
        link = _extract_link_from_email(mail.outbox[0])
        query = dict(pair.split('=', 1) for pair in link.split('?', 1)[1].split('&'))
        resp = self.client.post(
            _RESET_CONFIRM_URL,
            {'uid': query['uid'], 'token': query['token'], 'new_password': 'pw-brand-new-456'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        # کلِ تست در «همانِ ثانیه» اجرا می‌شود و مرزِ مستندشده (پنجره‌ی
        # یک‌ثانیه‌ایِ docstringِ authentication.py) توکنِ صادرشده در همان
        # ثانیه را زنده نگه می‌دارد. در دنیای واقعی نشستِ قبلِ بازیابی همیشه
        # بیش از یک ثانیه عمر دارد؛ همین فاصله را با مهرِ زمان شبیه‌سازی
        # می‌کنیم — همانِ الگویِ StaleAccessTokenInvalidationTests و بدونِ
        # sleep؛ سازوکار (iat در برابرِ password_changed_at) آنجا مستقیم
        # تست شده و اینجا «عملی‌بودنِ سیم‌کشی» (confirm →
        # _invalidate_all_sessions → پروفایل) اثبات می‌شود:
        profile = UserSecurityProfile.objects.get(user=self.carol)
        profile.password_changed_at = timezone.now() + timedelta(seconds=2)
        profile.save(update_fields=['password_changed_at'])

        # توکنِ دسترسیِ قبلِ بازیابی → 401 با کدِ password_changed:
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f'Bearer {old_access}')
        resp = api.get('/api/subjects/')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
        # توکنِ Refreshِ قبلِ بازیابی → 401 (لیستِ سیاه):
        resp = self.client.post('/api/auth/refresh/', {'refresh': old_refresh}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        # و مهرِ زمانِ تغییر هم ثبت شده (معیارِ لایه‌ی authentication) — همان
        # پروفایلی که بالا برای شبیه‌سازیِ فاصله جابه‌جا شد، خودِ confirm ساخته:
        self.assertIsNotNone(profile.password_changed_at)

    def test_other_users_sessions_unaffected(self):
        """بازیابیِ کارول به نشستِ باب نمی‌زند — جداسازیِ کاربر-به-کاربر."""
        bob_client = self.client_as(self.bob)
        self.assertEqual(bob_client.get('/api/subjects/').status_code, status.HTTP_200_OK)

        uid, token = _make_reset_link(self.carol)
        self.client.post(
            _RESET_CONFIRM_URL,
            {'uid': uid, 'token': token, 'new_password': 'pw-brand-new-456'},
            format='json',
        )

        self.assertEqual(bob_client.get('/api/subjects/').status_code, status.HTTP_200_OK)
        self.assertFalse(UserSecurityProfile.objects.filter(user=self.bob).exists())


class PasswordResetSettingsTests(SimpleTestCase):
    """متغیرهایِ محیطیِ ایمیل/بازیابی — هم‌الگویِ ThrottleAndSecuritySettingsTests:
    مقادیرِ پیش‌فرضِ dev-safe + «بوتِ واقعیِ» Production با مفسرِ جدا."""

    _ENV_KEYS = (
        'DJANGO_SECRET_KEY', 'DJANGO_DEBUG', 'DJANGO_ALLOWED_HOSTS',
        'DJANGO_CORS_ALLOW_ALL', 'DJANGO_ALLOWED_ORIGINS', 'DATABASE_URL',
        'DJANGO_ANON_THROTTLE_RATE', 'DJANGO_USER_THROTTLE_RATE',
        'DJANGO_AUTH_THROTTLE_RATE', 'DJANGO_SECURE_SSL_REDIRECT',
        'DJANGO_COOKIES_SECURE', 'DJANGO_HSTS_SECONDS',
        'DJANGO_PROXY_SSL_HEADER', 'DJANGO_EMAIL_BACKEND',
        'DJANGO_EMAIL_HOST', 'DJANGO_EMAIL_PORT', 'DJANGO_EMAIL_HOST_USER',
        'DJANGO_EMAIL_HOST_PASSWORD', 'DJANGO_EMAIL_USE_TLS',
        'DJANGO_DEFAULT_FROM_EMAIL', 'DJANGO_PASSWORD_RESET_TIMEOUT',
        'DJANGO_FRONTEND_BASE_URL',
    )

    def _boot(self, extra_env, code):
        """مفسرِ تازه‌ای با متغیرهایِ داده‌شده بالا می‌آورد و نتیجه را برمی‌گرداند."""
        env = os.environ.copy()
        env['DJANGO_SETTINGS_MODULE'] = 'backend.settings'
        for key in self._ENV_KEYS:
            env.pop(key, None)          # نشتِ محیطِ تست به نتیجه نداشته باشد
        env.update(extra_env)
        return subprocess.run(
            [sys.executable, '-c', code],
            capture_output=True, text=True, env=env,
            cwd=str(Path(__file__).resolve().parents[1]),   # پوشه‌ی backend/
            timeout=90,
        )

    def test_default_email_settings_are_dev_safe(self):
        """بدونِ هیچ متغیری: console backend (ایمیل در stdout، بی‌اتصالِ
        SMTP) + عمرِ یک‌ساعته + مبدأِ runserverِ محلی — نکته‌ی ۶.۱۰."""
        code = (
            'import django; django.setup(); from django.conf import settings; '
            "assert settings.EMAIL_BACKEND == "
            "'django.core.mail.backends.console.EmailBackend', 'BACKEND'; "
            'assert settings.PASSWORD_RESET_TIMEOUT == 3600, "TIMEOUT"; '
            "assert settings.FRONTEND_BASE_URL == 'http://127.0.0.1:8000', 'BASE'; "
            'assert settings.DEFAULT_FROM_EMAIL == "webmaster@localhost", "FROM"; '
            'print("dev-ok")'
        )
        result = self._boot({}, code)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn('dev-ok', result.stdout)

    def test_boot_prod_applies_email_env_values(self):
        """همه‌ی متغیرهایِ ایمیل از محیط خوانده و اعمال می‌شوند."""
        key = 'p' * 64
        code = (
            'import django; django.setup(); from django.conf import settings; '
            "assert settings.EMAIL_BACKEND == "
            "'django.core.mail.backends.smtp.EmailBackend', 'BACKEND'; "
            "assert settings.EMAIL_HOST == 'smtp.example.com', 'HOST'; "
            'assert settings.EMAIL_PORT == 465, "PORT"; '
            "assert settings.EMAIL_HOST_USER == 'mailer@example.com', 'USER'; "
            "assert settings.EMAIL_HOST_PASSWORD == 'secret', 'PASS'; "
            'assert settings.EMAIL_USE_TLS is False, "TLS"; '
            "assert settings.DEFAULT_FROM_EMAIL == 'no-reply@example.com', 'FROM'; "
            'assert settings.PASSWORD_RESET_TIMEOUT == 1800, "TIMEOUT"; '
            "assert settings.FRONTEND_BASE_URL == 'https://planner.example.com', 'BASE'; "
            'print("email-ok")'
        )
        result = self._boot(
            {'DJANGO_DEBUG': 'false', 'DJANGO_SECRET_KEY': key,
             'DJANGO_ALLOWED_HOSTS': 'example.com',
             'DJANGO_EMAIL_BACKEND': 'django.core.mail.backends.smtp.EmailBackend',
             'DJANGO_EMAIL_HOST': 'smtp.example.com',
             'DJANGO_EMAIL_PORT': '465',
             'DJANGO_EMAIL_HOST_USER': 'mailer@example.com',
             'DJANGO_EMAIL_HOST_PASSWORD': 'secret',
             'DJANGO_EMAIL_USE_TLS': 'off',
             'DJANGO_DEFAULT_FROM_EMAIL': 'no-reply@example.com',
             'DJANGO_PASSWORD_RESET_TIMEOUT': '1800',
             'DJANGO_FRONTEND_BASE_URL': 'https://planner.example.com'},
            code,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn('email-ok', result.stdout)

    def test_boot_prod_warns_on_console_email_backend(self):
        """DEBUG=false + backendِ console = هشدارِ صادقانه در stderr (بوت
        متوقف نمی‌شود — الگویِ هشدارهایِ SQLite/throttle)."""
        key = 'p' * 64
        result = self._boot(
            {'DJANGO_DEBUG': 'false', 'DJANGO_SECRET_KEY': key,
             'DJANGO_ALLOWED_HOSTS': 'example.com'},
            'import django; django.setup(); print("booted")',
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn('console email backend', result.stderr)
        self.assertIn('booted', result.stdout)

    def test_boot_invalid_timeout_refuses_to_boot(self):
        """عمرِ صفر/منفیِ لینک بی‌معناست → fail-fast با نامِ متغیر در پیام."""
        for bad in ('0', '-60'):
            result = self._boot({'DJANGO_PASSWORD_RESET_TIMEOUT': bad},
                                'import django; django.setup()')
            self.assertNotEqual(result.returncode, 0, msg=bad)
            self.assertIn('DJANGO_PASSWORD_RESET_TIMEOUT', result.stderr)
