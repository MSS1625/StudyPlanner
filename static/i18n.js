// static/i18n.js
// ----------------------------------------------------------------------------
// زیرساختِ چندزبانیِ فرانت‌اند (از 2026-09-09).
//
// معماری (قرینه‌ی کاتالوگِ gettext بک‌اند): «کلید» همان متنِ فارسیِ اصلی است
// (نقشِ msgid) و «مقدار» ترجمه‌ی انگلیسی (نقشِ کاتالوگِ en). تابعِ t برای
// زبانِ فارسی خودِ کلید را برمی‌گرداند — یعنی رفتارِ پیش‌فرض دقیقاً همانِ
// قبل از این فایل است؛ فقط حالتِ «en» به دیکشنری نگاه می‌کند.
//
// سه سازوکار:
//   ۱) t(key, params): ترجمه‌ی رشته‌های پویا در app.js (توست‌ها، جدول‌ها و...)
//   ۲) applyI18n(): بارگذاریِ اولیه — متن‌های ثابتِ HTML و placeholder/aria
//      را در حالتِ انگلیسی با دیکشنری جایگزین می‌کند (فارسی = بدونِ تغییر)
//   ۳) دکمه‌ی #langToggle: تعویضِ زبان + ذخیره در localStorage + بارگذاریِ
//      مجددِ صفحه تا همه‌ی رندرهای پویا با زبانِ تازه ساخته شوند.
//
// app.js پیش از هر رندری به t() وابسته است؛ برای همین i18n.js باید در HTML
// «قبل از» app.js بارگذاری شود (ترتیبِ اسکریپت‌ها در همه‌ی صفحات رعایت شده).
// ----------------------------------------------------------------------------

// کلیدِ ذخیره‌سازیِ زبانِ انتخابی در localStorage (هم‌خانواده‌ی ssp_token)
const I18N_STORAGE_KEY = 'ssp_lang';

// دیکشنریِ فارسی → انگلیسی (کلید = متنِ اصلی؛ تولیدشده با اسکریپتِ
// scripts/gen_i18n_js.py و در برابرِ رشته‌های استخراج‌شده از HTML اعتبارسنجی
// شده — برایِ افزودنِ رشته‌ی جدید، هم‌زمان HTML/app.js و همین دیکشنری را
// به‌روز کنید).
const TRANSLATIONS = {
    "برنامه‌ریز هوشمند مطالعه": "Smart Study Planner",
    "برای دانشجویان هدفمند": "For goal-driven students",
    "داشبورد": "Dashboard",
    "درس‌ها": "Subjects",
    "امتحان‌ها": "Exams",
    "برنامه مطالعه": "Study Plan",
    "ثبت مطالعه": "Log Study",
    "در حال بررسی...": "Checking...",
    "حساب کاربری": "Account",
    "خروج": "Log Out",
    "خوش آمدید": "Welcome",
    "دانشجو": "Student",
    "ورود به حساب": "Log In",
    "0 ساعت": "0 hours",
    "داشبورد | برنامه‌ریز هوشمند مطالعه": "Dashboard | Smart Study Planner",
    "باز کردن منو": "Open menu",
    "داشبورد اصلی": "Main Dashboard",
    "تصویر کلی از وضعیت درس‌ها و امتحان‌های پیشِ رو": "An overview of your subjects and upcoming exams",
    "تعداد درس‌ها": "Subjects",
    "امتحان‌های ثبت‌شده": "Registered Exams",
    "میانگین پیشرفت": "Average Progress",
    "هشدارهای فوری": "Urgent Alerts",
    "هشدارها و یادآوری‌ها": "Alerts & Reminders",
    "پیشرفت درس‌ها": "Subject Progress",
    "به‌روزرسانی": "Refresh",
    "درسی ثبت نشده است.": "No subjects registered yet.",
    "تقویم مطالعه": "Study Calendar",
    "امتحان ثبت نشده است.": "No exams registered yet.",
    "هنوز امتحانی ثبت نشده است.": "No exams registered yet.",
    "هشداری وجود ندارد.": "No alerts.",
    "تقسیم‌زمان پیشنهادی": "Suggested Time Split",
    "سهم هر درس از ساعات مطالعه‌ی هفته‌ی پیش‌رو": "Each subject's share of study hours in the coming week",
    "در حال بارگذاری...": "Loading...",
    "داده‌ای برای نمایش نمودار وجود ندارد.": "No data to display in the chart.",
    "درس‌ها | برنامه‌ریز هوشمند مطالعه": "Subjects | Smart Study Planner",
    "مدیریت درس‌ها": "Manage Subjects",
    "درس‌های خود را تعریف و پیشرفت را کنترل کنید": "Define your subjects and track your progress",
    "افزودن درس جدید": "Add a New Subject",
    "نام درس": "Subject Name",
    "مثلاً پایگاه داده": "e.g. Databases",
    "سختی (۱ تا ۵)": "Difficulty (1 to 5)",
    "هدف نمره (اختیاری)": "Target Grade (optional)",
    "مثلاً 18": "e.g. 18",
    "یادداشت کوتاه": "Short Note",
    "ویژگی‌های مهم این درس": "Key points about this subject",
    "ثبت درس": "Add Subject",
    "پاک‌سازی": "Clear",
    "فهرست درس‌ها": "Subject List",
    "مرتب‌سازی بر اساس:": "Sort by:",
    "حروف الفبا": "Alphabetical",
    "سختی": "Difficulty",
    "پیشرفت": "Progress",
    "هدف": "Goal",
    "ساعت باقی‌مانده": "Hours Left",
    "درسی هنوز ثبت نشده است.": "No subjects added yet.",
    "امتحان‌ها | برنامه‌ریز هوشمند مطالعه": "Exams | Smart Study Planner",
    "مدیریت امتحان‌ها و ددلاین‌ها": "Manage Exams & Deadlines",
    "برای هر درس، زمان مناسب برنامه‌ریزی کنید": "Plan the right time for each subject",
    "ثبت امتحان یا ددلاین": "Add Exam or Deadline",
    "انتخاب درس:": "Select subject:",
    "ابتدا درس را انتخاب کنید": "Select a subject first",
    "تاریخ امتحان یا ددلاین:": "Exam or deadline date:",
    "مثلا: ۵": "e.g. 5",
    "تعداد فصل/بخش باقی‌مانده:": "Remaining chapters/sections:",
    "ساعت مطالعه تخمینی باقی‌مانده:": "Estimated study hours remaining:",
    "مثلا: ۲۰": "e.g. 20",
    "یادداشت (اختیاری):": "Notes (optional):",
    "مثلاً: میان‌ترم، سالنِ ۲، فصل‌های ۱ تا ۵": "e.g. Midterm, Hall 2, Chapters 1-5",
    "ذخیره امتحان": "Save Exam",
    "انصراف از ویرایش": "Cancel edit",
    "فهرست امتحان‌ها": "Exam List",
    "نمایش:": "Show:",
    "فقط امتحان‌های آینده": "Upcoming exams only",
    "همه": "All",
    "درس": "Subject",
    "تاریخ": "Date",
    "درجه اهمیت": "Priority",
    "وضعیت": "Status",
    "عملیات": "Actions",
    "هیچ امتحانی یافت نشد.": "No exams found.",
    "ثبت مطالعه | برنامه‌ریز هوشمند مطالعه": "Log Study | Smart Study Planner",
    "هر بار که درس خواندی، همین‌جا ثبتش کن تا پیشرفتت واقعی باشد": "Every time you study, log it here so your progress stays real",
    "امروز چقدر خواندی؟": "How much did you study today?",
    "برای کدام امتحان؟": "For which exam?",
    "در حال بارگذاری امتحان‌ها...": "Loading exams...",
    "تاریخ مطالعه": "Study date",
    "چند ساعت خواندی؟": "How many hours did you study?",
    "مثلاً 1.5": "e.g. 1.5",
    "یادداشت (اختیاری)": "Notes (optional)",
    "مثلاً: فصل ۳ رو تموم کردم": "e.g. Finished chapter 3",
    "تاریخچه‌ی مطالعه": "Study History",
    "امتحان": "Exam",
    "ساعت": "Hours",
    "یادداشت": "Notes",
    "حذف": "Delete",
    "هنوز هیچ گزارش مطالعه‌ای ثبت نشده است.": "No study sessions logged yet.",
    "برنامه مطالعه | برنامه‌ریز هوشمند مطالعه": "Study Plan | Smart Study Planner",
    "برنامه‌ مطالعاتی پیشنهادی": "Recommended Study Plan",
    "الگوریتم ساده‌ی سیستم بر اساس حجم کار باقی‌مانده": "A simple rule-based algorithm driven by remaining workload",
    "بازه زمانی": "Time Range",
    "برنامه روزانه": "Daily Plan",
    "برنامه هفتگی": "Weekly Plan",
    "کل ساعت توصیه‌شده": "Total Recommended Hours",
    "درس‌های در اولویت": "Priority Subjects",
    "میانگین ساعت روزانه": "Average Daily Hours",
    "ساعت آزاد روزانه": "Daily Free Hours",
    "چند ساعت در روز می‌توانی درس بخوانی؟": "How many hours a day can you study?",
    "تولید / به‌روزرسانی برنامه": "Generate / Update Plan",
    "جزئیات برنامه": "Plan Details",
    "در حال بارگذاری برنامه...": "Loading plan...",
    "ورود | برنامه‌ریز هوشمند مطالعه": "Log In | Smart Study Planner",
    "برای ادامه، نام کاربری و رمز عبور را وارد کنید.": "Enter your username and password to continue.",
    "نام کاربری": "Username",
    "رمز عبور": "Password",
    "ورود": "Log In",
    "حساب ندارید؟": "Don't have an account?",
    "ثبت‌نام کنید": "Sign up",
    "ثبت‌نام | برنامه‌ریز هوشمند مطالعه": "Sign Up | Smart Study Planner",
    "ایجاد حساب جدید": "Create a New Account",
    "با ساخت حساب، برنامه‌ مطالعاتی خود را مدیریت کنید.": "Create an account to manage your study plan.",
    "ایمیل (اختیاری)": "Email (optional)",
    "ثبت‌نام": "Sign Up",
    "حساب دارید؟": "Already have an account?",
    "سلام دوست عزیز": "Hi there",
    "آنلاین": "Online",
    "خارج از سیستم": "Logged out",
    "در حال پردازش...": "Processing...",
    "نامشخص": "Unknown",
    "خطایی رخ داده است.": "Something went wrong.",
    "بارگذاری درس‌ها با خطا مواجه شد.": "Failed to load subjects.",
    "بارگذاری امتحان‌ها با خطا مواجه شد.": "Failed to load exams.",
    "ابتدا یک امتحان ثبت کنید": "Register an exam first",
    "یک امتحان را انتخاب کنید": "Select an exam",
    "کامل شده ✅": "Completed ✅",
    "ویرایش": "Edit",
    "ویرایش این امتحان": "Edit this exam",
    "ویرایش امتحان": "Edit Exam",
    "به‌روزرسانی امتحان": "Update Exam",
    "گزارش مطالعه حذف شد و ساعتِ آن به امتحان برگشت.": "Study session deleted and its hours were returned to the exam.",
    "این گزارش مطالعه حذف شود؟ ساعتِ مطالعه‌ی آن به امتحانِ مربوطه برمی‌گردد.": "Delete this study session? Its hours will be returned to the exam.",
    "آفرین! گزارش مطالعه ثبت شد. 🎉": "Well done! Study session logged. 🎉",
    "لطفاً امتحان، تاریخ و ساعت مطالعه را درست وارد کنید.": "Please enter a valid exam, date and study hours.",
    "داده‌ای برای نمایش وجود ندارد.": "No data to display.",
    "نشست شما منقضی شده بود؛ لطفاً دوباره وارد شوید.": "Your session had expired. Please log in again.",
    "لطفاً همه فیلدها را کامل کنید.": "Please fill in all fields.",
    "ورود موفقیت‌آمیز بود.": "Login successful.",
    "ثبت‌نام با موفقیت انجام شد!": "Registration successful!",
    "خطا در ثبت‌نام. لطفا دوباره تلاش کنید.": "Registration failed. Please try again.",
    "لطفاً نام درس را وارد کنید.": "Please enter the subject name.",
    "درس با موفقیت اضافه شد.": "Subject added successfully.",
    "لطفاً فیلدهای ضروری را کامل کنید.": "Please fill in the required fields.",
    "امتحان با موفقیت به‌روزرسانی شد.": "Exam updated successfully.",
    "امتحان با موفقیت ثبت شد.": "Exam registered successfully.",
    "ساعت مطالعه روزانه باید عددی بین ۱ تا ۲۴ باشد.": "Daily study hours must be a number between 1 and 24.",
    "برنامه مطالعه به‌روزرسانی شد.": "Study plan updated.",
    "نشست شما منقضی شده است؛ لطفاً دوباره وارد شوید.": "Your session has expired. Please log in again.",
    "👋 سلام، {username}": "👋 Hi, {username}",
    "{hours} ساعت": "{hours} hours",
    "{days} روز باقی‌مانده": "{days} days remaining",
    "{hours} ساعت باقی‌مانده": "{hours} hours remaining",
    "ساعت باقی‌مانده: {hours}": "Hours remaining: {hours}",
    "سختی: {difficulty}/5": "Difficulty: {difficulty}/5",
    "{completed} از {total} ساعت": "{completed} of {total} hours",
    "{days} روز": "{days} days",
    "{label}: {hours} ساعت در هفته‌ی پیش‌رو": "{label}: {hours} hours in the coming week",
    "امروز!": "Today!",
    "گذشته": "Past",
    "پایان یافته": "Finished",
    "برنامه‌ریزی نشده": "Not scheduled",
    "کم": "Low",
    "کم 🟢": "Low 🟢",
    "متوسط 🟡": "Medium 🟡",
    "خیلی زیاد 🔴": "Very high 🔴",
    "لطفاً ابتدا درسی ثبت کنید": "Please add a subject first",
    // --- پنلِ «پیش‌بینیِ هوشمند» (مؤلفه‌ی یادگیریِ آماری، از 2026-09-09) ---
    "پیش‌بینی هوشمند زمان واقعی": "Smart Actual-Time Forecast",
    "پیش‌بینیِ ساعتِ واقعیِ موردنیاز از تاریخچه‌ی مطالعه‌ی خودِ شما": "Predicts the real hours you will need, learned from your own study history",
    "در حال بارگذاری پیش‌بینی...": "Loading predictions...",
    "امتحانِ پیش‌رویی برای پیش‌بینی وجود ندارد.": "No upcoming exams to predict.",
    "مدلِ یادگیریِ شما": "Your learning model",
    "سوگیریِ تخمین": "Estimation bias",
    "تخمین‌های شما کمتر از واقعیت است": "Your estimates run low (you study more than planned)",
    "تخمین‌های شما بیشتر از واقعیت است": "Your estimates run high (you need less than planned)",
    "تخمین‌های شما دقیق است": "Your estimates are on target",
    "هنوز تاریخچه‌ی کافی برای یادگیری نیست": "Not enough history to learn from yet",
    "نمونه‌های آموزشی": "Training samples",
    "اعتماد مدل": "Model confidence",
    "{value}٪": "{value}%",
    "ریسک بالا": "High risk",
    "ریسک متوسط": "Medium risk",
    "ریسک کم": "Low risk",
    "تخمین شما": "Your estimate",
    "نیاز روزانه": "Daily need",
    "روزهای باقی‌مانده": "Days left",
};

// زبانِ فعال: فقط «en» ترجمه می‌شود؛ هر مقدارِ دیگر = فارسی (پیش‌فرض)
function currentLang() {
    try {
        return localStorage.getItem(I18N_STORAGE_KEY) === 'en' ? 'en' : 'fa';
    } catch (e) {
        return 'fa'; // localStorage در دسترس نیست (حالتِ خصوصیِ بعضی مرورگرها)
    }
}

// ترجمه با پارامترهای {name} — مثال: t('{days} روز', { days: 3 })
function t(key, params) {
    let text = key;
    if (currentLang() === 'en' && Object.prototype.hasOwnProperty.call(TRANSLATIONS, key)) {
        text = TRANSLATIONS[key];
    }
    if (params) {
        for (const [name, value] of Object.entries(params)) {
            text = text.split('{' + name + '}').join(String(value ?? ''));
        }
    }
    return text;
}

function setLanguage(lang) {
    try {
        localStorage.setItem(I18N_STORAGE_KEY, lang);
    } catch (e) {
        /* نادیده — در حالتِ بدونِ localStorage، انتخاب فقط تا رفرش بعدی می‌ماند */
    }
}

// جایگزینیِ متن‌های ثابتِ صفحه در حالتِ انگلیسی. فقط در حالتِ en کاری
// می‌کند (فارسی = متنِ اصلیِ خودِ HTML، بدونِ دست‌کاری).
function applyI18n() {
    const lang = currentLang();
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === 'en' ? 'ltr' : 'rtl';
    if (lang !== 'en') return;

    // متن‌ها: با TreeWalker از خودِ document (شاملِ <title> در head)؛
    // فقط گره‌هایی که متنِ trim‌شده‌شان کلیدِ دیکشنری است ترجمه می‌شوند —
    // فاصله‌های ابتدا/انتهایِ گره (تورفتگیِ HTML) دست‌نخورده می‌مانند.
    const walker = document.createTreeWalker(document, NodeFilter.SHOW_TEXT, {
        acceptNode(node) {
            const parent = node.parentNode;
            if (parent && (parent.nodeName === 'SCRIPT' || parent.nodeName === 'STYLE')) {
                return NodeFilter.FILTER_REJECT;
            }
            const value = node.nodeValue.trim();
            if (value && Object.prototype.hasOwnProperty.call(TRANSLATIONS, value)) {
                return NodeFilter.FILTER_ACCEPT;
            }
            return NodeFilter.FILTER_SKIP;
        },
    });
    const targets = [];
    let node;
    while ((node = walker.nextNode())) targets.push(node);
    targets.forEach((n) => {
        const raw = n.nodeValue;
        const core = raw.trim();
        const start = raw.indexOf(core);
        n.nodeValue = raw.slice(0, start) + TRANSLATIONS[core] + raw.slice(start + core.length);
    });

    // ویژگی‌ها: placeholder / title / aria-label (مقادیرِ فارسیِ ثابتِ HTML)
    document.querySelectorAll('[placeholder],[title],[aria-label]').forEach((el) => {
        ['placeholder', 'title', 'aria-label'].forEach((attr) => {
            const value = el.getAttribute(attr);
            if (value && Object.prototype.hasOwnProperty.call(TRANSLATIONS, value.trim())
                && value.trim() === value) {
                el.setAttribute(attr, TRANSLATIONS[value]);
            }
        });
    });
}

// اجرایِ بخشِ مرورگری فقط وقتی document وجود دارد (تست‌پذیری در Node)
if (typeof document !== 'undefined') {
    document.addEventListener('DOMContentLoaded', () => {
        applyI18n();
        // دکمه‌ی تعویضِ زبان: برچسبش همیشه «زبانِ مقصد» را نشان می‌دهد
        const toggle = document.getElementById('langToggle');
        if (toggle) {
            toggle.textContent = currentLang() === 'en' ? 'فارسی' : 'English';
            toggle.addEventListener('click', () => {
                setLanguage(currentLang() === 'en' ? 'fa' : 'en');
                // بارگذاریِ مجدد: ساده‌ترین راهِ «دوباره‌سازیِ همه‌ی رندرهای پویا»
                // (جدول‌ها، برنامه و...) با زبانِ تازه — بدونِ ردیابیِ دستیِ حالت
                window.location.reload();
            });
        }
    });
}

// برایِ تست‌پذیریِ خارج از مرورگر (Node): فقط دیکشنری را صادر می‌کند
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { TRANSLATIONS, I18N_STORAGE_KEY };
}
