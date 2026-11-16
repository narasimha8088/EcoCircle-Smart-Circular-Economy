"""
description_parser.py — turns the user's free-text item description into
structured fields the rest of the pipeline can use.

The text the user types is the ONLY place details like age, purchase price,
brand, weight, condition and known faults can come from (a photo can't tell
you an item is "3 years old" or "bought for ₹45,000"). Previously the text was
only appended to the Gemini prompt; none of it reached the numeric models
(M5 carbon, M6 resale), and nothing was echoed back to the user.

parse_description() is pure Python (no ML deps, no network) so it is fast,
deterministic and unit-testable.
"""

from __future__ import annotations

import re
from typing import Optional

MAX_DESCRIPTION_CHARS = 500

# ── Vocabulary ────────────────────────────────────────────────────────────────
CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "mobile":      ("phone", "smartphone", "mobile", "iphone", "galaxy", "pixel", "redmi",
                    "oneplus", "realme", "android", "oppo", "vivo", "motorola", "nokia", "poco", "iqoo",
                    "handset", "cellphone", "sim card"),
    "laptop":      ("laptop", "notebook", "macbook", "thinkpad", "chromebook", "ultrabook"),
    "appliance":   ("fridge", "refrigerator", "washing machine", "microwave", "mixer",
                    "grinder", "blender", "oven", "toaster", "fan", "cooler", "air conditioner",
                    "ac ", "heater", "geyser", "steam iron", "kettle", "vacuum", "purifier",
                    "induction", "cooker"),
    "furniture":   ("chair", "table", "sofa", "couch", "bed", "mattress", "shelf", "bookshelf",
                    "wardrobe", "cupboard", "desk", "cabinet", "stool"),
    "clothing":    ("shirt", "t-shirt", "jeans", "jacket", "dress", "saree", "kurta", "shoes",
                    "sneakers", "coat", "sweater", "clothes", "bag", "backpack", "tshirt", "hoodie", "trousers",
                    "pants", "skirt", "leggings", "blazer", "suit", "uniform", "shorts", "top", "tops",
                    "lehenga", "salwar", "hoodies", "jumper", "clothing", "garment", "garments"),
    "vehicle":     ("bike", "bicycle", "cycle", "scooter", "car", "motorcycle", "tyre", "tire"),
    "electronics": ("tv", "television", "monitor", "speaker", "headphones", "earphones",
                    "earbuds", "camera", "tablet", "ipad", "console", "playstation", "xbox",
                    "router", "printer", "charger", "keyboard", "mouse", "smartwatch",
                    "power bank", "projector", "microphone", "battery", "gadget"),
}

KNOWN_BRANDS = (
    "apple", "samsung", "sony", "lg", "dyson", "bose", "dell", "hp", "lenovo", "asus", "acer",
    "ikea", "philips", "bosch", "whirlpool", "xiaomi", "mi", "redmi", "realme", "oppo", "vivo",
    "oneplus", "motorola", "nokia", "google", "intex", "micromax", "lava", "karbonn", "boat",
    "jbl", "canon", "nikon", "panasonic", "godrej", "voltas", "bajaj", "havells", "prestige",
    "hitachi", "haier", "toshiba", "microsoft", "nintendo", "hero", "honda", "tvs", "yamaha",
    "nike", "adidas", "puma", "levis", "zara", "h&m", "tata", "usha", "orient", "crompton",
)

# condition tier -> trigger phrases (checked worst-first so "cracked screen, otherwise good" => poor/fair)
CONDITION_PHRASES: list[tuple[str, tuple[str, ...]]] = [
    ("poor", ("not working", "doesn't work", "does not work", "dead", "broken", "shattered",
              "won't turn on", "wont turn on", "won't start", "no power", "burnt", "burned",
              "water damage", "beyond repair", "junk", "scrap", "totally damaged")),
    ("fair", ("cracked", "crack", "scratched", "scratches", "dent", "dented", "worn", "faded",
              "chipped", "torn", "stain", "stained", "battery drains", "battery issue",
              "weak battery", "loose", "rust", "rusty", "peeling", "fair condition")),
    ("new",  ("brand new", "unused", "never used", "sealed", "unopened", "like new", "mint")),
    ("good", ("good condition", "working fine", "works fine", "works well", "fully working",
              "fully functional", "well maintained", "well-maintained", "excellent")),
]

ISSUE_PHRASES = (
    "cracked screen", "cracked", "broken screen", "shattered", "not working", "doesn't work",
    "does not work", "won't turn on", "wont turn on", "battery drains", "battery issue",
    "weak battery", "swollen battery", "water damage", "scratched", "scratches", "dent", "dented",
    "torn", "stain", "rust", "rusty", "loose hinge", "broken hinge", "faulty", "noisy",
    "overheating", "overheats", "slow", "no charging", "charging port", "not charging",
    "stuck", "leaking", "leak", "missing", "chipped", "faded", "peeling",
)

ACTION_HINTS: list[tuple[str, tuple[str, ...]]] = [
    ("donate",  ("donate", "donation", "give away", "give it away", "charity", "ngo")),
    ("resell",  ("sell", "resell", "resale", "sale", "list it", "marketplace", "olx")),
    ("repair",  ("repair", "fix", "get it fixed", "service it", "refurbish")),
    ("recycle", ("recycle", "recycling", "e-waste", "ewaste", "scrap", "dispose", "throw")),
    ("keep",    ("keep using", "keep it", "continue using")),
]

_NUM = r"(\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
_WORD_NUMS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
              "eight": 8, "nine": 9, "ten": 10, "half": 0.5, "a": 1}


def _to_float(s: str) -> float:
    return float(s.replace(",", ""))


def _word_boundary_find(text: str, phrase: str) -> bool:
    return re.search(r"(?<![a-z0-9])" + re.escape(phrase.strip()) + r"(?![a-z0-9])", text) is not None


def _parse_age_years(text: str) -> Optional[float]:
    """'3 years old', '2 yrs', '18 months', 'bought in 2021', 'a year old', 'six months old'."""
    total = 0.0
    found = False

    word_re = "|".join(sorted(_WORD_NUMS, key=len, reverse=True))
    # years — digits or words
    for m in re.finditer(rf"(?<![a-z0-9])(?:{_NUM}|({word_re}))\s*(?:\+\s*)?(?:years?|yrs?|y/o)\b(?!\s*(?:warranty|guarantee))", text):
        val = _to_float(m.group(1)) if m.group(1) else _WORD_NUMS[m.group(2)]
        total += val
        found = True
    # months
    for m in re.finditer(rf"(?<![a-z0-9])(?:{_NUM}|({word_re}))\s*(?:months?|mos?)\b", text):
        val = _to_float(m.group(1)) if m.group(1) else _WORD_NUMS[m.group(2)]
        total += val / 12.0
        found = True
    if found:
        return round(min(total, 60.0), 2)

    # "bought/purchased/since/from <year>"
    m = re.search(r"(?:bought|purchased|since|from|in|year)\s*(?:in\s*)?((?:19|20)\d{2})\b", text)
    if m:
        from datetime import date
        yr = int(m.group(1))
        age = date.today().year - yr
        if 0 <= age <= 60:
            return float(age)
    return None


def _parse_price_inr(text: str) -> Optional[float]:
    """'₹45,000', 'rs 45000', 'inr 45k', 'bought for 45000', '45k', '1.2 lakh'."""
    # lakh / k suffix
    m = re.search(rf"(?:₹|rs\.?|inr)\s*{_NUM}\s*(lakhs?|lacs?|k|thousand)?", text)
    if not m:
        m = re.search(rf"{_NUM}\s*(lakhs?|lacs?|k|thousand)\s*(?:rs|rupees|inr)?\b", text)
        if m:
            num, suf = _to_float(m.group(1)), m.group(2)
        else:
            m2 = re.search(rf"{_NUM}\s*(?:rs|rupees|inr)\b", text)
            if m2:
                num, suf = _to_float(m2.group(1)), None
            else:
                m3 = re.search(rf"(?:bought|purchased|paid|cost|costs|price|worth|priced)\s*(?:it\s*)?(?:for|at|of|was|is|:)?\s*{_NUM}\s*(lakhs?|lacs?|k|thousand)?", text)
                if not m3:
                    return None
                num, suf = _to_float(m3.group(1)), m3.group(2)
    else:
        num, suf = _to_float(m.group(1)), m.group(2)

    if suf:
        if suf.startswith(("lakh", "lac")):
            num *= 100_000
        else:
            num *= 1_000
    # Guard against picking up a year/size by accident
    if num < 10 or num > 50_000_000:
        return None
    if 1900 <= num <= 2100 and not suf:
        return None
    return float(num)


def _parse_weight_kg(text: str) -> Optional[float]:
    m = re.search(rf"{_NUM}\s*(kgs?|kilograms?|kilos?)\b", text)
    if m:
        v = _to_float(m.group(1))
        return v if 0 < v <= 2000 else None
    m = re.search(rf"{_NUM}\s*(g|grams?|gms?)\b", text)
    if m:
        v = _to_float(m.group(1)) / 1000.0
        return v if 0 < v <= 2000 else None
    return None


def _detect_category(text: str) -> Optional[str]:
    best, best_pos = None, 10 ** 9
    for cat, words in CATEGORY_KEYWORDS.items():
        for w in words:
            m = re.search(r"(?<![a-z0-9])" + re.escape(w.strip()) + r"(?![a-z0-9])", text)
            if m and m.start() < best_pos:
                best, best_pos = cat, m.start()
    return best


def _detect_brand(text: str) -> Optional[str]:
    for b in KNOWN_BRANDS:
        if _word_boundary_find(text, b):
            return b
    return None


def _detect_condition(text: str) -> Optional[str]:
    for tier, phrases in CONDITION_PHRASES:
        for p in phrases:
            if _word_boundary_find(text, p):
                return tier
    return None


_ISSUE_REGEX = (
    (r"battery\s+(?:is\s+|are\s+|was\s+|has\s+been\s+|seems\s+|got\s+)?(?:very\s+|really\s+|too\s+|quite\s+|so\s+)?"
     r"(?:weak|bad|poor|dead|draining|drains?|low|swollen|degraded|old|short|not\s+lasting|not\s+working)", "weak battery"),
    (r"(?:weak|bad|poor|dead|degraded|old|swollen)\s+battery", "weak battery"),
    (r"(?:screen|display)\s+(?:is\s+|has\s+)?(?:cracked|broken|shattered|flickering|blank|dead|damaged)", "damaged screen"),
    (r"(?:cracked|broken|shattered)\s+(?:screen|display)", "damaged screen"),
    (r"(?:not|isn't|isnt|won't|wont)\s+(?:charging|charge)", "not charging"),
    (r"(?:overheat\w*|gets?\s+(?:very\s+)?hot)", "overheating"),
    (r"(?:speaker|mic|microphone|camera|keyboard|touchpad|hinge|port)\s+(?:is\s+)?(?:not\s+working|broken|dead|damaged|loose)", "damaged component"),
)


def _detect_issues(text: str) -> list[str]:
    issues: list[str] = []
    for pattern, label in _ISSUE_REGEX:
        if re.search(pattern, text) and label not in issues:
            issues.append(label)
    for p in sorted(ISSUE_PHRASES, key=len, reverse=True):
        if _word_boundary_find(text, p) and not any(p in i for i in issues):
            issues.append(p)
    # Drop near-duplicates covered by a more specific label
    redundant = set()
    if "damaged screen" in issues:
        redundant |= {"cracked", "cracked screen", "broken screen", "shattered"}
    if "weak battery" in issues:
        redundant |= {"battery drains", "battery issue", "swollen battery"}
    issues = [i for i in issues if i not in redundant]
    return issues[:8]


_STOP_USING_PATTERNS = (
    r"\b(?:do\s*n'?o?t|dont|don't|no longer|not)\s+(?:want|wan|wish|like|need|plan)(?:\s+to|\s+2)?\s+(?:use|using|keep|keeping)\b",
    r"\b(?:do\s*n'?o?t|dont|don't)\s+(?:want|wan|need)\s+it\b",
    r"\bno\s+longer\s+(?:use|using|need|want|needed|wanted)\b",
    r"\b(?:not|never)\s+using\s+(?:it|this)\b",
    r"\bstopped\s+using\b",
    r"\bget(?:ting)?\s+rid\s+of\b",
    r"\bno\s+use\s+(?:to\s+me|for\s+me)\b",
    r"\bwant\s+to\s+(?:get\s+rid|discard|let\s+go)\b",
    r"\bdon'?t\s+use\s+it\b",
)


def _detect_action(text: str) -> Optional[str]:
    # An explicit "I don't want to use it further" must beat any other hint
    # (e.g. "weak battery" contains no action word, but "so what to do" is a request for advice).
    explicit = None
    for action, words in ACTION_HINTS:
        if action in ("donate", "resell", "recycle"):
            for w in words:
                if _word_boundary_find(text, w):
                    explicit = action
                    break
        if explicit:
            break
    if explicit:
        return explicit
    for pat in _STOP_USING_PATTERNS:
        if re.search(pat, text):
            return "stop_using"
    for action, words in ACTION_HINTS:
        for w in words:
            if _word_boundary_find(text, w):
                return action
    return None


def parse_description(raw: str | None) -> dict:
    """
    Parse free-text into structured hints. Every field is None / [] when the
    text doesn't state it — callers must treat missing values as "unknown",
    never invent them.
    """
    text_raw = (raw or "").strip()
    # Collapse whitespace & clip (the UI already caps at 500, but never trust the client)
    text_raw = re.sub(r"\s+", " ", text_raw)[:MAX_DESCRIPTION_CHARS]
    low = text_raw.lower()

    parsed = {
        "text":           text_raw,
        "has_text":       bool(text_raw),
        "category":       None,
        "brand":          None,
        "age_years":      None,
        "purchase_price": None,
        "weight_kg":      None,
        "condition":      None,
        "issues":         [],
        "intended_action": None,
    }
    if not text_raw:
        return parsed

    parsed["category"]        = _detect_category(low)
    parsed["brand"]           = _detect_brand(low)
    parsed["age_years"]       = _parse_age_years(low)
    parsed["purchase_price"]  = _parse_price_inr(low)
    parsed["weight_kg"]       = _parse_weight_kg(low)
    parsed["condition"]       = _detect_condition(low)
    parsed["issues"]          = _detect_issues(low)
    parsed["intended_action"] = _detect_action(low)
    # Reported faults with no stated condition => not "good"
    if parsed["issues"] and not parsed["condition"]:
        parsed["condition"] = "fair"
    return parsed


def understood_fields(parsed: dict) -> list[dict]:
    """Human-readable list of what was understood — shown back to the user."""
    out = []
    labels = [
        ("category",        "Item type",        lambda v: str(v).title()),
        ("brand",           "Brand",            lambda v: str(v).upper() if len(str(v)) <= 3 else str(v).title()),
        ("age_years",       "Age",              lambda v: f"{v:g} year{'s' if v != 1 else ''}"),
        ("purchase_price",  "Purchase price",   lambda v: f"₹{v:,.0f}"),
        ("weight_kg",       "Weight",           lambda v: f"{v:g} kg"),
        ("condition",       "Condition",        lambda v: str(v).title()),
        ("intended_action", "You want to",      lambda v: {"stop_using": "Stop using it"}.get(v, str(v).replace("_", " ").title())),
    ]
    for key, label, fmt in labels:
        v = parsed.get(key)
        if v not in (None, "", []):
            out.append({"key": key, "label": label, "value": fmt(v)})
    if parsed.get("issues"):
        out.append({"key": "issues", "label": "Reported issues", "value": ", ".join(parsed["issues"])})
    return out
