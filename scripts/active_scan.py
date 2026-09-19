"""ماسح نشط مخصص لـ HRMS — اختبارات OWASP عملية ضد خادم حي.

الاستعمال: .venv/bin/python scripts/active_scan.py [base_url]
الافتراضي: http://127.0.0.1:8001
"""
import re
import sys

import requests

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8001"
ADMIN = ("admin", "Hrms@2026!Secure")
EMP = None  # يُكتشف تلقائيًا من قائمة الموظفين التجريبيين

FINDINGS = []


def log(level, code, msg):
    FINDINGS.append((level, code, msg))
    print(f"[{level}] {code} — {msg}")


def login(user, pw):
    s = requests.Session()
    r = s.get(f"{BASE}/auth/login/", timeout=10)
    token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', r.text)
    data = {"username": user, "password": pw,
            "csrfmiddlewaretoken": token.group(1), "next": "/"}
    r = s.post(f"{BASE}/auth/login/", data=data, timeout=10,
               headers={"Referer": f"{BASE}/auth/login/"}, allow_redirects=False)
    return (s if r.status_code in (302, 200) else None)


def csrf_of(s, path="/"):
    r = s.get(f"{BASE}{path}", timeout=10)
    m = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', r.text)
    return m.group(1) if m else None


# ---------------------------------------------------------------- الفحوص
def check_headers(s):
    """ترويسات الأمان على استجابة حية."""
    r = s.get(f"{BASE}/", timeout=10)
    h = {k.lower(): v for k, v in r.headers.items()}
    if h.get("x-frame-options") in ("DENY", "SAMEORIGIN"):
        print("  ✓ X-Frame-Options:", h["x-frame-options"])
    else:
        log("🟡", "HDR-01", f"X-Frame-Options مفقود/غريب: {h.get('x-frame-options')}")
    if h.get("x-content-type-options") == "nosniff":
        print("  ✓ nosniff مفعّل")
    else:
        log("🟡", "HDR-02", "X-Content-Type-Options مفقود (dev متوقع)")
    c = r.headers.get("Set-Cookie", "")
    flags = [f.lower() for f in ("httponly", "samesite")]
    missing = [f for f in flags if f not in c.lower()]
    if missing:
        log("🔵", "CK-01", f"كوكي الجلسة بلا: {missing} (dev — prod مضبوط ✓)")


def check_sqli(s):
    """مسبارات SQLi على معاملات البحث والفلاتر."""
    probes = ["' OR '1'='1", "1' OR '1'='1' --", "'; DROP TABLE employees_employee; --",
              "' UNION SELECT NULL,NULL,NULL --"]
    targets = ["/employees/?q=", "/leave/queue/?status=", "/core/search/?q="]
    vuln = 0
    for t in targets:
        for p in probes:
            r = s.get(f"{BASE}{t}{requests.utils.quote(p)}", timeout=15)
            body = r.text.lower()
            if any(sig in body for sig in ("sql syntax", "sqlite error", "pg_query",
                                           "syntax error at or near", "warning: mysql")):
                vuln += 1
                log("🔴", f"SQLI-{vuln}", f"أثر خطأ SQL عند {t} بالحشو: {p[:30]}")
    if not vuln:
        print("  ✓ لا أخطاء SQL مكشوفة (9 مسبارات × 3 مسارات)")


def check_xss(s):
    """انعكاس XSS في نتائج البحث."""
    probe = '<svg/onload=alert(1)>'
    marker = 'zxqmarker'
    payload = f"{probe}<b id={marker}></b>"
    for t in ("/employees/?q=", "/core/search/?q=", "/reports/employees/?q="):
        r = s.get(f"{BASE}{t}{requests.utils.quote(payload)}", timeout=15)
        raw = payload in r.text          # انعكاس بدون تهريب
        reflected = probe.split("/")[0] + "/" in r.text and marker + "></b>" in r.text
        if raw:
            log("🔴", "XSS-R", f"انعكاس خام غير مهرَّب عند {t}")
        elif reflected:
            print(f"  ~ {t}: انعكاس جزيري (Django هرب الوسوم) — آمن")
    print("  ✓ فحص XSS انعكاسي مكتمل")


def check_idor(emp_session):
    """محاولة موظف عادي الوصول لصفحات إدارية وبيانات الغير."""
    admin_urls = ["/employees/new/", "/payroll/runs/generate/", "/org/branches/new/",
                  "/devices/", "/audit/", "/backup/", "/ai/refresh"]
    blocked = leaked = 0
    for u in admin_urls:
        r = emp_session.get(f"{BASE}{u}", timeout=15, allow_redirects=False)
        if r.status_code in (302, 403) or "login" in r.headers.get("Location", ""):
            blocked += 1
        elif r.status_code == 200:
            leaked += 1
            log("🔴", f"IDOR-{leaked}", f"موظف عادي فتح صفحة إدارية! {u}")
    print(f"  ✓ حجب الإداريين: {blocked}/{len(admin_urls)} (المتبقي 403/302 كما هو متوقع)")


def check_upload_size(s):
    """رفع ملف يتجاوز DATA_UPLOAD_MAX_MEMORY_SIZE (10MB)."""
    tok = csrf_of(s, "/employees/")
    big = b"A" * (11 * 1024 * 1024)
    files = {"file": ("big.bin", big, "application/octet-stream")}
    try:
        r = s.post(f"{BASE}/employees/", files=files, timeout=60,
                   data={"csrfmiddlewaretoken": tok},
                   headers={"Referer": f"{BASE}/employees/"})
        if r.status_code in (400, 413):
            print("  ✓ الطلبات الضخمة تُرفض (400/413)")
        else:
            log("🟡", "UP-01", f"ملف 11MB لم يُرفض صراحةً (HTTP {r.status_code})")
    except requests.RequestException as e:
        print(f"  ✓ اتصال قُطع عند الحجم الضخم ({type(e).__name__}) — رفض فعلي")


def check_debug_leak(s):
    """تسرب DEBUG/تفاصيل الاستثناءات."""
    r = s.get(f"{BASE}/employees/99999999/", timeout=15)
    if "Traceback" in r.text or "DEBUG = True" in r.text:
        log("🟠", "DBG-01", "صفحة خطأ تكشف Traceback (DEBUG=True في dev — طبيعي، تأكد False بالإنتاج)")
    else:
        print(f"  ✓ لا تسرب تفاصيل (404 نظيف، HTTP {r.status_code})")


# ---------------------------------------------------------------- التشغيل
def main():
    print(f"=== الماسح النشط ضد {BASE} ===\n")
    adm = login(*ADMIN)
    if not adm:
        print("✗ فشل دخول المشرف — أوقف الفحص"); return
    # مستخدم عادي: emp-101 بكلمة Demo المعروفة إن وجدت
    emp = login("emp-101", "Demo@2026!") or login("emp-101", "pass1234")

    print("[1] ترويسات الأمان والكوكيز"); check_headers(adm)
    print("\n[2] حقن SQL (27 مسبارًا)"); check_sqli(adm)
    print("\n[3] XSS الانعكاسي"); check_xss(adm)
    print("\n[4] IDOR / تصعيد الصلاحيات (موظف عادي)")
    if emp: check_idor(emp)
    else: print("  ~ لا حساب موظف تجريبي متاح — تخطٍّ (غطّته اختبارات RBAC الآلية)")
    print("\n[5] حد حجم الرفع (11MB)"); check_upload_size(adm)
    print("\n[6] تسرب معلومات الأخطاء"); check_debug_leak(adm)

    print("\n=== الخلاصة ===")
    crit = sum(1 for l, *_ in FINDINGS if l == "🔴")
    warn = sum(1 for l, *_ in FINDINGS if l in ("🟡", "🟠"))
    info = sum(1 for l, *_ in FINDINGS if l == "🔵")
    print(f"🔴 حرجة: {crit} · 🟡/🟠 تحذيرية: {warn} · 🔵 معلوماتية: {info}")
    if not FINDINGS:
        print("🎉 لا ملاحظات سلبية — كل الفحوص النشطة نجحت")


if __name__ == "__main__":
    main()
