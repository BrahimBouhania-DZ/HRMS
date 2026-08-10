# المرحلة الخامسة عشرة: وحدة الرواتب (Payroll Module)

> **HRMS-DOC-15** — توثيق وحدة الرواتب v2: النماذج، قواعد الأعمال (BR-PAY-*)، الخدمات، العروض، الاختبارات، والربط مع التقارير والإنتاج.

---

## جدول المحتويات

1. الهدف والنطاق
2. النماذج (Models)
3. قواعد الأعمال (Business Rules)
4. الخدمات (Services)
5. العروض والروابط
6. الصلاحيات (RBAC)
7. الاختبارات
8. التصدير (بنك/PDF/Excel)
9. نهاية الخدمة
10. الربط مع الإنتاج والتقارير

---

## 1. الهدف والنطاق

تنفيذ الوحدة المالية للنسخة v2 (راجع `10-roadmap.md` §5): حساب الرواتب الشهرية آليًا وفق الحضور، بعناصر أجر قابلة للتكوين، وسلسلة اعتماد (مسودة→مراجعة→اعتماد→تجميد)، وتصدير بنكي، وقسائم PDF، ونهاية خدمة.

النطاق المستبعد حاليًا: التكامل البنكي المباشر، الاستقطاعات القانونية الآلية (الضمان/الضرائب المتغيرة)، وربط أتمتة الدفع — كلها قابلة للإضافة كعناصر أجر أو خطوط لاحقًا دون كسر النموذج.

## 2. النماذج (Models) — `apps/payroll/models.py`

| النموذج | الوصف | الحقول الرئيسية |
|---|---|---|
| `PayElement` | عنصر أجر (إضافة/خصم) | `code`, `name_ar/fr/en`, `kind` (earning/deduction), `calculation` (fixed/percent_of_basic/attendance_based), `amount`, `percent`, `applies_to_all`, `applicable_genders`, `is_active` |
| `PayRun` | دورة صرف شهرية | `period_code` (فريد: YYYY-MM), `branch`, `status` (draft/reviewing/approved/frozen), `start/end_date`, `notes`, `created_by`, `reviewed_by`, `approved_by`, `frozen_by`, تواريخ القرارات |
| `Payslip` | قسيمة موظف داخل دورة | `pay_run`, `employee`, `total_earnings`, `total_deductions`, `net`, `attended_days`, `absent_days`, `late_minutes`, `days_in_period`, `elements_snapshot` (JSON) |
| `PayrollLine` | سطر مفصل (أثر تدقيق) | `payslip`, `element`, `label`, `amount`, `note` |
| `EndOfService` | نهاية خدمة | `employee`, `termination_date`, `total_years`, `service_reward`, `unused_leave_comp`, `notice_period`, `deductions`, `net`, `status` (draft/completed), `created_by` |

مفاتيح القرار:
- `Payslip.elements_snapshot` تحفظ العناصر وقت الحساب (التاريخية) — أي تعديل لاحق على العناصر لا يغيّر القسائم المجمّدة.
- الحالة تُخزَّن نصيًا مع `update_status` للمرور عبر سلسلة معتمدة (BR-PAY-001).
- كل حساب في `Decimal`/`float` داخل الخدمات ثم يُقيّد في `DecimalField`.

## 3. قواعد الأعمال (Business Rules)

| المعرّف | القاعدة |
|---|---|
| **BR-PAY-001** | ترتيب الحالة إلزامي: `draft → reviewing → approved → frozen`. التجميد نهائي؛ لا تعديل ولا انتقال بعد `frozen`. كل عملية تسجّل المسؤول (created/reviewed/approved/frozen_by). |
| **BR-PAY-002** | خصم الغياب: `(الأجر الأساسي ÷ أيام العمل الرسمية للشهر) × أيام الغياب`. يوم العمل الرسمي = أيام الأحد..الخميس (لا يشمل الجمعة/السبت). يُسجَّل خط `خصم غياب` لكل قسيمة. |
| **BR-PAY-003** | دورة واحدة لكل (فترة + فرع): محاولة توليد مكررة → `PayrollError`. |
| **BR-PAY-004** | تصدير البنك لا يتاح إلا بعد الاعتماد (approved/frozen). القسيمة PDF لا تتاح إلا بعد الاعتماد. |
| **BR-PAY-005** | عنصر `attendance_based` يُحسب × أيام الحضور الفعلية. عنصر `percent_of_basic` نسبة من الأجر الأساسي للعقد. |
| **BR-PAY-006** | نهاية الخدمة: `مكافأة = سنوات × أجر يومي × 0.5`، `تعويض إجازات = رصيد متبقٍ × أجر يومي`، `إشعار = شهر أساسي`. العامل قابل للتكوين. |
| **BR-PAY-007** | الأجر الأساسي يُقرأ من **أحدث عقد** للموظف (`apps.employees.models.Contract`) — لا يوجد حقل أجر على الموظف. |
| **BR-PAY-008** | الموظفون المشمولون: النشطون (`is_active=True`) في فرع الدورة. من بلا عقد يُحتسب له 0 أساسي (يظهر تحذير في السجل). |

## 4. الخدمات (Services) — `apps/payroll/services.py`

| الدالة | الدور |
|---|---|
| `official_workdays(period_code, branch)` | عدد أيام العمل الرسمية (خصم عطلة نهاية الأسبوع + العطل الرسمية إن وُجدت). |
| `generate_payrun(period_code, branch, user, force=False)` | ينشئ الدورة + القسائم + الخطوط (ذرية `transaction.atomic`). |
| `update_status(payrun, to, user)` | انتقال الحالة مع تحقق BR-PAY-001. |
| `review_payrun / approve_payrun / freeze_payrun` | غلافات `update_status`. |
| `bank_rows(payrun)` | صفوف التصدير البنكي (من لديهم `bank_account` فقط) بصافي الاعتماد. |
| `create_payslip_pdf(payslip, request)` | قسيمة PDF عربية RTL عبر WeasyPrint. |
| `calculate_end_of_service(employee, termination_date, user, reward_factor=0.5)` | حساب نهاية الخدمة وإنشاء سجل مسودة. |

تعبير الحساب:
```
net = base_salary + Σ(إضافات) − Σ(خصومات) − خصم_الغياب
خصم_الغياب = (base_salary ÷ official_workdays) × absent_days
```

## 5. العروض والروابط — `apps/payroll/views.py` + `urls.py`

| الرابط | الاسم | الوصف |
|---|---|---|
| `/payroll/elements/` | `payroll:element_list` | قائمة عناصر الأجر + إدارة |
| `/payroll/runs/` | `payroll:run_list` | دورات الصرف + التصدير |
| `/payroll/runs/generate/` | `payroll:run_generate` | توليد دورة |
| `/payroll/runs/<pk>/` | `payroll:run_detail` | تفاصيل الدورة (القسائم + القرارات) |
| `/payroll/runs/<pk>/status/<action>/` | `payroll:run_status` | مراجعة/اعتماد/تجميد |
| `/payroll/payslip/<pk>/pdf/` | `payroll:payslip_pdf` | قسيمة PDF (بعد الاعتماد) |
| `/payroll/runs/<pk>/export/bank/<fmt>/` | `payroll:bank_export` | CSV/Excel بعد الاعتماد |
| `/payroll/eos/` , `/payroll/eos/new/` | `payroll:eos_list/eos_create` | نهايات الخدمة |

كل عروض الكتابة محمية بالصلاحيات؛ العروض المالية (تصدير/PDF) تعيد `400` قبل الاعتماد.

## 6. الصلاحيات (RBAC)

`seed_rbac` يضيف 8 صلاحيات payroll:

| الرمز | الوصف |
|---|---|
| `payroll.element.*` | إدارة عناصر الأجر |
| `payroll.run.generate` | توليد الدورات |
| `payroll.run.review` | مراجعة |
| `payroll.run.approve` | اعتماد |
| `payroll.run.freeze` | تجميد |
| `payroll.payslip.view` | عرض القسائم/PDF |
| `payroll.bank.export` | التصدير البنكي |
| `payroll.eos.*` | نهاية الخدمة |

فصل المهام (SoD): من يولّد لا يعتمد إلزاميًا (مبدأيًا)، والصلاحيات منفصلة فعليًا. أدوار: `admin` الكل، `manager` يولد/يراجع، `hr` يدير العناصر، `finance` يعتمد/يجمد/يصدّر.

## 7. الاختبارات — `apps/payroll/tests.py` (T-027..T-031)

| الاختبار | التغطية |
|---|---|
| `test_official_workdays` | احتساب أيام العمل الرسمية (شهر سبت-البدء) |
| `test_generate_payrun_with_attendance` | عناصر ثابت/نسبة/حضور + خصم الغياب BR-PAY-002 + صافي |
| `test_duplicate_run_rejected` | BR-PAY-003 |
| `test_status_lifecycle_and_freeze` | BR-PAY-001 كاملًا + رفض المخالفة |
| `test_bank_rows_only_with_account` | تصدير لمن لديه حساب فقط |
| `test_end_of_service_calculation` | BR-PAY-006 |
| عروض | 403 بدون صلاحية، توليد عبر POST، مسار حالة عبر العروض، PDF/بنك بعد الاعتماد |

## 8. التصدير

- **البنك CSV/Excel**: صفوف (رقم موظف، اسم، حساب، صافي) — فقط بعد `approved` (BR-PAY-004).
- **القسيمة PDF**: قالب عربي RTL (WeasyPrint) يعرض الأساسي + عناصر × قيم + الخصومات + الصافي + الحضور/الغياب.
- **تقرير الأجور REP-30**: ملخص دورات الصرف (عدد قسائم، إضافات، خصومات، صافي) في `apps/reports` مع تصدير CSV/Excel/PDF.

## 9. نهاية الخدمة

من `calculate_end_of_service` مع عامل قابل للتكوين (`EOS_REWARD_FACTOR = 0.5`). تُنشأ بحالة `draft` وتُكمل يدويًا بعد المراجعة المحاسبية — لا تُعتمد آليًا (Roadmap §10.4: تتطلب مراجعة محاسب فعلية قبل الإنتاج).

## 10. الربط مع الإنتاج والتقارير

- يُدرج التقرير المالي **REP-30** في لوحة التقارير (`apps/reports`) بصلاحية `reports.view`.
- اللوحة الرئيسية (`apps/core/dashboard.py`) تعرض أرقام التقارير (REP-*) كروابط سريعة لمن يملك `reports.view`.
- التهيئة للإنتاج عبر `python manage.py deploy_prepare` (check + هجرات + collectstatic) — راجع `14-deployment.md`.
- البوليصة الموحّدة: `python manage.py seed_all` تشغّل RBAC + الإجازات + مشرف افتراضي في dev و prod.

---

## تسجيل التغييرات

| التاريخ | النسخة | التغيير |
|---|---|---|
| 2026-08-09 | 2.0 | توثيق وحدة الرواتب + REP-30 + seed_all + deploy_prepare + حزمة النشر |
