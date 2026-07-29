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
const API_BASE = "http://127.0.0.1:8000";

// نگاشتِ اسمِ خوانا -> مسیرِ واقعیِ API؛ این‌طوری اگر یک روز آدرسِ API عوض
// شود، فقط همین‌جا را باید ویرایش کرد، نه همه‌جای کد را.
const endpoints = {
    login: "/api/auth/login/",
    register: "/api/auth/register/",
    dashboard: "/api/dashboard/",
    subjects: "/api/subjects/",
    subjectDetail: (id) => `/api/subjects/${id}/`,
    exams: "/api/exams/",
    examDetail: (id) => `/api/exams/${id}/`,
    studyPlan: (range) => `/api/study-plan/?range=${range}`,
    studyPlanGenerate: "/api/study-plan/generate/",
    studyLogs: "/api/study-logs/",
    studyLogDetail: (id) => `/api/study-logs/${id}/`,
};

// سلکتورهای CSS برای عناصرِ مشترک بین همه‌ی صفحات (نوار وضعیت، دکمه‌ی خروج و...)
const selectors = {
    toast: "#toast",
    userGreeting: "#userGreeting",
    statusText: "#statusText",
    statusDot: "#statusDot",
    logoutButton: "#logoutButton",
    sidebarToggle: "#sidebarToggle",
    backdrop: "#backdrop",
};

// کلیدهایی که با آن‌ها اطلاعاتِ نشست (Session) در localStorage مرورگر ذخیره می‌شود
const storageKeys = {
    token: "ssp_token",
    username: "ssp_username",
};

// --- توابع کوچکِ خواندن/نوشتن/پاک‌کردنِ localStorage ---
// (توکنِ JWT و نامِ کاربری بعد از ورود، همین‌جا نگه‌داری می‌شوند)
const getToken = () => localStorage.getItem(storageKeys.token);
const setToken = (token) => localStorage.setItem(storageKeys.token, token);
const clearToken = () => localStorage.removeItem(storageKeys.token);
const setStoredUsername = (username) => localStorage.setItem(storageKeys.username, username);
const getStoredUsername = () => localStorage.getItem(storageKeys.username);
const clearStoredUsername = () => localStorage.removeItem(storageKeys.username);

// ---------------------------------------------------------------------
// لایه‌ی ارتباط با API
// ---------------------------------------------------------------------

// نسخه اصلاح شده و هوشمند برای خواندن دقیق خطاهای جنگو
// این تابع «مرکزیِ» همه‌ی درخواست‌هاست: همه‌ی توابعِ apiGet/apiPost/apiDelete
// در نهایت همین تابع را صدا می‌زنند. مزیتش این است که هدرِ Authorization،
// تبدیلِ بدنه به JSON، و مدیریتِ خطا فقط یک‌بار (نه در هر تابع جداگانه) نوشته می‌شود.
const apiRequest = async (path, { method = "GET", body, headers = {}, skipAuth = false } = {}) => {
    const token = getToken();

    const finalHeaders = { ...headers };
    // اگر توکن داریم و این درخواست نیاز به احراز هویت دارد (اکثرِ درخواست‌ها)،
    // آن را در هدرِ استاندارد Authorization: Bearer <token> می‌گذاریم.
    if (!skipAuth && token) {
        finalHeaders.Authorization = `Bearer ${token}`;
    }

    let payload = body;
    if (body && !(body instanceof FormData)) {
        // اگر بدنه یک آبجکتِ معمولی (نه FormData) است، به JSON تبدیلش می‌کنیم
        finalHeaders["Content-Type"] = "application/json";
        payload = JSON.stringify(body);
    }

    // اگر مسیر از قبل یک URL کامل بود (با http شروع شود) همان را استفاده کن،
    // وگرنه API_BASE را جلویش بچسبان.
    const response = await fetch(path.startsWith("http") ? path : `${API_BASE}${path}`, {
        method,
        headers: finalHeaders,
        body: payload ?? undefined,
    });

    // کدِ ۲۰۴ یعنی «موفق ولی بدونِ محتوا» (مثلاً بعد از DELETE موفق)
    if (response.status === 204) {
        return null;
    }

    // تلاش برای Parse کردنِ JSON؛ اگر پاسخ اصلاً JSON نبود، یک آبجکتِ خالی برگردان
    const data = await response.json().catch(() => ({}));
    
    if (!response.ok) {
        // اگر پاسخ کدِ خطا داشت (400/401/403/...)، سعی می‌کنیم مناسب‌ترین پیامِ
        // خطا را از بین شکل‌های مختلفی که DRF ممکن است برگرداند پیدا کنیم:
        let message = "خطایی رخ داده است.";
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

// سه Wrapper کوچک روی apiRequest، فقط برای خواناتر شدنِ کدِ صدازننده
// (مثلاً apiGet(endpoints.subjects) به‌جای apiRequest(endpoints.subjects, {method: "GET"}))
const apiGet = (path, options) => apiRequest(path, { ...options, method: "GET" });
const apiPost = (path, body, options) => apiRequest(path, { ...options, method: "POST", body });
const apiDelete = (path, options) => apiRequest(path, { ...options, method: "DELETE" });

// ---------------------------------------------------------------------
// توابع کمکیِ رابط کاربریِ مشترک
// ---------------------------------------------------------------------

// نمایشِ یک پیامِ کوچکِ موقت (Toast) در گوشه‌ی صفحه، برای موفقیت/خطا/اطلاع‌رسانی
const showToast = (message, type = "info") => {
    const toast = document.querySelector(selectors.toast);
    if (!toast) return;
    toast.textContent = message;
    toast.classList.remove("is-visible");
    toast.dataset.type = type;
    // requestAnimationFrame باعث می‌شود کلاسِ is-visible در فریمِ بعدی اضافه
    // شود تا انیمیشنِ CSS (transition) واقعاً اجرا شود (نه این‌که چون کلاس
    // همان لحظه اضافه شده، مرورگر انیمیشن را رد کند).
    requestAnimationFrame(() => toast.classList.add("is-visible"));
    setTimeout(() => toast.classList.remove("is-visible"), 4200);
};

// نمایشِ «سلام، فلانی» در بالای صفحه، بر اساس نام کاربریِ ذخیره‌شده در مرورگر
const updateUserGreeting = () => {
    const label = document.querySelector(selectors.userGreeting);
    if (!label) return;
    const username = getStoredUsername();
    label.textContent = username ? `👋 سلام، ${username}` : "سلام دوست عزیز";
};

// به‌روزرسانیِ نشانگرِ کوچکِ وضعیت (آنلاین/در حال پردازش/خارج از سیستم) در سایدبار
const updateStatusIndicator = (status = "online") => {
    const statusText = document.querySelector(selectors.statusText);
    const dot = document.querySelector(selectors.statusDot);
    if (!statusText || !dot) return;

    if (!getToken()) {
        statusText.textContent = "خارج از سیستم";
        dot.style.background = "#9ca3af";
        dot.style.boxShadow = "0 0 0 6px rgba(156, 163, 175, 0.25)";
        return;
    }

    switch (status) {
        case "online":
            statusText.textContent = "آنلاین";
            dot.style.background = "#22c55e";
            dot.style.boxShadow = "0 0 0 6px rgba(34, 197, 94, 0.25)";
            break;
        case "busy":
            statusText.textContent = "در حال پردازش...";
            dot.style.background = "#facc15";
            dot.style.boxShadow = "0 0 0 6px rgba(250, 204, 21, 0.25)";
            break;
        default:
            statusText.textContent = "نامشخص";
            dot.style.background = "#9ca3af";
            dot.style.boxShadow = "0 0 0 6px rgba(156, 163, 175, 0.25)";
    }
};

// اگر کاربر توکن ندارد (لاگین نکرده)، به‌زور به صفحه‌ی ورود می‌فرستیمش.
// این تابع در ابتدای init هر صفحه‌ی محافظت‌شده صدا زده می‌شود.
const requireAuth = () => {
    if (!getToken()) {
        window.location.href = "login.html";
    }
};

// خروج از حساب: پاک‌کردنِ توکن/نام کاربری از مرورگر و بازگشت به صفحه‌ی ورود
const logout = () => {
    clearToken();
    clearStoredUsername();
    window.location.href = "login.html";
};

// رویدادهایی که در همه‌ی صفحات مشترک‌اند (دکمه‌ی خروج، باز/بسته‌شدنِ سایدبارِ
// موبایل با دکمه‌ی همبرگری و کلیک روی پس‌زمینه‌ی تیره) + به‌روزرسانیِ اولیه‌ی
// نام کاربری و وضعیتِ اتصال. تقریباً هر initXPage این تابع را صدا می‌زند.
const bindGlobalEvents = () => {
    const logoutButton = document.querySelector(selectors.logoutButton);
    if (logoutButton) {
        logoutButton.addEventListener("click", (event) => {
            event.preventDefault();
            logout();
        });
    }

    const toggle = document.querySelector(selectors.sidebarToggle);
    const backdrop = document.querySelector(selectors.backdrop);

    if (toggle) {
        toggle.addEventListener("click", () => document.body.classList.toggle("sidebar-open"));
    }
    if (backdrop) {
        backdrop.addEventListener("click", () => document.body.classList.remove("sidebar-open"));
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
    const progressList = document.getElementById("progressList");
    if (progressList) {
        progressList.innerHTML = "";
        const subjects = data?.subjects_progress ?? [];
        if (!subjects.length) {
            progressList.innerHTML = `<p class="empty-state">درسی ثبت نشده است.</p>`;
        } else {
            subjects.forEach((subject) => {
                const row = document.createElement("div");
                row.className = "progress-row";
                row.innerHTML = `
                    <h4>${subject.name}</h4>
                    <div class="progress-meta">
                        <span>سختی: ${subject.difficulty}/5</span>
                        <span>${subject.completed_hours} از ${subject.total_hours} ساعت</span>
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
    const timeline = document.getElementById("timelineList");
    if (timeline) {
        timeline.innerHTML = "";
        const exams = data?.upcoming_exams ?? [];
        if (!exams.length) {
            timeline.innerHTML = `<p class="empty-state">امتحان ثبت نشده است.</p>`;
        } else {
            exams.forEach((exam) => {
                const item = document.createElement("div");
                item.className = "timeline-item";
                item.innerHTML = `
                    <strong>${exam.subject_name}</strong>
                    <span>${exam.exam_date} • ${exam.remaining_days} روز باقی‌مانده</span>
                    <span>ساعت باقی‌مانده: ${exam.remaining_hours}</span>
                `;
                timeline.appendChild(item);
            });
        }
    }

    // پنل «هشدارها و یادآوری‌ها»: هر آیتم بر اساس alert.type رنگ‌بندیِ متفاوتی
    // می‌گیرد (قرمز=danger فوری، زرد=warning نزدیک، آبی=info یادآوریِ خنثی)
    const alertsList = document.getElementById("alertsList");
    if (alertsList) {
        alertsList.innerHTML = "";
        const alerts = data?.alerts ?? [];
        if (!alerts.length) {
            alertsList.innerHTML = `<p class="empty-state">هشداری وجود ندارد.</p>`;
        } else {
            alerts.forEach((alert) => {
                const item = document.createElement("div");
                // اگر نوعِ هشدار چیزی غیر از سه‌ حالتِ شناخته‌شده بود، برای
                // ایمنی آن را «info» در نظر می‌گیریم (نه این‌که قرمز/داعیِ خطا نشان بدهد)
                const validTypes = ["danger", "warning", "info"];
                const alertType = validTypes.includes(alert.type) ? alert.type : "info";
                item.className = `alert alert--${alertType}`;
                item.innerHTML = `
                    <span>${alert.message}</span>
                    <strong>${alert.subject ?? ""}</strong>
                `;
                alertsList.appendChild(item);
            });
        }
    }

    // پنل «تقسیم‌زمان پیشنهادی»: نمودارِ میله‌ایِ سهمِ هر درس از هفته‌ی پیش‌رو
    const distribution = document.getElementById("studyDistribution");
    if (distribution) {
        const dist = Array.isArray(data?.study_distribution) ? data.study_distribution : [];
        if (!dist.length) {
            distribution.innerHTML = `<p class="empty-state">داده‌ای برای نمایش نمودار وجود ندارد.</p>`;
        } else {
            distribution.innerHTML = "";
            dist.forEach((entry) => {
                const bar = document.createElement("div");
                bar.className = "mini-bar";
                // حداقل ۶٪ ارتفاع می‌گذاریم تا حتی مقادیرِ خیلی کوچک هم دیده شوند
                bar.style.height = `${Math.max(entry.percent, 6)}%`;
                bar.title = `${entry.label}: ${entry.hours ?? 0} ساعت در هفته‌ی پیش‌رو`;
                bar.innerHTML = `<span>${entry.label}</span>`;
                distribution.appendChild(bar);
            });
        }
    }
};

// درخواستِ داده از سرور و رندرِ کاملِ داشبورد؛ در initDashboardPage صدا زده می‌شود
const loadDashboard = async () => {
    try {
        updateStatusIndicator("busy");
        const data = await apiGet(endpoints.dashboard);
        renderDashboard(data);
        updateStatusIndicator("online");
    } catch (error) {
        showToast(error.message, "error");
        updateStatusIndicator("busy");
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
        case "difficulty":
            return sorted.sort((a, b) => b.difficulty - a.difficulty);
        case "progress":
            return sorted.sort((a, b) => b.progress_percent - a.progress_percent);
        default:
            return sorted.sort((a, b) => a.name.localeCompare(b.name, "fa"));
    }
};

const renderSubjects = (subjects) => {
    const tbody = document.getElementById("subjectsTableBody");
    if (!tbody) return;
    tbody.innerHTML = "";

    if (!subjects.length) {
        tbody.innerHTML = `<tr><td colspan="5" class="empty-state">درسی هنوز ثبت نشده است.</td></tr>`;
        return;
    }

    subjects.forEach((subject) => {
        const row = document.createElement("tr");
        row.innerHTML = `
            <td>${subject.name}</td>
            <td>${subject.difficulty}/5</td>
            <td>${Math.round(subject.progress_percent ?? 0)}%</td>
            <td>${subject.target_score ?? "-"}</td>
            <td>${subject.remaining_hours ?? 0}</td>
        `;
        tbody.appendChild(row);
    });
};

const loadSubjects = async (sortKey = "name") => {
    try {
        updateStatusIndicator("busy");
        const subjects = await apiGet(endpoints.subjects);
        renderSubjects(sortSubjects(subjects ?? [], sortKey));
        updateStatusIndicator("online");
    } catch (error) {
        showToast(error.message, "error");
    }
};

// ---------------------------------------------------------------------
// صفحه‌ی امتحان‌ها (exams.html)
// ---------------------------------------------------------------------

// پر کردنِ کشوی «انتخاب درس» در فرمِ ثبتِ امتحان (بر اساس درس‌های خودِ کاربر)
const populateSubjectSelect = async () => {
    const select = document.getElementById("examSubject");
    if (!select) return;
    try {
        const subjects = await apiGet(endpoints.subjects);
        select.innerHTML = `<option value="" disabled selected>ابتدا درس را انتخاب کنید</option>`;
        if (!subjects.length) {
            select.innerHTML = `<option value="" disabled>لطفاً ابتدا درسی ثبت کنید</option>`;
            return;
        }
        subjects.forEach((subject) => {
            const option = document.createElement("option");
            option.value = subject.id;
            option.textContent = subject.name;
            select.appendChild(option);
        });
    } catch (error) {
        showToast("بارگذاری درس‌ها با خطا مواجه شد.", "error");
    }
};

const renderExams = (exams) => {
    const tbody = document.getElementById("examTableBody");
    if (!tbody) return;
    tbody.innerHTML = "";

    if (exams.length === 0) {
        tbody.innerHTML = "<tr><td colspan='5' class='text-center'>هیچ امتحانی یافت نشد.</td></tr>";
        return;
    }

    const today = new Date();
    today.setHours(0, 0, 0, 0);

    exams.forEach((exam) => {
        const examDate = new Date(exam.exam_date);
        const diffTime = examDate - today;
        // تبدیلِ اختلافِ میلی‌ثانیه‌ای به تعداد روز (۱۰۰۰ میلی‌ثانیه × ۶۰ ثانیه × ۶۰ دقیقه × ۲۴ ساعت)
        const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
        
        let daysText = "";
        if (diffDays > 0) {
            daysText = `${diffDays} روز باقی‌مانده`;
        } else if (diffDays === 0) {
            daysText = "امروز!";
        } else {
            daysText = "گذشته";
        }

        // برچسبِ اهمیت/فوریتِ امتحان، صرفاً برای نمایشِ بصریِ سریع در جدول
        let importanceLabel = "کم";
        if (diffDays >= 0 && diffDays <= 3) {
            importanceLabel = "خیلی زیاد 🔴";
        } else if (diffDays > 3 && diffDays <= 7) {
            importanceLabel = "متوسط 🟡";
        } else if (diffDays > 7) {
            importanceLabel = "کم 🟢";
        }

        const row = document.createElement("tr");
        row.innerHTML = `
            <td>${exam.subject_name ?? exam.subject}</td>
            <td>${exam.exam_date} <br> <small class="text-muted">${daysText}</small></td>
            <td>${exam.study_hours_remaining ?? 0} ساعت</td>
            <td>${importanceLabel}</td>
            <td>${diffDays < 0 ? "پایان یافته" : "برنامه‌ریزی نشده"}</td>
        `;
        tbody.appendChild(row);
    });
};

const loadExams = async (filter = "upcoming") => {
    try {
        updateStatusIndicator("busy");
        const exams = await apiGet(endpoints.exams);
        let filtered = [...exams];
        if (filter === "upcoming") {
            // فقط امتحان‌هایی که تاریخ‌شان از امروز به بعد است نشان بده
            const today = new Date().toISOString().split("T")[0];
            filtered = filtered.filter((exam) => exam.exam_date >= today);
        }
        renderExams(filtered);
        updateStatusIndicator("online");
    } catch (error) {
        showToast(error.message, "error");
    }
};

// ---------------------------------------------------------------------
// ثبت مطالعه (StudyLog)
// ---------------------------------------------------------------------

// پر کردنِ کشوی «انتخاب امتحان» در فرمِ ثبتِ مطالعه؛ برای هر امتحان، ساعتِ
// باقی‌مانده‌اش هم در متنِ گزینه نشان داده می‌شود تا کاربر بداند کدام
// امتحان هنوز نیاز به مطالعه دارد.
const populateExamSelectForLog = async () => {
    const select = document.getElementById("logExam");
    if (!select) return;
    try {
        const exams = await apiGet(endpoints.exams);
        const sorted = [...exams].sort((a, b) => a.exam_date.localeCompare(b.exam_date));

        if (!sorted.length) {
            select.innerHTML = `<option value="" disabled selected>ابتدا یک امتحان ثبت کنید</option>`;
            return;
        }

        select.innerHTML = `<option value="" disabled selected>یک امتحان را انتخاب کنید</option>`;
        sorted.forEach((exam) => {
            const option = document.createElement("option");
            option.value = exam.id;
            const remaining = exam.study_hours_remaining ?? 0;
            const remainingText = remaining > 0 ? `${remaining} ساعت باقی‌مانده` : "کامل شده ✅";
            option.textContent = `${exam.subject_name ?? exam.subject} — ${exam.exam_date} (${remainingText})`;
            select.appendChild(option);
        });
    } catch (error) {
        showToast("بارگذاری امتحان‌ها با خطا مواجه شد.", "error");
    }
};

const renderStudyLogs = (logs) => {
    const tbody = document.getElementById("studyLogTableBody");
    if (!tbody) return;
    tbody.innerHTML = "";

    if (!logs.length) {
        tbody.innerHTML = `<tr><td colspan="5" class="empty-state">هنوز هیچ گزارش مطالعه‌ای ثبت نشده است.</td></tr>`;
        return;
    }

    logs.forEach((log) => {
        const row = document.createElement("tr");
        row.innerHTML = `
            <td>${log.exam_name ?? "-"}</td>
            <td>${log.date}</td>
            <td>${log.hours_studied} ساعت</td>
            <td>${log.notes ? log.notes : "-"}</td>
            <td><button type="button" class="ghost-button ghost-button--sm" data-log-id="${log.id}">حذف</button></td>
        `;
        tbody.appendChild(row);
    });

    // چون این دکمه‌های «حذف» بعد از رندر ساخته می‌شوند، رویدادشان را همین‌جا
    // (بعد از innerHTML) اضافه می‌کنیم؛ نه در HTML اصلیِ صفحه.
    tbody.querySelectorAll("[data-log-id]").forEach((button) => {
        button.addEventListener("click", () => deleteStudyLog(button.dataset.logId));
    });
};

const loadStudyLogs = async () => {
    try {
        updateStatusIndicator("busy");
        const logs = await apiGet(endpoints.studyLogs);
        renderStudyLogs(logs ?? []);
        updateStatusIndicator("online");
    } catch (error) {
        showToast(error.message, "error");
    }
};

const deleteStudyLog = async (id) => {
    // چون حذفِ لاگ، ساعتِ کسرشده را برنمی‌گرداند، قبل از حذف حتماً تأیید می‌گیریم
    if (!confirm("این گزارش مطالعه حذف شود؟ (ساعتِ باقی‌مانده‌ی امتحان دوباره برنمی‌گردد)")) return;
    try {
        await apiDelete(endpoints.studyLogDetail(id));
        showToast("گزارش مطالعه حذف شد.", "success");
        await loadStudyLogs();
    } catch (error) {
        showToast(error.message, "error");
    }
};

const handleStudyLogForm = () => {
    const form = document.getElementById("studyLogForm");
    if (!form) return;

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const formData = new FormData(form);

        const data = {
            exam: Number(formData.get("exam")),
            date: formData.get("date"),
            hours_studied: Number(formData.get("hours_studied")),
            notes: formData.get("notes") || "",
        };

        if (!data.exam || !data.date || !data.hours_studied || data.hours_studied <= 0) {
            showToast("لطفاً امتحان، تاریخ و ساعت مطالعه را درست وارد کنید.", "error");
            return;
        }

        try {
            await apiPost(endpoints.studyLogs, data);
            showToast("آفرین! گزارش مطالعه ثبت شد. 🎉", "success");
            form.reset();
            // بعد از ثبت، تاریخ را دوباره روی «امروز» می‌گذاریم (چون form.reset آن را خالی می‌کند)
            const dateInput = document.getElementById("logDate");
            if (dateInput) dateInput.value = new Date().toISOString().split("T")[0];
            // هم لیست گزارش‌ها و هم کشوی امتحان‌ها (که ساعتِ باقی‌مانده‌اش عوض شده) را تازه می‌کنیم
            await Promise.all([loadStudyLogs(), populateExamSelectForLog()]);
        } catch (error) {
            showToast(error.message, "error");
        }
    });
};

const initStudyLogPage = () => {
    requireAuth();
    bindGlobalEvents();
    handleStudyLogForm();
    const dateInput = document.getElementById("logDate");
    if (dateInput) dateInput.value = new Date().toISOString().split("T")[0];
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
    const hoursInput = document.getElementById("dailyHoursInput");
    if (hoursInput && plan?.daily_available_hours != null && document.activeElement !== hoursInput) {
        hoursInput.value = plan.daily_available_hours;
    }

    const container = document.getElementById("planContainer");
    if (!container) return;

    container.innerHTML = "";
    const items = plan?.schedule ?? [];

    if (!items.length) {
        // پیامِ خودِ بک‌اند (مثلاً «هیچ امتحان آینده‌ای وجود ندارد») را نشان بده،
        // یا اگر نبود، یک پیامِ عمومی
        container.innerHTML = `<p class="empty-state">${plan?.message ?? "داده‌ای برای نمایش وجود ندارد."}</p>`;
        const total = document.getElementById("totalRecommended");
        if (total) total.textContent = "0 ساعت";
        const daily = document.getElementById("averageDaily");
        if (daily) daily.textContent = "0";
        const priority = document.getElementById("prioritySubjects");
        if (priority) priority.textContent = "-";
        return;
    }

    items.forEach((entry) => {
        const block = document.createElement("div");
        block.className = "plan-block";
        // اگر این بلوک چند روز را ادغام کرده (days_covered > 1)، یک برچسبِ
        // کوچک («۴ روز») کنارِ عنوان نشان بده
        const daysChip = entry.days_covered > 1 ? `<span class="plan-days-chip">${entry.days_covered} روز</span>` : "";
        block.innerHTML = `
            <div class="plan-header">
                <h4>${entry.title} ${daysChip}</h4>
                <span class="plan-hours">${entry.hours_badge ?? `${entry.total_hours ?? 0} ساعت`}</span>
            </div>
        `;
        const tasksWrapper = document.createElement("div");
        tasksWrapper.className = "plan-tasks";

        entry.tasks?.forEach((task) => {
            const taskRow = document.createElement("div");
            taskRow.className = "plan-task";
            taskRow.innerHTML = `
                <strong>${task.subject}</strong>
                <span>${task.hours} ساعت</span>
            `;
            tasksWrapper.appendChild(taskRow);
        });

        block.appendChild(tasksWrapper);
        container.appendChild(block);
    });

    // خلاصه‌ی پایینِ صفحه: مجموع ساعات پیشنهادی، میانگین روزانه و پرکارترین درس‌ها
    const total = document.getElementById("totalRecommended");
    if (total) total.textContent = `${plan?.totals?.recommended_hours ?? 0} ساعت`;

    const daily = document.getElementById("averageDaily");
    if (daily) daily.textContent = plan?.totals?.average_daily ?? 0;

    const priority = document.getElementById("prioritySubjects");
    if (priority) {
        priority.innerHTML = "";
        const subjects = plan?.totals?.top_subjects ?? [];
        if (!subjects.length) {
            priority.textContent = "-";
        } else {
            subjects.forEach((subject) => {
                const tag = document.createElement("span");
                tag.className = "tag";
                tag.textContent = subject;
                priority.appendChild(tag);
            });
        }
    }
};

// دریافتِ برنامه برای یک بازه‌ی مشخص («daily» یا «weekly») و رندرِ آن
const loadStudyPlan = async (range = "daily") => {
    try {
        updateStatusIndicator("busy");
        const plan = await apiGet(endpoints.studyPlan(range));
        renderPlan(plan);
        updateStatusIndicator("online");
    } catch (error) {
        showToast(error.message, "error");
    }
};

// ---------------------------------------------------------------------
// صفحات ورود / ثبت‌نام
// ---------------------------------------------------------------------

const handleLogin = () => {
    const form = document.getElementById("loginForm");
    if (!form) return;

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const username = form.username.value.trim();
        const password = form.password.value;

        if (!username || !password) {
            showToast("لطفاً همه فیلدها را کامل کنید.", "error");
            return;
        }

        try {
            // skipAuth: true چون هنوز توکنی نداریم که در هدر بفرستیم
            const data = await apiPost(endpoints.login, { username, password }, { skipAuth: true });
            setToken(data.access);
            setStoredUsername(username);
            showToast("ورود موفقیت‌آمیز بود.", "success");
            window.location.href = "index.html"
        } catch (error) {
            showToast(error.message, "error");
        }
    });
};

const handleRegister = () => {
    const form = document.getElementById("registerForm");
    if (!form) return;

    form.addEventListener("submit", async (e) => {
        e.preventDefault(); 

        const formData = new FormData(form);
        const data = Object.fromEntries(formData.entries());

        try {
            // اضافه شدن { skipAuth: true } که جا افتاده بود
            await apiPost(endpoints.register, data, { skipAuth: true });

            showToast("ثبت‌نام با موفقیت انجام شد!", "success");

            // بعد از ثبت‌نامِ موفق، دکمه‌ی فرم را تبدیل به یک لینکِ «ورود به حساب» می‌کنیم
            const actionBtn = document.getElementById("authActionBtn");
            if (actionBtn) {
                actionBtn.textContent = "ورود به حساب"; 
                actionBtn.type = "button"; 
                actionBtn.classList.add("success-button");
                
                actionBtn.onclick = () => {
                    window.location.href = "login.html";
                };
            }

            const loginPrompt = document.getElementById("loginPrompt");
            if (loginPrompt) {
                loginPrompt.style.display = "none"; 
            }

        } catch (error) {
            console.error("Error:", error);
            showToast(error.message || "خطا در ثبت‌نام. لطفا دوباره تلاش کنید.", "error");
        }
    });
};

// ---------------------------------------------------------------------
// فرم‌های ثبتِ درس و امتحان
// ---------------------------------------------------------------------

const handleSubjectForm = () => {
    const form = document.getElementById("subjectForm");
    if (!form) return;

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const formData = {
            name: form.name.value.trim(),
            difficulty: Number(form.difficulty.value),
            target_score: form.target_score.value ? Number(form.target_score.value) : null,
            total_hours: Number(form.total_hours.value),
            notes: form.notes.value.trim(),
        };

        if (!formData.name || !formData.total_hours) {
            showToast("لطفاً نام درس و حجم مطالعه را پر کنید.", "error");
            return;
        }

        try {
            await apiPost(endpoints.subjects, formData);
            showToast("درس با موفقیت اضافه شد.", "success");
            form.reset();
            await loadSubjects(document.getElementById("subjectSort")?.value ?? "name");
        } catch (error) {
            showToast(error.message, "error");
        }
    });
};

const handleExamForm = () => {
    const form = document.getElementById("examForm");
    if (!form) return;

    form.addEventListener("submit", async (event) => {
        event.preventDefault(); 
        
        const formData = new FormData(form);
        
        const data = {
            subject: Number(formData.get("subject")), 
            exam_date: formData.get("exam_date"),
            chapters_remaining: Number(formData.get("chapters_remaining")),
            study_hours_remaining: Number(formData.get("study_hours_remaining")),
        };

        if (!data.subject || !data.exam_date || isNaN(data.chapters_remaining) || isNaN(data.study_hours_remaining)) {
            showToast("لطفاً فیلدهای ضروری را کامل کنید.", "error");
            return;
        }

        try {
            await apiPost(endpoints.exams, data);
            showToast("امتحان با موفقیت ثبت شد.", "success");
            form.reset();
            await loadExams(document.getElementById("examFilter")?.value ?? "upcoming");
        } catch (error) {
            showToast(error.message, "error");
        }
    });
};

// ---------------------------------------------------------------------
// توابعِ init هر صفحه (هرکدام: requireAuth + bindGlobalEvents + کارِ مخصوصِ صفحه)
// ---------------------------------------------------------------------

const initDashboardPage = () => {
    requireAuth();
    bindGlobalEvents();
    document.getElementById("refreshDashboard")?.addEventListener("click", loadDashboard);
    loadDashboard();
};

const initSubjectsPage = () => {
    requireAuth();
    bindGlobalEvents();
    const sortSelect = document.getElementById("subjectSort");
    if (sortSelect) {
        sortSelect.addEventListener("change", () => loadSubjects(sortSelect.value));
    }
    handleSubjectForm();
    loadSubjects(sortSelect?.value ?? "name");
};

const initExamsPage = () => {
    requireAuth();
    bindGlobalEvents();
    handleExamForm();
    populateSubjectSelect();
    const filterSelect = document.getElementById("examFilter");
    if (filterSelect) {
        filterSelect.addEventListener("change", () => loadExams(filterSelect.value));
    }
    loadExams(filterSelect?.value ?? "upcoming");
};

// دکمه‌ی «روزانه/هفتگی» که در حال حاضر کلاسِ is-active دارد را پیدا می‌کند
const getActiveRange = () => document.querySelector(".toggle-button.is-active")?.dataset.range ?? "daily";

// فرمِ تنظیمِ «ساعت آزاد روزانه» در صفحه‌ی برنامه‌ی مطالعه
const handleDailyHoursForm = () => {
    const form = document.getElementById("dailyHoursForm");
    if (!form) return;

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const dailyHours = Number(form.daily_available_hours.value);

        if (!dailyHours || dailyHours <= 0 || dailyHours > 24) {
            showToast("ساعت مطالعه روزانه باید عددی بین ۱ تا ۲۴ باشد.", "error");
            return;
        }

        try {
            updateStatusIndicator("busy");
            await apiPost(endpoints.studyPlanGenerate, { daily_available_hours: dailyHours });
            showToast("برنامه مطالعه به‌روزرسانی شد.", "success");
            // بعد از تولیدِ مجدد، برنامه را دوباره برای همان بازه‌ای که کاربر
            // در حالِ مشاهده‌اش بود (روزانه یا هفتگی) بارگذاری می‌کنیم
            await loadStudyPlan(getActiveRange());
            updateStatusIndicator("online");
        } catch (error) {
            showToast(error.message, "error");
            updateStatusIndicator("online");
        }
    });
};

const initStudyPlanPage = () => {
    requireAuth();
    bindGlobalEvents();
    handleDailyHoursForm();
    const buttons = document.querySelectorAll(".toggle-button");
    buttons.forEach((button) => {
        button.addEventListener("click", () => {
            buttons.forEach((btn) => btn.classList.remove("is-active"));
            button.classList.add("is-active");
            loadStudyPlan(button.dataset.range);
        });
    });
    loadStudyPlan("daily");
};

// ---------------------------------------------------------------------
// روترِ سبک: بر اساس ویژگیِ data-page روی <body> هر صفحه، تابعِ init
// مخصوصِ همان صفحه را صدا می‌زند. این جایگزینِ یک کتابخانه‌ی Routing واقعی
// (که برای این پروژه اضافی بود) است.
// ---------------------------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
    const page = document.body.dataset.page;

    switch (page) {
        case "login":
            handleLogin();
            break;
        case "register":
            handleRegister();
            break;
        case "dashboard":
            initDashboardPage();
            break;
        case "subjects":
            initSubjectsPage();
            break;
        case "exams":
            initExamsPage();
            break;
        case "study-plan":
            initStudyPlanPage();
            break;
        case "study-log":
            initStudyLogPage();
            break;
        default:
            bindGlobalEvents();
    }
});
