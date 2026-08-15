"""اختبارات وحدة التوظيف (v4).

يغطي: إغلاق إعلان محقق الشواغر تلقائيًا، فحص شرط القبول قبل التوظيف،
تعطيل التوظيف لإعلان غير مفعّل، وقيود الصلاحيات عبر العروض.
"""

import datetime
import io

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from apps.auth_app.models import Permission, Role, RoleMember
from apps.employees.models import Employee
from apps.org.models import Branch, Department
from apps.recruitment import imports
from apps.recruitment.models import Candidate, Interview, JobPosting
from apps.recruitment.services import (
    RecruitmentError,
    close_posting,
    hire_candidate,
    publish_posting,
    schedule_interview,
    set_candidate_status,
)

User = get_user_model()


_SEQ = 0


def _posting(**kw):
    global _SEQ
    _SEQ += 1
    defaults = {
        "code": f"JOB-{_SEQ:02d}",
        "title_ar": "مطور برمجيات",
        "employment_type": JobPosting.EmploymentType.FULL_TIME,
        "status": JobPosting.Status.DRAFT,
        "openings_count": 2,
    }
    defaults.update(kw)
    return JobPosting.objects.create(**defaults)


def _candidate(posting=None, **kw):
    defaults = {
        "posting": posting or _posting(status=JobPosting.Status.PUBLISHED),
        "first_name_ar": "مرشح",
        "last_name_ar": "توظيف",
        "email": "candidate@example.com",
        "status": Candidate.Status.NEW,
    }
    defaults.update(kw)
    return Candidate.objects.create(**defaults)


def _user_with_role(username, *permission_codes, role_code="hr_manager"):
    role = Role.objects.create(code=role_code, name_ar=role_code, is_system=True)
    for code in permission_codes:
        role.permission_links.create(
            permission=Permission.objects.get_or_create(code=code, defaults={"module": "recruitment", "name_ar": code})[0]
        )
    user = User.objects.create_user(username=username, password="pass")
    RoleMember.objects.create(user=user, role=role)
    return user


class RecruitmentServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="mgr", password="pass")
        self.posting = _posting(status=JobPosting.Status.PUBLISHED)
        self.branch = Branch.objects.create(code="BR-1", name_ar="المركز الرئيسي")
        self.department = Department.objects.create(code="DP-1", name_ar="تكنولوجيا المعلومات", branch=self.branch)

    def test_publish_sets_published(self):
        posting = _posting()
        publish_posting(posting, user=self.user)
        posting.refresh_from_db()
        self.assertEqual(posting.status, JobPosting.Status.PUBLISHED)

    def test_close_posting(self):
        close_posting(self.posting, user=self.user)
        self.posting.refresh_from_db()
        self.assertEqual(self.posting.status, JobPosting.Status.CLOSED)

    def test_hire_closes_posting_when_openings_filled(self):
        opening = _posting(status=JobPosting.Status.PUBLISHED, openings_count=1)
        candidate = _candidate(posting=opening, status=Candidate.Status.OFFER)
        hire_candidate(candidate, user=self.user)
        opening.refresh_from_db()
        self.assertEqual(opening.status, JobPosting.Status.CLOSED)
        self.assertEqual(candidate.hired_employee.employee_code, "EMP-0001")

    def test_hire_requires_offer_status(self):
        candidate = _candidate()
        with self.assertRaises(RecruitmentError):
            hire_candidate(candidate, user=self.user)

    def test_hire_requires_active_posting(self):
        posting = _posting(status=JobPosting.Status.CLOSED)
        candidate = _candidate(posting=posting, status=Candidate.Status.OFFER)
        with self.assertRaises(RecruitmentError):
            hire_candidate(candidate, user=self.user)

    def test_hire_increments_employee_counter(self):
        hire_candidate(_candidate(status=Candidate.Status.OFFER), user=self.user)
        hire_candidate(_candidate(email="c2@example.com", status=Candidate.Status.OFFER), user=self.user)
        second = Candidate.objects.get(email="c2@example.com")
        self.assertEqual(second.hired_employee.employee_code, "EMP-0002")

    def test_schedule_interview_moves_new_candidate_to_screening(self):
        candidate = _candidate()
        interview = schedule_interview(
            candidate,
            scheduled_at=datetime.datetime.now(),
            user=self.user,
        )
        self.assertEqual(interview.status, Interview.Status.SCHEDULED)
        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.Status.SCREENING)

    def test_hire_refuses_scheduled_candidate(self):
        candidate = _candidate()
        schedule_interview(candidate, scheduled_at=datetime.datetime.now(), user=self.user)
        with self.assertRaises(RecruitmentError):
            hire_candidate(candidate, user=self.user)

    def test_status_transition_validation(self):
        candidate = _candidate(status=Candidate.Status.HIRED)
        with self.assertRaises(RecruitmentError):
            set_candidate_status(candidate, Candidate.Status.NEW, user=self.user)


class RecruitmentViewTests(TestCase):
    def setUp(self):
        self.manager = _user_with_role("manager", "recruitment.posting.view", "recruitment.posting.edit", "recruitment.candidate.view", "recruitment.candidate.manage")
        self.posting = _posting(status=JobPosting.Status.PUBLISHED)
        self.candidate = _candidate(posting=self.posting)

    def test_posting_list_requires_permission(self):
        response = self.client.get(reverse("recruitment:posting_list"))
        self.assertEqual(response.status_code, 302)
        self.client.force_login(self.manager)
        response = self.client.get(reverse("recruitment:posting_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.posting.title_ar)

    def test_posting_publish_via_view(self):
        posting = _posting(code="JOB-P")
        self.client.force_login(self.manager)
        response = self.client.post(reverse("recruitment:posting_publish", args=[posting.pk]))
        self.assertRedirects(response, reverse("recruitment:posting_list"))
        posting.refresh_from_db()
        self.assertEqual(posting.status, JobPosting.Status.PUBLISHED)

    def test_candidate_list_requires_permission(self):
        self.client.force_login(self.manager)
        response = self.client.get(reverse("recruitment:candidate_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.candidate.full_name)

    def test_candidate_status_via_view(self):
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse("recruitment:candidate_status", args=[self.candidate.pk, Candidate.Status.SCREENING])
        )
        self.assertRedirects(response, reverse("recruitment:candidate_detail", args=[self.candidate.pk]))
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.status, Candidate.Status.SCREENING)

    def test_hire_via_view(self):
        self.candidate.status = Candidate.Status.OFFER
        self.candidate.save()
        self.client.force_login(self.manager)
        response = self.client.post(reverse("recruitment:candidate_hire", args=[self.candidate.pk]))
        self.assertRedirects(response, reverse("recruitment:candidate_detail", args=[self.candidate.pk]))
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.status, Candidate.Status.HIRED)
        self.assertIsNotNone(self.candidate.hired_employee)


class ImportTests(TestCase):
    """استيراد جماعي من CSV / XLSX (إعلانات ومرشحون)."""

    def setUp(self):
        self.user = User.objects.create_user(username="imp", password="pass")
        self.branch = Branch.objects.create(code="BR-1", name_ar="المركز الرئيسي")
        self.department = Department.objects.create(code="DP-1", name_ar="تكنولوجيا المعلومات", branch=self.branch)

    def _csv_file(self, content, name="import.csv"):
        return SimpleUploadedFile(name, content.encode("utf-8-sig"))

    def _xlsx_file(self, headers, rows, name="import.xlsx"):
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.append(headers)
        for row in rows:
            ws.append(row)
        buffer = io.BytesIO()
        wb.save(buffer)
        return SimpleUploadedFile(name, buffer.getvalue())

    def test_read_table_csv(self):
        file = self._csv_file("code,title_ar\nJOB-1,مطور\n")
        records = imports.read_table(file)
        self.assertEqual(records, [{"code": "JOB-1", "title_ar": "مطور"}])

    def test_read_table_xlsx(self):
        file = self._xlsx_file(["code", "title_ar"], [["JOB-1", "مطور"], ["JOB-2", "محلل"]])
        records = imports.read_table(file)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[1]["title_ar"], "محلل")

    def test_read_table_rejects_unknown_extension(self):
        file = SimpleUploadedFile("import.txt", b"data")
        with self.assertRaises(imports.ImportFileError):
            imports.read_table(file)

    def test_import_postings_skips_errors(self):
        records = [
            {"code": "JOB-100", "title_ar": "مطور", "employment_type": "full_time", "openings_count": "2"},
            {"code": "JOB-100", "title_ar": "مكرر"},
            {"code": "JOB-101", "title_ar": ""},
            {"code": "JOB-102", "title_ar": "محلل", "department_code": "DP-1"},
        ]
        created, errors = imports.import_postings(records, user=self.user)
        self.assertEqual(created, 2)
        self.assertEqual(len(errors), 2)
        posting = JobPosting.objects.get(code="JOB-102")
        self.assertEqual(posting.department, self.department)
        self.assertEqual(posting.openings_count, 1)

    def test_import_candidates_links_posting(self):
        posting = JobPosting.objects.create(code="JOB-200", title_ar="مطور", status=JobPosting.Status.PUBLISHED)
        records = [
            {
                "first_name_ar": "ليلى", "last_name_ar": "بن عمر", "email": "lila@example.com",
                "posting_code": "JOB-200", "status": "new",
            },
            {"first_name_ar": "أحمد", "last_name_ar": "سعيد", "email": "bad-email"},
            {"first_name_ar": "محمد", "last_name_ar": "علي", "email": "m@example.com", "posting_code": "NOPE"},
        ]
        created, errors = imports.import_candidates(records, user=self.user)
        self.assertEqual(created, 1)
        self.assertEqual(len(errors), 2)
        candidate = Candidate.objects.get(email="lila@example.com")
        self.assertEqual(candidate.posting, posting)

    def test_import_candidates_rejects_closed_posting(self):
        posting = JobPosting.objects.create(code="JOB-201", title_ar="مطور", status=JobPosting.Status.CLOSED)
        records = [
            {
                "first_name_ar": "سارة", "last_name_ar": "خالد", "email": "sara@example.com",
                "posting_code": "JOB-201",
            }
        ]
        created, errors = imports.import_candidates(records, user=self.user)
        self.assertEqual(created, 0)
        self.assertEqual(len(errors), 1)
        self.assertIn("مغلق", errors[0]["errors"][0])

    def test_import_posting_status_and_employment_validated(self):
        records = [
            {"code": "JOB-300", "title_ar": "مطور", "status": "weird", "employment_type": "odd"},
        ]
        created, errors = imports.import_postings(records, user=self.user)
        self.assertEqual(created, 0)
        self.assertEqual(len(errors[0]["errors"]), 2)

    def test_import_view_requires_posting_permission(self):
        posting = _posting(status=JobPosting.Status.PUBLISHED)
        user = _user_with_role("noperm")
        self.client.force_login(user)
        file = self._csv_file("code,title_ar\nJOB-X1,مطور\n")
        response = self.client.post(reverse("recruitment:import"), {"entity": "postings", "file": file})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(JobPosting.objects.filter(code="JOB-X1").exists())

    def test_import_view_imports_postings(self):
        user = _user_with_role("hr1", "recruitment.posting.create")
        self.client.force_login(user)
        file = self._csv_file("code,title_ar\nJOB-X2,مطور جديد\n")
        response = self.client.post(reverse("recruitment:import"), {"entity": "postings", "file": file})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "1")
        self.assertTrue(JobPosting.objects.filter(code="JOB-X2").exists())

    def test_import_template_download(self):
        user = _user_with_role("hr2", "recruitment.posting.create")
        self.client.force_login(user)
        response = self.client.get(reverse("recruitment:import_template", args=["postings"]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertContains(response, "title_ar")


class JsonSqlImportTests(TestCase):
    """استيراد من ملفات JSON و SQL (جداول متعددة)."""

    def setUp(self):
        self.user = User.objects.create_user(username="imp2", password="pass")

    def _file(self, name, content):
        return SimpleUploadedFile(name, content.encode("utf-8"))

    def test_read_json_array(self):
        file = self._file("data.json", '[{"code": "JOB-J1", "title_ar": "مطور"}]')
        records = imports.read_table(file)
        self.assertEqual(records, [{"code": "JOB-J1", "title_ar": "مطور"}])

    def test_read_json_records_key(self):
        file = self._file("data.json", '{"records": [{"code": "JOB-J2", "title_ar": "محلل"}]}')
        records = imports.read_table(file)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["title_ar"], "محلل")

    def test_read_json_invalid(self):
        file = self._file("data.json", "not-json")
        with self.assertRaises(imports.ImportFileError):
            imports.read_table(file)

    def test_import_postings_from_json(self):
        file = self._file("data.json", '[{"code": "JOB-J3", "title_ar": "مطور", "openings_count": 3}]')
        records = imports.read_table(file)
        created, errors = imports.import_postings(records, user=self.user)
        self.assertEqual(created, 1)
        self.assertEqual(JobPosting.objects.get(code="JOB-J3").openings_count, 3)

    def test_read_sql_tables_mixed(self):
        sql = (
            "INSERT INTO recruitment_jobposting (code, title_ar, openings_count) "
            "VALUES ('JOB-S1', 'مطور', 2);\n"
            "INSERT INTO recruitment_candidate (first_name_ar, last_name_ar, email, status) "
            "VALUES ('ليلى', 'بن عمر', 'lila@example.com', 'new');\n"
        )
        file = self._file("data.sql", sql)
        table_map = imports.read_sql_tables(file)
        self.assertEqual(len(table_map["postings"]), 1)
        self.assertEqual(len(table_map["candidates"]), 1)
        self.assertEqual(table_map["candidates"][0]["first_name_ar"], "ليلى")

    def test_sql_value_escaping_and_multi_rows(self):
        sql = (
            "INSERT INTO recruitment_jobposting (code, title_ar, description) VALUES "
            "('JOB-S2', 'مطور', 'خبير، جافا'), "
            "('JOB-S3', 'محلل', 'he said \"hi\"'), "
            "('JOB-S4', 'مختبر', 'It''s fine');"
        )
        file = self._file("data.sql", sql)
        table_map = imports.read_sql_tables(file)
        postings = table_map["postings"]
        self.assertEqual(len(postings), 3)
        self.assertEqual(postings[0]["description"], "خبير، جافا")
        self.assertEqual(postings[1]["description"], 'he said "hi"')
        self.assertEqual(postings[2]["description"], "It's fine")

    def test_import_sql_via_view_imports_both_tables(self):
        posting = JobPosting.objects.create(code="JOB-S9", title_ar="مطور", status=JobPosting.Status.PUBLISHED)
        user = _user_with_role("hr3", "recruitment.posting.create", "recruitment.candidate.manage")
        self.client.force_login(user)
        sql = (
            "INSERT INTO jobposting (code, title_ar, status) VALUES ('JOB-S10', 'محلل', 'published');\n"
            "INSERT INTO candidate (first_name_ar, last_name_ar, email, posting_code, status) "
            "VALUES ('سارة', 'خالد', 'sara@example.com', 'JOB-S9', 'new');\n"
        )
        file = self._file("data.sql", sql)
        response = self.client.post(reverse("recruitment:import"), {"entity": "", "file": file})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(JobPosting.objects.filter(code="JOB-S10").exists())
        candidate = Candidate.objects.get(email="sara@example.com")
        self.assertEqual(candidate.posting, posting)

    def test_template_download_json_and_sql(self):
        user = _user_with_role("hr4", "recruitment.posting.create")
        self.client.force_login(user)
        for fmt, content_type in (("json", "application/json"), ("sql", "text/sql")):
            response = self.client.get(reverse("recruitment:import_template", args=["postings"]) + f"?fmt={fmt}")
            self.assertEqual(response.status_code, 200)
            self.assertIn(content_type, response["Content-Type"])
        self.assertContains(
            self.client.get(reverse("recruitment:import_template", args=["postings"]) + "?fmt=sql"),
            "INSERT INTO recruitment_jobposting",
        )
