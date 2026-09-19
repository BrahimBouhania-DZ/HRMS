#!/usr/bin/env bash
# ماسح نشط مخصص لـ HRMS — المرحلة 5 (OWASP) — يعمل ضد خادم حي
set -e
cd "$(dirname "$0")/.."
export DJANGO_SETTINGS_MODULE=config.settings.dev
nohup .venv/bin/python manage.py runserver 127.0.0.1:8001 >/tmp/hrms_audit_server.log 2>&1 &
echo $! > /tmp/hrms_audit.pid
for i in $(seq 1 20); do curl -s -o /dev/null http://127.0.0.1:8001/ && break; sleep 0.5; done
.venv/bin/python scripts/active_scan.py "$@"
kill "$(cat /tmp/hrms_audit.pid)" 2>/dev/null || true
