# نظام تسيير الموارد البشرية (HRMS)

> **Human Resource Management System** — نظام متكامل لإدارة الموارد البشرية، مبني بـ **Django 5** ويعمل داخل الشبكة المحلية (LAN) أو على الإنترنت.
> يدعم العربية (RTL) والفرنسية والإنجليزية.

---

## ✨ المزايا

| الوحدة | الوظائف |
|---|---|
| **الهيكل التنظيمي** | فروع، أقسام، مناصب، جداول دوام (إضافة/تعديل/حذف) |
| **الموظفون** | ملفات موظفين، عقود، سجل وظيفي، مستندات، بحث متقدم |
| **QR والبطاقات** | إصدار/إعادة توليد رمز QR لكل موظف + **بطاقة موظف قابلة للطباعة** (اسم + رقم وظيفي + QR) |
| **الحضور/الانصراف** | مسح QR (هاتف/قارئ ثابت)، أيام حضور، تأخير/غياب، استثناءات (إذن/مأمورية) |
| **الإجازات** | أنواع قابلة للتكوين، أرصدة سنوية، دورة موافقات متعددة المستويات، عطل رسمية |
| **الرواتب** | دورات رواتب (draft→review→approved→frozen)، قسائم، عناصر أجر، تصدير بنك، PDF |
| **الصلاحيات (RBAC)** | أدوار وصلاحيات وScope (كل موظف يرى نطاقه فقط)، Deny يتفوق دائمًا |
| **الإشعارات والتقارير** | إشعارات داخلية، تقارير PDF/Excel |
| **التوظيف** | إعلانات وظائف، مرشحون، مقابلات، استيراد المرشحين (Excel/CSV) |
| **الذكاء الاصطناعي** | مساعد ذكي، تنبؤ مخاطر الاستقالة/الغياب، لوحة تحليلات التدريب، حلقة تقييم + أسئلة مجهولة، إعادة تدريب مجدولة |

---

## 🛠️ التقنيات

- **Python 3.12 + Django 5** — `requirements.txt`
- **PostgreSQL** (الإنتاج) / **SQLite** (التطوير)
- **Pillow + qrcode** — صور الموظفين وأكواد QR
- **WeasyPrint** — تصدير PDF (يدعم RTL العربي)
- **Gunicorn + Nginx + systemd** — النشر على خادم LAN (`deploy/`)

---

## 📁 البنية

```
apps/
├── core/        # لوحة رئيسية، بحث، أوامر seed_demo / seed_all / deploy_prepare
├── auth_app/    # RBAC: مستخدمون، أدوار، صلاحيات، Scopes
├── org/         # فروع، أقسام، مناصب، دوام
├── employees/   # موظفون، عقود، QR Engine + Service، بطاقة قابلة للطباعة
├── attendance/  # مسح QR، أيام حضور، استثناءات
├── leave/       # أنواع إجازات، أرصدة، طلبات وموافقات
├── payroll/     # دورات رواتب، قسائم، عناصر أجر
├── devices/     # قارئات QR
├── recruitment/ # إعلانات وظائف، مرشحون، مقابلات، استيراد
├── ai/          # مساعد ذكي، تنبؤات، تحليلات التدريب
├── notif/       # إشعارات داخلية
└── reports/     # تقارير PDF/Excel
docs/            # الحزمة الهندسية الكاملة (00-index.md ... 17-ux-review.md)
```

---

## 🚀 التشغيل (تطوير)

```bash
# 1) بيئة افتراضية
python3 -m venv .venv
source .venv/bin/activate

# 2) التبعيات
pip install -r requirements.txt

# 3) الإعدادات — إنشاء .env من القالب
cp .env.example .env

# 4) الهجرات والتهيئة
export DJANGO_SETTINGS_MODULE=config.settings.dev
python manage.py migrate
python manage.py seed_all          # RBAC + أنواع الإجازات + مشرف افتراضي

# 5) التشغيل
python manage.py runserver
```

افتح `http://127.0.0.1:8000/`.

> ⚠️ **ملاحظة**: `config/settings/__init__.py` فارغ عمدًا — حدد دائماً
> `DJANGO_SETTINGS_MODULE` (`config.settings.dev` للتطوير، `config.settings.prod` للإنتاج).

---

## 🧪 بيانات تجريبية (Demo)

```bash
export DJANGO_SETTINGS_MODULE=config.settings.dev
python manage.py seed_demo                       # هيكل + 15 موظف + حضور + إجازات
python manage.py seed_demo --payrun              # + دورة رواتب 2026-07 معتمدة
python manage.py seed_demo --employees 12        # عدد موظفين محدد
python manage.py seed_demo --no-users            # بدون حسابات
```

| الحساب | كلمة المرور |
|---|---|
| `admin` (مشرف) | `Adm1n@2026!` (من `seed_all`) |
| `emp-101` ... `emp-115` | `Demo@2026!` |

### 🤖 الذكاء الاصطناعي (v3 → v5)

```bash
python manage.py seed_training                 # دورات/جلسات/تسجيلات/شهادات واقعية
python manage.py seed_ai_data                  # بيانات تدريب حقيقية لنماذج التنبؤ (60 موظفًا، 20٪ مغادرون)
python manage.py seed_ai_data --employees 80 --departed 0.25   # ضبط حجم/نسبة المغادرين
python manage.py train_ai_models               # تدريب نموذج مخاطر الاستقالة (AUC + تحقق متقاطع)
python manage.py train_ai_models --all         # + نموذج مخاطر الغياب
python manage.py retrain_ai_models_scheduled   # إعادة تدريب مجدولة مع فحص جودة البيانات + مراقبة انجراف AUC
```

| الصفحة | المسار | الصلاحية |
|---|---|---|
| لوحة التنبؤات | `/ai/` | `ai.analytics.view` |
| المساعد الذكي | `/ai/assistant/` | `ai.assistant.use` |
| تحليلات التدريب | `/ai/analytics/` | `ai.analytics.view` |

- **المساعد الذكي**: يجيب بثلاث لغات على أسئلة بيانات الموارد البشرية، حلقة تقييم (نعم/لا) تُغذّي إجابات أفضل، والأسئلة غير المُجابة تُعرض في التحليلات.
- **التنبؤات**: مخاطر الاستقالة والغياب لكل موظف نشط، تُحدَّث من اللوحة.
- **التحليلات**: مقاييس التدريب (AUC)، تقارير جودة البيانات، الأسئلة المجهولة، مراقبة انجراف النموذج (إعادة تدريب تلقائية عند انخفاض AUC>0.05).

بطاقة موظف قابلة للطباعة: `http://127.0.0.1:8000/employees/<pk>/card/` — من صفحة الموظف زر **«بطاقة الموظف (QR)»**.

---

## 📱 واجهة API للموبايل والأجهزة (v4)

واجهة REST (Django REST Framework) تحت `http://127.0.0.1:8000/api/v1/` — للموظفين (Token) والقارئات الثابتة (مفتاح API).

| المسار | الطريقة | الوصف |
|---|---|---|
| `auth/login/` | POST | `{username, password}` → `{token, employee}` (للموظفين فقط) |
| `auth/logout/` | POST | إبطال الرمز الحالي |
| `scan/` | POST | `{payload}` → دخول/خروج (موظف بصلاحية `attendance.scan` أو جهاز) |
| `me/` | GET | ملفي + رمز QR النشط + حالة اليوم |
| `me/attendance/` | GET | أيام الحضور (`?from=YYYY-MM-DD&to=YYYY-MM-DD`) |

**تسجيل الدخول:**
```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"username":"emp-101","password":"Demo@2026!"}'
```

**مسح QR (موظف):**
```bash
curl -X POST http://127.0.0.1:8000/api/v1/scan/ \
  -H "Authorization: Token <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"payload":"<نص QR>"}'
```

**مسح QR (قارئ ثابت)** — تُعرَّف الأجهزة من صفحة الأجهزة (مفتاح API يُعرض مرة واحدة):
```bash
curl -X POST http://127.0.0.1:8000/api/v1/scan/ \
  -H "X-Device-Code: <code>" -H "X-API-Key: <key>" \
  -H "Content-Type: application/json" \
  -d '{"payload":"<نص QR>"}'
```

الرد: `{ok, decision, detail, employee, time}` — `decision` ∈ `check_in | check_out | rejected | warning`.

---

## 🧑‍💼 التوظيف (v5)

إدارة دورة التوظيف كاملة من إعلان الوظيفة حتى التوظيف:

| المزايا | |
|---|---|
| **إعلانات الوظائف** | مناصب نشطة، وصف، حالة (مفتوح/مغلق) |
| **المرشحون** | بيانات كاملة، حالة (قيد المراجعة/مقبول/مرفوض)، تعيين مرشح إلى موظف |
| **المقابلات** | جدولة مقابلات لكل مرشح، نتائج وتوصيات |
| **الاستيراد** | استيراد جماعي للمرشحين من Excel/CSV |

---

## ✅ الاختبارات

```bash
export DJANGO_SETTINGS_MODULE=config.settings.test
python manage.py test apps
```

---

## 🌍 اللغات

عربي (افتراضي، RTL) / فرنسي / إنجليزي — التبديل من شريط التنقل. استخدم `makemessages`/`compilemessages` لتحديث الترجمات.

---

## 🎨 تجربة المستخدم (v5)

مراجعة UX/UI شاملة: تباين ألوان مطابق لـ WCAG AA، إصلاحات وصولية (وصف فريد للحقول، `role="search"`، جداول قابلة للتمرير بعناوين، أزرار أيقونات بأسماء واضحة)، رابط تخطّي المحتوى، مؤشر تركيز واضح، وأرقام monospaced في الجداول والإحصائيات. التفاصيل في [`docs/17-ux-review.md`](docs/17-ux-review.md).

---

## 📦 النشر (LAN)

راجع [`docs/14-deployment.md`](docs/14-deployment.md) ومجلد [`deploy/`](deploy/) (gunicorn + nginx + systemd).

```bash
export DJANGO_SETTINGS_MODULE=config.settings.prod
python manage.py deploy_prepare   # check + هجرات + collectstatic (يفشل عند أي انحراف)
```

---

## 📚 الوثائق

الحزمة الهندسية الكاملة (تحليل، تصميم، قاعدة بيانات، أمان، RBAC، نظام QR، رواتب، API):
ابدأ من [`docs/00-index.md`](docs/00-index.md).
