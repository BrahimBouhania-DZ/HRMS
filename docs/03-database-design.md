# المرحلة الثالثة: تصميم قاعدة البيانات (Database Design)

> **HRMS-DOC-03** — تصميم PostgreSQL الكامل: الجداول، الحقول، المفاتيح، العلاقات، الفهارس.
> كل جدول له معرّف `T-<رقم>` يُستخدم في مهام التطوير.

---

## جدول المحتويات

1. قواعد التصميم العامة
2. مخطط العلاقات الكامل (ERD مفصّل)
3. الجداول التفصيلية (حسب الوحدة)
4. الفهارس الاستراتيجية للأداء
5. اعتبارات البيانات الحساسة (Encryption at Rest)
6. الترحيلات والبيانات المرجعية (Seed Data)
7. تحذيرات وقرارات تصميمية

---

## 1. قواعد التصميم العامة

| القاعدة | التطبيق |
|---|---|
| المفتاح الأساسي | `id BIGSERIAL PRIMARY KEY` لكل الجداول |
| المفتاح الخارجي | `FOREIGN KEY ... ON DELETE RESTRICT` (منع الحذف التلقائي للبيانات التاريخية) |
| الحذف المنطقي | عمود `is_active` / `deleted_at` — لا حذف فعلي للبيانات التشغيلية |
| الطوابع الزمنية | `created_at`, `updated_at` (UTC) لكل جدول |
| التدقيق | `created_by`, `updated_by` (FK → auth_user) عند الحاجة |
| الأسماء | `snake_case`، أسماء الجداول بصيغة الجمع |
| النصوص المتعددة اللغات | حقول مثل `name_ar`, `name_fr`, `name_en` أو جدول ترجمات `Translations` للأنواع القابلة للتكوين |
| الأرقام المالية | `NUMERIC(15,2)` — لا `FLOAT` أبدًا للعملات |
| المعرّفات العمومية | `employee_code` و `leave_type.code` فريدة في نطاق الشركة |
| جداول الأنواع | أعمدة `enum` تُنفَّذ كـ `VARCHAR` مع قيود `CHECK` أو جداول تكوين (Config) — يفضل **جداول تكوين** للأنواع التي تتغير (إجازات، عناصر أجر) |

---

## 2. مخطط العلاقات الكامل (ERD)

```
auth_user 1──* auth_role_member (many-to-many User↔Role)
auth_role 1──* auth_permission (مفردات RBAC)

org_branch 1──* org_department
org_department 1──* org_department (self-ref parent)
org_department 1──* org_position
org_branch 1──* employees_membership
org_department 1──* employees_membership
org_position 1──* employees_membership
employees_membership 1──* employees_membership (manager self-ref)
auth_user 1──0..1 employees_employee
employees_employee 1──* employees_jobhistory
employees_employee 1──* employees_contract
employees_employee 1──* employees_document
employees_employee 1──0..1 employees_employeeqr
employees_employee 1──* attendance_attendanceday
org_shift 1──* attendance_attendanceday
attendance_attendanceday 1──* attendance_attendancescan
attendance_attendanceday 1──* attendance_exception
employees_employeeqr 1──* attendance_attendancescan
devices_qrdevice 1──* attendance_attendancescan

leave_leavetype 1──* leave_leavebalance
leave_leavetype 1──* leave_leaverequest
employees_employee 1──* leave_leavebalance
employees_employee 1──* leave_leaverequest
leave_leaverequest 1──* leave_leaveapproval
employees_employee 1──* payroll_payrollline
payroll_payelement 1──* payroll_payrollline
payroll_payrun 1──* payroll_payrollline
payroll_payrun 1──* payroll_payslip
employees_employee 1──* payroll_payslip
payroll_payrun 1──* payroll_endofservice
employees_employee 1──* payroll_endofservice

perf_perfcycle 1──* perf_perfreview
perf_perftemplate 1──* perf_perfreview
employees_employee 1──* perf_perfreview
perf_perfreview 1──* perf_perfobjective
perf_perfreview 1──* perf_pipplan
training_course 1──* training_session
training_session 1──* training_enrollment
training_enrollment 1──* training_certificate

notif_notification *──1 auth_user
audit_auditlog *──1 auth_user (actor, nullable)
devices_qrdevice 1──* devices_qrdeviceaudit
reports_reportjob 1──* reports_generatedfile
```

---

## 3. الجداول التفصيلية

### 3.1 المصادقة والصلاحيات (auth_app) — راجع `05-rbac.md`

#### T-001 `auth_user`

| الحقل | النوع | القيود | الوصف |
|---|---|---|---|
| id | BIGSERIAL | PK | |
| username | VARCHAR(150) | UNIQUE NOT NULL | |
| email | VARCHAR(254) | UNIQUE NULL | |
| password_hash | VARCHAR(255) | NOT NULL | Argon2id (راجع 09) |
| is_active | BOOLEAN | NOT NULL default true | |
| is_superuser | BOOLEAN | default false | |
| mfa_enabled | BOOLEAN | default false | |
| mfa_secret | VARCHAR(64) | NULL (مشفّر) | TOTP |
| language | VARCHAR(5) | default 'ar' | ar/fr/en |
| timezone | VARCHAR(64) | default توقيت الخادم | |
| failed_attempts | SMALLINT | default 0 | عدّاد محاولات |
| locked_until | TIMESTAMPTZ | NULL | قفل مؤقت |
| last_login | TIMESTAMPTZ | NULL | |
| password_changed_at | TIMESTAMPTZ | NULL | سياسة الانتهاء |
| created_at / updated_at | TIMESTAMPTZ | | |
| created_by / updated_by | FK → auth_user | NULL | |

**علاقات:** `1─0..1` مع `employees_employee` (رابط الحساب بالملف)، `*──*` مع `auth_role`.

#### T-002 `auth_role`

| الحقل | النوع | القيود |
|---|---|---|
| id | BIGSERIAL | PK |
| code | VARCHAR(50) | UNIQUE NOT NULL (admin, hr_manager, supervisor, accountant, employee) |
| name_ar / name_fr / name_en | VARCHAR | NOT NULL |
| is_system | BOOLEAN | default true (لا يُحذف) |
| description | TEXT | |

#### T-003 `auth_permission` (مفردات RBAC الموسعة)

| الحقل | النوع | القيود |
|---|---|---|
| id | BIGSERIAL | PK |
| code | VARCHAR(100) | UNIQUE NOT NULL (مثال: `attendance.scan.manage`) |
| module | VARCHAR(50) | NOT NULL |
| name_ar / name_fr / name_en | VARCHAR | |
| description | TEXT | |

#### T-004 `auth_role_member` (User ↔ Role)

| الحقل | النوع | القيود |
|---|---|---|
| id | BIGSERIAL | PK |
| user | FK → auth_user | ON DELETE CASCADE |
| role | FK → auth_role | ON DELETE CASCADE |
| branch_scope | FK → org_branch | NULL (تقييد الدور بفرع) |
| effective_from / effective_to | DATE | NULL |
| **UNIQUE** | (user, role, branch_scope) | |

#### T-005 `auth_role_permission` (Role ↔ Permission)

| الحقل | النوع | القيود |
|---|---|---|
| id | BIGSERIAL | PK |
| role | FK → auth_role | |
| permission | FK → auth_permission | |
| **UNIQUE** | (role, permission) | |

#### T-006 `auth_user_permission` (User ↔ Permission مباشر — استثناءات)

| الحقل | النوع | القيود |
|---|---|---|
| id | BIGSERIAL | PK |
| user | FK → auth_user | |
| permission | FK → auth_permission | |
| **UNIQUE** | (user, permission) | |

#### T-007 `auth_session`

| الحقل | النوع | القيود |
|---|---|---|
| id | BIGSERIAL | PK |
| user | FK → auth_user | NOT NULL |
| session_key | VARCHAR(64) | UNIQUE NOT NULL |
| ip_address | INET | |
| user_agent | VARCHAR(255) | |
| expires_at | TIMESTAMPTZ | NOT NULL |
| revoked | BOOLEAN | default false |
| created_at | TIMESTAMPTZ | |

#### T-008 `auth_password_reset`

| الحقل | النوع | القيود |
|---|---|---|
| id | BIGSERIAL | PK |
| user | FK → auth_user | |
| token_hash | VARCHAR(128) | UNIQUE NOT NULL |
| expires_at | TIMESTAMPTZ | NOT NULL |
| used_at | TIMESTAMPTZ | NULL |
| ip_address | INET | |

---

### 3.2 الهيكل التنظيمي (org)

#### T-009 `org_branch`

| الحقل | النوع | القيود |
|---|---|---|
| id | BIGSERIAL | PK |
| code | VARCHAR(30) | UNIQUE NOT NULL |
| name_ar / name_fr / name_en | VARCHAR(150) | NOT NULL |
| country / city / address | VARCHAR | |
| timezone | VARCHAR(64) | NOT NULL |
| work_calendar | FK → إعداد تقويم | (عطل رسمية) |
| is_active | BOOLEAN | default true |

#### T-010 `org_department`

| الحقل | النوع | القيود |
|---|---|---|
| id | BIGSERIAL | PK |
| parent | FK → org_department | NULL (شجرة) |
| branch | FK → org_branch | NOT NULL |
| code | VARCHAR(30) | UNIQUE (branch, code) |
| name_ar / name_fr / name_en | VARCHAR | NOT NULL |
| manager | FK → employees_employee | NULL (مشرف القسم) |
| is_active | BOOLEAN | |

#### T-011 `org_position`

| الحقل | النوع | القيود |
|---|---|---|
| id | BIGSERIAL | PK |
| department | FK → org_department | NOT NULL |
| code | VARCHAR(30) | UNIQUE |
| title_ar / title_fr / title_en | VARCHAR | NOT NULL |
| grade | VARCHAR(20) | |
| min_salary / max_salary | NUMERIC(15,2) | مرجعي |
| is_active | BOOLEAN | |

#### T-012 `org_shift` (جداول الدوام)

| الحقل | النوع | القيود |
|---|---|---|
| id | BIGSERIAL | PK |
| branch | FK → org_branch | NOT NULL |
| code | VARCHAR(30) | UNIQUE |
| name_ar / name_fr / name_en | VARCHAR | |
| start_time / end_time | TIME | |
| is_flexible | BOOLEAN | default false |
| grace_minutes | SMALLINT | (تسامح التأخير) |
| has_break | BOOLEAN | |
| break_start / break_end | TIME | |
| applies_days | SMALLINT[] | أيام الأسبوع |

#### T-013 `employees_membership`

| الحقل | النوع | القيود |
|---|---|---|
| id | BIGSERIAL | PK |
| employee | FK → employees_employee | NOT NULL |
| branch | FK → org_branch | NOT NULL |
| department | FK → org_department | NOT NULL |
| position | FK → org_position | NULL |
| manager | FK → employees_employee | NULL (self-ref) |
| shift | FK → org_shift | NULL |
| from_date | DATE | NOT NULL |
| to_date | DATE | NULL |
| **UNIQUE** | (employee, from_date) | عدم تداخل |

---

### 3.3 الموظفون (employees)

#### T-014 `employees_employee`

| الحقل | النوع | القيود | الوصف |
|---|---|---|---|
| id | BIGSERIAL | PK | |
| employee_code | VARCHAR(30) | UNIQUE NOT NULL | رقم الموظف |
| first_name_ar / last_name_ar | VARCHAR(100) | | |
| first_name_fr / last_name_fr | VARCHAR(100) | | |
| first_name_en / last_name_en | VARCHAR(100) | | |
| gender | VARCHAR(10) | CHECK | |
| birth_date | DATE | | |
| marital_status | VARCHAR(20) | | |
| national_id | VARCHAR(30) | UNIQUE NULL (مشفّر) | |
| passport_no | VARCHAR(30) | NULL (مشفّر) | |
| phone / email | VARCHAR | | |
| address | TEXT | | |
| bank_name / account_no / iban | VARCHAR | **مشفّر** | |
| employment_status | VARCHAR(20) | CHECK (active, probation, terminated, resigned, retired, suspended) | |
| hire_date / termination_date | DATE | | |
| termination_reason | VARCHAR(100) | | |
| photo | image | | |
| created_at / updated_at | TIMESTAMPTZ | | |
| created_by / updated_by | FK | | |

#### T-015 `employees_jobhistory`

| الحقل | النوع | القيود |
|---|---|---|
| id | BIGSERIAL | PK |
| employee | FK → employees_employee | |
| action | VARCHAR(30) | (hire, promotion, transfer, salary_change, termination) |
| branch / department / position | FK | عند الحدث |
| effective_date | DATE | NOT NULL |
| note | TEXT | |
| changed_by | FK → auth_user | |

#### T-016 `employees_contract`

| الحقل | النوع | القيود |
|---|---|---|
| id | BIGSERIAL | PK |
| employee | FK | NOT NULL |
| contract_type | VARCHAR(30) | (fixed, unlimited, probation, part_time) |
| start_date / end_date | DATE | |
| template | FK → قالب عقد (اختياري) | |
| signed_document | FK → employees_document | |
| salary_basic | NUMERIC(15,2) | |
| notice_period_days | SMALLINT | |
| status | VARCHAR(20) | (draft, active, expired, terminated) |

#### T-017 `employees_document`

| الحقل | النوع | القيود |
|---|---|---|
| id | BIGSERIAL | PK |
| employee | FK → employees_employee | NULL (وثائق عامة) |
| category | FK → doc_type | |
| title | VARCHAR | |
| file_path | VARCHAR(500) | NOT NULL |
| mime_type / size_bytes | | |
| version | SMALLINT | default 1 |
| parent_doc | FK → self | (سلسلة إصدارات) |
| expires_at | DATE | NULL |
| is_confidential | BOOLEAN | default false |
| allowed_roles | FK → auth_role | (اختياري) |
| uploaded_by | FK → auth_user | |
| created_at | TIMESTAMPTZ | |

#### T-018 `employees_employeeqr`

| الحقل | النوع | القيود | الوصف |
|---|---|---|---|
| id | BIGSERIAL | PK | |
| employee | FK | UNIQUE | |
| secret | CHAR(32) | UNIQUE NOT NULL (مشفّر عند الحاجة) | مفتاح QR |
| version | SMALLINT | default 1 | يتغير عند إعادة التوليد |
| status | VARCHAR(20) | (active, revoked, expired) | |
| activated_at / expires_at | TIMESTAMPTZ | | |
| revoked_at / revoked_by | | | |
| created_by | FK | | |

> **التفاصيل الكاملة لنظام QR في `06-qr-system.md`.**

---

### 3.4 الحضور والانصراف (attendance)

#### T-019 `attendance_attendanceday`

| الحقل | النوع | القيود | الوصف |
|---|---|---|---|
| id | BIGSERIAL | PK | |
| employee | FK | NOT NULL | |
| work_date | DATE | NOT NULL | |
| shift | FK → org_shift | NULL | |
| branch | FK → org_branch | | |
| state | VARCHAR(20) | (present, absent, leave, mission, exception, weekend) | |
| check_in / check_out | TIMESTAMPTZ | NULL | |
| worked_minutes | SMALLINT | | |
| late_minutes / early_minutes | SMALLINT | | |
| overtime_minutes | SMALLINT | | |
| is_corrected | BOOLEAN | default false | |
| **UNIQUE** | (employee, work_date) | | لا تكرار |

#### T-020 `attendance_attendancescan` (سجل المسح)

| الحقل | النوع | القيود |
|---|---|---|
| id | BIGSERIAL | PK |
| attendanceday | FK → T-019 | |
| employee | FK | |
| scanned_at | TIMESTAMPTZ | NOT NULL |
| source | VARCHAR(20) | (phone, fixed_reader, manual) |
| device | FK → devices_qrdevice | NULL |
| ip_address | INET | |
| decision | VARCHAR(20) | (check_in, check_out, rejected, warning) |
| qr_version | SMALLINT | |
| result_detail | VARCHAR(200) | |

#### T-021 `attendance_exception` (إذن/مأمورية/تعويض)

| الحقل | النوع | القيود |
|---|---|---|
| id | BIGSERIAL | PK |
| employee | FK | |
| attendanceday | FK | NULL |
| type | VARCHAR(20) | (permission, mission, compensatory, correction) |
| from_time / to_time | TIMESTAMPTZ | |
| hours | NUMERIC(5,2) | |
| reason | TEXT | |
| status | VARCHAR(20) | (pending, approved, rejected) |
| requested_by / approved_by | FK → auth_user | |

---

### 3.5 الإجازات (leave)

#### T-022 `leave_leavetype`

| الحقل | النوع | القيود |
|---|---|---|
| id | BIGSERIAL | PK |
| code | VARCHAR(30) | UNIQUE NOT NULL |
| name_ar / name_fr / name_en | VARCHAR | NOT NULL |
| days_per_year | SMALLINT | |
| carryover_allowed | BOOLEAN | |
| max_carryover_days | SMALLINT | |
| is_unpaid | BOOLEAN | default false |
| requires_approval_levels | SMALLINT | default 1 |
| applicable_to | VARCHAR(30) | (all, gender-specific) |
| is_active | BOOLEAN | |

#### T-023 `leave_leavebalance`

| الحقل | النوع | القيود |
|---|---|---|
| id | BIGSERIAL | PK |
| employee | FK | |
| leave_type | FK | |
| year | SMALLINT | |
| granted | NUMERIC(5,1) | |
| used | NUMERIC(5,1) | default 0 |
| carried_from | NUMERIC(5,1) | |
| adjusted | NUMERIC(5,1) | default 0 (تسوية) |
| **UNIQUE** | (employee, leave_type, year) | |

#### T-024 `leave_leaverequest`

| الحقل | النوع | القيود |
|---|---|---|
| id | BIGSERIAL | PK |
| employee | FK | |
| leave_type | FK | |
| from_date / to_date | DATE | |
| days | NUMERIC(5,1) | |
| reason | TEXT | |
| status | VARCHAR(20) | (draft, pending, approved, rejected, cancelled) |
| current_level | SMALLINT | default 1 |
| submitted_at | TIMESTAMPTZ | |
| requested_by | FK | |

#### T-025 `leave_leaveapproval` (سلسلة الموافقات)

| الحقل | النوع | القيود |
|---|---|---|
| id | BIGSERIAL | PK |
| leave_request | FK | |
| level | SMALLINT | |
| approver | FK → auth_user | |
| action | VARCHAR(20) | (approved, rejected, escalated) |
| comment | TEXT | |
| at | TIMESTAMPTZ | |
| **UNIQUE** | (leave_request, level) | |

#### T-026 `leave_public_holiday` (عطل رسمية)

| الحقل | النوع |
|---|---|
| id | PK |
| branch | FK → org_branch |
| date | DATE |
| name_ar / name_fr / name_en | VARCHAR |
| is_recurring | BOOLEAN |

---

### 3.6 الرواتب (payroll)

#### T-027 `payroll_payelement`

| الحقل | النوع | القيود |
|---|---|---|
| id | BIGSERIAL | PK |
| code | VARCHAR(30) | UNIQUE |
| name_ar / name_fr / name_en | VARCHAR | |
| kind | VARCHAR(10) | (earning, deduction) |
| calculation | VARCHAR(20) | (fixed, percent_of_basic, attendance_based) |
| amount / percent | NUMERIC(15,2) | |
| applies_to_all | BOOLEAN | |
| is_active | BOOLEAN | |

#### T-028 `payroll_payrun`

| الحقل | النوع | القيود |
|---|---|---|
| id | BIGSERIAL | PK |
| period_code | VARCHAR(10) | (2026-08) |
| branch | FK → org_branch | |
| status | VARCHAR(20) | (draft, reviewing, approved, frozen) |
| total_earnings / total_deductions / total_net | NUMERIC(15,2) | |
| generated_at | TIMESTAMPTZ | |
| generated_by / approved_by | FK | |
| approved_at | TIMESTAMPTZ | |
| **UNIQUE** | (period_code, branch) | |

#### T-029 `payroll_payrollline`

| الحقل | النوع | القيود |
|---|---|---|
| id | BIGSERIAL | PK |
| pay_run | FK | |
| employee | FK | |
| element | FK → payelement | |
| hours | NUMERIC(8,2) | NULL |
| amount | NUMERIC(15,2) | NOT NULL |
| note | VARCHAR(200) | |
| **UNIQUE** | (pay_run, employee, element) | |

#### T-030 `payroll_payslip`

| الحقل | النوع | القيود |
|---|---|---|
| id | BIGSERIAL | PK |
| pay_run | FK | |
| employee | FK | |
| basic_salary / total_earnings / total_deductions / net | NUMERIC(15,2) | |
| attended_days / absent_days / overtime_hours | | |
| bank_export_ref | VARCHAR(100) | NULL |
| pdf_path | VARCHAR(500) | |
| generated_at | TIMESTAMPTZ | |
| **UNIQUE** | (pay_run, employee) | |

#### T-031 `payroll_endofservice` (نهاية الخدمة)

| الحقل | النوع | القيود |
|---|---|---|
| id | BIGSERIAL | PK |
| employee | FK | |
| termination_date | DATE | |
| total_years | NUMERIC(5,2) | |
| service_reward | NUMERIC(15,2) | |
| unused_leave_comp | NUMERIC(15,2) | |
| notice_period | NUMERIC(15,2) | |
| deductions | NUMERIC(15,2) | |
| net | NUMERIC(15,2) | |
| status | VARCHAR(20) | (draft, approved, paid) |
| approved_by | FK | |

---

### 3.7 التدريب (training)

#### T-032 `training_course`

| الحقل | النوع | القيود |
|---|---|---|
| id | BIGSERIAL | PK |
| code | VARCHAR(30) | UNIQUE |
| title_ar / title_fr / title_en | VARCHAR | |
| description | TEXT | |
| category | VARCHAR(50) | |
| provider | VARCHAR(100) | (داخلي/خارجي) |
| cost | NUMERIC(15,2) | |
| is_active | BOOLEAN | |

#### T-033 `training_session`

| الحقل | النوع | القيود |
|---|---|---|
| id | BIGSERIAL | PK |
| course | FK | |
| start_date / end_date | DATE | |
| trainer | VARCHAR(100) | |
| location | VARCHAR(100) | |
| capacity | SMALLINT | |
| status | VARCHAR(20) | (planned, running, completed, cancelled) |

#### T-034 `training_enrollment`

| الحقل | النوع | القيود |
|---|---|---|
| id | BIGSERIAL | PK |
| session | FK | |
| employee | FK | |
| status | VARCHAR(20) | (pending, approved, completed, failed) |
| approved_by | FK | |
| **UNIQUE** | (session, employee) | |

#### T-035 `training_certificate`

| الحقل | النوع |
|---|---|
| id | PK |
| enrollment | FK |
| title | VARCHAR |
| issued_date | DATE |
| file_path | VARCHAR(500) |

---

### 3.8 تقييم الأداء (perf)

#### T-036 `perf_perfcycle`

| الحقل | النوع | القيود |
|---|---|---|
| id | BIGSERIAL | PK |
| name_ar / name_fr / name_en | VARCHAR | |
| period_start / period_end | DATE | |
| self_review_deadline / manager_review_deadline | DATE | |
| status | VARCHAR(20) | (draft, open, closed) |

#### T-037 `perf_perftemplate`

| الحقل | النوع |
|---|---|
| id | PK |
| name_ar / name_fr / name_en | VARCHAR |
| criteria_json | JSONB | (قائمة معايير بوزن) |
| is_active | BOOLEAN |

#### T-038 `perf_perfreview`

| الحقل | النوع | القيود |
|---|---|---|
| id | BIGSERIAL | PK |
| employee | FK | |
| cycle | FK | |
| template | FK | |
| self_score | NUMERIC(5,2) | NULL |
| manager_score | NUMERIC(5,2) | NULL |
| final_score | NUMERIC(5,2) | NULL |
| self_comment / manager_comment | TEXT | |
| status | VARCHAR(20) | (pending_self, pending_manager, done, closed) |
| **UNIQUE** | (employee, cycle) | |

#### T-039 `perf_perfobjective`

| الحقل | النوع |
|---|---|
| id | PK |
| review | FK |
| kpi_title | VARCHAR |
| weight | NUMERIC(5,2) |
| target / achieved | NUMERIC(15,2) |
| score | NUMERIC(5,2) |

#### T-040 `perf_pipplan`

| الحقل | النوع |
|---|---|
| id | PK |
| review | FK |
| start_date / end_date | DATE |
| action_items | TEXT |
| status | VARCHAR(20) | (open, closed) |
| supervisor_note | TEXT |

---

### 3.9 الإشعارات (notif)

#### T-041 `notif_notification`

| الحقل | النوع |
|---|---|
| id | PK |
| user | FK → auth_user |
| type | VARCHAR(30) | (leave_approved, payslip_ready, contract_expiry, doc_expiry, ...) |
| title / body | TEXT |
| related_model / related_id | VARCHAR | (ربط سياقي) |
| is_read | BOOLEAN | default false |
| created_at | TIMESTAMPTZ |

#### T-042 `notif_notificationpref`

| الحقل | النوع |
|---|---|
| id | PK |
| user | FK → auth_user |
| type | VARCHAR(30) |
| channel | VARCHAR(20) | (in_app, email) |
| enabled | BOOLEAN |

#### T-043 `notif_scheduledalert`

| الحقل | النوع |
|---|---|
| id | PK |
| alert_type | VARCHAR(30) |
| target_date | DATE |
| payload_json | JSONB |
| fired_at | TIMESTAMPTZ | NULL |

---

### 3.10 التدقيق والنسخ الاحتياطي (audit)

#### T-044 `audit_auditlog`

| الحقل | النوع | القيود | الوصف |
|---|---|---|---|
| id | BIGSERIAL | PK | |
| actor | FK → auth_user | NULL (أنظمة) | |
| actor_ip | INET | | |
| action | VARCHAR(30) | (create, update, delete, login, logout, scan, approve, ...) | |
| model_name | VARCHAR(100) | | |
| object_id | BIGINT | | |
| field_changes | JSONB | NULL | {field: [old, new]} |
| request_path | VARCHAR(300) | | |
| created_at | TIMESTAMPTZ | NOT NULL | فهرس عالي |

#### T-045 `audit_backupjob`

| الحقل | النوع |
|---|---|
| id | PK |
| started_at / finished_at | TIMESTAMPTZ |
| type | VARCHAR(20) | (full, wale) |
| target_path | VARCHAR(500) |
| checksum | VARCHAR(128) |
| status | VARCHAR(20) | (running, success, failed) |
| log | TEXT |

#### T-046 `audit_restorejob`

| الحقل | النوع |
|---|---|
| id | PK |
| source_backup | FK → backupjob |
| started_at / finished_at | TIMESTAMPTZ |
| status | VARCHAR(20) |
| log | TEXT |

---

### 3.11 أجهزة QR (devices)

#### T-047 `devices_qrdevice`

| الحقل | النوع | القيود |
|---|---|---|
| id | BIGSERIAL | PK |
| branch | FK → org_branch | |
| device_code | VARCHAR(50) | UNIQUE |
| api_key_hash | VARCHAR(128) | (مصادقة الجهاز) |
| location | VARCHAR(100) | |
| status | VARCHAR(20) | (active, inactive, maintenance) |
| last_seen | TIMESTAMPTZ | NULL |

#### T-048 `devices_qrdeviceaudit`

| الحقل | النوع |
|---|---|
| id | PK |
| device | FK |
| action | VARCHAR(30) |
| detail | TEXT |
| at | TIMESTAMPTZ |

---

### 3.12 التقارير (reports)

#### T-049 `reports_reportdefinition`

| الحقل | النوع | الوصف |
|---|---|---|
| id | PK | |
| code | VARCHAR(50) UNIQUE | |
| name_ar / name_fr / name_en | VARCHAR | |
| template_type | VARCHAR(20) | (pdf, xlsx, csv) |
| owner | FK → auth_user | |
| filters_json | JSONB | الفلاتر الافتراضية |
| is_shared | BOOLEAN | |

#### T-050 `reports_reportjob`

| الحقل | النوع |
|---|---|
| id | PK |
| report | FK → reportdefinition |
| requested_by | FK |
| status | VARCHAR(20) | (queued, running, done, failed) |
| started_at / finished_at | TIMESTAMPTZ |
| error | TEXT |

#### T-051 `reports_generatedfile`

| الحقل | النوع |
|---|---|
| id | PK |
| job | FK |
| file_path | VARCHAR(500) |
| format | VARCHAR(10) |
| size_bytes | BIGINT |
| expires_at | TIMESTAMPTZ |

---

### 3.13 وحدة الذكاء الاصطناعي (ai)

#### T-052 `ai_aiquery`

| الحقل | النوع | الوصف |
|---|---|---|
| id | PK | |
| user | FK → auth_user | |
| prompt | TEXT | |
| answer_json | JSONB | |
| language | VARCHAR(5) | |
| analytics_ref | VARCHAR(100) | NULL (ربط بنتيجة تحليل) |
| created_at | TIMESTAMPTZ |

#### T-053 `ai_analyticsjob`

| الحقل | النوع |
|---|---|
| id | PK |
| analysis_type | VARCHAR(50) | (absence, attendance, performance, payroll, turnover, productivity) |
| period_start / period_end | DATE |
| scope_json | JSONB | (branch/department) |
| result_json | JSONB |
| status | VARCHAR(20) |
| requested_by | FK |
| created_at | TIMESTAMPTZ |

#### T-054 `ai_prediction` (تنبؤات)

| الحقل | النوع |
|---|---|
| id | PK |
| employee | FK | NULL |
| prediction_type | VARCHAR(50) | (resignation, absence_risk) |
| probability | NUMERIC(4,3) | |
| features_json | JSONB | |
| model_version | VARCHAR(20) |
| created_at | TIMESTAMPTZ |

---

## 4. الفهارس الاستراتيجية للأداء (Indexes)

> قاعدة: كل FK كثيف الاستخدام + كل Query متكررة (لوحات، تقارير) تحصل على فهرس.

| الجدول | الفهرس | السبب |
|---|---|---|
| attendance_attendanceday | (employee, work_date) | UNIQUE — بحث الحضور اليومي |
| attendance_attendanceday | (work_date, branch) | تقارير الفروع اليومية |
| attendance_attendancescan | (employee, scanned_at DESC) | سجل موظف حديث |
| attendance_attendancescan | (scanned_at) | تقارير الساعة |
| leave_leaverequest | (employee, status) | صندوق طلبات الموظف |
| leave_leaverequest | (status, current_level) | طابور موافقات المشرف |
| leave_leaveapproval | (approver, at DESC) | مهام الموافقة |
| payroll_payslip | (employee, pay_run) | قسائم الموظف |
| payroll_payrollline | (pay_run) | تجميع الكشف |
| audit_auditlog | (model_name, object_id) | تدقيق كائن |
| audit_auditlog | (created_at DESC) | متصفح السجل |
| audit_auditlog | (actor, created_at DESC) | تدقيق مستخدم |
| employees_employee | (branch, employment_status) | لوحات الفرع |
| employees_membership | (manager, from_date) | شجرة فريق المشرف |
| notif_notification | (user, is_read, created_at DESC) | مركز الإشعارات |
| org_department | (parent) | تجوال الشجرة |
| employees_employee | GIN (search_vector) | بحث FTS عربي/إنجليزي |

### الاعتبارات

1. **FTS للعربية**: استخدم `pg_trgm` أو `unaccent` + dictionary عربي — اختبر دقة البحث العربي مبكرًا.
2. **جداول ضخمة**: `attendance_attendancescan` و `audit_auditlog` ستنمو سريعًا (5000 موظف × مسحين × 250 يوم ≈ **2.5M صف/سنة**) → خطط **Table Partitioning** بحسب الشهر/السنة منذ البداية.
3. **أرشفة**: سياسة أرشفة سجل المسح والتدقيق أكبر من N سنة إلى جداول أرشيف.

---

## 5. البيانات الحساسة (Encryption at Rest)

| النوع | الحل |
|---|---|
| كلمات المرور | Argon2id (Django default) — لا تخزين قابل للعكس |
| بيانات بنكية (IBAN/حساب) | **تشفير ميداني (Field-level AES-256)** باستخدام `django-cryptography` أو Fernet |
| وثائق حساسة | تشفير الملفات على القرص + أذونات نظام الملفات |
| أسرار QR / مفاتيح API الأجهزة | hash فقط (لا تخزين بنص صريح) |
| مفتاح التشفير | يُخزَّن في ملف إعدادات خارج الدليل العام (`.env` محمي بـ 600) |
| النسخ الاحتياطي | مشفّر عند الكتابة (راجع `09-security.md`) |

---

## 6. الترحيلات والبيانات المرجعية (Seed Data)

| مجموعة | المحتوى |
|---|---|
| Roles | 5 أدوار أساسية (admin, hr_manager, supervisor, accountant, employee) |
| Permissions | كل مفردات `05-rbac.md` |
| Leave types | سنوية، مرضية، أمومة، أبوة، مرهونة، خاصة (قابلة للتعديل) |
| Pay elements | أساسي، سكن، نقل، عمل إضافي، غياب، تأخير، مكافأة، خصم |
| Branches | فرع رئيسي افتراضي |
| Calendar | عطل رسمية افتراضية قابلة للتكوين |
| Admin user | مستخدم أول يُطلب تغيير كلمته أول دخول |

**أداة:** بيانات `fixtures` (JSON/YAML) + `DataMigration` مع أمر `load_initial_data`.

---

## 7. تحذيرات وقرارات تصميمية (Alert Box)

1. **⚠️ `ON DELETE RESTRICT`** للعلاقات التاريخية (contracts, payslips, attendanceday) — أي حذف فعلي سيخرب التقارير القانونية. حذف منطقي فقط.
2. **⚠️ Partitioning من اليوم الأول** لجدولي المسح والتدقيق — إضافته لاحقًا على بيانات ضخمة مكلف جدًا في PostgreSQL.
3. **⚠️ المبالغ المالية NUMERIC** — لا `FLOAT` ولا `DECIMAL` أقل من دقة 15,2 للأجور.
4. **⚠️ الأسماء متعددة اللغات**: لا تعتمد على إضافة أعمدة لاحقًا — صمم `name_ar/fr/en` أو جدول ترجمات لكل نوع قابل للتكوين منذ الآن.
5. **⚠️ الجلسات**: لا تُخزن الجلسات في ملفات — استخدم DB أو Redis Session لتمكين إلغاء الجلسات عن بعد.
6. **⚠️ التوقيت**: كل الأعمدة الزمنية `TIMESTAMPTZ` (بالتوقيت العالمي) والعرض بالتوقيت المحلي للفرع — أي خلط هنا يكسر الحضور.
7. **⚠️ ترحيل فترات مزدوجة**: الحضور الليلي قد يعبر منتصف الليل — نموذج `AttendanceDay` يجب أن يعرف قاعدة تخصيص الساعة لليوم (Config لكل فرع).
