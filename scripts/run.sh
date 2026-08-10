#!/usr/bin/env bash
# =============================================================
# HRMS — أوامر التشغيل من الطرفية
# الاستعمال: bash scripts/run.sh <الأمر>
# =============================================================
set -e

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP_DIR"

SETTINGS="config.settings.dev"
HOST="127.0.0.1"
PORT="8000"

# إعدادات بيئة الإنتاج (اختياري — LAN):
# export DJANGO_SETTINGS_MODULE=config.settings.prod
# export DJANGO_ALLOWED_HOSTS=192.168.1.10,localhost
# export DJANGO_DB_NAME=hrms DJANGO_DB_USER=hrms DJANGO_DB_PASSWORD=...

ADMIN_USERNAME="${ADMIN_USERNAME:-admin}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-Adm1n@2026!}"

help() {
    cat <<'EOF'
الأوامر المتاحة:
  run            تشغيل خادم التطوير (استخدام فعلي للتطبيق)
  migrate        تطبيق هجرات قاعدة البيانات
  makemigrations إنشاء هجرات جديدة بعد تعديل النماذج
  seed           التهيئة الموحّدة (seed_all): RBAC + إجازات + مشرف افتراضي — إلزامي أول مرة
  createsuper    إنشاء مستخدم مشرف
  test           تشغيل الاختبارات (بيئة التطوير — SQLite)
  test-pg        تشغيل الاختبارات على PostgreSQL (config.settings.test)
  check          فحص سلامة المشروع
  shell          جلسة Django Shell
  restart        إعادة تشغيل الخادم (يوقف أي خادم قائم ثم يشغّله)
  stop           إيقاف الخادم القائم
  deploy_prepare جمع الملفات الثابتة + التحقق من إعدادات الإنتاج
  collectstatic  جمع الملفات الثابتة (لـ nginx/prod)
  backup         نسخة احتياطية من قاعدة البيانات (backups/)
  restore FILE   استعادة قاعدة البيانات من نسخة سابقة
  reset_db       حذف قاعدة البيانات والبدء من جديد (⚠️ يفقد كل البيانات)

أمثلة:
  bash scripts/run.sh run            # تشغيل الخادم
  bash scripts/run.sh migrate        # الهجرات
  bash scripts/run.sh seed           # التهيئة الموحّدة (RBAC + إجازات + مشرف)
  bash scripts/run.sh createsuper    # مشرف جديد
EOF
}

stop_server() {
    pkill -f "manage.py runserver" 2>/dev/null || true
    echo "✔ تم إيقاف الخادم (إن كان قائمًا)"
}

case "${1:-}" in
    run)
        stop_server
        exec python3 manage.py runserver "$HOST:$PORT" --settings="$SETTINGS"
        ;;
    restart)
        stop_server
        sleep 1
        exec python3 manage.py runserver "$HOST:$PORT" --settings="$SETTINGS"
        ;;
    stop)
        stop_server
        ;;
    migrate)
        python3 manage.py migrate --settings="$SETTINGS"
        ;;
    makemigrations)
        python3 manage.py makemigrations --settings="$SETTINGS"
        ;;
    seed)
        python3 manage.py seed_all --settings="$SETTINGS"
        ;;
    createsuper)
        if [ -n "$ADMIN_PASSWORD" ]; then
            DJANGO_SUPERUSER_PASSWORD="$ADMIN_PASSWORD" \
                python3 manage.py createsuperuser \
                --username "$ADMIN_USERNAME" \
                --email "${ADMIN_EMAIL:-admin@hrms.local}" \
                --noinput --settings="$SETTINGS" || true
        else
            python3 manage.py createsuperuser --settings="$SETTINGS"
        fi
        ;;
    test)
        python3 manage.py test --settings="$SETTINGS"
        ;;
    test-pg)
        python3 manage.py test --settings=config.settings.test
        ;;
    check)
        python3 manage.py check --settings="$SETTINGS"
        ;;
    shell)
        python3 manage.py shell --settings="$SETTINGS"
        ;;
    reset_db)
        echo "⚠️  سيتم حذف قاعدة البيانات (db.sqlite3)!"
        read -r -p "للتأكيد اكتب: reset  → " ans
        [ "$ans" = "reset" ] || { echo "أُلغي."; exit 1; }
        rm -f db.sqlite3
        python3 manage.py migrate --settings="$SETTINGS"
        python3 manage.py seed_all --settings="$SETTINGS"
        echo "✔ قاعدة بيانات جديدة + أدوار جاهزة"
        ;;
    collectstatic)
        python3 manage.py collectstatic --noinput --settings="$SETTINGS"
        ;;
    backup)
        bash scripts/backup.sh
        ;;
    restore)
        [ -n "$2" ] || { echo "الاستعمال: bash scripts/run.sh restore <الملف>"; exit 1; }
        bash scripts/backup.sh restore "$2"
        ;;
    deploy_prepare)
        python3 manage.py deploy_prepare --settings=config.settings.prod
        ;;
    help|-h|--help|"")
        help
        ;;
    *)
        echo "أمر غير معروف: $1"
        help
        exit 1
        ;;
esac
