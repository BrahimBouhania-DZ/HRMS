#!/usr/bin/env bash
# =============================================================
# HRMS — تجهيز حزمة واحدة للنشر على خادم LAN
#   bash scripts/package.sh [الإصدار]
# الناتج:  releases/hrms-v<الإصدار>.tar.gz  (مجلد واحد جاهز للنقل)
#
# تشغيل على الخادم:
#   tar xzf hrms-v<الإصدار>.tar.gz
#   cd hrms  &&  python3 -m venv .venv  &&  .venv/bin/pip install -r requirements.txt
#   cp .env.example .env  وعدّل القيم  ثم: .venv/bin/python manage.py seed_all
#   .venv/bin/python manage.py deploy_prepare
#   راجع docs/14-deployment.md §2–§5
# =============================================================
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP_DIR"

VERSION="${1:-$(date +%Y%m%d)}"
OUT_DIR="$APP_DIR/releases"
mkdir -p "$OUT_DIR"
STAGE="$OUT_DIR/hrms"
PKG="$OUT_DIR/hrms-v${VERSION}.tar.gz"

echo "→ تجهيز الحزمة الإصدار $VERSION"

# مجلد مؤقت نظيف
rm -rf "$STAGE"
mkdir -p "$STAGE"

# نسخ المصدر (استثناء كل ما هو بيئي/كبير)
rsync -a --exclude-from=- ./ "$STAGE/" <<'EXCLUDES'
.git
.venv
__pycache__
*.pyc
db.sqlite3
backups/
media/
staticfiles/
releases/
.env
*.log
EXCLUDES

# تجميع الحزمة
tar -czf "$PKG" -C "$OUT_DIR" hrms
rm -rf "$STAGE"

echo "✔ الحزمة جاهزة: $PKG"
echo "  الحجم: $(du -h "$PKG" | cut -f1)"
echo "  ملفات الحزمة:"
tar -tzf "$PKG" | sed 's/^/    /' | head -40
echo "  (والمزيد...)"
