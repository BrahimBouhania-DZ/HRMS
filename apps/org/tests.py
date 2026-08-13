"""اختبارات الهيكل التنظيمي (T-009..T-012).

يغطي: الفرع، القسم (شجرة + قيود فريدة + مدير)، المنصب، جدول الدوام.
"""

from django.db import IntegrityError
from django.test import TestCase

from apps.employees.models import Employee
from apps.org.models import Branch, Department, Position, Shift


class OrgModelTests(TestCase):
    def test_branch_unique_code(self):
        Branch.objects.create(code="BR-1", name_ar="فرع أ")
        with self.assertRaises(IntegrityError):
            Branch.objects.create(code="BR-1", name_ar="فرع ب")

    def test_department_tree_and_unique_per_branch(self):
        b1 = Branch.objects.create(code="BR-A", name_ar="فرع أ")
        b2 = Branch.objects.create(code="BR-B", name_ar="فرع ب")
        root = Department.objects.create(code="IT", name_ar="تقنية", branch=b1)
        child = Department.objects.create(code="DEV", name_ar="تطوير", branch=b1, parent=root)
        self.assertEqual(child.parent, root)
        self.assertEqual(list(root.children.all()), [child])
        # نفس الرمز مسموح في فرع آخر لكن غير مسموح في نفس الفرع
        Department.objects.create(code="IT", name_ar="تقنية ب", branch=b2)
        with self.assertRaises(IntegrityError):
            Department.objects.create(code="IT", name_ar="مكرر", branch=b1)

    def test_department_manager_link(self):
        branch = Branch.objects.create(code="BR-M", name_ar="فرع")
        manager = Employee.objects.create(
            employee_code="E-MGR", first_name_ar="م", last_name_ar="د", branch=branch
        )
        dept = Department.objects.create(
            code="HR", name_ar="موارد", branch=branch, manager=manager
        )
        dept.refresh_from_db()
        self.assertEqual(dept.manager, manager)

    def test_position_unique_code(self):
        branch = Branch.objects.create(code="BR-P", name_ar="فرع")
        dept = Department.objects.create(code="D", name_ar="قسم", branch=branch)
        Position.objects.create(code="POS-1", name_ar="مهندس", department=dept)
        with self.assertRaises(IntegrityError):
            Position.objects.create(code="POS-1", name_ar="مكرر", department=dept)

    def test_shift_defaults(self):
        shift = Shift.objects.create(
            code="SH-1", name_ar="صباحي",
            start_time="08:00", end_time="16:00",
        )
        self.assertFalse(shift.is_flexible)
        self.assertEqual(shift.grace_minutes, 10)

    def test_str_reprs(self):
        branch = Branch.objects.create(code="BR-S", name_ar="فرع")
        dept = Department.objects.create(code="D-S", name_ar="قسم", branch=branch)
        pos = Position.objects.create(code="P-S", name_ar="منصب", department=dept)
        shift = Shift.objects.create(code="SH-S", name_ar="دوام", start_time="08:00", end_time="16:00")
        self.assertEqual(str(branch), "فرع")
        self.assertEqual(str(dept), "قسم")
        self.assertEqual(str(pos), "منصب")
        self.assertEqual(str(shift), "دوام")
