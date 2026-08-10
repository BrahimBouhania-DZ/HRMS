#!/usr/bin/env bash
# =============================================================
# HRMS — نسخ احتياطي لقاعدة البيانات
#   bash scripts/backup.sh            → نسخة SQLite/Postgres
#   bash scripts/backup.sh restore FILE  → استعادة من نسخة
# الوجهة الافتراضية: backups/ (تنشأ تلقائيًا)
# الاحتفاظ: آخر 14 نسخة (تلقائي)
# =============================================================
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP_DIR"
OUT_DIR="${BACKUP_DIR:-$APP_DIR/backups}"
mkdir -p "$OUT_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"

# تحديد نوع قاعدة البيانات من الإعدادات (بدون تشغيل الخادم)
DB_ENGINE="${DJANGO_DB_ENGINE:-sqlite}"
if [ -n "${DJANGO_SETTINGS_MODULE:-}" ] && [ "${DJANGO_SETTINGS_MODULE}" = "config.settings.prod" ]; then
    DB_ENGINE="postgres"
fi

do_backup() {
    if [ "$DB_ENGINE" = "postgres" ]; then
        # Postgres — يتطلب متغيرات DJANGO_DB_NAME/USER/PASSWORD/... في البيئة
        DB_HOST="${DJANGO_DB_HOST:-127.0.0.1}"
        DB_PORT="${DJANGO_DB_PORT:-5432}"
        : "${DJANGO_DB_NAME:?اضبط DJANGO_DB_NAME}"; : "${DJANGO_DB_USER:?اضبط DJANGO_DB_USER}"
        FILE="$OUT_DIR/hrms_${STAMP}.sql.gz"
        PGPASSWORD="${DJANGO_DB_PASSWORD:-}" pg_dump -h "$DB_HOST" -p "$DB_PORT" \
            -U "$DJANGO_DB_USER" -d "$DJANGO_DB_NAME" | gzip -9 > "$FILE"
    else
        FILE="$OUT_DIR/hrms_${STAMP}.sqlite3"
        python3 scripts/sqlite_backup.py backup db.sqlite3 "$FILE"
    fi
    echo "✔ نسخة احتياطية: $FILE"
    # تنظيف قديم
    ls -1t "$OUT_DIR"/hrms_* 2>/dev/null | tail -n +15 | xargs -r rm -f
}

do_restore() {
    [ $# -eq 1 ] || { echo "الاستعمال: bash scripts/backup.sh restore <الملف>"; exit 1; }
    [ -f "$1" ] || { echo "الملف غير موجود: $1"; exit 1; }
    if [ "$DB_ENGINE" = "postgres" ]; then
        : "${DJANGO_DB_NAME:?اضبط DJANGO_DB_NAME}"; : "${DJANGO_DB_USER:?اضبط DJANGO_DB_USER}"
        PGPASSWORD="${DJANGO_DB_PASSWORD:-}" gunzip -c "$1" | \
            PGPASSWORD="${DJANGO_DB_PASSWORD:-}" psql -h "${DJANGO_DB_HOST:-127.0.0.1}" \
            -U "$DJANGO_DB_USER" -d "$DJANGO_DB_NAME"
    else
        case "$1" in
            *.sqlite3) python3 scripts/sqlite_backup.py restore "$1" db.sqlite3 ;;
            *.sql) python3 -c "
import sqlite3,sys
con=sqlite3.connect('db.sqlite3')
con.executescript(open(sys.argv[1],encoding='utf-8').read())
con.commit(); con.close()" "$1" ;;
            *) echo "صيغة غير معروفة: $1"; exit 1 ;;
        esac
    fi
    echo "✔ تمت الاستعادة من $1"
}

case "${1:-}" in
    restore) do_restore "${2:-}" ;;
    "") do_backup ;;
    *) echo "أمر غير معروف: $1"; exit 1 ;;
esac
