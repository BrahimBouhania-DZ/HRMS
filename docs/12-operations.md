# المرحلة الثانية عشرة: دليل تشغيل المشرفين (Operations)

> **HRMS-DOC-12** — تشغيل/إيقاف/نسخ/استعادة/تحديث النظام ومراقبته يوميًا. هذا المرجع للمشرف (Admin) على خادم LAN.

---

## جدول المحتويات

1. المتطلبات
2. التشغيل والإيقاف
3. النسخ الاحتياطي والاستعادة
4. المستخدمون والصلاحيات
5. نصائح يومية ومراقبة
6. استكشاف الأخطاء الشائعة

---

## 1. المتطلبات

| البند | التطوير | الإنتاج (LAN) |
|---|---|---|
| نظام | أي | Debian/Ubuntu أو مماثل |
| Python | 3.11+ | 3.11+ + pip |
| قاعدة البيانات | SQLite (افتراضي) | PostgreSQL |
| إضافات | — | `libpango`, `libcairo` (لطباعة PDF) |

التثبيت: `pip install -r requirements.txt` (الإنتاج: داخل virtualenv).

---

## 2. التشغيل والإيقاف

### خادم التطوير (الاستخدام اليومي)

```bash
bash scripts/run.sh run        # تشغيل على 127.0.0.1:8000
bash scripts/run.sh restart    # إعادة تشغيل
bash scripts/run.sh stop       # إيقاف
```

### إنتاج LAN (systemd + gunicorn)

```bash
sudo systemctl start hrms
sudo systemctl stop hrms
sudo systemctl restart hrms
sudo systemctl status hrms
```

كل أوامر `run.sh` تعمل في الإنتاج بإضافة متغير البيئة:

```bash
export DJANGO_SETTINGS_MODULE=config.settings.prod
```

> **ملاحظة أمنية:** إعدادات الإنتاج تقرأ من متغيرات البيئة أو ملف `.env` في جذر المشروع — لا تُكتب الأسرار في ملفات الإعدادات.

---

## 3. النسخ الاحتياطي والاستعادة

### نسخة احتياطية (تلقائي الوجهة: `backups/`)

```bash
bash scripts/backup.sh
```

- يحتفظ بآخر 14 نسخة فقط (التنظيف تلقائي).
- SQLite: لقطة متسقة بآلية `sqlite3.backup`.
- PostgreSQL: `pg_dump` مضغوط (يتطلب `DJANGO_DB_*` في البيئة).

### الاستعادة

```bash
bash scripts/backup.sh restore backups/hrms_20260809_122804.sqlite3
bash scripts/run.sh restore backups/hrms_20260809_122804.sqlite3   # عبر run.sh
```

### الجدولة اليومية (اختياري — cron)

```cron
30 2 * * * cd /opt/hrms && bash scripts/backup.sh
*/30 8-18 * * * cd /opt/hrms && .venv/bin/python manage.py run_scheduled_reports  # تقارير مجدولة (T-REP-5)
```

> **توصية:** انسخ النسخ الاحتياطية إلى قرص/جهاز آخر شهريًا، واختبر استعادة فعلية قبل الاعتماد عليها (معيار قبول v1).

---

## 4. المستخدمون والصلاحيات

| المهمة | الأمر/المكان |
|---|---|
| إنشاء مشرف | `bash scripts/run.sh createsuper` |
| تهيئة الأدوار والصلاحيات | `bash scripts/run.sh seed` (إلزامي بعد reset/مشروع جديد) |
| الهجرات | `bash scripts/run.sh migrate` |
| إدارة المستخدمين والأدوار | لوحة `الإدارة` (`/admin/`) — الأدمن فقط |

الصلاحيات الفعلية تُحسب لحظيًا: أي تغيير على دور/صلاحية ينعكس فورًا دون إعادة تشغيل.

---

## 5. نصائح يومية ومراقبة

- راقب `sudo systemctl status hrms` وسجلات gunicorn (`journalctl -u hrms -f`).
- تحقق دوريًا من المسحات المرفوضة: تقرير REP-17 (السبب الأهم = مفاتيح/أجهزة معطلة).
- راجع حالة الأجهزة من `/devices/` — الجهاز المعطّل لا يقبل مسحات حتى يُفعَّل.
- قبل تحديث الكود: نفّذ نسخة احتياطية ثم `migrate` ثم `check`.

---

## 6. استكشاف الأخطاء الشائعة

| العرض | السبب | الحل |
|---|---|---|
| `403 رمز CSRF مفقود` على مسح API | أرسلت من جلسة مُصادَق عليها دون رأس `X-CSRFToken` | الأجهزة تُسجَّل بلا جلسة (مفتاح API فقط)؛ للمتصفح أضف الرأس |
| `401 مصادقة الجهاز مطلوبة` | مفتاح خاطئ أو جهاز معطّل أو غير موجود | أعد تسجيل جهاز جديد (المفتاح يظهر مرة واحدة) |
| `422 توقيع غير صالح` | نص QR تالف أو قديم | أعد توليد QR من صفحة "بطاقتي" |
| `400 payload مطلوب` | أُرسل JSON بدل form-data | أرسل `payload=<نص QR>` (application/x-www-form-urlencoded) |
| `Error loading psycopg2` | مكتبة Postgres غير مثبتة على آلة التطوير | ثبّت `requirements.txt` على خادم الإنتاج فقط |
| PDF لا يطبع | نقص pango/cairo | `apt install libpango-1.0-0 libpangocairo-1.0-0 libcairo2` |

---

## تسجيل التغييرات

| التاريخ | النسخة | التغيير |
|---|---|---|
| 2026-08-09 | 1.0 | الإصدار الأول (تشغيل/نسخ/استعادة/مراقبة) |
