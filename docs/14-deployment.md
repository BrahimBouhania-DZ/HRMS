# المرحلة الرابعة عشرة: دفتر نشر أول فرع (Deployment Runbook)

> **HRMS-DOC-14** — خطوات النشر الكامل على خادم LAN لأول فرع: PostgreSQL → venv → static → gunicorn → nginx → systemd → تدقيق.

---

## جدول المحتويات

1. التحضير على آلة التطوير
2. إعداد الخادم (Ubuntu/Debian)
3. قاعدة بيانات PostgreSQL
4. نشر التطبيق + المتغيرات
5. الملفات الثابتة + Gunicorn + Nginx + systemd
6. التدقيق النهائي (Checklist)
7. استقبال الفريق الأول

---

## 1. التحضير على آلة التطوير

```bash
cd ~/Desktop/HRMS
python3 manage.py test --settings=config.settings.dev    # كل الأخضر (SQLite)
python3 manage.py test --settings=config.settings.test  # كل الأخضر على PostgreSQL (اختياري — يتطلب DB مضبوط)
python3 manage.py check --settings=config.settings.dev
bash scripts/backup.sh                                   # نسخة قبل النقل
bash scripts/package.sh 2026-08-09                       # حزمة واحدة للنشر (اختياري)
```

نسخ المشروع إلى الخادم (بدون الحزمة): `rsync -av --exclude db.sqlite3 --exclude backups ./ user@server:/opt/hrms`

أو نقل الحزمة الجاهزة: `scp releases/hrms-v2026-08-09.tar.gz user@server:/opt/` ثم فك الضغط:

---

## 2. إعداد الخادم (Ubuntu/Debian)

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip \
    libpango-1.0-0 libpangocairo-1.0-0 libcairo2 \
    postgresql nginx gunicorn
```

---

## 3. قاعدة بيانات PostgreSQL

```bash
sudo -u postgres createuser --pwprompt hrms
sudo -u postgres createdb -O hrms hrms
```

---

## 4. نشر التطبيق + المتغيرات

```bash
cd /opt/hrms
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

أنشئ ملف `.env` (يقرأه الإعداد تلقائيًا — لا يُتجاوز متغيرات البيئة الحالية):

```dotenv
DJANGO_SECRET_KEY=بدّلني_بسري_قوي
DJANGO_ALLOWED_HOSTS=192.168.1.10,hrms.local
DJANGO_DB_NAME=hrms
DJANGO_DB_USER=hrms
DJANGO_DB_PASSWORD=بدّلني
DJANGO_DB_HOST=localhost
DJANGO_DB_PORT=5432
```

> **أمان:** غيّر كلمتي مرور Postgres و DJANGO_SECRET_KEY، واجعل ملكية `.env` للمستخدم hrms فقط.

ترحيل + تهيئة:

```bash
export DJANGO_SETTINGS_MODULE=config.settings.prod
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_all        # RBAC + إجازات + مشرف افتراضي (بوليصة موحّدة)
.venv/bin/python manage.py deploy_prepare   # check + تحقق هجرات + migrate + collectstatic
```

> `deploy_prepare` أمر Django حقيقي (المصدر: `apps/core/management/commands/deploy_prepare.py`) يُشغّل `check --deploy` + `makemigrations --check` + `migrate` + `collectstatic`، ويفشل في بيئة غير prod. قالب المتغيرات في `.env.example` — انسخه إلى `.env` وعدّله.

---

## 5. الملفات الثابتة + Gunicorn + Nginx + systemd

```bash
sudo cp deploy/hrms.service /etc/systemd/system/hrms.service
sudo systemctl daemon-reload
sudo systemctl enable --now hrms
sudo cp deploy/hrms-nginx.conf /etc/nginx/sites-available/hrms
sudo ln -s /etc/nginx/sites-available/hrms /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

تحقق:

```bash
sudo systemctl status hrms
curl -I http://192.168.1.10/auth/login/
```

> **أمان HTTPS:** على LAN يمكن وضع nginx خلف خادم TLS (ثقة ذاتية للشبكة الداخلية) — الإعدادات الحالية تفرض `SECURE_SSL_REDIRECT` وملفات HSTS؛ عند غياب TLS استخدم إصدارًا بـ `SECURE_SSL_REDIRECT=False`.

---

## 6. التدقيق النهائي (Checklist)

- [ ] `DJANGO_ALLOWED_HOSTS` محدّد (لا جوكر) — أُثبت بالخطأ عند غيابه.
- [ ] `DEBUG=False`، `SECRET_KEY` فريد.
- [ ] Postgres بدل SQLite، وملكيات الملفات صحيحة.
- [ ] نسخة احتياطية تعمل + استعادة مُختبرة (راجع `12-operations.md`).
- [ ] مستخدم "الموظف" يرى نطاقه فقط؛ الأدمن يرى الكل.
- [ ] قارئ QR مسجّل في `/devices/` ومفتاحه محفوظ.
- [ ] مسح حي: دخول/خروج + مسح متكرر مرفوض.
- [ ] دورة إجازة حية: طلب → اعتماد → خصم رصيد.

---

## 7. استقبال الفريق الأول

1. وثّق أسماء المستخدمين وكلمات المرور الأولية (وغيّرها عند أول دخول).
2. وزّع `docs/13-user-training.md` على الموظفين.
3. ابدأ بفرع واحد ومجموعة صغيرة (توصية roadmap §10.5).
4. جدول نسخة احتياطية يومية + اختبار استعادة شهري.

---

## تسجيل التغييرات

| التاريخ | النسخة | التغيير |
|---|---|---|
| 2026-08-09 | 1.0 | دفتر نشر أول فرع (LAN) |
| 2026-08-09 | 2.0 | حزمة `scripts/package.sh` + `.env.example` + `seed_all` الموحّد + `deploy_prepare` كأمر Django |
