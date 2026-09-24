"""Iranian licence plate helpers: parsing, Persian formatting, category and odd/even parity.

Raw national plate text (as produced by the recognizer) looks like ``12Sin34567``:
two digits, a letter code, three digits and the two-digit region (Iran) code.
Free-zone plates are digits only (5, 7 or 8 digits).
"""
import re

LETTERS = {
    "A": "الف", "B": "ب", "P": "پ", "Taxi": "ت", "J": "ج", "D": "د", "Sin": "س",
    "Sad": "ص", "T": "ط", "PuV": "ع", "Gh": "ق", "L": "ل", "M": "م", "N": "ن",
    "V": "و", "H": "ه", "Y": "ی", "PwD": "ژ",
}
FA_TO_CODE = {v: k for k, v in LETTERS.items()}
FA_TO_CODE.update({"آ": "A", "ا": "A", "ي": "Y", "ك": "K", "ت": "Taxi", "ع": "PuV", "ژ": "PwD"})

# Plate category by letter
CATEGORIES = {
    "A": "government", "P": "police", "Taxi": "taxi", "PuV": "public",
    "PwD": "disabled", "Sad": "private", "Sin": "private",
}
CATEGORY_LABELS = {
    "private": "شخصی", "government": "دولتی", "police": "انتظامی", "taxi": "تاکسی",
    "public": "عمومی", "disabled": "جانبازان و معلولین", "freezone": "مناطق آزاد", "unknown": "نامشخص",
}

FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
AR_DIGITS = "٠١٢٣٤٥٦٧٨٩"
_TO_EN = str.maketrans(FA_DIGITS + AR_DIGITS, "0123456789" * 2)
_TO_FA = str.maketrans("0123456789", FA_DIGITS)

NATIONAL_RE = re.compile(r"^(\d{2})([A-Za-z]+)(\d{3})(\d{2})$")


def to_fa_digits(text):
    return str(text).translate(_TO_FA)


def to_en_digits(text):
    return str(text).translate(_TO_EN)


def parse(raw):
    """Return plate parts dict or None."""
    if not raw:
        return None
    raw = to_en_digits(raw.strip())
    m = NATIONAL_RE.match(raw)
    if m:
        d2, letter, d3, region = m.groups()
        return {"type": "national", "d2": d2, "letter": letter, "d3": d3, "region": region}
    digits = re.sub(r"\D", "", raw)
    if digits and digits == raw and len(digits) in (5, 7, 8):
        return {"type": "freezone", "digits": digits}
    return None


def format_fa(raw):
    """Human-readable Persian text, e.g. ``۱۲ س ۳۴۵ - ایران ۶۷``."""
    p = parse(raw)
    if not p:
        return to_fa_digits(raw or "")
    if p["type"] == "freezone":
        return "منطقه آزاد " + to_fa_digits(p["digits"])
    letter = LETTERS.get(p["letter"], p["letter"])
    return f"{to_fa_digits(p['d2'])} {letter} {to_fa_digits(p['d3'])} - ایران {to_fa_digits(p['region'])}"


def category(raw):
    p = parse(raw)
    if not p:
        return "unknown"
    if p["type"] == "freezone":
        return "freezone"
    return CATEGORIES.get(p["letter"], "private")


def parity_digit(raw):
    """Digit that decides odd/even plans: the last digit of the three-digit group."""
    p = parse(raw)
    if not p:
        return None
    if p["type"] == "freezone":
        return int(p["digits"][-1])
    return int(p["d3"][-1])


def is_even(raw):
    d = parity_digit(raw)
    return None if d is None else d % 2 == 0


def normalize_query(text):
    """Convert user input (Persian/English, spaces, dashes, 'ایران') to a raw-plate search pattern.

    Unknown characters become ``%`` so partial searches work with SQL LIKE.
    """
    if not text:
        return ""
    text = to_en_digits(text).replace("ایران", " ").replace("-", " ").replace("_", " ")
    out = []
    i = 0
    tokens = text.split()
    for tok in tokens:
        buf = ""
        for ch in tok:
            if ch.isdigit():
                if buf:
                    out.append(FA_TO_CODE.get(buf, buf))
                    buf = ""
                out.append(ch)
            elif ch in ("*", "?", "%"):
                if buf:
                    out.append(FA_TO_CODE.get(buf, buf))
                    buf = ""
                out.append("%")
            else:
                buf += ch
        if buf:
            if buf == "الف":
                out.append("A")
            elif buf in FA_TO_CODE:
                out.append(FA_TO_CODE[buf])
            else:
                out.append(buf)
        i += 1
    return "".join(out)


def describe(raw):
    cat = category(raw)
    return {
        "raw": raw,
        "fa": format_fa(raw),
        "category": cat,
        "category_label": CATEGORY_LABELS.get(cat, "نامشخص"),
        "even": is_even(raw),
    }
