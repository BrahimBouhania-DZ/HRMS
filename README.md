# HRMS — نظام تسيير الموارد البشرية

> **Human Resource Management System** — نظام متكامل لإدارة الموارد البشرية، مبني بـ **Django 5**، يدعم **العربية (RTL) والفرنسية والإنجليزية**.

---

## ✨ المزايا

| الوحدة | الوظائف |
|---|---|
| **الهيكل التنظيمي** | فروع، أقسام، مناصب، جداول دوام |
| **الموظفون** | ملفات موظفين، عقود، سجل وظيفي، مستندات، بحث متقدم |
| **QR والبطاقات** | إصدار/إعادة توليد رمز QR + بطاقة موظف قابلة للطباعة |
| **الحضور/الانصراف** | مسح QR (هاتف/قارئ ثابت)، أيام حضور، تأخير/غياب |
| **الإجازات** | أنواع قابلة للتكوين، أرصدة سنوية، دورة موافقات متعددة المستويات |
| **الرواتب** | دورات رواتب، قسائم، عناصر أجر، تصدير بنك، PDF |
| **الصلاحيات (RBAC)** | أدوار وصلاحيات وScope، Deny يتفوق دائمًا |
| **الإشعارات والتقارير** | إشعارات داخلية، تقارير PDF/Excel |
| **التوظيف** | إعلانات وظائف، مرشحون، مقابلات، استيراد من Excel |
| **الذكاء الاصطناعي** | مساعد ذكي، تنبؤ مخاطر الاستقالة/الغياب، تحليلات التدريب |
| **لوحة التحكم السرية** | تغيير شعار الشركة + جميع الألوان (صفحة مخفية للمبرمج) |

---

## 🛠️ التقنيات

| المكون | التفاصيل |
|---|---|
| **Python** | 3.12+ |
| **Django** | 5.x |
| **قاعدة البيانات** | PostgreSQL (إنتاج) / SQLite (تطوير) |
| **المكتبات** | Pillow, qrcode, WeasyPrint, DRF |
| **النشر** | Gunicorn + Nginx + systemd (`deploy/`) |
| **المتصفح** | Chromium (Playwright للاختبارات البصرية) |

---

## 📁 بنية المشروع

```
HRMS/
├── config/
│   └── settings/
│       ├── base.py          # الإعدادات الأساسية المشتركة
│       ├── dev.py           # إعدادات التطوير (SQLite / DEBUG=True)
│       ├── prod.py          # إعدادات الإنتاج
│       └── test.py          # إعدادات الاختبارات
├── apps/
│   ├── core/                # لوحة رئيسية، بحث، سجل تدقيق، هوية الشركة
│   │   ├── views_branding.py   # عروض صفحة الشعار السرية
│   │   ├── branding_utils.py   # أدوات توليد الألوان
│   │   ├── context_processors.py  # حقن BRANDING_CSS في جميع القوالب
│   │   └── management/commands/
│   │       ├── seed_all.py          # تهيئة RBAC + إجازات + مشرف
│   │       ├── seed_branding.py     # تهيئة هوية الشركة
│   │       ├── seed_branding_admin.py # إنشاء حساب المبرمج
│   │       ├── seed_demo.py         # بيانات تجريبية
│   │       └── deploy_prepare.py    # تحضير النشر
│   ├── auth_app/            # RBAC: مستخدمون، أدوار، صلاحيات
│   ├── org/                 # فروع، أقسام، مناصب، دوام
│   ├── employees/           # موظفون، عقود، QR Engine، بطاقة قابلة للطباعة
│   ├── attendance/          # مسح QR، أيام حضور، استثناءات
│   ├── leave/               # إجازات، أرصدة، طلبات وموافقات
│   ├── payroll/             # دورات رواتب، قسائم، عناصر أجر
│   ├── devices/             # قارئات QR
│   ├── recruitment/         # توظيف: إعلانات، مرشحون، مقابلات
│   ├── training/            # دورات وجلسات تدريبية
│   ├── perf/                # تقييم الأداء
│   ├── notif/               # إشعارات داخلية
│   ├── reports/             # تقارير PDF/Excel
│   ├── ai/                  # مساعد ذكي، تنبؤات، تحليلات
│   └── api/                 # واجهة REST للموبايل
├── templates/               # قوالب Django
├── static/
│   ├── css/base.css         # الهوية البصرية (CSS Variables)
│   └── admin/custom_admin.css  # تنسيقات لوحة Django الإدارية
├── media/
│   └── branding/            # شعار الشركة + صور الموظفين
├── docs/                    # الوثائق الهندسية (00-index.md → 17-ux-review.md)
└── deploy/                  # gunicorn + nginx + systemd
```

---

## ⚙️ البيئة المتغيرات (.env)

> ⚠️ **ملف `.env` لا يُرفع إلى Git إطلاقًا** — احتفظ به محليًا فقط.

| المفتاح | الوصف | القيمة الحالية |
|---|---|---|
| `DJANGO_SECRET_KEY` | مفتاح سري للتوقيع | `CHANGE_ME_generate_a_long_random_secret_key` |
| `DJANGO_DEBUG` | وضع التطوير | `True` |
| `DJANGO_LANGUAGE_CODE` | اللغة الافتراضية | `ar` |
| `DJANGO_TIME_ZONE` | المنطقة الزمنية | `Africa/Algiers` |
| `DJANGO_ALLOWED_HOSTS` | النطاقات المسموحة | `127.0.0.1,localhost` |
| `DJANGO_DB_ENGINE` | محرك قاعدة البيانات | `postgres` |
| `DJANGO_DB_NAME` | اسم قاعدة البيانات | `hrms` |
| `DJANGO_DB_USER` | مستخدم قاعدة البيانات | `hrms` |
| `DJANGO_DB_PASSWORD` | كلمة مرور قاعدة البيانات | `<CHANGE_ME_db_password>` |
| `DJANGO_DB_HOST` | مضيف قاعدة البيانات | `localhost` |
| `DJANGO_DB_PORT` | منفذ قاعدة البيانات | `5432` |
| `BRANDING_SECRET_PATH` | المسار السري للوحة التحكم | `<BRANDING_SECRET_PATH>` |
| `BRANDING_ADMIN_USERNAME` | حساب المبرمج | `<BRANDING_ADMIN_USERNAME>` |
| `BRANDING_ADMIN_PASSWORD` | كلمة مرور المبرمج | `<CHANGE_ME_branding_password>` |
| `BRANDING_ADMIN_EMAIL` | بريد المبرمج | `branding@hrms.local` |
| `ADMIN_USERNAME` | حساب المشرف | `admin` |
| `ADMIN_PASSWORD` | كلمة مرور المشرف | `CHANGE_ME_strong_unique_admin_password` |
| `ADMIN_EMAIL` | بريد المشرف | `admin@hrms.local` |

---

## 🔐 بيانات الدخول

### 1. حساب المشرف العام (Django Admin)

| العنصر | القيمة |
|---|---|
| **URL** | `http://<HOST>:<PORT>/sec-admin/` |
| **المستخدم** | `admin` |
| **كلمة المرور** | `CHANGE_ME_strong_unique_admin_password` |
| **ملاحظة** | يُنشئه أمر `seed_all` — غيّر كلمة المرور بعد أول دخول |

### 2. حسابات الموظفين التجريبية (بعد `seed_demo`)

| المستخدم | كلمة المرور |
|---|---|
| `emp-101` | `Demo@2026!` |
| `emp-102` | `Demo@2026!` |
| `emp-103` | `Demo@2026!` |
| `emp-104` | `Demo@2026!` |
| `emp-105` | `Demo@2026!` |
| `emp-106` ... `emp-115` | `Demo@2026!` |

### 3. حساب المبرمج — لوحة التحكم السرية (الشعار + الألوان)

| العنصر | القيمة |
|---|---|
| **المسار السري** | `http://<HOST>:<PORT>/<BRANDING_SECRET_PATH>/` |
| **المستخدم** | `<BRANDING_ADMIN_USERNAME>` |
| **كلمة المرور** | `<CHANGE_ME_branding_password>` |
| **البريد** | `branding@hrms.local` |
| **ملاحظة** | لا توجد في أي قائمة — افتح المسار مباشرةً. الحساب is_staff فقط (ليس superuser) |

> ⚠️ **تكرار محاولات الدخول**: بعد 8 محاولات فاشلة، يُحظر الدخول 15 دقيقة.

---

## 🎨 لوحة التحكم السرية — الشعار والألوان

صفحة مخفية للمبرمج/المدير لتعديل:
- **شعار الشركة** (رفع/مسح صورة)
- **جميع الألوان** (46 متغير CSS — أزرق، رملي، ذهبي، أخضر، أحمر، خلفيات، حدود)
- **معلومات الهوية** (اسم الشركة 3 لغات، التاغلاين، خيارات ووترمارك البطاقة)
- **4 مقاييس لونية جاهزة** (الأصلية، ملكي بنفسجي، زمردي، دافئ ترابي)
- **استعادة الافتراضي** بنقرة واحدة

```
URL:  http://<HOST>:<PORT>/<BRANDING_SECRET_PATH>/
      → صفحة الدخول
      http://<HOST>:<PORT>/<BRANDING_SECRET_PATH>/dashboard/
      → لوحة التحكم بعد الدخول
```

عمليات الحفظ تُسجَّل في **سجل التدقيق** (`AuditLog`).

---

## 🗄️ قاعدة البيانات

### الاتصال (PostgreSQL)

| العنصر | القيمة |
|---|---|
| **النوع** | PostgreSQL 15+ |
| **المضيف** | `localhost:5432` |
| **اسم القاعدة** | `hrms` |
| **المستخدم** | `hrms` |
| **كلمة المرور** | `<CHANGE_ME_db_password>` |

```bash
# اختبار الاتصال
psql -h localhost -U hrms -d hrms -c "SELECT 1"
```

### SQLite (التطوير)

لлаستخدام SQLite بدلاً من PostgreSQL:
```bash
# عدّل .env
DJANGO_DB_ENGINE=sqlite
# ثم أعد تشغيل المigrات
python manage.py migrate
```

---

## 🚀 التشغيل

### تشغيل التطوير

```bash
# 1) تفعيل البيئة الافتراضية
source .venv/bin/activate

# 2) تحميل متغيرات البيئة
set -a; source .env; set +a

# 3) تشغيل الخادم
python manage.py runserver                    # المنفذ 8000
python manage.py runserver 127.0.0.1:8022     # منفذ مخصص
python manage.py runserver 127.0.0.1:8022 --noreload  # بدون إعادة تحميل تلقائي
```

###曜.example of running on LAN

```bash
# للوصول من أجهزة أخرى في الشبكة
python manage.py runserver 0.0.0.0:8022

# ثم افتح من جهاز آخر
http://<IP_ADDRESS>:8022/
```

---

## 📋 أوامر إدارة مهمة (Management Commands)

### التهيئة الأولية

```bash
# تهيئة كاملة: RBAC + أنواع إجازات + مشرف افتراضي
python manage.py seed_all

# تهيئة مع أرصدة سنة محددة
python manage.py seed_all --year 2027

# بدون إنشاء مشرف
python manage.py seed_all --no-admin
```

### هوية الشركة والشعار

```bash
# تهيئة شعار وهوية الشركة الافتراضية
python manage.py seed_branding

# إنشاء حساب المبرمج للوحة التحكم السرية
python manage.py seed_branding_admin
```

### البيانات التجريبية

```bash
# بيانات تجريبية: هيكل + 15 موظف + حضور + إجازات
python manage.py seed_demo

# مع دورة رواتب
python manage.py seed_demo --payrun

# عدد موظفين محدد
python manage.py seed_demo --employees 12

# بدون حسابات مستخدمين
python manage.py seed_demo --no-users
```

### الذكاء الاصطناعي

```bash
python manage.py seed_training                 # دورات/جلسات تدريبية
python manage.py seed_ai_data                  # بيانات تدريب للتنبؤ
python manage.py seed_ai_data --employees 80 --departed 0.25
python manage.py train_ai_models               # تدريب نموذج مخاطر الاستقالة
python manage.py train_ai_models --all         # + نموذج مخاطر الغياب
python manage.py retrain_ai_models_scheduled   # إعادة تدريب مجدولة
```

### النشر

```bash
# تحضير الإنتاج
export DJANGO_SETTINGS_MODULE=config.settings.prod
python manage.py deploy_prepare               # check + هجرات + collectstatic

# جمع الملفات الثابتة
python manage.py collectstatic --noinput
```

### إدارة قاعدة البيانات

```bash
# هجرات
python manage.py migrate

# إنشاء هجرة لتعديلات النماذج
python manage.py makemigrations

# عرض الهجرات
python manage.py showmigrations

# فحص النظام
python manage.py check
python manage.py check --deploy               # فحص أمان الإنتاج
```

---

## 🌐 جميع الروابط

### الصفحات الرئيسية

| الصفحة | المسار | الصلاحية |
|---|---|---|
| الرئيسية (لوحة المؤشرات) | `/` |所有 المستخدمين المسجلين |
| تسجيل الدخول | `/auth/login/` | عام |
| تسجيل الخروج | `/auth/logout/` | جميع المسجلين |

### الموظفون

| الصفحة | المسار | الصلاحية |
|---|---|---|
| قائمة الموظفين | `/employees/` | `employees.view` |
| إضافة موظف | `/employees/add/` | `employees.add` |
| ملف موظف + بطاقة QR | `/employees/<pk>/` | `employees.view` |
| بطاقة موظف قابلة للطباعة | `/employees/<pk>/card/` | `employees.view` |
| العقود | `/employees/contracts/` | `employees.view` |
| الوثائق | `/employees/documents/` | `employees.view` |

### الهيكل التنظيمي

| الصفحة | المسار | الصلاحية |
|---|---|---|
| الفروع | `/org/branches/` | `org.branch.view` |
| الأقسام | `/org/departments/` | `org.department.view` |
| المناصب | `/org/positions/` | `org.position.view` |
| جداول الدوام | `/org/shifts/` | `org.shift.view` |

### الحضور والإجازات

| الصفحة | المسار | الصلاحية |
|---|---|---|
| أيام الحضور | `/attendance/` | `attendance.view` |
| حضوري (الموظف) | `/attendance/my/` | جميع المسجلين |
| بطاقة QR الخاصة بي | `/attendance/qr/` | جميع المسجلين |
| طلبات الإجازة | `/leave/` | `leave.view` |
| إجازاتي | `/leave/my/` | جميع المسجلين |
| الأرصدة | `/leave/balances/` | `leave.view` |

### الرواتب والأداء

| الصفحة | المسار | الصلاحية |
|---|---|---|
| دورات الرواتب | `/payroll/` | `payroll.view` |
| عناصر الأجر | `/payroll/elements/` | `payroll.view` |
| دورات التقييم | `/perf/cycles/` | `perf.view` |
| التقييمات | `/perf/reviews/` | `perf.view` |

### التدريب والتوظيف

| الصفحة | المسار | الصلاحية |
|---|---|---|
| الدورات | `/training/courses/` | `training.view` |
| جلسات التدريب | `/training/sessions/` | `training.view` |
| إعلانات التوظيف | `/recruitment/postings/` | `recruitment.view` |
| المرشحون والمقابلات | `/recruitment/candidates/` | `recruitment.view` |

### التقارير

| الصفحة | المسار | الصلاحية |
|---|---|---|
| فهرس التقارير | `/reports/` | `reports.view` |
| تقرير الحضور | `/reports/attendance/` | `reports.view` |
| تقرير الرواتب | `/reports/payroll/` | `payroll.payslip.view` |
| تقرير الإجازات | `/reports/leave/` | `reports.view` |

### الذكاء الاصطناعي

| الصفحة | المسار | الصلاحية |
|---|---|---|
| لوحة التنبؤات | `/ai/predictions/` | `ai.analytics.view` |
| المساعد الذكي | `/ai/assistant/` | `ai.assistant.use` |
| تحليلات التدريب | `/ai/analytics/` | `ai.analytics.view` |

### الإشعارات

| الصفحة | المسار | الصلاحية |
|---|---|---|
| الإشعارات | `/notifications/` | جميع المسجلين |

### الإدارة (staff فقط)

| الصفحة | المسار | الصلاحية |
|---|---|---|
| لوحة Django الإدارية | `/sec-admin/` | `is_staff` |
| الأجهزة | `/devices/` | `is_superuser` |
| سجل التدقيق | `/audit/` | `is_superuser` |
| النسخ الاحتياطي | `/backup/` | `is_superuser` |

### واجهة API (MOBILE)

| الصفحة | المسار | الطريقة |
|---|---|---|
| دخول | `/api/v1/auth/login/` | POST |
| خروج | `/api/v1/auth/logout/` | POST |
| مسح QR | `/api/v1/scan/` | POST |
| ملفي الشخصي | `/api/v1/me/` | GET |
| حضوري | `/api/v1/me/attendance/` | GET |

### الصفحة السرية (الشعار + الألوان)

| الصفحة | المسار |
|---|---|
| صفحة الدخول | `/<BRANDING_SECRET_PATH>/` |
| لوحة التحكم | `/<BRANDING_SECRET_PATH>/dashboard/` |
| حفظ الشعار | `/<BRANDING_SECRET_PATH>/save-logo/` |
| حفظ الألوان | `/<BRANDING_SECRET_PATH>/save-colors/` |
| حفظ الهوية | `/<BRANDING_SECRET_PATH>/save-identity/` |
| الخروج | `/<BRANDING_SECRET_PATH>/logout/` |

---

## 🧪 الاختبارات

```bash
# تشغيل جميع اختبارات الوحدة
export DJANGO_SETTINGS_MODULE=config.settings.test
python manage.py test apps

# تشغيل اختبارات وحدة معينة
python manage.py test apps.core
python manage.py test apps.attendance
python manage.py test apps.employees

# اختبارات الصفحة السرية فقط
python manage.py test apps.core.tests_branding

# مع تفاصيل
python manage.py test apps -v 2

# إصلاح قاعدة اختبار قديمة
python manage.py test apps --noinput --parallel
```

### اختبارات بصرية (Playwright)

```bash
export PWCLI="/home/zro47/.agents/skills/playwright/scripts/playwright_cli.sh"

$PWCLI open "http://127.0.0.1:8022/"
$PWCLI snapshot
$PWCLI screenshot
$PWCLI close-all
```

---

## 🔧 ملاحظات تقنية مهمة

### القالب الأساسي (`templates/base.html`)

- الشعار يظهر في الترويسة via `COMPANY.logo` (إذا كان مُعرّفًا)
- الألوان المخصصة تُحقَّن via `{{ BRANDING_CSS|safe }}` في `<head>`
- زر تغيير المظهر (🌙) يعمل via `localStorage` + `data-theme="dark"`

### نمط الألوان

- الألوان الأساسية مُعرَّفة في `static/css/base.css` كمتغيرات `:root`
- النسق الداكن في `:root[data-theme="dark"]`
- الألوان المخصصة من لوحة التحكم تُحقَّن عبر `CompanySettings.css_overrides`

### أمان

- `DJANGO_SECRET_KEY` — يجب تغييره في الإنتاج
- `.env` لا يُرفع إلى Git
- الصفحة السرية لا تظهر في أي قائمة أو sitemap
- محاولات الدخول الفاشلة تُسجل في `AuditLog`

---

## 📚 الوثائق

الحزمة الهندسية الكاملة في [`docs/00-index.md`](docs/00-index.md):
- تحليل المتطلبات، التصميم، قاعدة البيانات، الأمان، RBAC، QR، الرواتب، API

---

## 📦 النشر (LAN/Prod)

```bash
export DJANGO_SETTINGS_MODULE=config.settings.prod
python manage.py deploy_prepare   # check + هجرات + collectstatic
```

راجل [`docs/14-deployment.md`](docs/14-deployment.md) و [`deploy/`](deploy/) (gunicorn + nginx + systemd).

---

## 📝 سجل التغييرات الأخيرة

| التاريخ | التغيير |
|---|---|
| 2026-09-14 | إضافة صفحة التحكم السرية (شعار + ألوان) |
| 2026-09-14 | إضافة حقل `css_overrides` إلى CompanySettings |
| 2026-09-14 | حقن `BRANDING_CSS` في جميع القوالب |
| 2026-09-14 | إظهار شعار الشركة في الترويسة إذا كان مُعرَّفًا |
| 2026-09-14 | إضافة اختبارات الصفحة السرية (19 اختبار) |
| 2026-09-14 | إصلاح تدرّجات الألوان (mix function bug fix) |
