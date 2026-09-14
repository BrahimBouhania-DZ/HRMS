"""أدوات توليد الألوان المخصصة لصفحة التحكم السرية.

تولّد block :root{...} يحقَّن أعلى الصفحة (المتغيرات المتجاوزة فقط؛
الباقي يبقى على قيم base.css). توليد التدرجات (dark/darker/soft) يتم عبر خلط لوني.
"""

from __future__ import annotations

import re
from typing import TypeAlias

Hex: TypeAlias = str
CSSVar: TypeAlias = str


# --------------------------------------------------------------------------
# القيمة الافتراضية لكل متغير :root مدعوم (النسخة الفعلية base.css)
# --------------------------------------------------------------------------
DEFAULTS: dict[CSSVar, Hex] = {
    # أزرق سماوي (السلسلة الكاملة)
    "--sky-50":  "#EAF7FC", "--sky-100": "#D6EEF9", "--sky-200": "#A9DBF1",
    "--sky-300": "#77C4E6", "--sky-400": "#49ADDA", "--sky-500": "#2E96C8",
    "--sky-600": "#1F7AA8", "--sky-700": "#196088", "--sky-800": "#144A69",
    "--sky-900": "#0E354C",
    # أصفر رملي
    "--sand-50": "#FBF6EC", "--sand-100": "#F6ECD8", "--sand-200": "#EAD9A9",
    "--sand-300": "#DDC37F", "--sand-400": "#D0A95C", "--sand-500": "#C29247",
    "--sand-600": "#A67733",
    # ذهبي
    "--gold-300": "#E6C968", "--gold-500": "#D4AF37", "--gold-600": "#B8922E",
    "--gold-700": "#96761F",
    # أخضر
    "--green-50": "#EDF7F1", "--green-100": "#D8EEE1", "--green-300": "#A3D8BC",
    "--green-500": "#5FAE83", "--green-600": "#3E9466", "--green-700": "#2F7A54",
    # أحمر
    "--red-50": "#FDEEEC", "--red-100": "#FADDD8", "--red-500": "#D9534F",
    "--red-600": "#C0392B", "--red-700": "#A93226",
    # دلالية
    "--brand": "#2E96C8", "--brand-dark": "#144A69", "--brand-darker": "#0E354C",
    "--brand-soft": "#EAF7FC",
    "--accent": "#C29247",
    "--gold": "#D4AF37",
    "--success": "#3E9466", "--success-soft": "#EDF7F1",
    "--danger": "#C0392B", "--danger-soft": "#FDEEEC",
    # سطح ولون
    "--bg": "#F1F6FA", "--bg-soft": "#F7FAFD", "--surface": "#FFFFFF",
    "--text": "#20303C", "--text-strong": "#16232D", "--muted": "#5B6B79",
    "--border": "#DEE8F0", "--border-strong": "#C9D8E4",
    # شكل
    "--radius": "#12px", "--radius-sm": "#8px", "--radius-lg": "#16px",
    "--shadow-sm": "0 1px 2px rgba(20,60,90,.07),0 4px 14px rgba(20,60,90,.05)",
    "--shadow-md": "0 2px 6px rgba(20,60,90,.08),0 12px 32px rgba(20,60,90,.10)",
    "--shadow-lg": "0 4px 12px rgba(20,60,90,.12),0 24px 56px rgba(20,60,90,.14)",
    "--ring": "0 0 0 3px rgba(46,150,200,.18)",
}


def _color_var(name: str) -> bool:
    """هل المتغير قيمته لون hex وليس shadow/radius/px؟"""
    return name.startswith("--") and any(
        p in name for p in ("sky", "sand", "gold", "green", "red", "brand",
                            "accent", "bg", "text", "muted", "surface", "border")
    )


ALLOWED_VARS: list[CSSVar] = sorted(DEFAULTS.keys())

# المتغيرات التي يمكن للمستخدم تعديلها مباشرة في المحرر (الألوان فقط)
COLOR_VARS: list[CSSVar] = sorted(k for k in DEFAULTS if _color_var(k))


# --------------------------------------------------------------------------
# خلط الألوان
# --------------------------------------------------------------------------
def _parse_hex(h: Hex) -> tuple[int, int, int]:
    """#RRGGBB أو #RGB → (R, G, B)"""
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        raise ValueError(f"لون غير صالح: {h}")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rgb_to_hex(r: int, g: int, b: int) -> Hex:
    return f"#{r:02x}{g:02x}{b:02x}"


def mix(c1: Hex, c2: Hex, t: float = 0.5) -> Hex:
    """خلط لونين: t=0 → c1 كاملاً، t=1 → c2 كاملاً."""
    r1, g1, b1 = _parse_hex(c1)
    r2, g2, b2 = _parse_hex(c2)
    return _rgb_to_hex(
        int(r1 + (r2 - r1) * t),
        int(g1 + (g2 - g1) * t),
        int(b1 + (b2 - b1) * t),
    )


def brighten(color: Hex, amount: float = 0.3) -> Hex:
    """إضاءة نحو الأبيض."""
    return mix(color, "#FFFFFF", amount)


def darken(color: Hex, amount: float = 0.3) -> Hex:
    """تغميق نحو الأسود."""
    return mix(color, "#000000", amount)


def soft_version(color: Hex) -> Hex:
    """allocate لون ناعم للخلفية (تخفيف شديد نحو الأبيض)."""
    return mix(color, "#FFFFFF", 0.88)


# --------------------------------------------------------------------------
# توليد الظلال التلقائية من اللون الأساسي
# --------------------------------------------------------------------------
def _derive_shades(base: Hex, shades: dict[str, float]) -> dict[CSSVar, Hex]:
    """يولّد تدرجات من base. القيمة t الإيجابية = خفيف (نحو الأبيض)،
    t=0 = base itself، t السالبة = داكن (نحو الأسود).
    الصيغة: mix(white, base, 1-t) للأضواء، mix(black, base, 1-|t|) للظلال.
    """
    result: dict[CSSVar, Hex] = {}
    for name, t in shades.items():
        if t == 0.0:
            val = base
        elif t > 0:
            val = mix("#FFFFFF", base, 1.0 - t)
        else:
            val = mix("#000000", base, 1.0 + t)
        result[f"--{name}"] = val
    return result


_SKY_SHADES: dict[str, float] = {
    "sky-50": 0.90, "sky-100": 0.78, "sky-200": 0.54, "sky-300": 0.30,
    "sky-400": 0.12, "sky-500": 0.0,
    "sky-600": -0.10, "sky-700": -0.25, "sky-800": -0.42, "sky-900": -0.60,
}
_SAND_SHADES: dict[str, float] = {
    "sand-50": 0.90, "sand-100": 0.78, "sand-200": 0.50, "sand-300": 0.25,
    "sand-400": 0.08, "sand-500": 0.0, "sand-600": -0.12,
}
_GOLD_SHADES: dict[str, float] = {"gold-300": 0.20, "gold-500": 0.0, "gold-600": -0.10, "gold-700": -0.22}
_GREEN_SHADES: dict[str, float] = {
    "green-50": 0.90, "green-100": 0.76, "green-300": 0.35,
    "green-500": 0.0, "green-600": -0.12, "green-700": -0.24,
}
_RED_SHADES: dict[str, float] = {
    "red-50": 0.90, "red-100": 0.76,
    "red-500": 0.0, "red-600": -0.10, "red-700": -0.22,
}


def derive_sky(base_hex: Hex) -> dict[CSSVar, Hex]:
    return _derive_shades(base_hex, _SKY_SHADES)


def derive_sand(base_hex: Hex) -> dict[CSSVar, Hex]:
    return _derive_shades(base_hex, _SAND_SHADES)


def derive_gold(base_hex: Hex) -> dict[CSSVar, Hex]:
    return _derive_shades(base_hex, _GOLD_SHADES)


def derive_green(base_hex: Hex) -> dict[CSSVar, Hex]:
    return _derive_shades(base_hex, _GREEN_SHADES)


def derive_red(base_hex: Hex) -> dict[CSSVar, Hex]:
    return _derive_shades(base_hex, _RED_SHADES)


# --------------------------------------------------------------------------
# توليد CSS block من التجاوزات المخزنة
# --------------------------------------------------------------------------
_HEX_RE = re.compile(r"^#[0-9a-fA-F]{3,6}$")


def validate_hex(value: str) -> bool:
    return bool(_HEX_RE.match(value.strip()))


def build_css_block(overrides: dict[CSSVar, str]) -> str:
    """يولّد نص `:root { ... }` من التجاوزات فقط.
    فارغ = لا شيء يُحقن (base.css يسري بالكامل).
    """
    if not overrides:
        return ""
    parts = []
    for var in sorted(overrides.keys()):
        val = overrides[var].strip()
        if var in DEFAULTS and val:
            parts.append(f"    {var}: {val};")
    if not parts:
        return ""
    return ":root {\n" + "\n".join(parts) + "\n}\n"


def build_full_palette(
    brand: Hex,
    sand: Hex | None = None,
    gold_color: Hex | None = None,
    green: Hex | None = None,
    red: Hex | None = None,
    surface: Hex | None = None,
    bg: Hex | None = None,
    text_color: Hex | None = None,
    border_color: Hex | None = None,
    overrides: dict[CSSVar, str] | None = None,
) -> dict[CSSVar, str]:
    """يولّد لوحة كاملة من اللون الأساسي مع اشتقاق تلقائي.
    يدعم overrides يدوية إضافية فوق كل ذلك."""
    result: dict[CSSVar, str] = {}

    # sky = brand
    result.update(derive_sky(brand))
    result["--brand"] = brand
    result["--brand-dark"] = darken(brand, 0.35)
    result["--brand-darker"] = darken(brand, 0.55)
    result["--brand-soft"] = soft_version(brand)

    # sand
    s = sand or result.get("--sand-500", DEFAULTS["--sand-500"])
    result.update(derive_sand(s))
    result["--accent"] = s

    # gold
    g = gold_color or DEFAULTS["--gold-500"]
    result.update(derive_gold(g))
    result["--gold"] = g

    # green
    gr = green or DEFAULTS["--green-600"]
    result.update(derive_green(gr))
    result["--success"] = gr
    result["--success-soft"] = soft_version(gr)

    # red
    r = red or DEFAULTS["--red-600"]
    result.update(derive_red(r))
    result["--danger"] = r
    result["--danger-soft"] = soft_version(r)

    # neutrals
    if surface:
        result["--surface"] = surface
        result["--bg-soft"] = mix(surface, "#F1F6FA", 0.06)
    if bg:
        result["--bg"] = bg
    if text_color:
        result["--text"] = text_color
        result["--text-strong"] = darken(text_color, 0.15)
        result["--muted"] = mix(text_color, "#FFFFFF", 0.60)
    if border_color:
        result["--border"] = border_color
        result["--border-strong"] = darken(border_color, 0.12)

    # hand-edited overrides last (highest priority)
    if overrides:
        result.update({k: v for k, v in overrides.items() if v})

    return result
