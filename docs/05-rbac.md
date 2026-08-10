# المرحلة الخامسة: نظام الصلاحيات (RBAC — Role-Based Access Control)

> **HRMS-DOC-05** — نظام صلاحيات مرن: أدوار قياسية + أدوار/صلاحيات مخصصة + نطاقات (Scopes).

---

## جدول المحتويات

1. المفاهيم الأساسية
2. نموذج البيانات (يعتمد على `03` T-002..T-006)
3. الأدوار القياسية (5 أدوار)
4. مفردات الصلاحيات (Permission Catalog)
5. الصلاحيات الافتراضية لكل دور (Matrix)
6. الصلاحيات المخصصة (Custom Roles)
7. نطاقات الصلاحية (Scope: عمومي / فرع / قسم / فريق / ذاتي)
8. تنفيذ التحقق في الكود (Enforcement)
9. سيناريوهات وحالات خاصة
10. مخرجات التطوير
11. تحذيرات وقرارات تصميمية

---

## 1. المفاهيم الأساسية

| المصطلح | المعنى |
|---|---|
| **Permission (صلاحية)** | مفردة دقيقة بصيغة `module.action.obj` (مثال: `payroll.run.approve`) |
| **Role (دور)** | مجموعة صلاحيات جاهزة (admin, hr_manager, ...) |
| **Custom Role** | دور منشأ من الواجهة بصلاحيات مختارة |
| **User-Role Scope** | تقييد الدور بفرع/قسم (مدير فرع لا يرى فرعًا آخر) |
| **Direct Permission** | استثناء مباشر لمستخدم (Grant أو Deny) |
| **نطاق البيانات (Data Scope)** | من يستطيع رؤية أي صف (عمومي/فرع/قسم/فريق/ذاتي) |

> **القاعدة الذهبية:** الصلاحية تحدد **ماذا** يستطيع المستخدم، ونطاق البيانات يحدد **على مَن/ماذا** تطبق. الاثنان معًا يشكلان القرار النهائي.

---

## 2. نموذج البيانات

```
auth_permission        ← مفردات الصلاحيات (code فريد)
auth_role              ← أدوار (is_system: أدوار مدمجة لا تُحذف)
auth_role_permission   ← Role ↔ Permission
auth_role_member       ← User ↔ Role (+ branch_scope, effective dates)
auth_user_permission   ← User ↔ Permission (استثناء مباشر، بـ grant/deny)
```

راجع `03-database-design.md` §3.1 للجداول الكاملة.

---

## 3. الأدوار القياسية

| الدور | رمز الكود | الوصف العام |
|---|---|---|
| **Admin** | `admin` | كل شيء تقنيًا (مستخدمون، إعدادات، نسخ احتياطي، سجل تدقيق) |
| **HR Manager** | `hr_manager` | كامل عمليات الموارد البشرية (لا صلاحيات نظام تقنية) |
| **Supervisor** | `supervisor` | إدارة فريقه فقط (حضور، إجازات، تقييم) |
| **Accountant** | `accountant` | الرواتب والمكافآت والخصومات (لا تعديل بيانات موظفين) |
| **Employee** | `employee` | ملفه وطلباته وقيسمه وحضوره |

> كل الأدوار القياسية `is_system=True`: يمكن تعديل صلاحياتها من الواجهة لكن لا يمكن حذفها.

---

## 4. مفردات الصلاحيات (Permission Catalog)

> **صيغة:** `module.object.action` — 3 مستويات عمليات: `view, create, edit, delete, approve`.

### 4.1 عام (core)

| الصلاحية | الوصف |
|---|---|
| `dashboard.view` | رؤية لوحة التحكم |
| `search.global` | البحث الموحّد |
| `notifications.view/manage` | مركز الإشعارات |
| `reports.view/generate/export` | التقارير والتصدير |
| `settings.view/edit` | الإعدادات العامة |
| `system.audit.view` | سجل التدقيق |
| `system.backup.manage` | النسخ الاحتياطي والاستعادة |

### 4.2 الهيكل التنظيمي (org)

| الصلاحية | الوصف |
|---|---|
| `org.branch.view/create/edit/disable` | الفروع |
| `org.department.view/create/edit/disable` | الأقسام |
| `org.position.view/create/edit` | المناصب |
| `org.shift.view/create/edit` | جداول الدوام |

### 4.3 الموظفون (employees)

| الصلاحية | الوصف |
|---|---|
| `employee.view` | عرض بيانات موظفين (ضمن النطاق) |
| `employee.create` / `employee.edit` | إضافة/تعديل |
| `employee.terminate` | إنهاء خدمة |
| `employee.import` / `employee.export` | استيراد/تصدير جماعي |
| `employee.contract.view/manage` | العقود |
| `employee.document.view/manage` | الوثائق |
| `employee.qr.manage` | إصدار/إلغاء/إعادة توليد QR |
| `employee.salary.view` | رؤية بيانات الراتب (حساسة) |
| `employee.bankdata.view` | رؤية البيانات البنكية (حساسة جدًا) |

### 4.4 الحضور (attendance)

| الصلاحية | الوصف |
|---|---|
| `attendance.view` | رؤية الحضور (ضمن النطاق) |
| `attendance.scan` | استخدام QR للدخول/الخروج |
| `attendance.manual.record` | تسجيل يدوي (بوابة الطوارئ) |
| `attendance.correct` | تصحيح حضور |
| `attendance.exception.manage` | إذن/مأمورية/تعويض |
| `attendance.export` | تصدير |

### 4.5 الإجازات (leave)

| الصلاحية | الوصف |
|---|---|
| `leave.request` | تقديم طلبات |
| `leave.approve` | موافقة (حسب السلسلة والنطاق) |
| `leave.balance.view/adjust` | أرصدة وتعديلها |
| `leave.type.manage` | أنواع الإجازات والعطل |

### 4.6 الرواتب (payroll)

| الصلاحية | الوصف |
|---|---|
| `payroll.view` | رؤية الرواتب (ضمن النطاق) |
| `payroll.run.generate` | توليد الدورة |
| `payroll.run.review` | مراجعة الكشف |
| `payroll.run.approve` | اعتماد وتجميد |
| `payroll.payslip.view` | قسائم الموظفين |
| `payroll.element.manage` | عناصر الأجر |
| `payroll.eos.manage` | نهاية الخدمة |
| `payroll.bank.export` | تصدير بنك |

### 4.7 التدريب والتقييم (training/perf)

| الصلاحية | الوصف |
|---|---|
| `training.manage` / `training.enroll` | إدارة/تسجيل الدورات |
| `perf.manage` / `perf.review` / `perf.self` | دورات التقييم وتقييم/تقييم ذاتي |
| `perf.pip.manage` | خطط تحسين الأداء |

### 4.8 الأجهزة والذكاء الاصطناعي (devices/ai)

| الصلاحية | الوصف |
|---|---|
| `device.manage` | إدارة قارئات QR |
| `ai.assistant.use` | استخدام المساعد الذكي |
| `ai.analytics.view` | رؤية نتائج التحليلات والتنبؤات |
| `ai.reports.generate` | توليد تقارير ذكية |

---

## 5. مصفوفة الصلاحيات الافتراضية (Matrix)

| الصلاحية | Admin | HR Manager | Supervisor | Accountant | Employee |
|---|:--:|:--:|:--:|:--:|:--:|
| dashboard.view | ✔ | ✔ | ✔ | ✔ | ✔ |
| search.global | ✔ | ✔ | ✔ | ✔ | ✔ (نطاقه) |
| employee.view | ✔ | ✔ | ✔ (فريقه) | ✔ (بلا راتب) | ✔ (نفسه) |
| employee.create/edit | ✔ | ✔ | ✘ | ✘ | ✘ |
| employee.terminate | ✔ | ✔ | ✘ | ✘ | ✘ |
| employee.import/export | ✔ | ✔ | ✘ | ✘ | ✘ |
| employee.contract.manage | ✔ | ✔ | ✘ | ✘ | ✘ |
| employee.document.manage | ✔ | ✔ | ✘ | ✘ | ✘ |
| employee.qr.manage | ✔ | ✔ | ✘ | ✘ | ✘ |
| employee.salary.view | ✔ | ✔ | ✘ | ✔ | ✘ |
| employee.bankdata.view | ✔ | ✘ | ✘ | ✘ | ✘ |
| attendance.view | ✔ | ✔ | ✔ (فريقه) | ✘ | ✘ |
| attendance.scan | ✔ | ✔ | ✔ | ✘ | ✔ |
| attendance.correct | ✔ | ✔ | ✔ (فريقه) | ✘ | ✘ |
| attendance.exception.manage | ✔ | ✔ | ✔ (فريقه) | ✘ | ✘ |
| leave.request | ✔ | ✔ | ✔ | ✘ | ✔ |
| leave.approve | ✔ | ✔ | ✔ (فريقه) | ✘ | ✘ |
| leave.balance.adjust | ✔ | ✔ | ✘ | ✘ | ✘ |
| payroll.view | ✔ | ✔ | ✘ | ✔ | ✘ |
| payroll.run.generate/review | ✔ | ✘ | ✘ | ✔ | ✘ |
| payroll.run.approve | ✔ | ✔ | ✘ | ✘ | ✘ |
| payroll.payslip.view | ✔ | ✔ | ✘ | ✔ | ✔ (نفسه) |
| payroll.element.manage | ✔ | ✘ | ✘ | ✘ | ✘ |
| training.manage | ✔ | ✔ | ✘ | ✘ | ✘ |
| perf.manage | ✔ | ✔ | ✔ (فريقه) | ✘ | ✘ |
| perf.self | ✔ | ✔ | ✔ | ✘ | ✔ |
| device.manage | ✔ | ✘ | ✘ | ✘ | ✘ |
| ai.assistant.use | ✔ | ✔ | ✔ (فريقه) | ✔ (رواتب) | ✘ |
| reports.export | ✔ | ✔ | ✔ (فريقه) | ✔ (مالية) | ✘ |
| settings.edit | ✔ | ✘ | ✘ | ✘ | ✘ |
| system.audit.view | ✔ | ✘ | ✘ | ✘ | ✘ |
| system.backup.manage | ✔ | ✘ | ✘ | ✘ | ✘ |

> هذه **افتراضية قابلة للتعديل** من الواجهة لأي دور (بما فيها القياسية).

---

## 6. الصلاحيات المخصصة (Custom Roles)

| الخطوة | التفصيل |
|---|---|
| إنشاء دور | من `الإعدادات ← الأدوار`: اسم (متعدد اللغات)، وصف، قائمة صلاحيات منتقاة. |
| الميراث (اختياري) | `role.parent` — يرث الدور الفرعي صلاحيات الأب (مثال: `Dept Assistant` يرث `employee`). |
| تعيين مستخدم | `الإعدادات ← المستخدمون ← الدور` مع `branch_scope` (اختياري). |
| تواريخ السريان | `effective_from/to` لدور مؤقت (مثال: ممثل عن المشرف أثناء غيابه). |
| تحقق | جدول صلاحيات الدور الفرعي = (ميراث الأب) ∪ (خاصته) — تُحسب لحظيًا دون تكرار. |

### مثال عملي

```
دور مخصص: "مراقب مطابقة Payroll"
صلاحياته: payroll.view + payroll.run.review + reports.export
نطاقه: فرع "الجزائر" فقط
→ يمكنه مراجعة الكشوف والتصدير، لكن لا يعتمد ولا يعدّل عناصر الأجر.
```

---

## 7. نطاقات الصلاحية (Data Scopes)

| النطاق | المعنى | مثال |
|---|---|---|
| **GLOBAL** | كل البيانات | Admin, HR Manager |
| **BRANCH** | فرع محدد (+ فروعه؟ حسب السياسة) | مدير فرع |
| **DEPARTMENT** | قسم محدد | رئيس قسم عبر فرع |
| **TEAM** | من يرأسهم مباشرة/غير مباشرة | Supervisor |
| **SELF** | بيانات المستخدم نفسه | Employee |
| **NONE** | لا شيء | |

### تنفيذ النطاق

- كل استعلام (QuerySet) يُحدد نطاقه من `Membership` الخاص بالمستخدم الحالي.
- القرار يُتخذ في **طبقة الخدمات (Service Layer)** وليس في الواجهة — لا مجال لتجاوز العرض.
- عند توليد أي تقرير: النطاق يُقيّد المصدر قبل التجميع.

---

## 8. تنفيذ التحقق في الكود (Enforcement)

### 8.1 المستويات الثلاثة

| المستوى | المكان | الوصف |
|---|---|---|
| 1. المصادقة | Middleware | التحقق من الجلسة/الحساب النشط لكل طلب |
| 2. التفويض | Decorators/Permission Classes | تحقق `Permission` قبل تنفيذ الوظيفة |
| 3. النطاق | Service Layer | فلترة الكويري حسب Scope المستخدم |

### 8.2 قواعد التنفيذ

1. **لا تثق بالواجهة أبدًا**: الأزرار تُخفى لتحسين UX، لكن التحقق الإجباري في الخادم.
2. **Permission Chaining**: `user.effective_permissions()` تجمع (دور → ميراث → استثناء مباشر) وتحسب Deny أولًا.
3. **Audit**: أي عملية كتابة تسجل في `audit_auditlog` (المستخدم، IP، قبل/بعد).
4. **API للأجهزة**: تستخدم مفاتيح أجهزة لا جلسات مستخدمين، وصلاحياتها محصورة بـ `attendance.scan`.
5. **التقارير والذكاء الاصطناعي**: تلتزمان بنفس نطاق الصلاحيات (لا وسيلة للالتفاف عبر تقرير أو أمر AI).

---

## 9. سيناريوهات وحالات خاصة

| الحالة | السلوك |
|---|---|
| مشرف غادرت فريقه | تنتقل العضويات لمنصب فوقه تلقائيًا (إعادة توجيه) |
| موظف فُصل | يُعطَّل حسابه فورًا، تُلغى جلساته، وتُلغى صلاحياته |
| صلاحية أُزيلت من دور | جلسات المستخدمين تفقدها فورًا (تحقق لحظي من DB) |
| مستخدم بدورين | صلاحياته = اتحاد الأدوار (Union) مع احترام Deny المباشر |
| استثناء مباشر | `auth_user_permission` بـ `grant`/`deny` يتجاوز الدور |
| نطاق فرع متعدد | `branch_scope` يقبل عدة فروع (جدول `role_branch_scopes`) |
| التقارير المجدولة | تُنفَّذ بهوية منشئها للحفاظ على النطاق |

---

## 10. مخرجات التطوير (Tasks)

| # | المهمة |
|---|---|
| T-RBAC-1 | نماذج Permission/Role/RoleMember + هجرات + Admin |
| T-RBAC-2 | Seed الأدوار والصلاحيات الافتراضية |
| T-RBAC-3 | خدمة `effective_permissions()` مع الميراث والاستثناءات |
| T-RBAC-4 | Decorators/PermissionClasses لكل وحدات الواجهة |
| T-RBAC-5 | نظام Scope على كل الكويريات الحرجة (employees, attendance, leave, payroll) |
| T-RBAC-6 | واجهة إدارة الأدوار المخصصة والاستثناءات |
| T-RBAC-7 | اختبارات: قفل النطاق، استثناءات، ميراث، إلغاء فوري |

---

## 11. تحذيرات وقرارات تصميمية (Alert Box)

1. **⚠️ لا تُخفِ التحقق في الواجهة فقط**: الفلاتر وعناصر الواجهة ليست أمانًا — الخادم وحده مصدر الحقيقة.
2. **⚠️ نطاق البيانات أثقل من الصلاحية**: 90% من الأخطاء الأمنية في أنظمة HR تأتي من نطاق خاطئ (رأى مدير فرع موظفي فرع آخر) لا من صلاحية مفقودة.
3. **⚠️ Deny يتفوق على Grant**: تأكد من أولوية القرار في `effective_permissions()`.
4. **⚠️ الأدوار القياسية قابلة للتعديل**: قد يطلب العميل تقييد HR Manager — لا تُبنِ صلاحيات مدمجة في الكود.
5. **⚠️ الفصل الوظيفي (SoD)**: لا تجعل نفس الشخص يولّد ويعتمد كشف الراتب — مبدأ المحاسبة (وإن وُجدت استثناءات عملية فوثّقها).
