"""كتالوج الصلاحيات ومصفوفة الأدوار القياسية — مصدر الحقيقة للـ Seed.

المرجع: docs/05-rbac.md §4 (Permission Catalog) و §5 (Matrix).
صيغة الصلاحية: module.object.action (view/create/edit/delete/approve/...).
"""

PERMISSION_CATALOG = [
    # ---- عام (core) ----
    {"code": "dashboard.view", "module": "core", "name_ar": "لوحة التحكم"},
    {"code": "search.global", "module": "core", "name_ar": "البحث الموحّد"},
    {"code": "notifications.view", "module": "core", "name_ar": "عرض الإشعارات"},
    {"code": "notifications.manage", "module": "core", "name_ar": "إدارة الإشعارات"},
    {"code": "reports.view", "module": "core", "name_ar": "التقارير"},
    {"code": "reports.generate", "module": "core", "name_ar": "توليد التقارير"},
    {"code": "reports.export", "module": "core", "name_ar": "تصدير التقارير"},
    {"code": "settings.view", "module": "core", "name_ar": "عرض الإعدادات"},
    {"code": "settings.edit", "module": "core", "name_ar": "تعديل الإعدادات"},
    {"code": "system.audit.view", "module": "core", "name_ar": "سجل التدقيق"},
    {"code": "system.backup.manage", "module": "core", "name_ar": "النسخ الاحتياطي والاستعادة"},

    # ---- الهيكل التنظيمي (org) ----
    {"code": "org.branch.view", "module": "org", "name_ar": "عرض الفروع"},
    {"code": "org.branch.create", "module": "org", "name_ar": "إضافة فرع"},
    {"code": "org.branch.edit", "module": "org", "name_ar": "تعديل فرع"},
    {"code": "org.branch.disable", "module": "org", "name_ar": "تعطيل فرع"},
    {"code": "org.department.view", "module": "org", "name_ar": "عرض الأقسام"},
    {"code": "org.department.create", "module": "org", "name_ar": "إضافة قسم"},
    {"code": "org.department.edit", "module": "org", "name_ar": "تعديل قسم"},
    {"code": "org.department.disable", "module": "org", "name_ar": "تعطيل قسم"},
    {"code": "org.position.view", "module": "org", "name_ar": "عرض المناصب"},
    {"code": "org.position.create", "module": "org", "name_ar": "إضافة منصب"},
    {"code": "org.position.edit", "module": "org", "name_ar": "تعديل منصب"},
    {"code": "org.shift.view", "module": "org", "name_ar": "عرض جداول الدوام"},
    {"code": "org.shift.create", "module": "org", "name_ar": "إضافة جدول دوام"},
    {"code": "org.shift.edit", "module": "org", "name_ar": "تعديل جدول دوام"},

    # ---- الموظفون (employees) ----
    {"code": "employee.view", "module": "employees", "name_ar": "عرض بيانات الموظفين"},
    {"code": "employee.create", "module": "employees", "name_ar": "إضافة موظف"},
    {"code": "employee.edit", "module": "employees", "name_ar": "تعديل بيانات موظف"},
    {"code": "employee.terminate", "module": "employees", "name_ar": "إنهاء خدمة"},
    {"code": "employee.import", "module": "employees", "name_ar": "استيراد جماعي"},
    {"code": "employee.export", "module": "employees", "name_ar": "تصدير جماعي"},
    {"code": "employee.contract.view", "module": "employees", "name_ar": "عرض العقود"},
    {"code": "employee.contract.manage", "module": "employees", "name_ar": "إدارة العقود"},
    {"code": "employee.document.view", "module": "employees", "name_ar": "عرض الوثائق"},
    {"code": "employee.document.manage", "module": "employees", "name_ar": "إدارة الوثائق"},
    {"code": "employee.qr.manage", "module": "employees", "name_ar": "إصدار/إدارة QR"},
    {"code": "employee.salary.view", "module": "employees", "name_ar": "بيانات الراتب (حساسة)"},
    {"code": "employee.bankdata.view", "module": "employees", "name_ar": "البيانات البنكية (حساسة جدًا)"},

    # ---- الحضور (attendance) ----
    {"code": "attendance.view", "module": "attendance", "name_ar": "عرض الحضور"},
    {"code": "attendance.scan", "module": "attendance", "name_ar": "مسح QR للدخول/الخروج"},
    {"code": "attendance.manual.record", "module": "attendance", "name_ar": "تسجيل يدوي"},
    {"code": "attendance.correct", "module": "attendance", "name_ar": "تصحيح حضور"},
    {"code": "attendance.exception.manage", "module": "attendance", "name_ar": "إدارة الاستثناءات"},
    {"code": "attendance.export", "module": "attendance", "name_ar": "تصدير الحضور"},

    # ---- الإجازات (leave) ----
    {"code": "leave.request", "module": "leave", "name_ar": "تقديم طلبات إجازة"},
    {"code": "leave.approve", "module": "leave", "name_ar": "الموافقة على الإجازات"},
    {"code": "leave.balance.view", "module": "leave", "name_ar": "عرض الأرصدة"},
    {"code": "leave.balance.adjust", "module": "leave", "name_ar": "تعديل الأرصدة"},
    {"code": "leave.type.manage", "module": "leave", "name_ar": "إدارة أنواع الإجازات"},

    # ---- الرواتب (payroll) ----
    {"code": "payroll.view", "module": "payroll", "name_ar": "عرض الرواتب"},
    {"code": "payroll.run.generate", "module": "payroll", "name_ar": "توليد الدورة"},
    {"code": "payroll.run.review", "module": "payroll", "name_ar": "مراجعة الكشف"},
    {"code": "payroll.run.approve", "module": "payroll", "name_ar": "اعتماد وتجميد"},
    {"code": "payroll.payslip.view", "module": "payroll", "name_ar": "قسائم الموظفين"},
    {"code": "payroll.element.manage", "module": "payroll", "name_ar": "عناصر الأجر"},
    {"code": "payroll.eos.manage", "module": "payroll", "name_ar": "نهاية الخدمة"},
    {"code": "payroll.bank.export", "module": "payroll", "name_ar": "تصدير بنك"},

    # ---- التدريب والتقييم (training/perf) ----
    {"code": "training.manage", "module": "training", "name_ar": "إدارة الدورات"},
    {"code": "training.enroll", "module": "training", "name_ar": "التسجيل في الدورات"},
    {"code": "perf.manage", "module": "perf", "name_ar": "إدارة التقييم"},
    {"code": "perf.review", "module": "perf", "name_ar": "تقييم الموظفين"},
    {"code": "perf.self", "module": "perf", "name_ar": "تقييم ذاتي"},
    {"code": "perf.pip.manage", "module": "perf", "name_ar": "خطط تحسين الأداء"},

    # ---- التوظيف (recruitment) ----
    {"code": "recruitment.posting.view", "module": "recruitment", "name_ar": "عرض إعلانات الوظائف"},
    {"code": "recruitment.posting.create", "module": "recruitment", "name_ar": "إنشاء إعلان وظيفة"},
    {"code": "recruitment.posting.edit", "module": "recruitment", "name_ar": "تعديل/نشر/إغلاق إعلان"},
    {"code": "recruitment.candidate.view", "module": "recruitment", "name_ar": "عرض المرشحين"},
    {"code": "recruitment.candidate.manage", "module": "recruitment", "name_ar": "إدارة المرشحين والمقابلات والتوظيف"},

    # ---- الأجهزة والذكاء الاصطناعي (devices/ai) ----
    {"code": "device.manage", "module": "devices", "name_ar": "إدارة قارئات QR"},
    {"code": "ai.assistant.use", "module": "ai", "name_ar": "استخدام المساعد الذكي"},
    {"code": "ai.analytics.view", "module": "ai", "name_ar": "نتائج التحليلات"},
    {"code": "ai.reports.generate", "module": "ai", "name_ar": "توليد تقارير ذكية"},
]

ROLE_DEFINITIONS = [
    {
        "code": "admin",
        "name_ar": "مدير النظام",
        "name_fr": "Administrateur",
        "name_en": "Admin",
        "description": "كل الصلاحيات بما فيها إدارة المستخدمين والإعدادات والنسخ الاحتياطي.",
        "permissions": "*",
    },
    {
        "code": "hr_manager",
        "name_ar": "مدير الموارد البشرية",
        "name_fr": "DRH",
        "name_en": "HR Manager",
        "description": "كامل عمليات الموارد البشرية (لا صلاحيات تقنية).",
        "permissions": [
            "dashboard.view", "search.global", "notifications.view", "notifications.manage",
            "reports.view", "reports.generate", "reports.export",
            "org.branch.view", "org.department.view", "org.position.view", "org.shift.view",
            "employee.view", "employee.create", "employee.edit", "employee.terminate",
            "employee.import", "employee.export",
            "employee.contract.view", "employee.contract.manage",
            "employee.document.view", "employee.document.manage",
            "employee.qr.manage", "employee.salary.view",
            "attendance.view", "attendance.scan", "attendance.manual.record",
            "attendance.correct", "attendance.exception.manage", "attendance.export",
            "leave.request", "leave.approve", "leave.balance.view", "leave.balance.adjust",
            "leave.type.manage",
            "payroll.view", "payroll.run.approve", "payroll.payslip.view",
            "training.manage", "training.enroll", "perf.manage", "perf.review", "perf.self",
            "recruitment.posting.view", "recruitment.posting.create", "recruitment.posting.edit",
            "recruitment.candidate.view", "recruitment.candidate.manage",
            "ai.assistant.use", "ai.analytics.view", "ai.reports.generate",
        ],
    },
    {
        "code": "supervisor",
        "name_ar": "مشرف",
        "name_fr": "Superviseur",
        "name_en": "Supervisor",
        "description": "إدارة فريقه فقط: حضور، إجازات، تقييم.",
        "permissions": [
            "dashboard.view", "search.global", "notifications.view",
            "reports.view", "reports.export",
            "employee.view", "attendance.view", "attendance.scan",
            "attendance.correct", "attendance.exception.manage",
            "leave.request", "leave.approve", "leave.balance.view",
            "perf.manage", "perf.review", "perf.self",
            "ai.assistant.use",
        ],
    },
    {
        "code": "accountant",
        "name_ar": "محاسب",
        "name_fr": "Comptable",
        "name_en": "Accountant",
        "description": "الرواتب والمكافآت (لا تعديل بيانات موظفين).",
        "permissions": [
            "dashboard.view", "search.global", "notifications.view",
            "reports.view", "reports.generate", "reports.export",
            "employee.view", "employee.salary.view",
            "payroll.view", "payroll.run.generate", "payroll.run.review",
            "payroll.payslip.view", "payroll.bank.export",
            "ai.assistant.use",
        ],
    },
    {
        "code": "employee",
        "name_ar": "موظف",
        "name_fr": "Employé",
        "name_en": "Employee",
        "description": "ملفه وطلباته وقسمه وحضوره.",
        "permissions": [
            "dashboard.view", "search.global", "notifications.view",
            "employee.view",
            "attendance.view", "attendance.scan",
            "leave.request", "leave.balance.view",
            "perf.self",
            "payroll.payslip.view",
        ],
    },
]

ROLE_NAMES = {
    "admin": ("مدير النظام", "Administrateur", "Admin"),
    "hr_manager": ("مدير الموارد البشرية", "DRH", "HR Manager"),
    "supervisor": ("مشرف", "Superviseur", "Supervisor"),
    "accountant": ("محاسب", "Comptable", "Accountant"),
    "employee": ("موظف", "Employé", "Employee"),
}
