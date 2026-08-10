# المرحلة الثانية: تصميم النظام (System Design)

> **HRMS-DOC-02** — البنية المعمارية، الرسوم البيانية، وهيكل المجلدات.

---

## جدول المحتويات

1. مبادئ التصميم المعتمدة
2. System Architecture (البنية العامة)
3. Component Diagram
4. Deployment Diagram
5. Sequence Diagram
6. Class Diagram (مبسط)
7. ER Diagram (مستوى مفاهيمي)
8. هيكل المجلدات (Folder Structure)
9. خيارات التوسع المستقبلي
10. تحذيرات وقرارات تصميمية

---

## 1. مبادئ التصميم المعتمدة

| المبدأ | التطبيق في المشروع |
|---|---|
| **Clean Architecture** | فصل: Domain → Application → Infrastructure → Interface (Web/API) |
| **SOLID** | واجهات ضيقة لكل خدمة، كل وحدة مسؤولة عن عمل واحد |
| **DDD (عند الحاجة)** | التجمّعات (Aggregates): Employee، LeaveRequest، PayrollRun، AttendanceDay |
| **Modular Monolith** | وحدات Django Apps مستقلة بدايةً، مع إمكانية تحويل كل وحدة لخدمة مستقلة لاحقًا (قابلية الانفصال) |
| **Event-Driven (خفيف)** | إشارات (Signals) داخل التطبيق لإشعارات/تدقيق بدون اقتران |
| **DTO / Use-Case طبقة** | الواجهات لا تلمس ORM مباشرة؛ تمر عبر Services |
| **Testability** | حقن التبعيات + وحدات خدمة نقية قابلة للاختبار |

> **قرار معماري رئيسي:** نبدأ بـ **Modular Monolith** (وحدات Django داخل تطبيق واحد + PostgreSQL) لأنها أسرع للبناء، أسهل للإدارة على خادم LAN واحد، وتسمح لاحقًا بفصل الوحدات الثقيلة (Payroll، AI) إلى خدمات مستقلة دون إعادة كتابة Domain.

---

## 2. System Architecture (البنية العامة)

```
┌────────────────────────────────────────────────────────────────────┐
│                        LAN (الشبكة المحلية)                        │
│                                                                    │
│  ┌─────────────┐   ┌─────────────┐   ┌──────────────┐             │
│  │  متصفحات     │   │  قارئات QR  │   │  خوادم أخرى  │             │
│  │ الموظفين/    │   │  ثابتة عند  │   │  (برايد LAN) │             │
│  │ الإدارة      │   │  المداخل    │   │              │             │
│  └──────┬──────┘   └──────┬──────┘   └──────┬───────┘             │
│         │  HTTPS/HTTP    │   REST API      │  SMTP              │
│         ▼                ▼                 ▼                    │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │                      الخادم المركزي (Server)                │  │
│  │  ┌───────────────────────────────────────────────────────┐  │  │
│  │  │                 Django Web Application                │  │  │
│  │  │  ┌─────────────────────────────────────────────────┐  │  │  │
│  │  │  │   Interface Layer (HTTP Views / DRF / WS)        │  │  │  │
│  │  │  └───────────────────────┬─────────────────────────┘  │  │  │
│  │  │  ┌───────────────────────▼─────────────────────────┐  │  │  │
│  │  │  │   Application Layer (Services / Use Cases)       │  │  │  │
│  │  │  └───────────────────────┬─────────────────────────┘  │  │  │
│  │  │  ┌───────────────────────▼─────────────────────────┐  │  │  │
│  │  │  │   Domain Layer (Models/Entities + Rules)         │  │  │  │
│  │  │  └───────────────────────┬─────────────────────────┘  │  │  │
│  │  │  ┌───────────────────────▼─────────────────────────┐  │  │  │
│  │  │  │   Infrastructure (ORM, Cache, Files, Celery)     │  │  │  │
│  │  │  └─────────────────────────────────────────────────┘  │  │  │
│  │  └───────────────────────────────────────────────────────┘  │  │
│  │                                                              │  │
│  │  ┌───────────┐   ┌───────────────┐   ┌─────────────────┐     │  │
│  │  │ PostgreSQL │   │ Redis (Cache/  │   │  ملفات / وثائق  │     │  │
│  │  │  (محلية)    │   │  Queue/مداول)  │   │  (Disk LAN)     │     │  │
│  │  └───────────┘   └───────────────┘   └─────────────────┘     │  │
│  │                                                              │  │
│  │  ┌───────────────────────────────────────────────────────┐   │  │
│  │  │     AI Module (محلي — لا إنترنت)                        │   │  │
│  │  │     تحليلات + توليد نصوص + تنبؤات (راجع 07)            │   │  │
│  │  └───────────────────────────────────────────────────────┘   │  │
│  └─────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────┘
```

### عناصر البنية

| المكوّن | الدور |
|---|---|
| **Django (WSGI/ASGI)** | يقدّم الواجهة الويب + REST API للأجهزة + مهام مجدولة |
| **PostgreSQL** | قاعدة البيانات المحلية الوحيدة (بيانات + فهارس + FTS) |
| **Redis** | تخزين مؤقت، قوائم انتظار Celery، إدارة الجلسات (اختياري) |
| **Celery + Beat** | مهام خلفية: كشف الرواتب، إشعارات، نسخ احتياطي، عمليات AI |
| **ملفات محلية (NFS/SMB)** | مستودع الوثائق والنسخ الاحتياطي |
| **DRF (Django REST Framework)** | API موحد لقارئات QR والأجهزة والتكامل |
| **واجهات القوالب** | Django Templates + HTMX/Alpine للتفاعل الخفيف (أو SPA لاحقًا) |

### قرارات واجهة العرض

| الخيار | القرار |
|---|---|
| **نمط الواجهة** | **Server-side Rendering (Django Templates) + HTMX** للإصدار 1.0 |
| المبرر | أقل تعقيدًا، RTL سهل، أداء جيد على LAN، صيانة أبسط بفريق صغير |
| المسار البديل | الانتقال لـ SPA (React/Vue) في v2 عبر نفس REST API — لا يتطلب تغيير البنية |

---

## 3. Component Diagram

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          hrms (Django Project)                            │
│                                                                            │
│  ┌────────────┐ ┌────────────┐ ┌─────────────┐ ┌─────────────┐            │
│  │ auth_app   │ │ org_app    │ │ employees   │ │ attendance  │            │
│  │ (users,    │ │ (branch,   │ │ (employee,  │ │ (shifts,    │            │
│  │  roles,    │ │  dept,     │ │  job_hist,  │ │  scans,     │            │
│  │  sessions) │ │  position) │ │  docs)      │ │  exceptions)│            │
│  └─────┬──────┘ └─────┬──────┘ └─────┬───────┘ └─────┬───────┘            │
│        │              │              │                │                    │
│  ┌─────▼──────┐ ┌─────▼──────┐ ┌─────▼───────┐ ┌─────▼───────┐            │
│  │ leave_app  │ │ payroll_app│ │ perf_app    │ │ training_app│            │
│  │ (types,    │ │ (elements, │ │ (cycles,    │ │ (courses,    │            │
│  │  balances, │ │  runs,     │ │  reviews,   │ │  enrollments)│           │
│  │  requests) │ │  payslips) │ │  kpis, pip) │ │             │            │
│  └─────┬──────┘ └─────┬──────┘ └─────┬───────┘ └─────┬───────┘            │
│        │              │              │                │                    │
│  ┌─────▼──────┐ ┌─────▼──────┐ ┌─────▼───────┐ ┌─────▼────────┐           │
│  │ notif_app  │ │ report_app │ │ ai_app      │ │ audit/backup │           │
│  │ (in-app,   │ │ (exports   │ │ (analytics, │ │ (audit_log,  │           │
│  │  email)    │ │  pdf/xlsx) │ │  assistant, │ │  backup_jobs)│           │
│  │            │ │            │ │  forecasts) │ │              │           │
│  └────────────┘ └────────────┘ └─────────────┘ └──────────────┘           │
│                                                                            │
│  ┌──────────────────────────────┐   ┌──────────────────────────┐           │
│  │  core/ (مشترك)               │   │  config/ (settings/URLs)  │           │
│  │  - base models, services,    │   │  - قاعدة i18n و RTL        │           │
│  │    middleware, permissions   │   │  - إعدادات LAN/HTTPS       │           │
│  └──────────────────────────────┘   └──────────────────────────┘           │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Deployment Diagram

```
┌─────────────────────────────  LAN  ─────────────────────────────┐
│                                                                 │
│  ┌─────────── خادم التطبيق (App Server) ────────────────┐        │
│  │  Linux (Ubuntu Server 22.04 LTS)                    │        │
│  │  ├── Nginx (TLS reverse proxy + static)             │        │
│  │  ├── Gunicorn (WSGI workers) — Django               │        │
│  │  ├── Celery worker + Beat (مهام خلفية)              │        │
│  │  ├── Redis (cache/queue)                            │        │
│  │  ├── PostgreSQL 16 (محلية)                          │        │
│  │  └── AI Module (محلي — منفصل Process)               │        │
│  └──────────────────────────────────────────────────────┘        │
│                     ▲              │                             │
│        HTTPS (LAN) │              │ REST API                     │
│                     │              ▼                             │
│  ┌───────────────┐ │   ┌─────────────────────────┐               │
│  │ متصفحات العملاء │◄┘   │ قارئات QR الثابتة        │               │
│  │ (Chrome/Firefox)│      │ (بوابات المداخل)        │               │
│  └───────────────┘        └─────────────────────────┘               │
│                                                                   │
│  ┌─────────────────────────┐     ┌────────────────────────────┐   │
│  │ تخزين الملفات            │     │ خادم نسخ احتياطي ثانوي       │   │
│  │ (SMB/NFS على الخادم)     │◄────│ (NAS/قرص خارجي عبر LAN)     │   │
│  └─────────────────────────┘     └────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────┘

ملاحظات النشر:
- خادم واحد مركزي كافي لـ 5000 موظف (انظر أداء التوسع في §9).
- HTTPS عبر شهادة محلية (Internal CA) داخل LAN.
- إعادة نشر: systemd + نسخ الكود عبر git أو rsync من سيرفر Dev.
```

### متطلبات الأجهزة المقترحة (مرجعية لـ 5000 موظف)

| المورد | الحد الأدنى | الموصى به |
|---|---|---|
| CPU | 8 vCPU | 16 vCPU |
| RAM | 16 GB | 32 GB |
| Disk | 200 GB SSD (بيانات) + 100 GB (وثائق) | 500 GB SSD + NAS للنسخ |
| الشبكة | Gigabit LAN | 10G أو تجميعة |

---

## 5. Sequence Diagram

### 5.1 تسجيل الحضور عبر QR (مبسط)

```
الموظف(هاتف)    واجهة API    Auth&DeviceSvc    QRService    AttendanceSvc    DB(Postgres)
    │  scan QR    │              │               │             │               │
    │────────────►│  POST /scan  │               │             │               │
    │             │─────────────►│               │             │               │
    │             │              │  verify token │             │               │
    │             │              │──────────────►│             │               │
    │             │              │  (signature)  │             │               │
    │             │              │◄──────────────│             │               │
    │             │              │  check active │             │               │
    │             │              │──────────────►│             │               │
    │             │              │◄──────────────│  record event│              │
    │             │              │               │────────────►│               │
    │             │              │               │             │ insert scan   │
    │             │              │               │             │──────────────►│
    │             │              │               │  compute rule│              │
    │             │              │               │ (in/out)     │              │
    │             │  HTTP 201    │               │             │               │
    │◄────────────│◄─────────────│◄──────────────│◄────────────│◄──────────────│
```

### 5.2 دورة كشف الرواتب

```
Beat(Scheduler)   PayrollService   AttendanceSvc    LeaveSvc    HRMgr(اعتماد)     DB
     │ schedule │       │               │              │            │            │
     │─────────►│       │               │              │            │            │
     │          │ open_run(period)      │              │            │            │
     │          │──────────────────────►│              │            │            │
     │          │ aggregate attendance  │              │            │            │
     │          │───────────────────────────────────────►           │            │
     │          │ fetch leaves/balances │              │            │            │
     │          │───────────────────────────────────────────────────►            │
     │          │ compute each employee │              │            │            │
     │          │────────────► compute │              │            │            │
     │          │ validate rules BR-PAY │              │            │            │
     │          │────────────────────────────────────────────────────────────────►│
     │          │ draft run created     │              │            │            │
     │          │ notify accountant     │              │            │            │
     │          │───────────────────────────────────────────────────►            │
     │          │  (موافقة) approve_run  │              │            │            │
     │          │◄──────────────────────────────────────────────────│            │
     │          │ freeze period │              │            │            │
     │          │────────────► generate payslips │           │            │
     │          │──────────────────────────────────────────────────►             │
```

---

## 6. Class Diagram (مستوى Domain — مبسط)

> الاكتمال التفصيلي للجداول والحقول في `03-database-design.md`.

```
User
├─ username, email, password_hash
├─ is_active, is_superuser, mfa_secret
├─ language, timezone
├─ 1..1 ─── EmployeeProfile (optional)
├─ * ───── Role (مفوض) , * ──── Permission (مباشر)
└─ * ───── Session

Branch 1─* Department 1─* Position 1─* Membership
                                        ├─ employee_id (EF)
                                        ├─ branch/dept/position (EF)
                                        ├─ manager_id (self ref EF)
                                        └─ from_date, to_date

Employee
├─ id, employee_code (UNIQUE)
├─ first_name, last_name (multi-lang)
├─ status (enum)
├─ phone, email, birth_date
├─ marital_status, bank_account (encrypted)
├─ 1─* JobHistory 1─* Contract 1─* Document
└─ 1─1 EmployeeQR (secret, status, expires_at)

Attendance
├─ AttendanceDay (employee, date, shift, state, hours)
├─ AttendanceScan (attendance_day, timestamp, device, source, decision)
└─ AttendanceException (type, hours, approved_by, status)

Leave
├─ LeaveType (code, days_per_year, carryover, unpaid?)
├─ LeaveBalance (employee, type, year, granted, used, carried)
├─ LeaveRequest (employee, type, from/to, days, reason, status)
└─ LeaveApproval (request, approver, action, comment, at)

Payroll
├─ PayElement (code, kind: earn/deduct, default_value)
├─ PayRun (period, branch, status, frozen, totals)
├─ PayrollLine (pay_run, employee, element, amount)
└─ Payslip (pay_run, employee, totals, generated_at)

Perf: PerfCycle, PerfTemplate, PerfReview(employee, cycle, self_score, mgr_score, final), PerfObjective(KPI, weight, score), PipPlan
Training: Course, Session, Enrollment, Certificate
Notify: Notification, NotificationPref, ScheduledAlert
Report: ReportDefinition, ReportJob, GeneratedFile
Audit: AuditLog(actor, action, model, object_id, old, new, ip, at)
Backup: BackupJob, RestoreJob
QR: EmployeeQR, QrScanLog, QrDevice(branch, name, status)
```

---

## 7. ER Diagram (مستوى مفاهيمي)

> مخطط العلاقات الكامل بالجداول والمفاتيح في `03-database-design.md`.

```
Branch ─┬─ Department ─┬─ Position ─┬─ Membership ─┬─ Employee
        │              │            │              │
        │              │            │              ├─ JobHistory
        │              │            │              ├─ Contract
        │              │            │              ├─ Document
        │              │            │              ├─ EmployeeQR ── QrScanLog
        │              │            │              ├─ AttendanceDay ── AttendanceScan
        │              │            │              │        └─ AttendanceException
        │              │            │              ├─ LeaveBalance ─ LeaveRequest ─ LeaveApproval
        │              │            │              ├─ PayrollLine ── PayRun ── Payslip
        │              │            │              ├─ PerfReview ── PerfObjective
        │              │            │              ├─ Enrollment ── Session ─ Course
        │              │            │              └─ User ── Role ── Permission

AuditLog ◄── كل العمليات    |    Notification ── User    |    ReportJob ── GeneratedFile
QrDevice ◄── QrScanLog
```

---

## 8. هيكل المجلدات (Folder Structure)

```text
hrms/
├── manage.py
├── requirements/
│   ├── base.txt
│   ├── dev.txt
│   └── prod.txt
├── config/                      # مشروع Django
│   ├── settings/
│   │   ├── base.py              # عام + i18n + RTL + أمان
│   │   ├── dev.py
│   │   └── prod.py
│   ├── urls.py
│   ├── wsgi.py / asgi.py
│   └── celery.py
├── apps/                        # الوحدات (Modular Monolith)
│   ├── core/                    # نماذج أساسية، Permissions، Middleware، BaseModel
│   │   ├── models/  services/  permissions/  middleware/  managers/
│   ├── auth_app/                # User, Role, Permission, Session, MFA, PassReset
│   ├── org/                     # Branch, Department, Position, Membership
│   ├── employees/               # Employee, JobHistory, Contract, Document, EmployeeQR
│   ├── attendance/              # Shift, AttendanceDay, AttendanceScan, Exception
│   ├── leave/                   # LeaveType, LeaveBalance, LeaveRequest, LeaveApproval
│   ├── payroll/                 # PayElement, PayRun, PayrollLine, Payslip, EndOfService
│   ├── perf/                    # PerfCycle, Template, Review, Objective, PipPlan
│   ├── training/                # Course, Session, Enrollment, Certificate
│   ├── notif/                   # Notification, Pref, Scheduler
│   ├── reports/                 # ReportDefinition, Exports (pdf/xlsx/csv), Jobs
│   ├── ai/                      # AI Assistant, Analytics, Forecasts (راجع 07)
│   ├── audit/                   # AuditLog, BackupJob, RestoreJob
│   └── devices/                 # QrDevice API (قارئات QR)
├── templates/
│   ├── base/                    # base.html (RTL/LTR)، nav، sidebar
│   ├── auth/  org/  employees/  attendance/  leave/  payroll/
│   ├── perf/  training/  reports/  ai/  dashboard/  ...
│   └── partials/                # جداول، موافقات، إشعارات
├── static/
│   ├── css/  js/  img/  vendor/ # (HTMX, Alpine, Chart.js محلية)
├── locale/                      # ملفات i18n
│   ├── ar/  fr/  en/
├── media/                       # وثائق مرفوعة (محمية)
├── backup/                      # مخرجات النسخ الاحتياطي (خارج Git)
├── scripts/                     # إدارة: backup, restore, seed, fixtures
├── tests/                       # اختبارات لكل وحدة
│   ├── conftest.py
│   ├── factories/  integration/  unit/
└── docs/                        # هذه الحزمة
```

### قواعد هيكل الوحدات

1. كل وحدة تحتوي: `models/`, `services/`, `views/`, `urls.py`, `admin.py`, `i18n`.
2. **Domain لا يستورد من Infrastructure**: الوحدات لا تستورد ORM إلا عبر طبقة Repository عند الحاجة (قاعدة Clean Architecture).
3. **الاقتران بين الوحدات**: عبر `services` فقط، وليس عبر استيراد نماذج بعضها مباشرة إلا عبر `core`.
4. **Events**: أحداث مثل `employee.terminated`, `leave.approved` تصدرها الخدمة، وتستهلكها `notif` و`audit` و`ai`.

---

## 9. خيارات التوسع المستقبلي (Scalability Path)

| السيناريو | الحل |
|---|---|
| نمو إلى 20K موظف | فصل تقارير ثقيلة لخدمة تقارير مستقلة + قراءة النسخ (Read Replica) |
| تعدد الخوادم | تحويل Modular Monolith إلى Microservices للوحدات الحرجة (Payroll/AI) |
| اندماج مع ERP محاسبي | واجهة REST API موثقة (OpenAPI) — جاهزة منذ v1 |
| دعم فروع دولية | إضافة نموذج عملة وتقويم وعطلة لكل فرع (متوقع الآن) |
| دخول عن بعد (VPN) | طبقة SSO + OAuth2 خارجي في v3 |

---

## 10. تحذيرات وقرارات تصميمية (Alert Box)

1. **⚠️ Modular Monolith وليس Microservices في v1**: Microservices على خادم LAN واحد يضيف تعقيدًا دون فائدة. الانفصال ممكن لاحقًا لأن حدود الوحدات واضحة.
2. **⚠️ الواجهة SSR + HTMX**: يخالف الاتجاهات الحديثة (SPA) لكنه أسرع وأبسط على LAN، وREST API جاهز للانتقال لاحقًا.
3. **⚠️ Redis اختياري في v1**: يمكن البدء بدون Redis والاعتماد على DB cache، لكن مهام Celery تتطلب Broker — استخدم Redis من البداية لتجنب إعادة التهيئة.
4. **⚠️ HTTPS داخل LAN**: لا تهمل TLS حتى داخل الشبكة (بيانات رواتب حساسة). شهادة Internal CA.
5. **⚠️ التوقيت (Timezones)**: فرع واحد أو عدة مناطق زمنية — القرار يؤثر على حساب الحضور. اختر `TIME_ZONE` لكل فرع إن اختلف.
6. **⚠️ ترقيم التقارير**: أي تقرير يجب أن يدعم **Paginate + Stream** حتى مع 5000 صف، لا جلب كامل.
