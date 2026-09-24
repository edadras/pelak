import re

from difflib import SequenceMatcher

import cv2

NATIONAL_LETTER_CODES = {
    "Sin", "Sad", "T", "Taxi", "A", "B", "D", "Gh", "H", "J", "L", "M", "N",
    "P", "PuV", "PwD", "V", "Y",
}
NATIONAL_PATTERN = re.compile(r"^\d{2}[A-Za-z]+\d{3}\d{2}$")
FREEZONE_DIGIT_LENGTHS = {5, 7, 8}


def is_likely_freezone_crop(crop):
    """Both national and free-zone plates are wide; use two-row detection instead."""
    return False


def _similar_digit_rows(left, right):
    if left == right:
        return True
    if not left or not right:
        return False
    if abs(len(left) - len(right)) > 1:
        return False
    return SequenceMatcher(None, left, right).ratio() >= 0.75


def detect_two_row_layout(model_char, enhanced, params, char_conf_threshold):
    """Free-zone plates repeat the same digits on two horizontal rows."""
    image = cv2.resize(enhanced, (600, 132))
    thresholds = [
        char_conf_threshold,
        max(char_conf_threshold * 0.55, 0.10),
    ]

    for threshold in thresholds:
        try:
            detections = model_char(image).pred[0]
        except Exception:
            continue

        items = []
        for det in detections:
            conf = det[4].item()
            if conf <= threshold:
                continue
            char = params.char_id_dict.get(str(int(det[5].item())), "")
            if not char or not char.isdigit():
                continue
            x_center = (det[0].item() + det[2].item()) / 2
            y_center = (det[1].item() + det[3].item()) / 2
            items.append((x_center, y_center, char, conf))

        if len(items) < 6:
            continue

        row_texts = _split_items_by_rows(items, image.shape[0])
        rows = []
        for text, conf in row_texts:
            digits = re.sub(r"\D", "", text)
            if len(digits) >= 4:
                rows.append((digits, conf))

        if len(rows) < 2:
            continue

        lengths = [len(row[0]) for row in rows]
        if min(lengths) >= 4 and max(lengths) - min(lengths) <= 2:
            if _similar_digit_rows(rows[0][0], rows[1][0]):
                return True, rows

    return False, []


def remove_blue_strip(crop):
    height, width = crop.shape[:2]
    if width / max(height, 1) >= 2.5:
        return crop[:, int(width * 0.17) :]
    return crop


def _enhance_for_ocr(crop):
    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    blurred = cv2.GaussianBlur(enhanced, (3, 3), 0)
    sharp = cv2.addWeighted(enhanced, 1.4, blurred, -0.4, 0)
    return cv2.cvtColor(sharp, cv2.COLOR_GRAY2RGB)


def _row_image(crop, start_ratio, end_ratio):
    height, width = crop.shape[:2]
    start = int(height * start_ratio)
    end = max(int(height * end_ratio), start + 1)
    row = crop[start:end, :]
    pad = max(height - row.shape[0], 0)
    padded = cv2.copyMakeBorder(
        row, 0, pad, 0, 0, cv2.BORDER_CONSTANT, value=(255, 255, 255)
    )
    return cv2.resize(padded, (600, 132))


def _top_row_image(crop):
    return _row_image(crop, 0.0, 0.55)


def _bottom_row_image(crop):
    return _row_image(crop, 0.50, 1.0)


def _bottom_row_otsu(crop):
    row = _bottom_row_image(crop)
    gray = cv2.cvtColor(row, cv2.COLOR_RGB2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return cv2.cvtColor(binary, cv2.COLOR_GRAY2RGB)


def _contrast_stretch(row):
    gray = cv2.cvtColor(row, cv2.COLOR_RGB2GRAY)
    low = float(gray.min())
    high = float(gray.max())
    if high - low < 16:
        return row
    stretched = ((gray - low) * (255.0 / (high - low))).astype("uint8")
    return cv2.cvtColor(stretched, cv2.COLOR_GRAY2RGB)


def _upscale_if_small(crop, min_width=420):
    height, width = crop.shape[:2]
    if width >= min_width:
        return crop
    scale = min_width / width
    return cv2.resize(
        crop,
        (int(width * scale), int(height * scale)),
        interpolation=cv2.INTER_CUBIC,
    )


def _resize_row(row, width=900, height=198):
    return cv2.resize(row, (width, height), interpolation=cv2.INTER_CUBIC)


def _collect_digit_items(detections, params, threshold, image_width):
    items = []
    for det in detections:
        conf = det[4].item()
        if conf <= threshold:
            continue
        char = params.char_id_dict.get(str(int(det[5].item())), "")
        if not char or not char.isdigit():
            continue
        x_center = (det[0].item() + det[2].item()) / 2
        items.append((x_center, char, conf))

    if not items:
        return []

    min_gap = max(image_width * 0.045, 8)
    sorted_items = sorted(items, key=lambda item: item[0])
    merged = [sorted_items[0]]
    for item in sorted_items[1:]:
        if item[0] - merged[-1][0] < min_gap:
            if item[2] > merged[-1][2]:
                merged[-1] = item
        else:
            merged.append(item)
    return merged


def _items_to_text(items):
    if not items:
        return "", 0.0
    items = sorted(items, key=lambda item: item[0])
    text = "".join(item[1] for item in items)
    conf = sum(item[2] for item in items) / len(items)
    return text, conf


def _vote_digit_strings(candidates):
    valid = [
        (text, conf)
        for text, conf in candidates
        if text and text.isdigit() and len(text) in FREEZONE_DIGIT_LENGTHS
    ]
    if not valid:
        return None

    by_length = {}
    for text, conf in valid:
        by_length.setdefault(len(text), []).append((text, conf))

    best_len = max(
        by_length.keys(),
        key=lambda length: (len(by_length[length]), sum(conf for _, conf in by_length[length])),
    )
    group = by_length[best_len]

    result = []
    confidences = []
    for index in range(best_len):
        votes = {}
        for text, conf in group:
            if index < len(text):
                votes[text[index]] = votes.get(text[index], 0.0) + conf
        if not votes:
            continue
        best_char = max(votes.items(), key=lambda item: item[1])[0]
        result.append(best_char)
        confidences.append(max(votes.values()) / len(group))

    if not result:
        return None

    return "".join(result), sum(confidences) / len(confidences)


def _run_digit_ocr(model_char, image, params, thresholds):
    readings = []
    width = image.shape[1]
    for threshold in thresholds:
        try:
            detections = model_char(image).pred[0]
        except Exception:
            continue
        items = _collect_digit_items(detections, params, threshold, width)
        text, conf = _items_to_text(items)
        if text:
            readings.append((text, conf))
    return readings


def _read_freezone_consensus(model_char, white, enhanced, params, char_conf_threshold):
    thresholds = [
        char_conf_threshold,
        max(char_conf_threshold * 0.55, 0.10),
        max(char_conf_threshold * 0.35, 0.08),
    ]

    bottom_variants = [
        ("freezone_bottom", _bottom_row_image(enhanced)),
        ("freezone_bottom_white", _bottom_row_image(white)),
        ("freezone_bottom_large", _resize_row(_bottom_row_image(enhanced))),
        ("freezone_bottom_otsu", _bottom_row_otsu(enhanced)),
        ("freezone_bottom_white_large", _resize_row(_bottom_row_image(white))),
        ("freezone_bottom_contrast", _contrast_stretch(_bottom_row_image(enhanced))),
        ("freezone_bottom_contrast_large", _resize_row(_contrast_stretch(_bottom_row_image(enhanced)))),
    ]

    all_readings = []
    strategy_readings = {}
    for strategy_name, image in bottom_variants:
        readings = _run_digit_ocr(model_char, image, params, thresholds)
        strategy_readings[strategy_name] = readings
        all_readings.extend(readings)

    voted = _vote_digit_strings(all_readings)
    if voted:
        text, conf = voted
        return {
            "text": normalize_plate_text(text, "freezone"),
            "conf": conf,
            "strategy": "freezone_consensus",
        }

    best_text = ""
    best_conf = 0.0
    best_strategy = ""
    for strategy_name, readings in strategy_readings.items():
        for text, conf in readings:
            if len(text) in FREEZONE_DIGIT_LENGTHS and conf > best_conf:
                best_text = text
                best_conf = conf
                best_strategy = strategy_name

    if best_text:
        return {
            "text": normalize_plate_text(best_text, "freezone"),
            "conf": best_conf,
            "strategy": best_strategy or "freezone_bottom",
        }

    return None


def merge_plate_boxes(boxes):
    if len(boxes) <= 1:
        return boxes

    merged = [dict(box) for box in boxes]
    changed = True
    while changed:
        changed = False
        groups = []
        used = [False] * len(merged)

        for index, box in enumerate(merged):
            if used[index]:
                continue
            group = dict(box)
            used[index] = True

            for other_index, other in enumerate(merged):
                if used[other_index]:
                    continue
                if _should_merge_boxes(group, other):
                    group = _union_box(group, other)
                    used[other_index] = True
                    changed = True

            groups.append(group)

        merged = groups

    merged.sort(key=lambda item: item["conf"], reverse=True)
    return merged


def _should_merge_boxes(a, b):
    y_overlap = min(a["ymax"], b["ymax"]) - max(a["ymin"], b["ymin"])
    height_a = a["ymax"] - a["ymin"]
    height_b = b["ymax"] - b["ymin"]
    min_height = max(min(height_a, height_b), 1)

    if y_overlap < min_height * 0.35:
        return False

    horizontal_gap = max(b["xmin"] - a["xmax"], a["xmin"] - b["xmax"], 0)
    avg_width = ((a["xmax"] - a["xmin"]) + (b["xmax"] - b["xmin"])) / 2
    return horizontal_gap <= avg_width * 0.8


def _union_box(a, b):
    return {
        "xmin": min(a["xmin"], b["xmin"]),
        "ymin": min(a["ymin"], b["ymin"]),
        "xmax": max(a["xmax"], b["xmax"]),
        "ymax": max(a["ymax"], b["ymax"]),
        "conf": max(a["conf"], b["conf"]),
    }


def extract_plate_boxes(plates_result, conf_threshold):
    boxes = []
    for _, plate in plates_result.iterrows():
        conf = float(plate["confidence"])
        if conf < conf_threshold:
            continue
        boxes.append(
            {
                "xmin": int(plate["xmin"]),
                "ymin": int(plate["ymin"]),
                "xmax": int(plate["xmax"]),
                "ymax": int(plate["ymax"]),
                "conf": conf,
            }
        )
    return merge_plate_boxes(boxes)


def _detections_to_text(
    detections, params, char_conf_threshold, digits_only=False, row_filter=None, img_shape=None
):
    items = []
    for det in detections:
        conf = det[4].item()
        if conf <= char_conf_threshold:
            continue
        char = params.char_id_dict.get(str(int(det[5].item())), "")
        if not char:
            continue
        if digits_only and not char.isdigit():
            continue
        x_center = (det[0].item() + det[2].item()) / 2
        y_center = (det[1].item() + det[3].item()) / 2
        items.append((x_center, y_center, char, conf))

    if not items:
        return "", 0.0

    if img_shape is not None and row_filter == "top":
        mid_y = img_shape[0] / 2
        items = [item for item in items if item[1] < mid_y * 1.12]
    elif img_shape is not None and row_filter == "bottom":
        mid_y = img_shape[0] / 2
        items = [item for item in items if item[1] > mid_y * 0.88]
    elif img_shape is not None and row_filter is None and digits_only:
        row_texts = _split_items_by_rows(items, img_shape[0])
        if row_texts:
            return max(row_texts, key=lambda item: len(item[0]))

    if not items:
        return "", 0.0

    items.sort(key=lambda item: item[0])
    chars = [item[2] for item in items]
    confidences = [item[3] for item in items]
    return "".join(chars), sum(confidences) / len(confidences)


def _split_items_by_rows(items, image_height):
    if len(items) < 3:
        text = "".join(item[2] for item in sorted(items, key=lambda item: item[0]))
        confidences = [item[3] for item in items]
        if not confidences:
            return []
        return [(text, sum(confidences) / len(confidences))]

    ys = [item[1] for item in items]
    if max(ys) - min(ys) <= image_height * 0.15:
        text = "".join(item[2] for item in sorted(items, key=lambda item: item[0]))
        confidences = [item[3] for item in items]
        return [(text, sum(confidences) / len(confidences))]

    y_split = (min(ys) + max(ys)) / 2
    rows = [[], []]
    for item in items:
        rows[0 if item[1] < y_split else 1].append(item)

    results = []
    for row_items in rows:
        if not row_items:
            continue
        row_items.sort(key=lambda item: item[0])
        text = "".join(item[2] for item in row_items)
        confidences = [item[3] for item in row_items]
        results.append((text, sum(confidences) / len(confidences)))
    return results


def _has_national_letter(text):
    if not text:
        return False
    for code in NATIONAL_LETTER_CODES:
        if code in text:
            return True
    return bool(re.search(r"\d[A-Za-z]+\d", text))


def _is_valid_national(text):
    return bool(NATIONAL_PATTERN.match(text or ""))


def _is_digits_only_freezone(text, two_row=False):
    digits = re.sub(r"\D", "", text or "")
    if not digits or re.search(r"[A-Za-z]", text):
        return False
    if len(digits) in (7, 8):
        return True
    return len(digits) == 5 and two_row


def classify_plate_type(text, two_row=False):
    if not text:
        return "unknown"

    if _is_valid_national(text):
        return "national"

    if _has_national_letter(text):
        return "national"

    if _is_digits_only_freezone(text, two_row=two_row):
        return "freezone"

    return "unknown"


def normalize_plate_text(text, plate_type=None):
    if not text:
        return text

    if plate_type is None:
        plate_type = classify_plate_type(text)

    if plate_type == "national":
        return text

    digits = re.sub(r"\D", "", text)
    digits = _dedupe_freezone_digits(digits)
    return _format_freezone_digits(digits)


def _format_freezone_digits(digits):
    if len(digits) == 7:
        return f"{digits[:5]}{digits[5:]}"
    if len(digits) == 8:
        return digits
    if len(digits) >= 5:
        return digits[:5] if len(digits) <= 6 else digits[:8]
    return digits


def _dedupe_freezone_digits(digits):
    if len(digits) <= 7:
        return digits

    half = len(digits) // 2
    if digits[:half] == digits[half : half * 2]:
        return digits[:half]

    if len(digits) == 10 and digits[:5] == digits[5:]:
        return digits[:5]

    return digits


def _run_ocr_strategies(model_char, strategies, params, thresholds):
    candidates = []
    for threshold in thresholds:
        for strategy_name, image, digits_only, row_filter in strategies:
            try:
                detections = model_char(image).pred[0]
                text, conf = _detections_to_text(
                    detections,
                    params,
                    threshold,
                    digits_only=digits_only,
                    row_filter=row_filter,
                    img_shape=image.shape[:2],
                )
            except Exception:
                continue
            if not text:
                continue

            plate_type = classify_plate_type(text)
            normalized = normalize_plate_text(text, plate_type)
            candidates.append(
                {
                    "text": normalized,
                    "conf": conf,
                    "strategy": strategy_name,
                    "plate_type": plate_type,
                }
            )
    return candidates


def _score_national(candidate):
    text = candidate["text"]
    score = candidate["conf"]
    if _is_valid_national(text):
        return score * 10.0
    if _has_national_letter(text):
        return score * 5.0
    if re.search(r"[A-Za-z]", text):
        return score * 3.0

    digits = re.sub(r"\D", "", text)
    if len(digits) >= 6:
        return score * 1.5
    return score * 0.2


def _best_valid_national(candidates):
    valid = [item for item in candidates if _is_valid_national(item["text"])]
    if not valid:
        return None
    return max(valid, key=_score_national)


def _resolve_plate_reading(
    national_candidates,
    freezone_candidates,
    consensus_freezone,
    two_row_detected,
    two_row_rows,
):
    best_national = _pick_best(national_candidates, _score_national)
    best_freezone = _pick_best(freezone_candidates, _score_freezone)

    valid_national = _best_valid_national(national_candidates)
    if valid_national:
        return _finalize_national_candidate(valid_national)

    if best_national and re.search(r"[A-Za-z]", best_national["text"]):
        return _finalize_national_candidate(best_national)

    if two_row_detected:
        national_with_letter = any(
            re.search(r"[A-Za-z]", item["text"]) for item in national_candidates
        )
        if not national_with_letter:
            if consensus_freezone:
                return _finalize_freezone_candidate(consensus_freezone)
            if best_freezone:
                return _finalize_freezone_candidate(best_freezone)

            voted = _vote_digit_strings(list(two_row_rows))
            if voted:
                text, conf = voted
                return (
                    normalize_plate_text(text, "freezone"),
                    conf,
                    "freezone",
                    "two_row_detect",
                )

    if best_freezone:
        freezone_digits = re.sub(r"\D", "", best_freezone["text"])
        if len(freezone_digits) in (7, 8):
            return _finalize_freezone_candidate(best_freezone)

    if best_national:
        national_digits = re.sub(r"\D", "", best_national["text"])
        freezone_digits = re.sub(r"\D", "", best_freezone["text"]) if best_freezone else ""
        if re.search(r"[A-Za-z]", best_national["text"]) or len(national_digits) > len(freezone_digits):
            plate_type = classify_plate_type(best_national["text"], two_row=two_row_detected)
            if plate_type == "unknown":
                if re.search(r"[A-Za-z]", best_national["text"]) or not two_row_detected:
                    plate_type = "national"
            return (
                best_national["text"],
                best_national["conf"],
                plate_type,
                best_national["strategy"],
            )

    if best_freezone and two_row_detected:
        return _finalize_freezone_candidate(best_freezone)

    if best_national:
        plate_type = classify_plate_type(best_national["text"], two_row=two_row_detected)
        return (
            best_national["text"],
            best_national["conf"],
            plate_type,
            best_national["strategy"],
        )

    if best_freezone:
        return _finalize_freezone_candidate(best_freezone)

    return "", 0.0, "unknown", ""


def _score_freezone(candidate):
    digits = re.sub(r"\D", "", candidate["text"])
    if re.search(r"[A-Za-z]", candidate["text"]):
        return 0.0
    if len(digits) not in FREEZONE_DIGIT_LENGTHS:
        if len(digits) < 5:
            return 0.0
        return candidate["conf"] * len(digits) * 0.5

    length_bonus = {5: 1.4, 7: 1.6, 8: 1.5}.get(len(digits), 1.0)
    strategy = candidate.get("strategy", "")
    strategy_bonus = 1.0
    if strategy == "freezone_consensus":
        strategy_bonus = 2.0
    elif "bottom" in strategy:
        strategy_bonus = 1.6

    return candidate["conf"] * (len(digits) ** 1.5) * length_bonus * strategy_bonus


def _pick_best(candidates, scorer):
    scored = [(scorer(item), item) for item in candidates]
    scored = [(score, item) for score, item in scored if score > 0]
    if not scored:
        return None
    return max(scored, key=lambda pair: pair[0])[1]


def _finalize_freezone_candidate(candidate):
    digits = re.sub(r"\D", "", candidate["text"])
    normalized = normalize_plate_text(digits, "freezone")
    return (
        normalized or digits or candidate["text"],
        candidate["conf"],
        "freezone",
        candidate["strategy"],
    )


def _finalize_national_candidate(candidate):
    return (
        candidate["text"],
        candidate["conf"],
        "national",
        candidate["strategy"],
    )


def read_plate_text(model_char, crop, params, char_conf_threshold):
    """Run national and free-zone OCR, then pick the best supported result."""
    crop = _upscale_if_small(crop)
    white = remove_blue_strip(crop)
    enhanced = _enhance_for_ocr(white)
    thresholds = [
        char_conf_threshold,
        max(char_conf_threshold * 0.6, 0.12),
        max(char_conf_threshold * 0.4, 0.08),
    ]

    two_row_detected, two_row_rows = detect_two_row_layout(
        model_char, enhanced, params, char_conf_threshold
    )

    national_strategies = [
        ("national_std", cv2.resize(crop, (600, 132)), False, None),
        ("national_enhanced", cv2.resize(_enhance_for_ocr(crop), (600, 132)), False, None),
        ("national_white", cv2.resize(white, (600, 132)), False, None),
        ("national_large", cv2.resize(_enhance_for_ocr(crop), (800, 176)), False, None),
    ]
    freezone_strategies = [
        ("freezone_bottom", _bottom_row_image(enhanced), True, "bottom"),
        ("freezone_bottom_white", _bottom_row_image(white), True, "bottom"),
        ("freezone_bottom_large", _resize_row(_bottom_row_image(enhanced)), True, "bottom"),
        ("freezone_top", _top_row_image(enhanced), True, "top"),
        ("freezone_enhanced", cv2.resize(enhanced, (600, 132)), True, None),
        ("freezone_white", cv2.resize(white, (600, 132)), True, None),
    ]

    national_candidates = _run_ocr_strategies(
        model_char, national_strategies, params, thresholds
    )
    freezone_candidates = []
    consensus_freezone = None
    if two_row_detected:
        freezone_candidates = _run_ocr_strategies(
            model_char, freezone_strategies, params, thresholds
        )
        consensus_freezone = _read_freezone_consensus(
            model_char, white, enhanced, params, char_conf_threshold
        )
        if consensus_freezone:
            freezone_candidates.append(consensus_freezone)

    return _resolve_plate_reading(
        national_candidates,
        freezone_candidates,
        consensus_freezone,
        two_row_detected,
        two_row_rows,
    )


def recognize_plates(image_rgb, model_plate, model_char, params, plate_conf_threshold, char_conf_threshold):
    plates_result = model_plate(image_rgb).pandas().xyxy[0]
    merged_boxes = extract_plate_boxes(plates_result, plate_conf_threshold)
    results = []

    for box in merged_boxes:
        cropped = image_rgb[box["ymin"] : box["ymax"], box["xmin"] : box["xmax"]]
        if cropped.size == 0:
            continue

        plate_text, char_conf_avg, plate_type, _strategy = read_plate_text(
            model_char, cropped, params, char_conf_threshold
        )
        if not plate_text:
            continue

        digit_count = len(re.sub(r"\D", "", plate_text))
        if plate_type == "unknown" and digit_count < 4:
            continue

        results.append(
            {
                "raw_text": plate_text,
                "plate_type": plate_type,
                "plate_conf": box["conf"],
                "char_conf_avg": char_conf_avg,
                "bbox": (box["xmin"], box["ymin"], box["xmax"], box["ymax"]),
            }
        )

    if len(results) > 1:
        results.sort(
            key=lambda item: (
                len(re.sub(r"\D", "", item["raw_text"])),
                item["plate_conf"],
            ),
            reverse=True,
        )
        results = [results[0]]

    results.sort(key=lambda item: item["plate_conf"], reverse=True)
    return results
