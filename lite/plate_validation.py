import re

from helper.text_decorators import (
    clean_license_plate_text,
    format_license_plate_label,
    format_license_plate_persian,
)

NATIONAL_PATTERN = re.compile(r"^\d{2}[A-Za-z]+\d{3}\d{2}$")
NATIONAL_EXTRACT = re.compile(r"\d{2}[A-Za-z]+\d{3}\d{2}")
FREEZONE_LENGTHS = {5, 7, 8}

TYPE_LABELS = {"national": "ملی", "freezone": "منطقه آزاد", "unknown": "نامشخص"}


def is_garbage_plate_text(text):
    if not text:
        return True
    if len(text) > 14:
        return True
    if re.search(r"(\d)\1{5,}", text):
        return True
    if len(text) <= 3:
        return True
    letters = re.sub(r"[^A-Za-z]", "", text)
    digits = re.sub(r"\D", "", text)
    if digits and not letters and len(digits) <= 4:
        return True
    return False


def extract_valid_plate_text(text, plate_type=None):
    cleaned = (text or "").strip()
    if NATIONAL_PATTERN.match(cleaned):
        return cleaned, "national"

    match = NATIONAL_EXTRACT.search(cleaned)
    if match:
        return match.group(0), "national"

    digits = re.sub(r"\D", "", cleaned)
    if digits and not re.search(r"[A-Za-z]", cleaned) and len(digits) in FREEZONE_LENGTHS:
        return digits, "freezone"

    if plate_type == "freezone" and len(digits) in FREEZONE_LENGTHS:
        return digits, "freezone"

    return None, None


def accept_plate_detection(plate, min_char_conf=0.65, min_plate_conf=0.72):
    if float(plate.get("char_conf_avg", 0)) < min_char_conf:
        return None
    if float(plate.get("plate_conf", 0)) < min_plate_conf:
        return None

    source = plate.get("clean_text") or plate.get("raw_text") or ""
    if is_garbage_plate_text(source):
        return None

    valid_text, plate_type = extract_valid_plate_text(source, plate.get("plate_type"))
    if not valid_text:
        return None

    return {
        "raw_text": valid_text,
        "clean_text": clean_license_plate_text(valid_text, plate_type=plate_type),
        "persian_text": format_license_plate_persian(valid_text, plate_type=plate_type),
        "label": format_license_plate_label(valid_text, plate_type=plate_type),
        "plate_type": plate_type,
        "plate_type_label": TYPE_LABELS.get(plate_type, "نامشخص"),
        "plate_conf": plate.get("plate_conf"),
        "char_conf_avg": plate.get("char_conf_avg"),
        "bbox": plate.get("bbox"),
    }


def plate_group_key(plate):
    return plate.get("clean_text") or plate.get("raw_text") or ""
