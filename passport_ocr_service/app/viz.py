"""
Visual inspection zone (VIZ): the printed, human-readable text of the passport pages.

The MRZ only carries the core identity fields. Everything else — place of birth, issue date, issuing
authority, and on many passports a personal-data page with parents' names, address, phone number and
emergency contact — exists only as printed text. This module reads it with whole-page OCR and maps
values to their printed captions.

Layout rules:
  * Data page (ICAO 9303 Part 4): the caption sits ABOVE its value ("Date of birth" / "01 APR 1995").
  * Personal-data / observations pages: the caption sits LEFT of its value ("Telephone No: +880…").
Captions are matched loosely (OCR garbles them, bilingual captions carry a native-script prefix).

Every value carries a confidence (0–1) from Tesseract's word confidences, agreement between the
preprocessing variants, and pattern validation (dates, phone numbers, document numbers).
"""

import datetime
import difflib
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
import pytesseract

_PAGE_WIDTH = 2400
_CONFIG = "--oem 1 --psm 11"
# Extra whole-page reads, only for confirming an MRZ number correction the shared reads did not settle
_EXTRA_READS = ((1600, "--oem 1 --psm 11"), (2000, "--oem 1 --psm 3"))

# Tesseract runs as a subprocess, so threads give real parallelism (it is single-threaded: OMP_THREAD_LIMIT=1)
POOL = ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 2), thread_name_prefix="ocr")
_MIN_WORD_CONF = 20

# (field, caption variants, value position). "below" = data page, "right" = personal-data page.
_CAPTIONS: List[Tuple[str, Tuple[str, ...], str]] = [
    ("surname", ("surname", "nom"), "below"),
    ("given_names", ("given names", "given name", "prenoms"), "below"),
    ("nationality", ("nationality", "nationalite"), "below"),
    ("personal_number", ("personal no", "personal number", "personal no."), "below"),
    ("date_of_birth", ("date of birth", "date de naissance"), "below"),
    ("previous_passport_number", ("previous passport no", "previous passport"), "below"),
    ("place_of_birth", ("place of birth", "lieu de naissance"), "below"),
    ("date_of_issue", ("date of issue", "date de delivrance"), "below"),
    ("issuing_authority", ("issuing authority", "authority", "autorite"), "below"),
    ("date_of_expiry", ("date of expiry", "date d expiration"), "below"),
    ("passport_number", ("passport number", "passport no", "no de passeport"), "below"),
    ("father_name", ("father s name", "fathers name", "father name"), "right"),
    ("mother_name", ("mother s name", "mothers name", "mother name"), "right"),
    ("spouse_name", ("spouse s name", "spouses name", "spouse name"), "right"),
    ("legal_guardian_name", ("legal guardian s name", "legal guardian name", "guardian s name"), "right"),
    ("permanent_address", ("permanent address",), "right"),
    ("present_address", ("present address", "current address"), "right"),
    ("relationship", ("relationship",), "right"),
    ("telephone", ("telephone no", "telephone", "phone no", "mobile no", "contact no"), "right"),
    ("emergency_contact", ("emergency contact",), "section"),
    # Short captions: exact match only (fuzzy matching would hit ordinary words)
    ("name", ("name",), "right"),
    ("address", ("address",), "right"),
]
_EXACT_ONLY = {"name", "address", "nom"}
_EMERGENCY_FIELDS = {"name": "emergency_contact_name", "relationship": "emergency_contact_relationship",
                     "address": "emergency_contact_address", "telephone": "emergency_contact_telephone"}
_HOLDER_FIELDS = {"name": "full_name", "address": "address"}
_MIN_CONFIDENCE = 0.4  # below this a value is more likely OCR noise than text
# Words of captions — a line made of them is a caption, never a value (e.g. the authority's neighbour)
_CAPTION_WORDS = {"DATE", "OF", "ISSUE", "EXPIRY", "BIRTH", "HOLDER", "HOLDERS", "SIGNATURE", "NAME", "SEX",
                  "AUTHORITY", "ISSUING", "PLACE", "NATIONALITY", "SURNAME", "GIVEN", "PASSPORT", "NO", "TYPE",
                  "CODE", "COUNTRY", "PERSONAL", "PREVIOUS", "S"}
# Words that only ever appear in captions: a name/place/authority value containing one is a misplaced caption
_CAPTION_ONLY = {"DATE", "EXPIRY", "BIRTH", "HOLDER", "HOLDERS", "SIGNATURE", "AUTHORITY", "NATIONALITY",
                 "SURNAME", "PASSPORT", "ISSUING", "GIVEN"}

_MONTHS = {m: i for i, m in enumerate(
    ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"), 1)}
_MONTH_FIXES = {"0CT": "OCT", "N0V": "NOV", "J0L": "JUL", "JUI": "JUL", "AUC": "AUG", "5EP": "SEP", "MAV": "MAY"}
_DATE_RE = re.compile(r"\b(\d{1,2})\s*[./-]?\s*([A-Z0-9]{3})[A-Z]*(?:\s*/\s*[A-Z]+)?\s*[./-]?\s*(\d{4})\b")
_NUMERIC_DATE_RE = re.compile(r"\b(\d{2})[./-](\d{2})[./-](\d{4})\b")
_PHONE_RE = re.compile(r"(?<![\d])(\+?\d[\d\s-]{8,16}\d)(?![\d])")
_DOC_NO_RE = re.compile(r"\b([A-Z]{0,3}\d{6,9}[A-Z]{0,2})\b")


@dataclass
class _Line:
    text: str
    conf: float
    left: int
    top: int
    right: int
    bottom: int

    @property
    def height(self) -> int:
        return max(1, self.bottom - self.top)

    @property
    def cy(self) -> float:
        return (self.top + self.bottom) / 2.0


@dataclass
class VizField:
    value: str
    confidence: float


@dataclass
class VizResult:
    fields: Dict[str, VizField] = field(default_factory=dict)
    words: set = field(default_factory=set)       # every word read on the page (upper-case)
    text: str = ""                                  # all page text, letters/digits only, for lookups
    raw: str = ""                                   # all page text with spacing, one OCR line per row


# ----------------------------------------------------------------------------- OCR

def _resize(img: np.ndarray, width: int) -> np.ndarray:
    h, w = img.shape[:2]
    scale = width / float(w)
    return cv2.resize(img, (width, int(h * scale)), interpolation=cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA)


def _variants(page_bgr: np.ndarray) -> List[np.ndarray]:
    """Gray, and the darkest colour channel — coloured security printing fades, black text stays."""
    if page_bgr.ndim == 2:
        return [_resize(page_bgr, _PAGE_WIDTH)]
    return [_resize(page_bgr.min(axis=2), _PAGE_WIDTH),
            _resize(cv2.cvtColor(page_bgr, cv2.COLOR_BGR2GRAY), _PAGE_WIDTH)]


def _ocr_lines(img: np.ndarray, timeout_s: int) -> List[_Line]:
    try:
        d = pytesseract.image_to_data(img, config=_CONFIG, timeout=timeout_s, output_type=pytesseract.Output.DICT)
    except RuntimeError:
        return []
    groups: Dict[tuple, list] = {}
    for i, word in enumerate(d["text"]):
        word = word.strip()
        conf = float(d["conf"][i])
        if not word or conf < _MIN_WORD_CONF:
            continue
        key = (d["block_num"][i], d["par_num"][i], d["line_num"][i])
        groups.setdefault(key, []).append((d["left"][i], d["top"][i], d["width"][i], d["height"][i], word, conf))
    lines = []
    for words in groups.values():
        words.sort()
        lines.append(_Line(
            text=" ".join(w[4] for w in words),
            conf=sum(w[5] for w in words) / (100.0 * len(words)),
            left=min(w[0] for w in words), top=min(w[1] for w in words),
            right=max(w[0] + w[2] for w in words), bottom=max(w[1] + w[3] for w in words),
        ))
    lines.sort(key=lambda l: (l.top, l.left))
    return lines


# ----------------------------------------------------------------------------- captions

def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z ]", " ", text.lower())).strip()


def _caption(line: _Line) -> Optional[Tuple[str, str, str]]:
    """(field, position, value-on-same-line) if the line is a caption. Bilingual: English after the last '/'."""
    raw = line.text
    head, sep, tail = raw.partition(":")
    candidates = {_norm(head), _norm(head.split("/")[-1])}
    best, best_ratio = None, 0.0
    for name, variants, position in _CAPTIONS:
        for variant in variants:
            for cand in candidates:
                if not cand:
                    continue
                if variant in _EXACT_ONLY or len(variant) <= 4:
                    ratio = 1.0 if cand == variant or cand.endswith(" " + variant) and len(cand.split()) <= 2 else 0.0
                elif len(cand.split()) < len(variant.split()):
                    ratio = 0.0  # the page title "PASSPORT" is not the "Passport No" caption
                else:
                    ratio = difflib.SequenceMatcher(None, variant, cand).ratio()
                    # Garbled native-script prefix before the caption ("Sex ere Place of Birth") — but a
                    # section header must stand alone: "PERSONAL DATA AND EMERGENCY CONTACT" is a page title
                    extra = 1 if position == "section" else 3
                    if ratio < 0.8 and cand.endswith(variant) and len(cand.split()) <= len(variant.split()) + extra:
                        ratio = 0.9
                if ratio > best_ratio:
                    best, best_ratio = (name, position), ratio
    if not best or best_ratio < 0.8:
        return None
    inline = tail.strip() if sep else ""
    if len(re.sub(r"[^A-Za-z0-9]", "", inline)) < 4:
        inline = ""  # stray marks after the colon; the value is a separate OCR line
    return best[0], best[1], inline


def _value_right(label: _Line, lines: List[_Line], captions: set) -> List[_Line]:
    row = [l for l in lines if l is not label and id(l) not in captions and l.left > label.right - 5
           and abs(l.cy - label.cy) < 0.7 * max(label.height, l.height)]
    return sorted(row, key=lambda l: l.left)[:3]


def _value_below(label: _Line, lines: List[_Line], captions: set) -> List[_Line]:
    h = label.height
    below = [l for l in lines if l is not label and id(l) not in captions
             and label.bottom - 0.3 * h < l.top < label.bottom + 2.5 * h
             # bilingual captions: the native-script part (often unreadable) extends far to the left
             and label.left - 0.2 * _PAGE_WIDTH < l.left < label.right]
    below.sort(key=lambda l: (l.top, abs(l.left - label.left)))
    # Alternatives only from the same visual row as the nearest line — never from rows further down
    return [l for l in below if l.top < below[0].top + 1.2 * below[0].height][:3] if below else []


def _continuation(first: _Line, lines: List[_Line], captions: set, caption_rows: List[float]) -> List[_Line]:
    """Following lines of a multi-line value (addresses): left-aligned, close below, not on a caption row."""
    out, last = [first], first
    while True:
        nxt = [l for l in lines if l not in out and id(l) not in captions
               and 0 <= l.top - last.bottom < 1.6 * last.height
               and first.left - 3 * first.height < l.left < first.left + 12 * first.height
               and not any(abs(l.cy - row) < 0.6 * l.height for row in caption_rows)]
        if not nxt:
            return out
        last = min(nxt, key=lambda l: l.top)
        # Same row split by OCR into pieces: take them all, left to right
        row = sorted([l for l in lines if l not in out and id(l) not in captions
                      and abs(l.cy - last.cy) < 0.5 * last.height and l.left >= first.left - 3 * first.height],
                     key=lambda l: l.left)
        out.extend(row or [last])


def _value_parts(first: _Line, name: str, position: str, label: _Line, lines: List[_Line],
                 captions: set, caption_rows: List[float]) -> List[_Line]:
    """The value's full extent: same-row pieces (OCR splits on wide gaps) and, for addresses, following lines."""
    same_row = [l for l in lines if id(l) not in captions and abs(l.cy - first.cy) < 0.5 * first.height
                and l.left >= first.left]
    if name.endswith("address") or name == "address":
        row = sorted(same_row, key=lambda l: l.left)
        return row + [l for l in _continuation(first, lines, captions, caption_rows)[1:] if l not in row]
    row = [l for l in same_row if l.left < first.left + 0.45 * _PAGE_WIDTH
           and (position == "right" or l.left < label.right + 4 * label.height)]
    return sorted(row, key=lambda l: l.left) or [first]


def _row_text(parts: List[_Line]) -> Tuple[str, float]:
    text = " ".join(p.text for p in parts).strip(" :;,.|")
    return re.sub(r"\s+", " ", text), sum(p.conf for p in parts) / len(parts)


def fits_validity(d: datetime.date, expiry: datetime.date) -> bool:
    """Passports are valid 5 or 10 years: the issue date sits that far before expiry (± a day or two)."""
    for years in (5, 10):
        try:
            start = expiry.replace(year=expiry.year - years)
        except ValueError:
            start = expiry.replace(year=expiry.year - years, day=28)
        if abs((d - start).days) <= 2:
            return True
    return False


def _issue_and_authority(lines: List[_Line], fields: Dict[str, VizField],
                         dob: Optional[datetime.date], expiry: Optional[datetime.date]) -> None:
    """
    Captions on the data page are often unreadable (security print). The issue date is still
    recognisable: the one printed date that fits the passport's validity period. On ICAO data pages
    the issuing authority is printed on the same row, to its right.
    """
    if not expiry:
        return
    today = datetime.date.today()
    issue_line = None
    for line in lines:
        d = parse_date(line.text)
        if d and d not in (dob, expiry) and d <= today and fits_validity(d, expiry):
            issue_line = line
            if "date_of_issue" not in fields:
                fields["date_of_issue"] = VizField(d.isoformat(), round(min(0.9, line.conf), 2))
            break
    if issue_line is None or "issuing_authority" in fields:
        return
    h = issue_line.height
    row = [l for l in lines if l.left > issue_line.right and abs(l.cy - issue_line.cy) < 1.5 * h
           and parse_date(l.text) is None and len(re.sub(r"[^A-Z]", "", l.text.upper())) >= 3
           and re.fullmatch(r"[A-Za-z][A-Za-z /.,'()-]+", l.text.strip())
           and not set(re.findall(r"[A-Z]+", l.text.upper())) <= _CAPTION_WORDS
           and not _caption(l)]
    if row:
        best = min(row, key=lambda l: l.left)
        fields["issuing_authority"] = VizField(best.text.strip().upper(), round(best.conf * 0.85, 2))


def _extract(lines: List[_Line], dob: Optional[datetime.date] = None,
             expiry: Optional[datetime.date] = None) -> Dict[str, VizField]:
    found = []
    for line in lines:
        hit = _caption(line)
        if hit:
            found.append((line, hit))
    captions = {id(l) for l, _ in found}
    caption_rows = [l.cy for l, _ in found]
    emergency_top = min((l.top for l, (name, _, _) in found if name == "emergency_contact"), default=None)
    # The emergency section ends where the data page starts (first caption with its value below)
    emergency_bottom = min((l.top for l, (_, pos, _) in found if pos == "below" and emergency_top is not None
                            and l.top > emergency_top), default=float("inf"))

    fields: Dict[str, VizField] = {}
    for label, (name, position, inline) in found:
        if position == "section":
            continue
        if emergency_top is not None and emergency_top < label.top < emergency_bottom and name in _EMERGENCY_FIELDS:
            name = _EMERGENCY_FIELDS[name]
        else:
            name = _HOLDER_FIELDS.get(name, name)
        if inline:
            options = [(inline, label.conf)]
        else:
            finder = _value_right if position == "right" else _value_below
            options = [_row_text(_value_parts(first, name, position, label, lines, captions, caption_rows))
                       for first in finder(label, lines, captions)]
        # First candidate that validates: a rejected line (caption text, junk) gives way to the next one
        for text, conf in options:
            value, conf = _validate(name, text, conf)
            if value:
                if name not in fields or conf > fields[name].confidence:
                    fields[name] = VizField(value, round(conf, 2))
                break
    _issue_and_authority(lines, fields, dob, expiry)
    return fields


# ----------------------------------------------------------------------------- validation

def parse_date(text: str) -> Optional[datetime.date]:
    """'01 APR 1995', '16 JUN/JUIN 1986', '04.05.1988' → date."""
    t = text.upper()
    m = _DATE_RE.search(t)
    if m:
        month = _MONTH_FIXES.get(m.group(2), m.group(2))
        if month in _MONTHS:
            try:
                return datetime.date(int(m.group(3)), _MONTHS[month], int(m.group(1)))
            except ValueError:
                return None
    m = _NUMERIC_DATE_RE.search(t)
    if m:
        try:
            return datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    return None


def _validate(name: str, text: str, conf: float) -> Tuple[Optional[str], float]:
    text = text.strip()
    if name.startswith("date_of"):
        d = parse_date(text)
        return (d.isoformat(), conf) if d else (None, 0.0)
    if "telephone" in name:
        m = _PHONE_RE.search(text.replace("O", "0"))
        return (re.sub(r"[\s-]", "", m.group(1)), conf) if m else (None, 0.0)
    if name in ("passport_number", "previous_passport_number"):
        m = _DOC_NO_RE.search(text.upper().replace(" ", ""))
        return (m.group(1), conf) if m else (None, 0.0)
    if name in ("place_of_birth", "issuing_authority"):
        words = re.sub(r"[^A-Za-z /.,'-]", " ", text).upper().split()
        if name == "place_of_birth" and len(words) > 1 and len(words[0]) <= 2:
            words = words[1:]  # the sex letter printed on the same row ("M  LAKSHMIPUR")
        clean = " ".join(words).strip(" ,.-/")
        if (re.search(r"\d", text) or len(re.sub(r"[^A-Z]", "", clean)) < 3
                or set(re.findall(r"[A-Z]+", clean)) & (_CAPTION_ONLY | set(_MONTHS))):
            return None, 0.0
        return clean, conf
    if name == "personal_number":
        digits = re.sub(r"[^0-9A-Z]", "", text.upper())
        return (digits, conf) if len(digits) >= 5 else (None, 0.0)
    # Free text: keep letters, digits and address punctuation; drop OCR junk
    if "address" in name:
        text = _PHONE_RE.sub(" ", text)  # the phone row below an address is its own field
    clean = re.sub(r"[^A-Za-z0-9 ,./#()'+-]", "", text)
    # Lone letters wrapped in punctuation ("C)", "(e") are specks, not words
    clean = " ".join(t for t in clean.split() if not re.fullmatch(r"[^A-Za-z0-9]*[A-Za-z][^A-Za-z0-9]+|[^A-Za-z0-9]+[A-Za-z][^A-Za-z0-9]*", t))
    clean = re.sub(r"\s+", " ", clean).strip(" ,.-").upper()
    if len(re.sub(r"[^A-Z]", "", clean)) < 3:
        return None, 0.0
    if "address" not in name and set(re.findall(r"[A-Z]+", clean)) & _CAPTION_ONLY:
        return None, 0.0
    return (clean, conf) if clean else (None, 0.0)


# ----------------------------------------------------------------------------- public

def _letters_digits(text: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", text.upper())


class PageOCR:
    """
    Whole-page OCR of one upright page, shared by the visual-zone reader and the MRZ number
    confirmation, so the page is read once. start() runs it in the background (both variants in
    parallel) while the MRZ is still being read.
    """

    def __init__(self, page_bgr: np.ndarray, timeout_s: int = 20):
        self.page = page_bgr
        self.timeout_s = timeout_s
        self._futures = None
        self._extra: List[str] = []
        self._lock = threading.Lock()

    def start(self) -> "PageOCR":
        with self._lock:
            if self._futures is None:
                self._futures = [POOL.submit(_ocr_lines, img, self.timeout_s) for img in _variants(self.page)]
        return self

    def lines(self) -> List[List[_Line]]:
        return [f.result() for f in self.start()._futures]

    def __iter__(self):
        """Page texts (letters and digits only), shared reads first, extra scales only if still needed."""
        for lines in self.lines():
            yield _letters_digits(" ".join(l.text for l in lines))
        yield from list(self._extra)
        gray = self.page if self.page.ndim == 2 else cv2.cvtColor(self.page, cv2.COLOR_BGR2GRAY)
        for width, config in _EXTRA_READS[len(self._extra):]:
            try:
                text = _letters_digits(pytesseract.image_to_string(_resize(gray, width), config=config,
                                                                   timeout=self.timeout_s))
            except RuntimeError:
                text = ""
            self._extra.append(text)
            yield text


def read_visual_zone(page: PageOCR, dob: Optional[datetime.date] = None,
                     expiry: Optional[datetime.date] = None) -> VizResult:
    """
    Reads every captioned field on the page(s); values agreeing across OCR variants gain confidence.
    dob/expiry (verified from the MRZ) help find the issue date and authority when captions are unreadable.
    """
    result = VizResult()
    per_variant: List[Dict[str, VizField]] = []
    texts = []
    for lines in page.lines():
        per_variant.append(_extract(lines, dob, expiry))
        for l in lines:
            result.words.update(re.findall(r"[A-Z0-9]+", l.text.upper()))
            texts.append(l.text.upper())
    result.text = re.sub(r"[^A-Z0-9]", "", " ".join(texts))
    result.raw = "\n".join(texts)

    names = {k for fields in per_variant for k in fields}
    for name in names:
        values = [f[name] for f in per_variant if name in f]
        best = max(values, key=lambda v: v.confidence)
        agreeing = [v for v in values if v.value == best.value]
        conf = best.confidence * 0.95
        if len(agreeing) >= 2:
            conf = min(0.99, max(conf, best.confidence) + 0.1)
        elif len(values) >= 2:
            conf *= 0.8  # variants disagree
        if conf >= _MIN_CONFIDENCE:
            result.fields[name] = VizField(best.value, round(conf, 2))

    if "telephone" not in result.fields and "emergency_contact_telephone" not in result.fields:
        phones = _PHONE_RE.findall(" ".join(texts))
        if phones:
            result.fields["telephone"] = VizField(re.sub(r"[\s-]", "", phones[0]), 0.6)
    return result
