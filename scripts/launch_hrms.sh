#!/usr/bin/env bash
# =============================================================
# HRMS — مشغّل التطبيق من أيقونة سطح المكتب
# يشغّل الخادم (إن لم يكن قائمًا) ويفتح المتصفح تلقائيًا
# =============================================================
set -e

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PY="$APP_DIR/.venv/bin/python"
HOST="127.0.0.1"
PORT="8000"
URL="http://$HOST:$PORT/"

cd "$APP_DIR"

# تشغيل الخادم في الخلفية إن لم يكن قائمًا
if ! curl -s -o /dev/null --max-time 2 "$URL"; then
    nohup "$VENV_PY" manage.py runserver "$HOST:$PORT" --settings=config.settings.dev \
        >/tmp/hrms_server.log 2>&1 &
    disown
    # انتظار جاهزية الخادم (حتى 15 ثانية)
    for i in $(seq 1 30); do
        if curl -s -o /dev/null --max-time 2 "$URL"; then
            break
        fi
        sleep 0.5
    done
fi

# فتح المتصفح الافتراضي
xdg-open "$URL" >/dev/null 2>&1 || true
