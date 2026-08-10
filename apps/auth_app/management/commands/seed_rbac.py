"""أمر تهيئة RBAC: إنشاء كتالوج الصلاحيات والأدوار القياسية (T-RBAC-2).

الاستخدام:
    python manage.py seed_rbac                 # إنشاء مفقود فقط (idempotent)
    python manage.py seed_rbac --force         # إعادة مزامنة قائمة صلاحيات الأدوار

المرجع: docs/05-rbac.md §4/§5.
"""

from django.core.management.base import BaseCommand

from apps.auth_app.rbac_catalog import PERMISSION_CATALOG, ROLE_DEFINITIONS
from apps.auth_app.models import Permission, Role, RolePermission


class Command(BaseCommand):
    help = "تهيئة الأدوار القياسية الخمسة وكتالوج الصلاحيات (T-RBAC-2)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="إعادة مزامنة صلاحيات الأدوار القياسية (لا تُحذف استثناءات مخصصة)",
        )

    def handle(self, *args, **options):
        # 1) كتالوج الصلاحيات
        created = 0
        for item in PERMISSION_CATALOG:
            _, was_created = Permission.objects.get_or_create(
                code=item["code"],
                defaults={
                    "module": item["module"],
                    "name_ar": item["name_ar"],
                    "name_fr": item.get("name_fr", ""),
                    "name_en": item.get("name_en", ""),
                },
            )
            created += int(was_created)
        self.stdout.write(self.style.SUCCESS(f"الصلاحيات: {len(PERMISSION_CATALOG)} (جديد: {created})"))

        # 2) الأدوار القياسية
        for role_def in ROLE_DEFINITIONS:
            role, was_created = Role.objects.get_or_create(
                code=role_def["code"],
                defaults={
                    "name_ar": role_def["name_ar"],
                    "name_fr": role_def["name_fr"],
                    "name_en": role_def["name_en"],
                    "description": role_def["description"],
                    "is_system": True,
                },
            )
            if not was_created:
                # تحديث الأسماء/الوصف حتى مع التعديل اليدوي
                for field in ("name_ar", "name_fr", "name_en", "description"):
                    setattr(role, field, role_def[field])
                role.save(update_fields=["name_ar", "name_fr", "name_en", "description"])
            self._sync_role_permissions(role, role_def["permissions"], force=options["force"])
        self.stdout.write(self.style.SUCCESS("الأدوار القياسية الخمسة جاهزة"))

    def _sync_role_permissions(self, role, permission_spec, force=False):
        """مزامنة صلاحيات الدور. '*' تعني كل الكتالوج."""
        catalog = Permission.objects.all()
        if permission_spec != "*":
            catalog = catalog.filter(code__in=permission_spec)

        desired = set(catalog.values_list("code", flat=True))
        if not force and role.code in ("admin",):
            pass  # admin يبقى '*'

        current = set(role.permission_links.values_list("permission__code", flat=True))
        missing = desired - current
        extra = current - desired if force else set()

        RolePermission.objects.bulk_create(
            [RolePermission(role=role, permission=Permission.objects.get(code=code)) for code in missing],
            ignore_conflicts=True,
        )
        if extra:
            RolePermission.objects.filter(
                role=role, permission__code__in=extra
            ).delete()
            self.stdout.write(
                f"  {role.code}: +{len(missing)}/{len(desired)} صلاحيات"
                + (f" -{len(extra)}" if extra else "")
            )
