# واجهة التكامل REST (API)

> **HRMS-DOC-16** — المرجع العملي لواجهة API للتكامل مع تطبيق الموبايل وأجهزة QR والجهات الخارجية.
> النطاق: `/api/v1/` — تنسيق JSON — مصادقة Token أو DeviceKey.

---

## جدول المحتويات

1. [نظرة عامة](#1-نظرة-عامة)
2. [المصادقة](#2-المصادقة)
3. [الأخطاء](#3-الأخطاء)
4. [المصادقة والملف الشخصي](#4-المصادقة-والملف-الشخصي)
5. [مسح QR](#5-مسح-qr)
6. [الموظف](#6-الموظف)
7. [التوظيف](#7-التوظيف)
8. [أمثلة curl](#8-أمثلة-curl)
9. [مواصفة OpenAPI](#9-مواصفة-openapi)

---

## 1. نظرة عامة

| الحقل | القيمة |
|---|---|
| العنوان الأساسي (Base URL) | `http://<LAN-IP>:8000/api/v1/` |
| تنسيق الطلب/الاستجابة | JSON (`Content-Type: application/json`) |
| رموز النجاح | `200 OK`، `201 Created` |
| التوثيق | هذه الوثيقة + [مواصفة OpenAPI 3.0](./openapi.yaml) |

الواجهة مبنية بـ Django REST Framework، ومصممة لثلاث حالات استخدام:

1. **تطبيق موبايل للموظف** — تسجيل دخول + ملفي + حضوري + مسح QR من الهاتف.
2. **أجهزة QR الثابتة** — إرسال مسحات بحساب جهاز (DeviceKey) دون حساب مستخدم.
3. **تكامل التوظيف** — قراءة إعلانات/مرشحين وإضافة مرشحين من بوابة خارجية.

---

## 2. المصادقة

### 2.1 Token (للموظفين والمستخدمين)

- تُحصل عليه عبر `POST auth/login/`.
- يُرسل في كل الطلبات عدا `auth/login`:

```
Authorization: Token <token>
```

### 2.2 DeviceKey (للأجهزة)

- تُسجَّل الأجهزة في النظام مسبقًا (رمز الجهاز + مفتاح API).
- تُرسل الترويسات التالية في مسح QR:

```
X-Device-Code: <device_code>
X-API-Key: <api_key>
```

| الترويسة | الوصف |
|---|---|
| `X-Device-Code` | رمز الجهاز الفريد (مثل `READER-01`) |
| `X-API-Key` | مفتاح API السري للجهاز |

> تحذير: `X-API-Key` سرّ حساس — لا يُشارك ولا يُخزَّن في تطبيق الموبايل.

---

## 3. الأخطاء

| الحالة | المعنى | الشكل |
|---|---|---|
| `400` | طلب غير صالح (تحقق/فلاتر/تواريخ) | `{"error": "..."}` أو `{"field": [...]}` |
| `401` | غير مصادق (رمز مفقود/باطل/جهاز مرفوض) | `{"detail": "..."}` |
| `403` | مصادق بلا صلاحية | `{"detail": "..."}` |
| `404` | المورد غير موجود | `{"detail": "..."}` |
| `422` | مسح QR مرفوض (مفتاح/رمز منتهي/مكرر) | `{"ok": false, "error": "..."}` |

---

## 4. المصادقة والملف الشخصي

### `POST /auth/login/`

إرسال بيانات الدخول → رمز + ملف الموظف.

| الحقل | النوع | مطلوب | وصف |
|---|---|---|---|
| `username` | string | ✅ | اسم المستخدم |
| `password` | string | ✅ | كلمة المرور |

- **القيود**: الحساب يجب أن يملك ملف موظف (واجهة الموبايل للموظفين).

**طلب:**
```json
{ "username": "ahmed.b", "password": "secret" }
```

**استجابة 200:**
```json
{
  "token": "9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b",
  "employee": {
    "id": 7,
    "employee_code": "EMP-0007",
    "full_name_ar": "أحمد بن يوسف",
    "first_name_ar": "أحمد",
    "last_name_ar": "بن يوسف",
    "phone": "0550123456",
    "email": "ahmed@lan.local",
    "employment_status": "active",
    "branch": "المركز الرئيسي",
    "department": "تكنولوجيا المعلومات",
    "position": "مطور",
    "qr_payload": "...",
    "today": null
  }
}
```

**أخطاء:** `400` (بيانات غير صحيحة أو حساب بلا ملف موظف).

---

### `POST /auth/logout/`

إبطال رمز المصادقة الحالي.

**استجابة 200:**
```json
{ "ok": true }
```

---

## 5. مسح QR

### `POST /scan/`

إرسال رمز QR → قرار الدخول/الخروج.

| الحقل | النوع | مطلوب | وصف |
|---|---|---|---|
| `payload` | string | ✅ | محتوى رمز QR (المسح بواسطة التطبيق أو الجهاز) |

**المصادقة:** جهاز نشط (DeviceKey) **أو** موظف مصادق بصلاحية `attendance.scan` يمسح **رمزه هو** فقط (يُرفض رمز الغير).

**استجابة 200:**
```json
{
  "ok": true,
  "decision": "check_in",
  "detail": "تم تسجيل الدخول",
  "employee": "أحمد بن يوسف",
  "time": "2026-08-13T07:58:12.304Z"
}
```

- `decision`: `check_in` | `check_out` | `rejected`.
- `ok: false` مع `decision: rejected` → تُفحص `detail` لمعرفة السبب.

**أخطاء:** `400` (payload ناقص)، `401` (لا مصادقة)، `403` (بلا صلاحية)، `422` (QR مرفوض/رمز غريب).

---

## 6. الموظف

### `GET /me/`

الملف الشخصي + رمز QR النشط + حالة اليوم.

**استجابة 200:** نفس كائن `employee` في تسجيل الدخول.

**أخطاء:** `404` إذا لم يملك الحساب ملف موظف.

---

### `GET /me/attendance/?from=YYYY-MM-DD&to=YYYY-MM-DD`

أيام الحضور (آخر 90 يومًا كحد أقصى).

**استجابة 200:**
```json
[
  {
    "work_date": "2026-08-12",
    "state": "present",
    "check_in": "07:55:00",
    "check_out": "16:05:00",
    "worked_minutes": 490,
    "late_minutes": 0,
    "early_minutes": 0,
    "overtime_minutes": 10,
    "is_corrected": false
  }
]
```

**أخطاء:** `400` (صيغة تاريخ خاطئة).

---

## 7. التوظيف

> كل endpoints التوظيف تتطلب Token ومصادقة، والصلاحيات كالتالي:
> - قراءة الإعلانات: `recruitment.posting.view`
> - قراءة المرشحين: `recruitment.candidate.view`
> - إضافة مرشح: `recruitment.candidate.manage`

### `GET /recruitment/postings/?status=`

قائمة الإعلانات — **افتراضيًا المنشورة فقط** (`published`)، ويُمكن طلب غيرها عبر `status`:
`draft` | `published` | `closed`.

**استجابة 200:**
```json
[
  {
    "id": 3,
    "code": "JOB-003",
    "title_ar": "مطور برمجيات",
    "title_fr": "Développeur logiciel",
    "title_en": "Software Developer",
    "department": "تكنولوجيا المعلومات",
    "branch": "المركز الرئيسي",
    "employment_type": "full_time",
    "openings_count": 2,
    "requirements": "...",
    "description": "...",
    "status": "published",
    "status_display": "منشور",
    "publish_date": "2026-08-01",
    "close_date": null,
    "candidate_count": 5
  }
]
```

---

### `GET /recruitment/postings/<id>/`

تفاصيل إعلان واحد (نفس الحقول أعلاه).

---

### `GET /recruitment/candidates/?status=&posting=`

قائمة المرشحين مع فلاتر اختيارية:
- `status`: `new` | `screening` | `interviewed` | `offer` | `hired` | `rejected` | `withdrawn`
- `posting`: معرّف الإعلان

**استجابة 200:**
```json
[
  {
    "id": 12,
    "posting": 3,
    "first_name_ar": "ليلى",
    "last_name_ar": "بن عمر",
    "first_name_fr": "Lila",
    "last_name_fr": "Ben Omar",
    "first_name_en": "Lila",
    "last_name_en": "Ben Omar",
    "email": "lila@example.com",
    "phone": "0661",
    "source": "",
    "status": "new",
    "status_display": "جديد",
    "applied_date": "2026-08-13",
    "notes": ""
  }
]
```

---

### `POST /recruitment/candidates/`

إضافة مرشح لإعلان (صلاحية `recruitment.candidate.manage`).

| الحقل | النوع | مطلوب | وصف |
|---|---|---|---|
| `posting` | integer | — | معرّف الإعلان (يفضَّل إرساله) |
| `first_name_ar` | string | ✅ | الاسم |
| `last_name_ar` | string | ✅ | اللقب |
| `email` | string (email) | ✅ | البريد |
| `phone` | string | — | الهاتف |
| `first_name_fr` / `last_name_fr` | string | — | فرنسي |
| `first_name_en` / `last_name_en` | string | — | إنجليزي |
| `source` | string | — | المصدر |
| `notes` | string | — | ملاحظات |

> `status` و `applied_date` للقراءة فقط — يُحددها النظام (الجديد + تاريخ اليوم).

**طلب:**
```json
{
  "posting": 3,
  "first_name_ar": "ليلى",
  "last_name_ar": "بن عمر",
  "email": "lila@example.com",
  "phone": "0661"
}
```

**استجابة 201:** كائن المرشح (أعلاه).

**أخطاء:** `400` (`{"error": "الإعلان مغلق ولا يقبل مرشحين جدد"}` إن كان الإعلان مغلقًا، أو أخطاء تحقق الحقول).

---

## 8. أمثلة curl

```bash
# 1) تسجيل الدخول والحصول على Token
curl -X POST http://localhost:8000/api/v1/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"username":"ahmed.b","password":"secret"}'

# 2) ملفي (بعد حفظ الرمز في TOKEN)
TOKEN="<token>"
curl http://localhost:8000/api/v1/me/ \
  -H "Authorization: Token $TOKEN"

# 3) الإعلانات المنشورة
curl "http://localhost:8000/api/v1/recruitment/postings/" \
  -H "Authorization: Token $TOKEN"

# 4) إضافة مرشح
curl -X POST http://localhost:8000/api/v1/recruitment/candidates/ \
  -H "Authorization: Token $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"posting":3,"first_name_ar":"ليلى","last_name_ar":"بن عمر","email":"lila@example.com"}'

# 5) مسح QR بجهاز ثابت
curl -X POST http://localhost:8000/api/v1/scan/ \
  -H "X-Device-Code: READER-01" \
  -H "X-API-Key: <api_key>" \
  -H "Content-Type: application/json" \
  -d '{"payload":"<qr_payload>"}'
```

---

## 9. مواصفة OpenAPI

المواصفة الآلية الكاملة للواجهة (جميع المسارات، المخططات، وآليات المصادقة) متاحة كملف **OpenAPI 3.0.3**:

- **الملف:** [`docs/openapi.yaml`](./openapi.yaml)
- **الاستعمال:** يُستورد مباشرة في Swagger UI / Redoc / Postman / أي أداة تدعم OpenAPI.
- **المحتوى:** 8 مسارات (`auth/login`، `auth/logout`، `scan`، `me`، `me/attendance`، `recruitment/postings`، `recruitment/postings/{pk}`، `recruitment/candidates`)، 11 مخططًا، و3 آليات مصادقة (Token / DeviceKey / Session).

> عند أي تعديل على `apps/api/views.py` أو `apps/api/serializers.py` يجب تحديث `docs/openapi.yaml` بالتوازي (معايير القبول v3 — وثيقة تكامل REST).
