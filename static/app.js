// static/app.js
// ----------------------------------------------------------------------------
// این تک‌فایل، تمام منطق جاوااسکریپتیِ فرانت‌اند است (بدون هیچ فریم‌ورکی مثل
// React/Vue). هر صفحه‌ی HTML این فایل را <script src="app.js"> می‌کند و بر
// اساس ویژگیِ data-page روی تگ <body> (نگاه کنید به انتهای همین فایل)،
// تابعِ init مخصوصِ همان صفحه اجرا می‌شود.
//
// ساختار کلیِ فایل (از بالا به پایین):
//   ۱) تنظیمات پایه (آدرس API، سلکتورهای DOM، کلیدهای localStorage)
//   ۲) توابع کمکیِ ارتباط با API (apiRequest/apiGet/apiPost/apiDelete)
//   ۳) توابع کمکیِ رابط کاربریِ مشترک (Toast، وضعیتِ اتصال، سایدبار)
//   ۴) توابعِ مخصوص هر صفحه (داشبورد، درس‌ها، امتحان‌ها، ثبت مطالعه، برنامه)
//   ۵) روترِ سبک در انتهای فایل که تابعِ init درست را صدا می‌زند
// ----------------------------------------------------------------------------

// آدرسِ پایه‌ی سرور بک‌اند (Django). چون فرانت‌اند و بک‌اند دو پروژه‌ی جدا
// هستند، هر درخواست باید این آدرس را جلوی مسیرِ API بگذارد.
const API_BASE = 'http://127.0.0.1:8000';

// نگاشتِ اسمِ خوانا -> مسیرِ واقعیِ API؛ این‌طوری اگر یک روز آدرسِ API عوض
// شود، فقط همین‌جا را باید ویرایش کرد، نه همه‌جای کد را.
const endpoints = {
    login: '/api/auth/login/',
    tokenRefresh: '/api/auth/refresh/',
    // خروجِ سرور-محور (از 2026-09-08): توکنِ Refresh به سرور فرستاده می‌شود
    // تا باطل شود (لیستِ سیاه) — نه فقط پاک‌شدن از مرورگر.
    logout: '/api/auth/logout/',
    // تغییرِ رمزِ عبور (از 2026-09-10): رمزِ فعلی + رمزِ جدید می‌فرستد؛ سرور
    // همه‌ی نشست‌هایِ دیگر را باطل می‌کند و جفتِ توکنِ تازه در پاسخ برمی‌گرداند.
    passwordChange: '/api/auth/password/',
    // بازیابیِ رمزِ فراموش‌شده (از 2026-09-12): «ایمیل برو» (identifier = نامِ
    // کاربری یا ایمیل؛ پاسخِ همیشگیِ عمومی) و «تعیینِ رمزِ جدید» با uid/token
    // که از لینکِ ایمیل آمده‌اند. هر دو بی‌لاگین‌اند (skipAuth).
    passwordReset: '/api/auth/password/reset/',
    passwordResetConfirm: '/api/auth/password/reset/confirm/',
    register: '/api/auth/register/',
    dashboard: '/api/dashboard/',
    subjects: '/api/subjects/',
    subjectDetail: (id) => `/api/subjects/${id}/`,
    exams: '/api/exams/',
    examDetail: (id) => `/api/exams/${id}/`,
    studyPlan: (range) => `/api/study-plan/?range=${range}`,
    studyPlanGenerate: '/api/study-plan/generate/',
    // پیش‌بینیِ هوشمند (از 2026-09-09): مؤلفه‌ی یادگیریِ آماری — مدلِ
    // کالیبراسیون + ساعتِ واقعیِ پیش‌بینی‌شده برایِ امتحان‌هایِ آینده
    predictions: '/api/predictions/',
    studyLogs: '/api/study-logs/',
    studyLogDetail: (id) => `/api/study-logs/${id}/`,
};

// سلکتورهای CSS برای عناصرِ مشترک بین همه‌ی صفحات (نوار وضعیت، دکمه‌ی خروج و...)
const selectors = {
    toast: '#toast',
    userGreeting: '#userGreeting',
    statusText: '#statusText',
    statusDot: '#statusDot',
    logoutButton: '#logoutButton',
    changePasswordButton: '#changePasswordButton',
    changePasswordModal: '#changePasswordModal',
    passwordResetModal: '#passwordResetModal',
    forgotPasswordLink: '#forgotPasswordLink',
    sidebarToggle: '#sidebarToggle',
    backdrop: '#backdrop',
};

// کلیدهایی که با آن‌ها اطلاعاتِ نشست (Session) در localStorage مرورگر ذخیره می‌شود
const storageKeys = {
    token: 'ssp_token',
    refreshToken: 'ssp_refresh_token',
    username: 'ssp_username',
};

// --- توابع کوچکِ خواندن/نوشتن/پاک‌کردنِ localStorage ---
// (توکنِ JWT و نامِ کاربری بعد از ورود، همین‌جا نگه‌داری می‌شوند)
const getToken = () => localStorage.getItem(storageKeys.token);
const setToken = (token) => localStorage.setItem(storageKeys.token, token);
const clearToken = () => localStorage.removeItem(storageKeys.token);
// توکنِ «تمدید» (Refresh): از 2026-09-06 کنارِ توکنِ دسترسی ذخیره می‌شود تا
// بعد از انقضایِ توکنِ دسترسی (۱ روز)، تمدیدِ بی‌صدا ممکن باشد.
const getRefreshToken = () => localStorage.getItem(storageKeys.refreshToken);
const setRefreshToken = (token) =>
    localStorage.setItem(storageKeys.refreshToken, token);
const clearRefreshToken = () =>
    localStorage.removeItem(storageKeys.refreshToken);
const setStoredUsername = (username) =>
    localStorage.setItem(storageKeys.username, username);
const getStoredUsername = () => localStorage.getItem(storageKeys.username);
const clearStoredUsername = () => localStorage.removeItem(storageKeys.username);

// ---------------------------------------------------------------------
// لایه‌ی ارتباط با API
// ---------------------------------------------------------------------

// نسخه اصلاح شده و هوشمند برای خواندن دقیق خطاهای جنگو
// این تابع «مرکزیِ» همه‌ی درخواست‌هاست: همه‌ی توابعِ apiGet/apiPost/apiDelete
// در نهایت همین تابع را صدا می‌زنند. مزیتش این است که هدرِ Authorization،
// تبدیلِ بدنه به JSON، و مدیریتِ خطا فقط یک‌بار (نه در هر تابع جداگانه) نوشته می‌شود.
const apiRequest = async (
    path,
    { method = 'GET', body, headers = {}, skipAuth = false, _isRetry = false } = {},
) => {
    const token = getToken();

    const finalHeaders = { ...headers };
    // چندزبانی (از 2026-09-09): زبانِ انتخابیِ کاربر به سرور هم اعلام می‌شود
    // تا پیام‌های خطای API (که gettext دارند) با همان زبان برگردند؛
    // Accept-Language جزو هدرهایِ safelistشده‌ی CORS است (preflight اضافه نمی‌سازد).
    finalHeaders['Accept-Language'] = currentLang() === 'en' ? 'en' : 'fa';
    // اگر توکن داریم و این درخواست نیاز به احراز هویت دارد (اکثرِ درخواست‌ها)،
    // آن را در هدرِ استاندارد Authorization: Bearer <token> می‌گذاریم.
    if (!skipAuth && token) {
        finalHeaders.Authorization = `Bearer ${token}`;
    }

    let payload = body;
    if (body && !(body instanceof FormData)) {
        // اگر بدنه یک آبجکتِ معمولی (نه FormData) است، به JSON تبدیلش می‌کنیم
        finalHeaders['Content-Type'] = 'application/json';
        payload = JSON.stringify(body);
    }

    // اگر مسیر از قبل یک URL کامل بود (با http شروع شود) همان را استفاده کن،
    // وگرنه API_BASE را جلویش بچسبان.
    const response = await fetch(
        path.startsWith('http') ? path : `${API_BASE}${path}`,
        {
            method,
            headers: finalHeaders,
            body: payload ?? undefined,
        },
    );

    // کدِ ۲۰۴ یعنی «موفق ولی بدونِ محتوا» (مثلاً بعد از DELETE موفق)
    if (response.status === 204) {
        return null;
    }

    // تلاش برای Parse کردنِ JSON؛ اگر پاسخ اصلاً JSON نبود، یک آبجکتِ خالی برگردان
    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
        // ۴۰۱ یعنی توکنِ دسترسیِ منقضی/بی‌اعتبار. استراتژی (از 2026-09-06): یک‌بار
        // بی‌صدا با توکنِ Refresh تمدید می‌کنیم و «همان درخواست» را دوباره می‌زنیم؛
        // اگر تمدید ممکن نشد (Refresh هم منقضی/ذخیره‌نشده) یا تکرارِ درخواست هم
        // ۴۰۱ داد، نشست واقعاً تمام است: توکن‌ها پاک و کاربر به صفحه‌ی ورود
        // هدایت می‌شود (با پیامِ «منقضی شد»).
        if (response.status === 401 && !skipAuth) {
            if (!_isRetry && getRefreshToken()) {
                const newToken = await refreshAccessToken();
                if (newToken) {
                    return apiRequest(path, {
                        method, body, headers, skipAuth, _isRetry: true,
                    });
                }
            }
            forceLogoutExpired();
            throw new Error(t('نشست شما منقضی شده است؛ لطفاً دوباره وارد شوید.'));
        }

        // اگر پاسخ کدِ خطا داشت (400/401/403/...)، سعی می‌کنیم مناسب‌ترین پیامِ
        // خطا را از بین شکل‌های مختلفی که DRF ممکن است برگرداند پیدا کنیم:
        let message = t('خطایی رخ داده است.');
        if (data?.detail) {
            message = data.detail;
        } else if (data?.message) {
            message = data.message;
        } else if (typeof data === 'object' && Object.keys(data).length > 0) {
            // حالتِ رایج در DRF: خطای اعتبارسنجیِ هر فیلد جدا برگردانده می‌شود
            // (مثلاً {"username": ["این نام قبلاً ثبت شده"]})؛ اولین مورد را نشان می‌دهیم.
            const firstKey = Object.keys(data)[0];
            if (Array.isArray(data[firstKey])) {
                message = `${firstKey}: ${data[firstKey][0]}`;
            } else {
                message = JSON.stringify(data);
            }
        }
        // با throw کردن یک خطا، توابعِ صدازننده (که این تابع را await کرده‌اند)
        // می‌توانند با try/catch خطا را بگیرند و به کاربر Toast نشان دهند.
        throw new Error(message);
    }

    return data;
};

// Wrapperهای کوچک روی apiRequest، فقط برای خواناتر شدنِ کدِ صدازننده
// (مثلاً apiGet(endpoints.subjects) به‌جای apiRequest(endpoints.subjects, {method: "GET"}))
const apiGet = (path, options) =>
    apiRequest(path, { ...options, method: 'GET' });
const apiPost = (path, body, options) =>
    apiRequest(path, { ...options, method: 'POST', body });
// PATCH برای ویرایشِ جزئیِ یک منبع (مثلاً ویرایشِ امتحان)؛ بدنه‌ی کامل فرستاده
// می‌شود ولی PATCH اجازه می‌دهد فیلدهای ارسالی همان‌ها اعمال شوند.
const apiPatch = (path, body, options) =>
    apiRequest(path, { ...options, method: 'PATCH', body });
const apiDelete = (path, options) =>
    apiRequest(path, { ...options, method: 'DELETE' });

// ---------------------------------------------------------------------
// تمدیدِ خودکارِ نشست (از 2026-09-06)
// ---------------------------------------------------------------------

// وقتی «کلِ نشست» از دست رفته باشد (توکنِ Refresh هم منقضی/بی‌اعتبار)،
// همه‌ی داده‌های نشست پاک و کاربر به صفحه‌ی ورود هدایت می‌شود؛ پارامترِ
// expired=1 باعث می‌شود صفحه‌ی ورود یک Toast توضیحی نشان بدهد، نه این‌که
// کاربر بی‌خبر وسطِ کار رها شود. اگر همین الان روی صفحه‌ی ورود هستیم،
// هدایتی انجام نمی‌شود (جلویِ هر نوعِ حلقه‌ی هدایت را می‌گیرد).
const forceLogoutExpired = () => {
    clearToken();
    clearRefreshToken();
    clearStoredUsername();
    if (document.body.dataset.page !== 'login') {
        window.location.href = 'login.html?expired=1';
    }
};

// تمدیدِ توکنِ دسترسی با توکنِ Refreshِ ذخیره‌شده. چند درخواستِ هم‌زمانِ ۴۰۱‌شده
// نباید چند بار تمدید بزنند؛ برای همین تا پایانِ تمدیدِ در جریان، همه‌ی
// صدازننده‌ها منتظرِ همان Promise واحد می‌مانند (dedupe).
let refreshPromise = null;
const refreshAccessToken = async () => {
    const refreshToken = getRefreshToken();
    if (!refreshToken) return null;

    if (!refreshPromise) {
        refreshPromise = (async () => {
            try {
                // skipAuth: این خودشِ درخواستِ تمدید است؛ نباید واردِ منطقِ ۴۰۱/
                // تمدیدِ apiRequest شود (وگرنه حلقه می‌سازیم).
                const data = await apiPost(
                    endpoints.tokenRefresh,
                    { refresh: refreshToken },
                    { skipAuth: true },
                );
                if (data?.access) setToken(data.access);
                // از 2026-09-08 چرخشِ توکنِ Refresh رویِ سرور فعال است (ROTATE_
                // REFRESH_TOKENS=True): هر تمدید، توکنِ Refreshِ تازه هم برمی‌گرداند
                // و قبلی باطل می‌شود؛ این سطر توکنِ تازه را ذخیره می‌کند تا زنجیره‌ی
                // تمدید ادامه پیدا کند (اگر ذخیره نشود، نشست بعد از اولین تمدید
                // تمام می‌شود — چون توکنِ قبلی دیگر قابلِ استفاده نیست).
                if (data?.refresh) setRefreshToken(data.refresh);
                return data?.access ?? null;
            } catch {
                // ۴۰۱/خطایِ سرور در خودِ تمدید = نشست تمام؛ null یعنی «تمدید نشد»
                return null;
            } finally {
                refreshPromise = null;
            }
        })();
    }
    return refreshPromise;
};

// ---------------------------------------------------------------------
// توابع کمکیِ رابط کاربریِ مشترک
// ---------------------------------------------------------------------

// گریختن (Escape) از کاراکترهای خاصِ HTML؛ برای هرجایی که داده‌ی کاربر با
// innerHTML رندر می‌شود لازم است تا متنِ کاربر نتواند به‌عنوانِ HTML تفسیر
// شود (جلوگیری از XSS). قاعده‌ی امنیتی: هر مقدارِ متنی که از API می‌آید —
// نام و یادداشتِ درس/امتحان/گزارش، پیام‌ها و برچسب‌ها — پیش از درج در
// innerHTML باید با escapeHtml بسته شود؛ همه‌ی رندرکننده‌ها
// (Subjects/Exams/StudyLogs/Dashboard/Plan) از آن استفاده می‌کنند.
// اعدادِ اعتبارسنجی‌شده‌ی سمتِ سرور (ساعت/درصد/تاریخ) بدون escape می‌مانند.
const escapeHtml = (value) =>
    String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');

// نمایشِ یک پیامِ کوچکِ موقت (Toast) در گوشه‌ی صفحه، برای موفقیت/خطا/اطلاع‌رسانی
const showToast = (message, type = 'info') => {
    const toast = document.querySelector(selectors.toast);
    if (!toast) return;
    toast.textContent = message;
    toast.classList.remove('is-visible');
    toast.dataset.type = type;
    // requestAnimationFrame باعث می‌شود کلاسِ is-visible در فریمِ بعدی اضافه
    // شود تا انیمیشنِ CSS (transition) واقعاً اجرا شود (نه این‌که چون کلاس
    // همان لحظه اضافه شده، مرورگر انیمیشن را رد کند).
    requestAnimationFrame(() => toast.classList.add('is-visible'));
    setTimeout(() => toast.classList.remove('is-visible'), 4200);
};

// نمایشِ «سلام، فلانی» در بالای صفحه، بر اساس نام کاربریِ ذخیره‌شده در مرورگر
const updateUserGreeting = () => {
    const label = document.querySelector(selectors.userGreeting);
    if (!label) return;
    const username = getStoredUsername();
    label.textContent = username
        ? t('👋 سلام، {username}', { username })
        : t('سلام دوست عزیز');
};

// به‌روزرسانیِ نشانگرِ کوچکِ وضعیت (آنلاین/در حال پردازش/خارج از سیستم) در سایدبار
const updateStatusIndicator = (status = 'online') => {
    const statusText = document.querySelector(selectors.statusText);
    const dot = document.querySelector(selectors.statusDot);
    if (!statusText || !dot) return;

    if (!getToken()) {
        statusText.textContent = t('خارج از سیستم');
        dot.style.background = '#9ca3af';
        dot.style.boxShadow = '0 0 0 6px rgba(156, 163, 175, 0.25)';
        return;
    }

    switch (status) {
        case 'online':
            statusText.textContent = t('آنلاین');
            dot.style.background = '#22c55e';
            dot.style.boxShadow = '0 0 0 6px rgba(34, 197, 94, 0.25)';
            break;
        case 'busy':
            statusText.textContent = t('در حال پردازش...');
            dot.style.background = '#facc15';
            dot.style.boxShadow = '0 0 0 6px rgba(250, 204, 21, 0.25)';
            break;
        default:
            statusText.textContent = t('نامشخص');
            dot.style.background = '#9ca3af';
            dot.style.boxShadow = '0 0 0 6px rgba(156, 163, 175, 0.25)';
    }
};

// اگر کاربر توکن ندارد (لاگین نکرده)، به‌زور به صفحه‌ی ورود می‌فرستیمش.
// این تابع در ابتدای init هر صفحه‌ی محافظت‌شده صدا زده می‌شود.
const requireAuth = () => {
    if (!getToken()) {
        window.location.href = 'login.html';
    }
};

// خروج از حساب (از 2026-09-08 سرور-محور): اول توکنِ Refresh با POST به
// /api/auth/logout/ رویِ سرور باطل می‌شود (لیستِ سیاه)، بعد داده‌های نشست از
// مرورگر پاک و کاربر به صفحه‌ی ورود برمی‌گردد. به این ترتیب حتی اگر کسی
// به localStorageِ دستگاهِ قدیمی دسترسی پیدا کند، توکنِ خروج‌شده دیگر
// قابلِ تمدید نیست (قبل از این تغییر، توکن تا پایانِ عمرش معتبر می‌ماند).
const logout = async () => {
    const refreshToken = getRefreshToken();
    if (refreshToken) {
        try {
            // skipAuth: این درخواست هدرِ Authorization نمی‌خواهد (خودِ توکنِ
            // Refresh اثباتِ هویت است) و نباید واردِ منطقِ ۴۰۱/تمدید شود.
            await apiPost(
                endpoints.logout,
                { refresh: refreshToken },
                { skipAuth: true },
            );
        } catch {
            // اگر سرور در دسترس نبود، خروجِ محلی همچنان انجام می‌شود؛ کاربر
            // نباید به‌خاطرِ قطعیِ سرور در حسابِ باز بماند. عمداً نادیده.
        }
    }
    clearToken();
    clearRefreshToken();
    clearStoredUsername();
    window.location.href = 'login.html';
};

// ---------------------------------------------------------------------
// تغییرِ رمزِ عبور (امنیتِ حساب — از 2026-09-10)
// ---------------------------------------------------------------------
// دکمه‌ی «تغییر رمز عبور» و پنجره‌یِ (مودالِ) فرمش هر دو با جاوااسکریپت
// ساخته می‌شوند، نه در HTMLِ صفحات — چون این رابط باید در «همه‌ی» صفحاتِ
// لاگین‌شده در دسترس باشد و هر ۷ فایلِ HTML فقط یک دکمه‌یِ خروجِ مشترک
// دارند (#logoutButton)؛ تزریقِ کنارِ همان دکمه، یک نقطه‌یِ حقیقت می‌سازد
// (فقط app.js) و HTMLها دست‌نخورده می‌مانند. مودال هم «تنها در لحظه‌یِ
// باز‌شدن» ساخته می‌شود تا برچسب‌هایش با زبانِ جاری (t()) رندر شوند.

// فرمِ مودال را (یک‌بار) می‌سازد و برمی‌گرداند. هیچ CSSِ جدیدِ خاصِ
// ساختار لازم نیست — از همان کلاس‌هایِ موجودِ فرم/دکمه استفاده می‌کند و
// پوششِ نیمه‌شفافِ صفحه فقط با چند کلاسِ pw- در styles.css.
const buildChangePasswordModal = () => {
    const overlay = document.createElement('div');
    overlay.id = 'changePasswordModal';
    overlay.className = 'pw-modal-overlay';
    overlay.hidden = true;

    const modal = document.createElement('div');
    modal.className = 'pw-modal';
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-modal', 'true');
    modal.setAttribute('aria-labelledby', 'pwModalTitle');

    const title = document.createElement('h3');
    title.id = 'pwModalTitle';
    title.textContent = t('تغییر رمز عبور حساب');

    const form = document.createElement('form');
    form.id = 'pwForm';
    form.className = 'pw-form';
    form.noValidate = true; // اعتبارسنجیِ خودکارِ مرورگر خاموش؛ پیام‌هایِ ما دوزبانه‌اند

    const fields = [
        { id: 'pwCurrent', label: t('رمز عبور فعلی'), autocomplete: 'current-password' },
        { id: 'pwNew', label: t('رمز عبور جدید'), autocomplete: 'new-password' },
        { id: 'pwConfirm', label: t('تکرار رمز عبور جدید'), autocomplete: 'new-password' },
    ];
    for (const field of fields) {
        const wrapper = document.createElement('div');
        wrapper.className = 'form-field';
        const label = document.createElement('label');
        label.htmlFor = field.id;
        label.textContent = field.label;
        const input = document.createElement('input');
        input.type = 'password';
        input.id = field.id;
        input.name = field.id;
        input.autocomplete = field.autocomplete;
        input.required = true;
        input.minLength = 8;
        wrapper.appendChild(label);
        wrapper.appendChild(input);
        form.appendChild(wrapper);
    }

    const hint = document.createElement('p');
    hint.className = 'field-hint';
    hint.textContent = t('رمز عبور باید حداقل ۸ نویسه باشد، با نام کاربری شما شبیه نباشد و از رمزهای رایج نباشد.');
    form.appendChild(hint);

    // خطای درونِ خودِ پنجره (به‌جای Toast که زیرِ پوششِ نیمه‌شفاف می‌مانَد):
    const errorBox = document.createElement('p');
    errorBox.id = 'pwError';
    errorBox.className = 'pw-error';
    errorBox.hidden = true;
    errorBox.setAttribute('role', 'alert');
    form.appendChild(errorBox);

    const actions = document.createElement('div');
    actions.className = 'pw-modal-actions';
    const cancelButton = document.createElement('button');
    cancelButton.type = 'button';
    cancelButton.className = 'ghost-button';
    cancelButton.id = 'pwCancel';
    cancelButton.textContent = t('انصراف');
    cancelButton.addEventListener('click', closeChangePasswordModal);
    const submitButton = document.createElement('button');
    submitButton.type = 'submit';
    submitButton.className = 'primary-button';
    submitButton.id = 'pwSubmit';
    submitButton.textContent = t('ذخیره‌ی رمز جدید');
    actions.appendChild(cancelButton);
    actions.appendChild(submitButton);
    form.appendChild(actions);

    form.addEventListener('submit', submitChangePassword);

    modal.appendChild(title);
    modal.appendChild(form);
    overlay.appendChild(modal);
    // کلیک روی پس‌زمینه‌یِ نیمه‌شفاف = بستن (کلیک داخلِ خودِ مودال نبسته می‌کند)
    overlay.addEventListener('click', (event) => {
        if (event.target === overlay) closeChangePasswordModal();
    });
    document.body.appendChild(overlay);
    return overlay;
};

const openChangePasswordModal = () => {
    const overlay =
        document.querySelector(selectors.changePasswordModal) ||
        buildChangePasswordModal();
    clearPwError();
    overlay.hidden = false;
    // فوکوس روی اولین فیلد تا کاربر بدونِ کلیکِ اضافه، مستقیم تایپ کند
    const first = overlay.querySelector('#pwCurrent');
    if (first) first.focus();
};

const setPwError = (message) => {
    const errorBox = document.querySelector('#pwError');
    if (!errorBox) return;
    errorBox.textContent = message;
    errorBox.hidden = false;
};

const clearPwError = () => {
    const errorBox = document.querySelector('#pwError');
    if (!errorBox) return;
    errorBox.textContent = '';
    errorBox.hidden = true;
};

const closeChangePasswordModal = () => {
    const overlay = document.querySelector(selectors.changePasswordModal);
    if (!overlay) return;
    overlay.hidden = true;
    // پاک‌سازیِ فیلدها و پیام‌ها برای باز‌شدنِ بعدی (رمزها هرگز در DOM نمانند)
    overlay.querySelectorAll('input').forEach((input) => {
        input.value = '';
        input.disabled = false;
    });
    const submit = overlay.querySelector('#pwSubmit');
    if (submit) submit.disabled = false;
    clearPwError();
};

// ثبتِ تغییرِ رمز: اعتبارسنجیِ سریعِ سمتِ کلاینت، بعد POST به سرور.
// در صورتِ موفقیت، جفتِ توکنِ تازه در پاسخ می‌آید و «همان‌جا» ذخیره می‌شود
// تا نشستِ همین مرورگر بی‌وقفه ادامه یابد — همه‌ی نشست‌هایِ دیگر (دستگاه‌های
// دیگر/توکن‌هایِ دزدیده‌شده) در همان لحظه با سمتِ سرور باطل شده‌اند.
const submitChangePassword = async (event) => {
    event.preventDefault();
    const overlay = document.querySelector(selectors.changePasswordModal);
    if (!overlay) return;

    const current = overlay.querySelector('#pwCurrent')?.value ?? '';
    const next = overlay.querySelector('#pwNew')?.value ?? '';
    const confirm = overlay.querySelector('#pwConfirm')?.value ?? '';

    // خطای تطابق/کوتاهی را همین‌جا نشان می‌دهیم (سرور هم همین‌ها را با
    // پیام‌های خودش برمی‌گرداند؛ این فقط پرشِ سریع‌تر است).
    if (next.length < 8) {
        setPwError(t('رمز عبور جدید باید حداقل ۸ نویسه باشد.'));
        return;
    }
    if (next !== confirm) {
        setPwError(t('رمزهای جدید یکسان نیستند.'));
        return;
    }

    const submitButton = overlay.querySelector('#pwSubmit');
    if (submitButton) submitButton.disabled = true;
    clearPwError();
    try {
        const body = await apiPost(endpoints.passwordChange, {
            current_password: current,
            new_password: next,
        });
        // توکن‌هایِ تازه‌یِ نشستِ جاری (پاسخِ سرور بعد از ابطالِ همه‌یِ توکن‌ها):
        if (body?.access) setToken(body.access);
        if (body?.refresh) setRefreshToken(body.refresh);
        closeChangePasswordModal();
        showToast(
            t('رمز عبور با موفقیت تغییر کرد؛ نشست‌های دیگر باطل شدند.'),
            'success',
        );
    } catch (error) {
        // پیامِ سرور (با زبانِ درخواست از طریقِ Accept-Language ترجمه‌شده) —
        // داخلِ خودِ پنجره، چون Toast زیرِ پوششِ نیمه‌شفاف دیده نمی‌شود:
        setPwError(error.message || t('خطا در تغییر رمز عبور.'));
        if (submitButton) submitButton.disabled = false;
    }
};

// دکمه‌یِ «تغییر رمز عبور» را کنارِ دکمه‌یِ خروج (در نوارِ بالا) تزریق
// می‌کند؛ اگر صفحه‌یِ لاگین/ثبت‌نام است (دکمه‌یِ خروج ندارد) هیچ کاری
// نمی‌کند — تغییرِ رمز فقط برایِ کاربرِ لاگین‌شده معنا دارد.
const injectChangePasswordButton = () => {
    const logoutButton = document.querySelector(selectors.logoutButton);
    if (!logoutButton) return;
    if (document.querySelector(selectors.changePasswordButton)) return;

    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'ghost-button';
    button.id = 'changePasswordButton';
    button.textContent = t('تغییر رمز عبور');
    button.addEventListener('click', (event) => {
        event.preventDefault();
        openChangePasswordModal();
    });
    // قبل ازِ دکمه‌یِ خروج می‌نشیند (خروج همیشه آخرین دکمه می‌ماند):
    logoutButton.parentNode.insertBefore(button, logoutButton);
};

// بستنِ مودال با کلیدِ Escape — رفتارِ استانداردِ پنجره‌هایِ سیستمی.
document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    const overlay = document.querySelector(selectors.changePasswordModal);
    if (overlay && !overlay.hidden) closeChangePasswordModal();
    const resetOverlay = document.querySelector(selectors.passwordResetModal);
    if (resetOverlay && !resetOverlay.hidden) closePasswordResetModal();
});

// ---------------------------------------------------------------------
// بازیابیِ رمزِ فراموش‌شده (از 2026-09-12) — دو قطعه:
//   ۱) مودالِ «ایمیلِ بازیابی بفرست» در صفحه‌ی ورود (لینکِ #forgotPasswordLink)
//   ۲) صفحه‌یِ reset-password.html برایِ تعیینِ رمزِ جدید با uid/token لینک
// ---------------------------------------------------------------------

// مودالِ درخواستِ لینک — الگوی همانِ مودالِ تغییرِ رمز (کلاس‌هایِ pw- موجود؛
// فقط در لحظه‌یِ باز‌شدن ساخته می‌شود تا برچسب‌ها با زبانِ جاری رندر شوند).
const buildPasswordResetModal = () => {
    const overlay = document.createElement('div');
    overlay.id = 'passwordResetModal';
    overlay.className = 'pw-modal-overlay';
    overlay.hidden = true;

    const modal = document.createElement('div');
    modal.className = 'pw-modal';
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-modal', 'true');
    modal.setAttribute('aria-labelledby', 'prModalTitle');

    const title = document.createElement('h3');
    title.id = 'prModalTitle';
    title.textContent = t('بازیابیِ رمزِ عبور');

    const form = document.createElement('form');
    form.id = 'prForm';
    form.className = 'pw-form';
    form.noValidate = true; // اعتبارسنجیِ خودکارِ مرورگر خاموش؛ پیام‌هایِ ما دوزبانه‌اند

    const wrapper = document.createElement('div');
    wrapper.className = 'form-field';
    const label = document.createElement('label');
    label.htmlFor = 'prIdentifier';
    label.textContent = t('نام کاربری یا ایمیل');
    const input = document.createElement('input');
    input.type = 'text';
    input.id = 'prIdentifier';
    input.name = 'identifier';
    input.autocomplete = 'username'; // شاید نامِ کاربری باشد؛ مرورگر پرشِ سریع بدهد
    input.required = true;
    input.autofocus = true;
    wrapper.appendChild(label);
    wrapper.appendChild(input);
    form.appendChild(wrapper);

    const hint = document.createElement('p');
    hint.className = 'field-hint';
    hint.textContent = t(
        'اگر حساب شما وجود داشته باشد، لینکِ بازیابی به ایمیلِ شما ارسال می‌شود.',
    );
    form.appendChild(hint);

    // خطای درونِ خودِ پنجره (به‌جای Toast که زیرِ پوششِ نیمه‌شفاف می‌مانَد):
    const errorBox = document.createElement('p');
    errorBox.id = 'prError';
    errorBox.className = 'pw-error';
    errorBox.hidden = true;
    errorBox.setAttribute('role', 'alert');
    form.appendChild(errorBox);

    const actions = document.createElement('div');
    actions.className = 'pw-modal-actions';
    const cancelButton = document.createElement('button');
    cancelButton.type = 'button';
    cancelButton.className = 'ghost-button';
    cancelButton.id = 'prCancel';
    cancelButton.textContent = t('انصراف');
    cancelButton.addEventListener('click', closePasswordResetModal);
    const submitButton = document.createElement('button');
    submitButton.type = 'submit';
    submitButton.className = 'primary-button';
    submitButton.id = 'prSubmit';
    submitButton.textContent = t('ارسالِ لینکِ بازیابی');
    actions.appendChild(cancelButton);
    actions.appendChild(submitButton);
    form.appendChild(actions);

    form.addEventListener('submit', submitPasswordResetRequest);

    modal.appendChild(title);
    modal.appendChild(form);
    overlay.appendChild(modal);
    // کلیک روی پس‌زمینه‌یِ نیمه‌شفاف = بستن (کلیک داخلِ خودِ مودال نبسته می‌کند)
    overlay.addEventListener('click', (event) => {
        if (event.target === overlay) closePasswordResetModal();
    });
    document.body.appendChild(overlay);
    return overlay;
};

const setPrError = (message) => {
    const errorBox = document.querySelector('#prError');
    if (!errorBox) return;
    errorBox.textContent = message;
    errorBox.hidden = false;
};

const clearPrError = () => {
    const errorBox = document.querySelector('#prError');
    if (!errorBox) return;
    errorBox.textContent = '';
    errorBox.hidden = true;
};

const openPasswordResetModal = () => {
    const overlay =
        document.querySelector(selectors.passwordResetModal) ||
        buildPasswordResetModal();
    clearPrError();
    overlay.hidden = false;
    // فوکوس روی فیلد تا کاربر بدونِ کلیکِ اضافه، مستقیم تایپ کند
    const first = overlay.querySelector('#prIdentifier');
    if (first) first.focus();
};

const closePasswordResetModal = () => {
    const overlay = document.querySelector(selectors.passwordResetModal);
    if (!overlay) return;
    overlay.hidden = true;
    // پاک‌سازیِ فیلد و پیام‌ها برای باز‌شدنِ بعدی
    const input = overlay.querySelector('#prIdentifier');
    if (input) input.value = '';
    const submit = overlay.querySelector('#prSubmit');
    if (submit) submit.disabled = false;
    clearPrError();
};

// ارسالِ درخواست: identifier → POST. پاسخِ سرور عمداً «عمومی» است (نمی‌گوید
// حساب وجود داشت یا نه — ضدِ کشفِ حساب)؛ همان متن را بی‌واسطه نشان می‌دهیم
// و پنجره را می‌بندیم. اگر کاربر ایمیل ندارد، متنِ همین پیام است که به او
// می‌رسد (ایمیلِ جایی نمی‌رود) — صداقتِ طراحی در سمتِ سرور مستند شده.
const submitPasswordResetRequest = async (event) => {
    event.preventDefault();
    const overlay = document.querySelector(selectors.passwordResetModal);
    if (!overlay) return;

    const identifier = (overlay.querySelector('#prIdentifier')?.value ?? '').trim();
    if (!identifier) {
        setPrError(t('نام کاربری یا ایمیل را وارد کنید.'));
        return;
    }

    const submitButton = overlay.querySelector('#prSubmit');
    if (submitButton) submitButton.disabled = true;
    clearPrError();
    try {
        const body = await apiPost(
            endpoints.passwordReset,
            { identifier },
            { skipAuth: true },
        );
        closePasswordResetModal();
        // پیامِ سرور (با زبانِ درخواست از طریقِ Accept-Language ترجمه‌شده):
        showToast(body?.detail || t('درخواستِ بازیابی ثبت شد.'), 'info');
    } catch (error) {
        setPrError(error.message || t('خطا در ارسالِ درخواستِ بازیابی.'));
        if (submitButton) submitButton.disabled = false;
    }
};

// صفحه‌یِ reset-password.html: uid و token از query string می‌آیند (لینکِ
// ایمیل). بدونِ آن‌ها فرم بی‌معناست — خطای صریح + غیرفعال‌کردنِ فرم. در
// موفقیت، سرور رمز را عوض کرده و همه‌ی نشست‌ها را باطل کرده است؛ ما فقط
// پیام را نشان می‌دهیم و بعد از یک مکثِ کوتاه به صفحه‌ی ورود می‌بریم.
const handlePasswordReset = () => {
    const form = document.getElementById('resetPasswordForm');
    if (!form) return;

    const params = new URLSearchParams(window.location.search);
    const uid = params.get('uid') || '';
    const token = params.get('token') || '';

    if (!uid || !token) {
        const error = document.getElementById('resetLinkError');
        if (error) {
            error.textContent = t(
                'این صفحه فقط از طریقِ لینکِ ایمیلِ بازیابی معنا دارد؛ لینک را از ایمیلِ دریافتی دوباره باز کنید.',
            );
            error.hidden = false;
        }
        // ارسالِ فرمِ بدونِ لینک فقط خطایِ سرورِ تکراری می‌شود — قفل می‌کنیم:
        const submit = document.getElementById('resetActionBtn');
        if (submit) submit.disabled = true;
        return;
    }

    form.addEventListener('submit', async (event) => {
        event.preventDefault();
        const next = form.new_password.value;
        const confirm = form.confirm_password.value;

        if (next.length < 8) {
            showToast(t('رمز عبور جدید باید حداقل ۸ نویسه باشد.'), 'error');
            return;
        }
        if (next !== confirm) {
            showToast(t('رمزهای جدید یکسان نیستند.'), 'error');
            return;
        }

        const submitButton = document.getElementById('resetActionBtn');
        if (submitButton) submitButton.disabled = true;
        try {
            const body = await apiPost(
                endpoints.passwordResetConfirm,
                { uid, token, new_password: next },
                { skipAuth: true },
            );
            showToast(
                body?.detail || t('رمز عبور با موفقیت بازنشانی شد.'),
                'success',
            );
            // مکثِ خواندنی برایِ دیدنِ پیام، بعد هدایت به ورود (ورودِ تازه لازم
            // است — بازیابیِ موفق عمداً توکن صادر نمی‌کند):
            setTimeout(() => {
                window.location.href = 'login.html';
            }, 2000);
        } catch (error) {
            showToast(error.message, 'error');
            if (submitButton) submitButton.disabled = false;
        }
    });
};

// رویدادهایی که در همه‌ی صفحات مشترک‌اند (دکمه‌ی خروج، باز/بسته‌شدنِ سایدبارِ
// موبایل با دکمه‌ی همبرگری و کلیک روی پس‌زمینه‌ی تیره) + به‌روزرسانیِ اولیه‌ی
// نام کاربری و وضعیتِ اتصال. تقریباً هر initXPage این تابع را صدا می‌زند.
const bindGlobalEvents = () => {
    const logoutButton = document.querySelector(selectors.logoutButton);
    if (logoutButton) {
        logoutButton.addEventListener('click', (event) => {
            event.preventDefault();
            logout();
        });
    }

    // دکمه‌ی «تغییر رمز عبور» (از 2026-09-10): در همان نوارِ مشترکِ همه‌ی
    // صفحاتِ لاگین‌شده، کنارِ دکمه‌ی خروج تزریق می‌شود (خودِ app.js می‌سازدش
    // — HTMLها تغییر نکرده‌اند).
    injectChangePasswordButton();

    const toggle = document.querySelector(selectors.sidebarToggle);
    const backdrop = document.querySelector(selectors.backdrop);

    if (toggle) {
        toggle.addEventListener('click', () =>
            document.body.classList.toggle('sidebar-open'),
        );
    }
    if (backdrop) {
        backdrop.addEventListener('click', () =>
            document.body.classList.remove('sidebar-open'),
        );
    }

    updateUserGreeting();
    updateStatusIndicator();
};

// ---------------------------------------------------------------------
// صفحه‌ی داشبورد (index.html)
// ---------------------------------------------------------------------

// داده‌ی JSON دریافتی از GET /api/dashboard/ را می‌گیرد و تمام پنل‌های
// داشبورد (کارت‌های آماری، پیشرفتِ درس‌ها، تقویم امتحان‌ها، هشدارها،
// نمودارِ تقسیم‌زمان) را با آن پر می‌کند.
const renderDashboard = (data) => {
    // چهار کارتِ آماریِ بالای صفحه؛ کلیدِ هر آبجکت همان id عنصرِ HTML است
    const totals = {
        totalSubjects: data?.total_subjects ?? 0,
        totalExams: data?.total_exams ?? 0,
        averageProgress: `${Math.round(data?.average_progress ?? 0)}%`,
        pendingAlerts: data?.urgent_alerts_count ?? 0,
    };

    Object.entries(totals).forEach(([id, value]) => {
        const el = document.getElementById(id);
        if (el) el.textContent = value;
    });

    // پنل «پیشرفت درس‌ها»: برای هر درس یک نوارِ پیشرفت رسم می‌کنیم
    const progressList = document.getElementById('progressList');
    if (progressList) {
        progressList.innerHTML = '';
        const subjects = data?.subjects_progress ?? [];
        if (!subjects.length) {
            progressList.innerHTML = `<p class="empty-state">${t('درسی ثبت نشده است.')}</p>`;
        } else {
            subjects.forEach((subject) => {
                const row = document.createElement('div');
                row.className = 'progress-row';
                row.innerHTML = `
                    <h4>${escapeHtml(subject.name)}</h4>
                    <div class="progress-meta">
                        <span>${t('سختی: {difficulty}/5', { difficulty: subject.difficulty })}</span>
                        <span>${t('{completed} از {total} ساعت', { completed: subject.completed_hours, total: subject.total_hours })}</span>
                    </div>
                    <div class="progress-bar">
                        <span style="width: ${subject.progress_percent}%"></span>
                    </div>
                `;
                progressList.appendChild(row);
            });
        }
    }

    // پنل «تقویم مطالعه»: فهرستِ امتحان‌های پیشِ‌رو به ترتیبِ نزدیک‌ترین
    const timeline = document.getElementById('timelineList');
    if (timeline) {
        timeline.innerHTML = '';
        const exams = data?.upcoming_exams ?? [];
        if (!exams.length) {
            timeline.innerHTML = `<p class="empty-state">${t('امتحان ثبت نشده است.')}</p>`;
        } else {
            exams.forEach((exam) => {
                const item = document.createElement('div');
                item.className = 'timeline-item';
                item.innerHTML = `
                    <strong>${escapeHtml(exam.subject_name)}</strong>
                    <span>${exam.exam_date} • ${t('{days} روز باقی‌مانده', { days: exam.remaining_days })}</span>
                    <span>${t('ساعت باقی‌مانده: {hours}', { hours: exam.remaining_hours })}</span>
                `;
                timeline.appendChild(item);
            });
        }
    }

    // پنل «هشدارها و یادآوری‌ها»: هر آیتم بر اساس alert.type رنگ‌بندیِ متفاوتی
    // می‌گیرد (قرمز=danger فوری، زرد=warning نزدیک، آبی=info یادآوریِ خنثی)
    const alertsList = document.getElementById('alertsList');
    if (alertsList) {
        alertsList.innerHTML = '';
        const alerts = data?.alerts ?? [];
        if (!alerts.length) {
            alertsList.innerHTML = `<p class="empty-state">${t('هشداری وجود ندارد.')}</p>`;
        } else {
            alerts.forEach((alert) => {
                const item = document.createElement('div');
                // اگر نوعِ هشدار چیزی غیر از سه‌ حالتِ شناخته‌شده بود، برای
                // ایمنی آن را «info» در نظر می‌گیریم (نه این‌که قرمز/داعیِ خطا نشان بدهد)
                const validTypes = ['danger', 'warning', 'info'];
                const alertType = validTypes.includes(alert.type)
                    ? alert.type
                    : 'info';
                item.className = `alert alert--${alertType}`;
                item.innerHTML = `
                    <span>${escapeHtml(alert.message)}</span>
                    <strong>${escapeHtml(alert.subject ?? '')}</strong>
                `;
                alertsList.appendChild(item);
            });
        }
    }

    // پنل «تقسیم‌زمان پیشنهادی»: نمودارِ میله‌ایِ سهمِ هر درس از هفته‌ی پیش‌رو
    const distribution = document.getElementById('studyDistribution');
    if (distribution) {
        const dist = Array.isArray(data?.study_distribution)
            ? data.study_distribution
            : [];
        if (!dist.length) {
            distribution.innerHTML = `<p class="empty-state">${t('داده‌ای برای نمایش نمودار وجود ندارد.')}</p>`;
        } else {
            distribution.innerHTML = '';
            dist.forEach((entry) => {
                const bar = document.createElement('div');
                bar.className = 'mini-bar';
                // حداقل ۶٪ ارتفاع می‌گذاریم تا حتی مقادیرِ خیلی کوچک هم دیده شوند
                bar.style.height = `${Math.max(entry.percent, 6)}%`;
                bar.title = t('{label}: {hours} ساعت در هفته‌ی پیش‌رو', { label: entry.label, hours: entry.hours ?? 0 });
                bar.innerHTML = `<span>${escapeHtml(entry.label)}</span>`;
                distribution.appendChild(bar);
            });
        }
    }
};

// درخواستِ داده از سرور و رندرِ کاملِ داشبورد؛ در initDashboardPage صدا زده می‌شود
const loadDashboard = async () => {
    try {
        updateStatusIndicator('busy');
        const data = await apiGet(endpoints.dashboard);
        renderDashboard(data);
        updateStatusIndicator('online');
    } catch (error) {
        showToast(error.message, 'error');
        updateStatusIndicator('busy');
    }
};

// ---------------------------------------------------------------------
// صفحه‌ی درس‌ها (subjects.html)
// ---------------------------------------------------------------------

// مرتب‌سازیِ سمت-کلاینتِ فهرستِ درس‌ها (سرور همیشه فهرستِ خام را می‌فرستد،
// ترتیبِ نمایش را خودِ فرانت‌اند بر اساس انتخابِ کاربر تعیین می‌کند)
const sortSubjects = (subjects, key) => {
    const sorted = [...subjects];
    switch (key) {
        case 'difficulty':
            return sorted.sort((a, b) => b.difficulty - a.difficulty);
        case 'progress':
            return sorted.sort(
                (a, b) => b.progress_percent - a.progress_percent,
            );
        default:
            return sorted.sort((a, b) => a.name.localeCompare(b.name, currentLang()));
    }
};

const renderSubjects = (subjects) => {
    const tbody = document.getElementById('subjectsTableBody');
    if (!tbody) return;
    tbody.innerHTML = '';

    if (!subjects.length) {
        tbody.innerHTML = `<tr><td colspan="5" class="empty-state">${t('درسی هنوز ثبت نشده است.')}</td></tr>`;
        return;
    }

    subjects.forEach((subject) => {
        const row = document.createElement('tr');
        // یادداشتِ درس (اگر وجود داشته باشد) به‌صورتِ زیرنویسِ کم‌رنگ زیرِ نام
        // درس نمایش داده می‌شود؛ ستونِ جدول اضافه نمی‌شود تا چیدمان حفظ شود.
        const notesMarkup = subject.notes
            ? `<br><small class="text-muted">${escapeHtml(subject.notes)}</small>`
            : '';
        row.innerHTML = `
            <td>${escapeHtml(subject.name)}${notesMarkup}</td>
            <td>${subject.difficulty}/5</td>
            <td>${Math.round(subject.progress_percent ?? 0)}%</td>
            <td>${subject.target_score ?? '-'}</td>
            <td>${subject.remaining_hours ?? 0}</td>
        `;
        tbody.appendChild(row);
    });
};

const loadSubjects = async (sortKey = 'name') => {
    try {
        updateStatusIndicator('busy');
        const subjects = await apiGet(endpoints.subjects);
        renderSubjects(sortSubjects(subjects ?? [], sortKey));
        updateStatusIndicator('online');
    } catch (error) {
        showToast(error.message, 'error');
    }
};

// ---------------------------------------------------------------------
// صفحه‌ی امتحان‌ها (exams.html)
// ---------------------------------------------------------------------

// پر کردنِ کشوی «انتخاب درس» در فرمِ ثبتِ امتحان (بر اساس درس‌های خودِ کاربر)
const populateSubjectSelect = async () => {
    const select = document.getElementById('examSubject');
    if (!select) return;
    try {
        const subjects = await apiGet(endpoints.subjects);
        select.innerHTML = `<option value="" disabled selected>${t('ابتدا درس را انتخاب کنید')}</option>`;
        if (!subjects.length) {
            select.innerHTML = `<option value="" disabled>${t('لطفاً ابتدا درسی ثبت کنید')}</option>`;
            return;
        }
        subjects.forEach((subject) => {
            const option = document.createElement('option');
            option.value = subject.id;
            option.textContent = subject.name;
            select.appendChild(option);
        });
    } catch (error) {
        showToast(t('بارگذاری درس‌ها با خطا مواجه شد.'), 'error');
    }
};

const renderExams = (exams) => {
    const tbody = document.getElementById('examTableBody');
    if (!tbody) return;
    tbody.innerHTML = '';

    if (exams.length === 0) {
        tbody.innerHTML =
            `<tr><td colspan='6' class='text-center'>${t('هیچ امتحانی یافت نشد.')}</td></tr>`;
        return;
    }

    const today = new Date();
    today.setHours(0, 0, 0, 0);

    exams.forEach((exam) => {
        const examDate = new Date(exam.exam_date);
        const diffTime = examDate - today;
        // تبدیلِ اختلافِ میلی‌ثانیه‌ای به تعداد روز (۱۰۰۰ میلی‌ثانیه × ۶۰ ثانیه × ۶۰ دقیقه × ۲۴ ساعت)
        const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));

        let daysText = '';
        if (diffDays > 0) {
            daysText = t('{days} روز باقی‌مانده', { days: diffDays });
        } else if (diffDays === 0) {
            daysText = t('امروز!');
        } else {
            daysText = t('گذشته');
        }

        // برچسبِ اهمیت/فوریتِ امتحان، صرفاً برای نمایشِ بصریِ سریع در جدول
        let importanceLabel = t('کم');
        if (diffDays >= 0 && diffDays <= 3) {
            importanceLabel = t('خیلی زیاد 🔴');
        } else if (diffDays > 3 && diffDays <= 7) {
            importanceLabel = t('متوسط 🟡');
        } else if (diffDays > 7) {
            importanceLabel = t('کم 🟢');
        }

        // یادداشتِ امتحان (اگر باشد) به‌صورتِ زیرنویسِ کم‌رنگ زیرِ نام درس —
        // همان الگوی جدولِ درس‌ها؛ چیدمانِ جدول حفظ می‌شود.
        const notesMarkup = exam.notes
            ? `<br><small class="text-muted">${escapeHtml(exam.notes)}</small>`
            : '';

        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${escapeHtml(exam.subject_name ?? String(exam.subject ?? ''))}${notesMarkup}</td>
            <td>${exam.exam_date} <br> <small class="text-muted">${daysText}</small></td>
            <td>${t('{hours} ساعت', { hours: exam.study_hours_remaining ?? 0 })}</td>
            <td>${importanceLabel}</td>
            <td>${diffDays < 0 ? t('پایان یافته') : t('برنامه‌ریزی نشده')}</td>
            <td></td>
        `;

        // سلولِ «عملیات»: دکمه‌ی ویرایش با گوشه‌دادنِ آبجکتِ exam از طریقِ
        // closure — همان الگوی دکمه‌های «حذف» در renderStudyLogs.
        const actionsTd = row.lastElementChild;
        const editBtn = document.createElement('button');
        editBtn.type = 'button';
        // btn-edit: دکمه‌ی قرصیِ مخصوصِ سطحِ سفیدِ جدول — آیکونِ مداد با CSS mask
        editBtn.className = 'btn-edit';
        editBtn.title = t('ویرایش این امتحان');
        editBtn.textContent = t('ویرایش');
        editBtn.addEventListener('click', () => startExamEdit(exam));
        actionsTd.appendChild(editBtn);

        tbody.appendChild(row);
    });
};

// ورود به «حالتِ ویرایش»: فرمِ امتحان با داده‌های امتحانِ انتخاب‌شده پر
// می‌شود، examId ست می‌شود و ظاهرِ فرم (عنوانِ پنل، متنِ دکمه‌ی ذخیره و
// دکمه‌ی انصراف) به حالتِ ویرایش می‌رود. submit بعدی به‌جای POST به
// PATCH /api/exams/{id}/ می‌رود (تشخیص در handleExamForm).
const startExamEdit = (exam) => {
    const form = document.getElementById('examForm');
    if (!form) return;

    form.elements.subject.value = String(exam.subject);
    form.elements.exam_date.value = exam.exam_date;
    form.elements.chapters_remaining.value = exam.chapters_remaining;
    form.elements.study_hours_remaining.value = exam.study_hours_remaining;
    if (form.elements.notes) form.elements.notes.value = exam.notes ?? '';

    const examIdInput = document.getElementById('examId');
    if (examIdInput) examIdInput.value = exam.id;

    const cancelBtn = document.getElementById('cancelExamEditBtn');
    if (cancelBtn) cancelBtn.style.display = '';

    const submitBtn = form.querySelector('button[type="submit"]');
    if (submitBtn) submitBtn.textContent = t('به‌روزرسانی امتحان');

    const panelTitle = document.getElementById('examFormTitle');
    if (panelTitle) panelTitle.textContent = t('ویرایش امتحان');

    // جدول پایینِ فرم است؛ کاربر را به فرمِ پرشده ببریم تا تغییرات را ببیند
    form.scrollIntoView({ behavior: 'smooth', block: 'start' });
};

const loadExams = async (filter = 'upcoming') => {
    try {
        updateStatusIndicator('busy');
        const exams = await apiGet(endpoints.exams);
        let filtered = [...exams];
        if (filter === 'upcoming') {
            // فقط امتحان‌هایی که تاریخ‌شان از امروز به بعد است نشان بده
            const today = new Date().toISOString().split('T')[0];
            filtered = filtered.filter((exam) => exam.exam_date >= today);
        }
        renderExams(filtered);
        updateStatusIndicator('online');
    } catch (error) {
        showToast(error.message, 'error');
    }
};

// ---------------------------------------------------------------------
// ثبت مطالعه (StudyLog)
// ---------------------------------------------------------------------

// پر کردنِ کشوی «انتخاب امتحان» در فرمِ ثبتِ مطالعه؛ برای هر امتحان، ساعتِ
// باقی‌مانده‌اش هم در متنِ گزینه نشان داده می‌شود تا کاربر بداند کدام
// امتحان هنوز نیاز به مطالعه دارد.
const populateExamSelectForLog = async () => {
    const select = document.getElementById('logExam');
    if (!select) return;
    try {
        const exams = await apiGet(endpoints.exams);
        const sorted = [...exams].sort((a, b) =>
            a.exam_date.localeCompare(b.exam_date),
        );

        if (!sorted.length) {
            select.innerHTML = `<option value="" disabled selected>${t('ابتدا یک امتحان ثبت کنید')}</option>`;
            return;
        }

        select.innerHTML = `<option value="" disabled selected>${t('یک امتحان را انتخاب کنید')}</option>`;
        sorted.forEach((exam) => {
            const option = document.createElement('option');
            option.value = exam.id;
            const remaining = exam.study_hours_remaining ?? 0;
            const remainingText =
                remaining > 0 ? t('{hours} ساعت باقی‌مانده', { hours: remaining }) : t('کامل شده ✅');
            option.textContent = `${exam.subject_name ?? exam.subject} — ${exam.exam_date} (${remainingText})`;
            select.appendChild(option);
        });
    } catch (error) {
        showToast(t('بارگذاری امتحان‌ها با خطا مواجه شد.'), 'error');
    }
};

const renderStudyLogs = (logs) => {
    const tbody = document.getElementById('studyLogTableBody');
    if (!tbody) return;
    tbody.innerHTML = '';

    if (!logs.length) {
        tbody.innerHTML = `<tr><td colspan="5" class="empty-state">${t('هنوز هیچ گزارش مطالعه‌ای ثبت نشده است.')}</td></tr>`;
        return;
    }

    logs.forEach((log) => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${escapeHtml(log.exam_name ?? '-')}</td>
            <td>${log.date}</td>
            <td>${t('{hours} ساعت', { hours: log.hours_studied })}</td>
            <td>${log.notes ? escapeHtml(log.notes) : '-'}</td>
            <td><button type="button" class="btn-danger-sm" data-log-id="${log.id}">${t('حذف')}</button></td>
        `;
        tbody.appendChild(row);
    });

    // چون این دکمه‌های «حذف» بعد از رندر ساخته می‌شوند، رویدادشان را همین‌جا
    // (بعد از innerHTML) اضافه می‌کنیم؛ نه در HTML اصلیِ صفحه.
    tbody.querySelectorAll('[data-log-id]').forEach((button) => {
        button.addEventListener('click', () =>
            deleteStudyLog(button.dataset.logId),
        );
    });
};

const loadStudyLogs = async () => {
    try {
        updateStatusIndicator('busy');
        const logs = await apiGet(endpoints.studyLogs);
        renderStudyLogs(logs ?? []);
        updateStatusIndicator('online');
    } catch (error) {
        showToast(error.message, 'error');
    }
};

const deleteStudyLog = async (id) => {
    // حذفِ گزارش از این پس ساعتِ کسرشده را هم به امتحانِ مربوطه
    // برمی‌گرداند (بک‌اند: متدِ delete رویِ مدلِ StudyLog)؛ باز هم برای
    // جلوگیری از حذفِ ناخواسته، تأیید می‌گیریم.
    if (
        !confirm(
            t('این گزارش مطالعه حذف شود؟ ساعتِ مطالعه‌ی آن به امتحانِ مربوطه برمی‌گردد.'),
        )
    )
        return;
    try {
        await apiDelete(endpoints.studyLogDetail(id));
        showToast(t('گزارش مطالعه حذف شد و ساعتِ آن به امتحان برگشت.'), 'success');
        await loadStudyLogs();
        // متنِ «X ساعت باقی‌مانده» کنارِ گزینه‌های کشویِ امتحان‌ها هم باید
        // با ساعتِ برگشته به‌روز شود، وگرنه تا رفرشِ بعدی عددِ قدیمی می‌ماند
        await populateExamSelectForLog();
    } catch (error) {
        showToast(error.message, 'error');
    }
};

const handleStudyLogForm = () => {
    const form = document.getElementById('studyLogForm');
    if (!form) return;

    form.addEventListener('submit', async (event) => {
        event.preventDefault();
        const formData = new FormData(form);

        const data = {
            exam: Number(formData.get('exam')),
            date: formData.get('date'),
            hours_studied: Number(formData.get('hours_studied')),
            notes: formData.get('notes') || '',
        };

        if (
            !data.exam ||
            !data.date ||
            !data.hours_studied ||
            data.hours_studied <= 0
        ) {
            showToast(
                t('لطفاً امتحان، تاریخ و ساعت مطالعه را درست وارد کنید.'),
                'error',
            );
            return;
        }

        try {
            await apiPost(endpoints.studyLogs, data);
            showToast(t('آفرین! گزارش مطالعه ثبت شد. 🎉'), 'success');
            form.reset();
            // بعد از ثبت، تاریخ را دوباره روی «امروز» می‌گذاریم (چون form.reset آن را خالی می‌کند)
            const dateInput = document.getElementById('logDate');
            if (dateInput)
                dateInput.value = new Date().toISOString().split('T')[0];
            // هم لیست گزارش‌ها و هم کشوی امتحان‌ها (که ساعتِ باقی‌مانده‌اش عوض شده) را تازه می‌کنیم
            await Promise.all([loadStudyLogs(), populateExamSelectForLog()]);
        } catch (error) {
            showToast(error.message, 'error');
        }
    });
};

const initStudyLogPage = () => {
    requireAuth();
    bindGlobalEvents();
    handleStudyLogForm();
    const dateInput = document.getElementById('logDate');
    if (dateInput) dateInput.value = new Date().toISOString().split('T')[0];
    populateExamSelectForLog();
    loadStudyLogs();
};

// ---------------------------------------------------------------------
// صفحه‌ی برنامه‌ی مطالعه (study_plan.html)
// ---------------------------------------------------------------------

// داده‌ی JSON دریافتی از GET /api/study-plan/ (شکل: {schedule, totals, ...})
// را می‌گیرد و بلوک‌های برنامه (هرکدام شاملِ چند تسکِ درس/ساعت) را می‌سازد.
const renderPlan = (plan) => {
    // اگر کاربر همین الان مشغولِ تایپ در ورودیِ ساعتِ روزانه است، مقدارش را
    // با داده‌ی تازه بازنویسی نکن (تا وسطِ تایپِ کاربر پاک نشود)
    const hoursInput = document.getElementById('dailyHoursInput');
    if (
        hoursInput &&
        plan?.daily_available_hours != null &&
        document.activeElement !== hoursInput
    ) {
        hoursInput.value = plan.daily_available_hours;
    }

    const container = document.getElementById('planContainer');
    if (!container) return;

    container.innerHTML = '';
    const items = plan?.schedule ?? [];

    if (!items.length) {
        // پیامِ خودِ بک‌اند (مثلاً «هیچ امتحان آینده‌ای وجود ندارد») را نشان بده،
        // یا اگر نبود، یک پیامِ عمومی
        container.innerHTML = `<p class="empty-state">${escapeHtml(plan?.message ?? t('داده‌ای برای نمایش وجود ندارد.'))}</p>`;
        const total = document.getElementById('totalRecommended');
        if (total) total.textContent = t('0 ساعت');
        const daily = document.getElementById('averageDaily');
        if (daily) daily.textContent = '0';
        const priority = document.getElementById('prioritySubjects');
        if (priority) priority.textContent = '-';
        return;
    }

    items.forEach((entry) => {
        const block = document.createElement('div');
        block.className = 'plan-block';
        // اگر این بلوک چند روز را ادغام کرده (days_covered > 1)، یک برچسبِ
        // کوچک («۴ روز») کنارِ عنوان نشان بده
        const daysChip =
            entry.days_covered > 1
                ? `<span class="plan-days-chip">${t('{days} روز', { days: entry.days_covered })}</span>`
                : '';
        block.innerHTML = `
            <div class="plan-header">
                <h4>${escapeHtml(entry.title)} ${daysChip}</h4>
                <span class="plan-hours">${escapeHtml(entry.hours_badge ?? t('{hours} ساعت', { hours: entry.total_hours ?? 0 }))}</span>
            </div>
        `;
        const tasksWrapper = document.createElement('div');
        tasksWrapper.className = 'plan-tasks';

        entry.tasks?.forEach((task) => {
            const taskRow = document.createElement('div');
            taskRow.className = 'plan-task';
            taskRow.innerHTML = `
                <strong>${escapeHtml(task.subject)}</strong>
                <span>${t('{hours} ساعت', { hours: task.hours })}</span>
            `;
            tasksWrapper.appendChild(taskRow);
        });

        block.appendChild(tasksWrapper);
        container.appendChild(block);
    });

    // خلاصه‌ی پایینِ صفحه: مجموع ساعات پیشنهادی، میانگین روزانه و پرکارترین درس‌ها
    const total = document.getElementById('totalRecommended');
    if (total)
        total.textContent = t('{hours} ساعت', { hours: plan?.totals?.recommended_hours ?? 0 });

    const daily = document.getElementById('averageDaily');
    if (daily) daily.textContent = plan?.totals?.average_daily ?? 0;

    const priority = document.getElementById('prioritySubjects');
    if (priority) {
        priority.innerHTML = '';
        const subjects = plan?.totals?.top_subjects ?? [];
        if (!subjects.length) {
            priority.textContent = '-';
        } else {
            subjects.forEach((subject) => {
                const tag = document.createElement('span');
                tag.className = 'tag';
                tag.textContent = subject;
                priority.appendChild(tag);
            });
        }
    }
};

// دریافتِ برنامه برای یک بازه‌ی مشخص («daily» یا «weekly») و رندرِ آن
const loadStudyPlan = async (range = 'daily') => {
    try {
        updateStatusIndicator('busy');
        const plan = await apiGet(endpoints.studyPlan(range));
        renderPlan(plan);
        updateStatusIndicator('online');
    } catch (error) {
        showToast(error.message, 'error');
    }
};

// ---------------------------------------------------------------------
// پیش‌بینیِ هوشمند (مؤلفه‌ی یادگیریِ آماری — 2026-09-09)
// ---------------------------------------------------------------------

// مقدارهایِ ماشین‌خوانِ API (risk/bias از GET /api/predictions/) را به
// متنِ نمایشی نگاشت می‌کنیم؛ کلید = متنِ فارسی (عرفِ msgid، نکته‌ی 6.14
// AI_CONTEXT) و ترجمه‌ی en از دیکشنریِ i18n.js می‌آید.
const RISK_LABELS = {
    high: 'ریسک بالا',
    medium: 'ریسک متوسط',
    low: 'ریسک کم',
};

const BIAS_LABELS = {
    underestimates: 'تخمین‌های شما کمتر از واقعیت است',
    overestimates: 'تخمین‌های شما بیشتر از واقعیت است',
    accurate: 'تخمین‌های شما دقیق است',
    unknown: 'هنوز تاریخچه‌ی کافی برای یادگیری نیست',
};

// داده‌ی JSON دریافتی از GET /api/predictions/ (شکل: {model, predictions,
// summary}) را در پنلِ «پیش‌بینیِ هوشمند» صفحه‌ی برنامه رندر می‌کند.
// ساختارِ بلوک‌ها عمداً همان plan-block/plan-taskِ بالا است تا بدونِ CSSِ
// جدید، هم‌ظاهرِ بقیه‌ی صفحه بماند؛ نامِ درس‌ها مثلِ همیشه escape می‌شوند.
const renderPredictions = (report) => {
    const container = document.getElementById('predictionsContainer');
    if (!container) return;

    container.innerHTML = '';
    const items = report?.predictions ?? [];

    if (!items.length) {
        container.innerHTML = `<p class="empty-state">${escapeHtml(t('امتحانِ پیش‌رویی برای پیش‌بینی وجود ندارد.'))}</p>`;
        return;
    }

    // --- کارتِ وضعیتِ مدل: ضریبِ کالیبراسیون، سوگیری و اعتماد ---
    const model = report?.model ?? {};
    const biasLabel = BIAS_LABELS[model.bias] ?? BIAS_LABELS.unknown;
    const modelBlock = document.createElement('div');
    modelBlock.className = 'plan-block';
    modelBlock.innerHTML = `
        <div class="plan-header">
            <h4>${escapeHtml(t('مدلِ یادگیریِ شما'))}</h4>
            <span class="plan-hours">×${escapeHtml(String(model.calibration_factor ?? 1))}</span>
        </div>
        <div class="plan-tasks">
            <div class="plan-task">
                <strong>${escapeHtml(t('سوگیریِ تخمین'))}</strong>
                <span>${escapeHtml(t(biasLabel))}</span>
            </div>
            <div class="plan-task">
                <strong>${escapeHtml(t('نمونه‌های آموزشی'))}</strong>
                <span>${escapeHtml(String(model.sample_count ?? 0))}</span>
            </div>
            <div class="plan-task">
                <strong>${escapeHtml(t('اعتماد مدل'))}</strong>
                <span>${escapeHtml(t('{value}٪', { value: Math.round((model.confidence ?? 0) * 100) }))}</span>
            </div>
        </div>
    `;
    container.appendChild(modelBlock);

    // --- به‌ازای هر امتحانِ آینده: یک بلوکِ پیش‌بینی ---
    items.forEach((item) => {
        const riskLabel = RISK_LABELS[item.risk] ?? RISK_LABELS.low;
        const block = document.createElement('div');
        block.className = 'plan-block';
        block.innerHTML = `
            <div class="plan-header">
                <h4>${escapeHtml(item.subject)} <span class="plan-days-chip">${escapeHtml(t(riskLabel))}</span></h4>
                <span class="plan-hours">${escapeHtml(t('{hours} ساعت', { hours: item.predicted_hours ?? 0 }))}</span>
            </div>
        `;
        const tasksWrapper = document.createElement('div');
        tasksWrapper.className = 'plan-tasks';
        tasksWrapper.innerHTML = `
            <div class="plan-task">
                <strong>${escapeHtml(t('تخمین شما'))}</strong>
                <span>${escapeHtml(t('{hours} ساعت', { hours: item.planned_hours ?? 0 }))}</span>
            </div>
            <div class="plan-task">
                <strong>${escapeHtml(t('نیاز روزانه'))}</strong>
                <span>${escapeHtml(t('{hours} ساعت', { hours: item.required_daily_hours ?? 0 }))}</span>
            </div>
            <div class="plan-task">
                <strong>${escapeHtml(t('روزهای باقی‌مانده'))}</strong>
                <span>${escapeHtml(t('{days} روز', { days: item.days_left ?? 0 }))}</span>
            </div>
        `;
        block.appendChild(tasksWrapper);
        container.appendChild(block);
    });
};

// دریافتِ گزارشِ پیش‌بینی از API و رندرِ آن (مستقل از بازه‌ی روزانه/هفتگی —
// پیش‌بینی همیشه برای همه‌ی امتحان‌هایِ آینده است)
const loadPredictions = async () => {
    try {
        const report = await apiGet(endpoints.predictions);
        renderPredictions(report);
    } catch (error) {
        const container = document.getElementById('predictionsContainer');
        if (container) {
            container.innerHTML = `<p class="empty-state">${escapeHtml(error.message)}</p>`;
        }
    }
};

// ---------------------------------------------------------------------
// صفحات ورود / ثبت‌نام
// ---------------------------------------------------------------------

const handleLogin = () => {
    const form = document.getElementById('loginForm');
    if (!form) return;

    // اگر کاربر به‌خاطرِ انقضای نشست به این صفحه آمده باشد (?expired=1)،
    // یک توضیحِ کوتاه نشان بده تا معلوم شود چرا وسطِ کار بیرون افتاد.
    if (new URLSearchParams(window.location.search).get('expired')) {
        showToast(t('نشست شما منقضی شده بود؛ لطفاً دوباره وارد شوید.'), 'info');
    }

    // لینکِ «رمز را فراموش کرده‌اید؟» (از 2026-09-12): مودالِ درخواستِ لینکِ
    // بازیابی — فقط در همین صفحه معنا دارد و همین‌جا بسته می‌شود.
    const forgotLink = document.querySelector(selectors.forgotPasswordLink);
    if (forgotLink) {
        forgotLink.addEventListener('click', (event) => {
            event.preventDefault(); // href="#" فقط برایِ دسترس‌پذیری است
            openPasswordResetModal();
        });
    }

    form.addEventListener('submit', async (event) => {
        event.preventDefault();
        const username = form.username.value.trim();
        const password = form.password.value;

        if (!username || !password) {
            showToast(t('لطفاً همه فیلدها را کامل کنید.'), 'error');
            return;
        }

        try {
            // skipAuth: true چون هنوز توکنی نداریم که در هدر بفرستیم
            const data = await apiPost(
                endpoints.login,
                { username, password },
                { skipAuth: true },
            );
            setToken(data.access);
            // توکنِ Refresh را هم ذخیره می‌کنیم (رفعِ 2026-09-06): بعد از انقضایِ
            // توکنِ دسترسی، apiRequest بی‌صدا همین توکن را برایِ تمدید می‌فرستد.
            if (data.refresh) setRefreshToken(data.refresh);
            setStoredUsername(username);
            showToast(t('ورود موفقیت‌آمیز بود.'), 'success');
            window.location.href = 'index.html';
        } catch (error) {
            showToast(error.message, 'error');
        }
    });
};

const handleRegister = () => {
    const form = document.getElementById('registerForm');
    if (!form) return;

    form.addEventListener('submit', async (e) => {
        e.preventDefault();

        const formData = new FormData(form);
        const data = Object.fromEntries(formData.entries());

        try {
            // اضافه شدن { skipAuth: true } که جا افتاده بود
            await apiPost(endpoints.register, data, { skipAuth: true });

            showToast(t('ثبت‌نام با موفقیت انجام شد!'), 'success');

            // بعد از ثبت‌نامِ موفق، دکمه‌ی فرم را تبدیل به یک لینکِ «ورود به حساب» می‌کنیم
            const actionBtn = document.getElementById('authActionBtn');
            if (actionBtn) {
                actionBtn.textContent = t('ورود به حساب');
                actionBtn.type = 'button';
                actionBtn.classList.add('success-button');

                actionBtn.onclick = () => {
                    window.location.href = 'login.html';
                };
            }

            const loginPrompt = document.getElementById('loginPrompt');
            if (loginPrompt) {
                loginPrompt.style.display = 'none';
            }
        } catch (error) {
            console.error('Error:', error);
            showToast(
                error.message || t('خطا در ثبت‌نام. لطفا دوباره تلاش کنید.'),
                'error',
            );
        }
    });
};

// ---------------------------------------------------------------------
// فرم‌های ثبتِ درس و امتحان
// ---------------------------------------------------------------------

const handleSubjectForm = () => {
    const form = document.getElementById('subjectForm');
    if (!form) return;

    form.addEventListener('submit', async (event) => {
        event.preventDefault();
        // فیلدِ total_hours حذف شد: ساعت‌های مطالعه در سطحِ امتحان دنبال می‌شوند
        // و فیلدِ محاسباتیِ total_hours سریالایزر از همان‌جا مشتق می‌شود (رفعِ فیلد یتیم).
        // notes از این پس یک فیلد واقعیِ مدل Subject است و واقعاً ذخیره می‌شود.
        const formData = {
            name: form.name.value.trim(),
            difficulty: Number(form.difficulty.value),
            target_score: form.target_score.value
                ? Number(form.target_score.value)
                : null,
            notes: form.notes.value.trim(),
        };

        if (!formData.name) {
            showToast(t('لطفاً نام درس را وارد کنید.'), 'error');
            return;
        }

        try {
            await apiPost(endpoints.subjects, formData);
            showToast(t('درس با موفقیت اضافه شد.'), 'success');
            form.reset();
            await loadSubjects(
                document.getElementById('subjectSort')?.value ?? 'name',
            );
        } catch (error) {
            showToast(error.message, 'error');
        }
    });
};

// بازنشانیِ فرمِ امتحان به حالتِ «ثبتِ جدید». فرم و examId را خالی می‌کند،
// دکمه‌ی «انصراف» را مخفی می‌کند و عنوانِ پنل و متنِ دکمه‌ی submit را به
// حالتِ ثبت برمی‌گرداند — یعنی دقیقاً معکوسِ کاری که startExamEdit می‌کند.
// این تابع هم بعد از «انصراف» از ویرایش و هم بعد از ثبت/ویرایشِ موفق صدا زده می‌شود.
const resetExamForm = () => {
    const form = document.getElementById('examForm');
    if (form) form.reset();

    const examIdInput = document.getElementById('examId');
    if (examIdInput) examIdInput.value = '';

    const cancelBtn = document.getElementById('cancelExamEditBtn');
    if (cancelBtn) cancelBtn.style.display = 'none';

    const submitBtn = form?.querySelector('button[type="submit"]');
    if (submitBtn) submitBtn.textContent = t('ذخیره امتحان');

    const panelTitle = document.getElementById('examFormTitle');
    if (panelTitle) panelTitle.textContent = t('ثبت امتحان یا ددلاین');
};

const handleExamForm = () => {
    const form = document.getElementById('examForm');
    if (!form) return;

    form.addEventListener('submit', async (event) => {
        event.preventDefault();

        const formData = new FormData(form);
        // اگر examId پر باشد یعنی کاربر در «حالتِ ویرایش» است: به‌جای POST،
        // درخواست به PATCH /api/exams/{id}/ می‌رود (تشخیصِ حالت فقط همین‌جاست).
        const examId = formData.get('examId');

        const data = {
            subject: Number(formData.get('subject')),
            exam_date: formData.get('exam_date'),
            chapters_remaining: Number(formData.get('chapters_remaining')),
            study_hours_remaining: Number(
                formData.get('study_hours_remaining'),
            ),
            // فیلدِ یادداشت — قبلاً یتیم بود و بی‌صدا دور ریخته می‌شد (رفع شد)
            notes: formData.get('notes')?.trim() || '',
        };

        if (
            !data.subject ||
            !data.exam_date ||
            isNaN(data.chapters_remaining) ||
            isNaN(data.study_hours_remaining)
        ) {
            showToast(t('لطفاً فیلدهای ضروری را کامل کنید.'), 'error');
            return;
        }

        try {
            if (examId) {
                await apiPatch(endpoints.examDetail(examId), data);
                showToast(t('امتحان با موفقیت به‌روزرسانی شد.'), 'success');
            } else {
                await apiPost(endpoints.exams, data);
                showToast(t('امتحان با موفقیت ثبت شد.'), 'success');
            }
            // در هر دو حالت (ثبتِ جدید یا ویرایش) فرم به حالتِ اولیه برمی‌گردد
            resetExamForm();
            await loadExams(
                document.getElementById('examFilter')?.value ?? 'upcoming',
            );
        } catch (error) {
            showToast(error.message, 'error');
        }
    });
};

// ---------------------------------------------------------------------
// توابعِ init هر صفحه (هرکدام: requireAuth + bindGlobalEvents + کارِ مخصوصِ صفحه)
// ---------------------------------------------------------------------

const initDashboardPage = () => {
    requireAuth();
    bindGlobalEvents();
    document
        .getElementById('refreshDashboard')
        ?.addEventListener('click', loadDashboard);
    loadDashboard();
};

const initSubjectsPage = () => {
    requireAuth();
    bindGlobalEvents();
    const sortSelect = document.getElementById('subjectSort');
    if (sortSelect) {
        sortSelect.addEventListener('change', () =>
            loadSubjects(sortSelect.value),
        );
    }
    handleSubjectForm();
    loadSubjects(sortSelect?.value ?? 'name');
};

const initExamsPage = () => {
    requireAuth();
    bindGlobalEvents();
    handleExamForm();
    // دکمه‌ی «انصراف» از ویرایش: خروج از حالتِ ویرایش بدونِ ذخیره (قبلاً
    // onclick درون‌خطی در exams.html بود؛ برای هم‌راستا شدنِ با الگویِ
    // بقیه‌ی صفحه‌ها، اینجا با addEventListener بسته می‌شود)
    document
        .getElementById('cancelExamEditBtn')
        ?.addEventListener('click', resetExamForm);
    populateSubjectSelect();
    const filterSelect = document.getElementById('examFilter');
    if (filterSelect) {
        filterSelect.addEventListener('change', () =>
            loadExams(filterSelect.value),
        );
    }
    loadExams(filterSelect?.value ?? 'upcoming');
};

// دکمه‌ی «روزانه/هفتگی» که در حال حاضر کلاسِ is-active دارد را پیدا می‌کند
const getActiveRange = () =>
    document.querySelector('.toggle-button.is-active')?.dataset.range ??
    'daily';

// فرمِ تنظیمِ «ساعت آزاد روزانه» در صفحه‌ی برنامه‌ی مطالعه
const handleDailyHoursForm = () => {
    const form = document.getElementById('dailyHoursForm');
    if (!form) return;

    form.addEventListener('submit', async (event) => {
        event.preventDefault();
        const dailyHours = Number(form.daily_available_hours.value);

        if (!dailyHours || dailyHours <= 0 || dailyHours > 24) {
            showToast(
                t('ساعت مطالعه روزانه باید عددی بین ۱ تا ۲۴ باشد.'),
                'error',
            );
            return;
        }

        try {
            updateStatusIndicator('busy');
            await apiPost(endpoints.studyPlanGenerate, {
                daily_available_hours: dailyHours,
            });
            showToast(t('برنامه مطالعه به‌روزرسانی شد.'), 'success');
            // بعد از تولیدِ مجدد، برنامه را دوباره برای همان بازه‌ای که کاربر
            // در حالِ مشاهده‌اش بود (روزانه یا هفتگی) بارگذاری می‌کنیم
            await loadStudyPlan(getActiveRange());
            // پیش‌بینی‌ها هم به‌روز می‌شوند: سطحِ ریسک به ساعتِ آزادِ روزانه
            // (که همین‌جا عوض شد) حساس است — نه فقط به تاریخِ امتحان
            loadPredictions();
            updateStatusIndicator('online');
        } catch (error) {
            showToast(error.message, 'error');
            updateStatusIndicator('online');
        }
    });
};

const initStudyPlanPage = () => {
    requireAuth();
    bindGlobalEvents();
    handleDailyHoursForm();
    const buttons = document.querySelectorAll('.toggle-button');
    buttons.forEach((button) => {
        button.addEventListener('click', () => {
            buttons.forEach((btn) => btn.classList.remove('is-active'));
            button.classList.add('is-active');
            loadStudyPlan(button.dataset.range);
        });
    });
    loadStudyPlan('daily');
    // پنلِ «پیش‌بینیِ هوشمند» (از 2026-09-09) — مستقل از بازه‌ی نمایش
    loadPredictions();
};

// ---------------------------------------------------------------------
// روترِ سبک: بر اساس ویژگیِ data-page روی <body> هر صفحه، تابعِ init
// مخصوصِ همان صفحه را صدا می‌زند. این جایگزینِ یک کتابخانه‌ی Routing واقعی
// (که برای این پروژه اضافی بود) است.
// ---------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', () => {
    const page = document.body.dataset.page;

    switch (page) {
        case 'login':
            handleLogin();
            break;
        case 'register':
            handleRegister();
            break;
        case 'reset-password':
            handlePasswordReset();
            break;
        case 'dashboard':
            initDashboardPage();
            break;
        case 'subjects':
            initSubjectsPage();
            break;
        case 'exams':
            initExamsPage();
            break;
        case 'study-plan':
            initStudyPlanPage();
            break;
        case 'study-log':
            initStudyLogPage();
            break;
        default:
            bindGlobalEvents();
    }
});
