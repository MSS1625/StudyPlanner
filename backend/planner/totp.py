# planner/totp.py
# ----------------------------------------------------------------------------
# «کدِ یک‌بارمصرفِ زمان‌محور» (TOTP — RFC 6238) برایِ ورودِ دومرحله‌ای
# (از 2026-09-14).
#
# چرا پیاده‌سازیِ دستی و نه کتابخانه‌ی pyotp؟ پروژه تا امروز عمداً هیچ
# وابستگیِ جدیدی به requirements.txt اضافه نکرده (کاربرِ پروژه محیطِ pipِ
# پایداری ندارد و هر Task باید با «pip install هیچ» اعمال شود — همان اصلِ
# Taskهای ML و بازیابیِ رمز). خبرِ خوب: TOTP کلاً به چیزِ خاصی نیاز ندارد؛
# کلِ الگوریتم = HMAC-SHA1 + برشِ پویا (Dynamic Truncation) و همه‌ی این‌ها
# در کتابخانه‌ی استانداردِ پایتون (hmac/hashlib/struct/base64/secrets)
# هستند. این فایل ~۱۰۰ خطِ خالص و بدونِ ORM است — مثلِ ml.py جدا از
# لایه‌ی API تا در تست‌هایِ بدونِ DB (SimpleTestCase) هم اجرا شود.
#
# الگوریتم (RFC 4226 §5.3 + RFC 6238 §4):
#   ۱) کلیدِ مشترکِ base32 → بایت‌ها؛  ۲) شمارنده = زمانِ یونیکس ÷ گامِ ۳۰ثانیه‌ای؛
#   ۳) HMAC-SHA1(کلید، شمارنده‌ی big-endianِ ۸بایتی)؛
#   ۴) «برشِ پویا»: بایتِ آخر & 0x0F = جابه‌جایی؛ ۴ بایت از آن نقطه &
#      0x7FFFFFFF؛  ۵) mod 10^رقم → کدِ ۶رقمیِ صفرپُرشده.
#
# سازگاری: همین پارامترها (SHA1 / ۶ رقم / ۳۰ ثانیه) پیش‌فرضِ همه‌ی
# اپلیکیشن‌هایِ احرازگر (Google Authenticator، Aegis، Microsoft
# Authenticator و…) است — پس کدِ همین ماژول با گوشیِ کاربر جور است.
# ----------------------------------------------------------------------------

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

# پارامترهایِ ثابتِ رفتار (نه تنظیمِ استقرار — مثلِ RETENTION_LIMIT عمداً
# ثابت‌اند چون مقدارِ دیگر یعنی ناسازگاری با اپلیکیشنِ احرازگرِ کاربر).
DEFAULT_STEP = 30          # طولِ هر گامِ زمانی به ثانیه
DEFAULT_DIGITS = 6         # طولِ کد
VERIFY_WINDOW = 1          # پذیرشِ کدِ یک گام قبل/بعد (خطای ساعتِ گوشی)

# نامِ صادرشونده‌ی ثابتِ شناسنامه — برچسبِ حساب در اپلیکیشنِ احرازگر.
ISSUER = 'Smart Study Planner'


def generate_secret(nbytes=20):
    """کلیدِ مشترکِ تازه به‌صورتِ base32 (۳۲ نویسه برایِ ۲۰ بایت).

    ۲۰ بایت = ۱۶۰ بیت — همانِ پیشنهادِ RFC 4226 §4 (طولِ کلیدِ HMAC-SHA1).
    الفبایِ خروجیِ base32 (A-Z و 2-7) عمداً حروفِ بزرگ و بدونِ نویسه‌هایِ
    گیج‌کننده‌ی 0/O و 1/I است — تایپِ دستیِ کاربر راحت‌تر و خطایش کمتر است.
    """
    return base64.b32encode(secrets.token_bytes(nbytes)).decode('ascii')


def _decode_secret(secret):
    """base32 → بایت‌ها، باِ مدارایِ ورودیِ انسانی.

    اپلیکیشن‌هایِ احرازگر کلید را با فاصله/خط‌تیره و حروفِ کوچک نشان
    می‌دهند؛ رمزگشایی این‌جا همه را نرمال می‌کند (حذفِ فاصله‌ها + بزرگ‌
    کردنِ حروف + پُرکردنِ padding) تا همان کلیدِ ذخیره‌شده دربیاید.
    """
    normalized = (secret or '').strip().replace(' ', '').replace('-', '').upper()
    padding = '=' * (-len(normalized) % 8)
    return base64.b32decode(normalized + padding, casefold=True)


def _code_at_counter(key, counter, digits):
    """هسته‌ی RFC 4226: کدِ HOTP برایِ یک شمارنده‌ی مشخص."""
    digest = hmac.new(key, struct.pack('>Q', counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    # & 0x7FFFFFFF یعنی بی‌اهمیت‌کردنِ بیتِ علامت (۳۱ بیتِ پایین).
    truncated = struct.unpack('>I', digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(truncated % (10 ** digits)).zfill(digits)


def current_step(timestamp=None, step=DEFAULT_STEP):
    """شماره‌ی گامِ زمانیِ «الان» (زمانِ یونیکس ÷ گام — صفرِ هر گام)."""
    if timestamp is None:
        timestamp = time.time()
    return int(timestamp // step)


def totp_code(secret, timestamp=None, step=DEFAULT_STEP, digits=DEFAULT_DIGITS):
    """کدِ «لحظه‌یِ» کلید — همان چیزی که اپلیکیشنِ احرازگر نشان می‌دهد.

    (کاربردِ اصلی: تست‌ها و اثبات‌هایِ زنده — سرورِ تولیدی فقط verify می‌کند
    و هرگز کد نمی‌سازد؛ ساختِ کد وظیفه‌ی اپلیکیشنِ گوشیِ کاربر است.)
    """
    key = _decode_secret(secret)
    return _code_at_counter(key, current_step(timestamp, step), digits)


def verify_totp(
    secret, code, timestamp=None, step=DEFAULT_STEP, digits=DEFAULT_DIGITS,
    window=VERIFY_WINDOW, last_used_step=None,
):
    """کدِ واردشده را با کلید بسنجد — خروجی «شماره‌ی گامِ» منطبق یا None.

    - مقایسه با hmac.compare_digest (ثابت‌زمان) — کانالِ زمانی به مهاجمِ
      اندازه‌گیرنده‌یِ پاسخ، چیزی نمی‌دهد.
    - window=۱ یعنی کدِ «گامِ قبل» و «گامِ بعدِ» هم پذیرفته می‌شود (خطای
      عادیِ ساعتِ گوشی/سرور تا ~۳۰ ثانیه). پذیرشِ هر دو جهت، رفتارِ
      استانداردِ pyotp و اکثرِ پیاده‌سازی‌هاست.
    - last_used_step: «ضدِ پخشِ مجدد» (replay) — گام‌هایِ <= آن رد می‌شوند؛
      یعنی همان کدی که یک‌بار پذیرفته شد، دوباره کار نمی‌کند (RFC 6238
      §5.2: کد باید یک‌بارمصرف باشد). None یعنی هنوز هیچ کدی مصرف نشده.
    - خروجیِ «گام» (نه True) تا فراخواننده بتواند همان را در
      UserSecurityProfile.last_used_totp_step ذخیره کند. اگر چند گامِ
      کاندید منطبق بودند (تصادفی و نادر)، بزرگ‌ترین برمی‌گردد تا مصرفِ
      آینده سخت‌گیرانه‌تر بماند (امنیت > بخشش).
    """
    code = (code or '').strip()
    if len(code) != digits or not code.isdigit():
        return None

    key = _decode_secret(secret)
    base = current_step(timestamp, step)

    matched = None
    for candidate in range(base - window, base + window + 1):
        if candidate < 0:
            continue
        if last_used_step is not None and candidate <= last_used_step:
            continue
        if hmac.compare_digest(_code_at_counter(key, candidate, digits), code):
            matched = candidate if matched is None else max(matched, candidate)
    return matched


def build_otpauth_uri(secret, username, issuer=ISSUER):
    """لینکِ استانداردِ ثبتِ حساب در اپلیکیشنِ احرازگر (otpauth://).

    همه‌ی پارامترها صریح‌اند (algorithm/digits/period) حتی جایی که پیش‌فرضِ
    عرف‌اند — اپلیکیشن‌هایِ محافظه‌کار با پیش‌فرضِ ضمنی بد رفتار می‌کنند.
    «issuer:username» باید URL-encode شود (RFC 6238 §7 با ارجاع به otpauth
    URI scheme)؛ issuer دو جا هست: در برچسب (بعد از ://) و در query — هر دو
    برایِ سازگاریِ حداکثری با اپ‌هایِ مختلف.
    """
    label = quote(f'{issuer}:{username}', safe='')
    return (
        f'otpauth://totp/{label}'
        f'?secret={secret}'
        f'&issuer={quote(issuer, safe="")}'
        f'&algorithm=SHA1&digits={DEFAULT_DIGITS}&period={DEFAULT_STEP}'
    )
