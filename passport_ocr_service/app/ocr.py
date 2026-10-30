"""
Image → MRZ text.

Pipeline (all in memory, nothing written to disk):
  1. For each orientation (0°, 180°, 90°, 270°): locate the MRZ band with morphology
     (black-hat + horizontal gradient + closing — the MRZ is a dense block of dark text
     spanning most of the page width).
  2. OCR the band with Tesseract restricted to the MRZ alphabet, on several preprocessing variants.
  3. Parse every candidate and keep the one with the most valid check digits; stop early on a
     fully valid MRZ.
  4. A document/personal number that fails its check digit is only corrected when the corrected
     value is also printed in the visual zone of the page (a check digit alone is 1-in-10).
"""

import re
from typing import Dict, Iterator, List, Optional, Tuple

import cv2
import numpy as np
import pytesseract

from app.mrz_parser import MRZResult, parse_mrz_text, reparse
from app.viz import POOL, PageOCR

_TESS_CONFIG = "--oem 1 --psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<"
_DETECT_WIDTH = 1200
_OCR_WIDTH = 1800
_EXTRA_WIDTHS = (1500, 2200)


def _resize_width(img: np.ndarray, width: int) -> np.ndarray:
    h, w = img.shape[:2]
    if w == width:
        return img
    scale = width / float(w)
    interp = cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA
    return cv2.resize(img, (width, int(h * scale)), interpolation=interp)


def _mrz_bands(gray: np.ndarray) -> List[np.ndarray]:
    """Candidate MRZ crops, most likely first; the bottom third is always tried as a fallback."""
    small = _resize_width(gray, _DETECT_WIDTH)
    scale = gray.shape[1] / float(small.shape[1])

    rect = cv2.getStructuringElement(cv2.MORPH_RECT, (13, 5))
    square = cv2.getStructuringElement(cv2.MORPH_RECT, (21, 21))
    blur = cv2.GaussianBlur(small, (3, 3), 0)
    blackhat = cv2.morphologyEx(blur, cv2.MORPH_BLACKHAT, rect)
    grad = cv2.Sobel(blackhat, ddepth=cv2.CV_32F, dx=1, dy=0, ksize=-1)
    grad = np.absolute(grad)
    lo, hi = grad.min(), grad.max()
    grad = (255 * ((grad - lo) / (hi - lo + 1e-6))).astype("uint8")
    grad = cv2.morphologyEx(grad, cv2.MORPH_CLOSE, rect)
    thresh = cv2.threshold(grad, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, square)
    thresh = cv2.erode(thresh, None, iterations=2)

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    sh, sw = small.shape[:2]
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if w / float(h or 1) > 4 and w > 0.5 * sw:  # TD1 cards: 3 shorter lines, slightly less wide
            boxes.append((y, x, w, h))
    # Morphology often finds each MRZ line as its own band: merge vertically stacked bands
    # (gap smaller than a line height) into one block, so OCR sees all 2-3 lines together.
    boxes.sort(key=lambda b: b[0])
    merged = []
    for y, x, w, h in boxes:
        if merged:
            my, mx, mw, mh = merged[-1]
            if y - (my + mh) < max(h, mh) * 1.2:
                nx, ny = min(mx, x), my
                merged[-1] = (ny, nx, max(mx + mw, x + w) - nx, max(my + mh, y + h) - ny)
                continue
        merged.append((y, x, w, h))
    # Lowest block first — the MRZ sits at the bottom of the data page
    merged.sort(key=lambda b: -b[0])

    crops = []
    H, W = gray.shape[:2]
    for y, x, w, h in merged[:3]:
        pad_x, pad_y = int(0.03 * sw), int(0.35 * h)
        x0, y0 = max(0, int((x - pad_x) * scale)), max(0, int((y - pad_y) * scale))
        x1, y1 = min(W, int((x + w + pad_x) * scale)), min(H, int((y + h + pad_y) * scale))
        if y1 - y0 > 10 and x1 - x0 > 50:
            crops.append(gray[y0:y1, x0:x1])
    crops.append(gray[int(H * 0.62):, :])  # fallback: bottom of the page
    return crops


def _variants(crop: np.ndarray) -> Iterator[np.ndarray]:
    img = _resize_width(crop, _OCR_WIDTH)
    yield img
    yield cv2.threshold(img, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
    yield cv2.adaptiveThreshold(img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15)
    # Different scales change how Tesseract segments glyphs — a cheap ensemble for hard images
    for width in _EXTRA_WIDTHS:
        yield _resize_width(crop, width)


def _name_quality(result: MRZResult) -> int:
    """Higher is better: stray single letters in names are typical misread filler (AKBAR<S<S)."""
    tokens = (result.surname + " " + result.given_names).split()
    return -sum(1 for t in tokens if len(t) == 1 or looks_like_filler(t))


def looks_like_filler(token: str) -> bool:
    """A name token made of misread '<' filler: runs like CCCC/KKK/EERERE, or mostly C/E/K/R letters."""
    if re.search(r"(.)\1\1", token):
        return True
    fillerish = sum(1 for c in token if c in "CEKR<")
    return len(token) >= 4 and fillerish * 2 > len(token)


def _rank(result: MRZResult) -> tuple:
    return (result.valid, result.score, _name_quality(result))


def _is_chevron(gray: np.ndarray, box: tuple) -> bool:
    """
    Tesseract's most common MRZ error is reading the '<' filler as 'K'. The glyphs differ clearly on
    their left edge: 'K' has a full-height vertical stem there, '<' only its apex at mid-height.
    The glyph is binarised locally and the minority pixels are taken as ink, so this works for any
    background/contrast.
    """
    x1, y1, x2, y2 = box
    glyph = gray[max(0, y1):y2, max(0, x1):x2]
    if glyph.size == 0 or glyph.shape[0] < 6 or glyph.shape[1] < 3:
        return False
    ink = cv2.threshold(glyph, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1] > 0
    if ink.mean() > 0.5:
        ink = ~ink
    left = ink[:, : max(1, int(ink.shape[1] * 0.25))]
    return left.any(axis=1).mean() < 0.6


def _ocr_text(img: np.ndarray, timeout_s: int) -> str:
    text = pytesseract.image_to_string(img, config=_TESS_CONFIG, timeout=timeout_s)
    if "K" not in text:
        return text

    # Character boxes come in reading order (no whitespace); y is measured from the bottom
    boxes = [ln.split() for ln in pytesseract.image_to_boxes(img, config=_TESS_CONFIG, timeout=timeout_s).splitlines()]
    boxes = [b for b in boxes if len(b) >= 5]
    chars = [c for c in text if not c.isspace()]
    if len(boxes) != len(chars) or any(b[0] != c for b, c in zip(boxes, chars)):
        return text  # could not align boxes with the text — keep the plain read

    gray = img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    height = gray.shape[0]
    fixed, k = [], 0
    for ch in text:
        if ch.isspace():
            fixed.append(ch)
            continue
        box = boxes[k]
        k += 1
        if ch == "K":
            x1, y1, x2, y2 = (int(v) for v in box[1:5])
            if _is_chevron(gray, (x1, height - y2, x2, height - y1)):
                ch = "<"
        fixed.append(ch)
    return "".join(fixed)


def _confirm(result: MRZResult, page: PageOCR) -> MRZResult:
    """
    Applies proposed corrections whose exact value is printed on the page. A field with several
    printed candidates stays unverified — it is ambiguous.
    """
    fields = {f for f, _, _ in result.corrections}
    confirmed: Dict[str, List[List[str]]] = {}
    for text in page:
        for field_name, value, lines in result.corrections:
            if field_name not in confirmed and len(value) >= 5 and value in text:
                matches = [l for f, v, l in result.corrections if f == field_name and v in text]
                confirmed[field_name] = matches
        if set(confirmed) == fields:
            break
    lines = [list(l) for l in result.lines]
    for options in confirmed.values():
        if len(options) == 1:  # merge per character: two fields may sit on the same line
            for i, (orig, new) in enumerate(zip(result.lines, options[0])):
                for j, (a, b) in enumerate(zip(orig, new)):
                    if a != b:
                        lines[i][j] = b
    lines = ["".join(l) for l in lines]
    if lines == result.lines:
        return result
    fixed = reparse(result.format, lines)
    if fixed.score < result.score:
        return result
    fixed.warnings.append("Some MRZ characters were unreadable and were confirmed against the printed passport page")
    return fixed


_ROTATIONS = (None, cv2.ROTATE_180, cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_90_COUNTERCLOCKWISE)


def _rotate(img: np.ndarray, code: Optional[int]) -> np.ndarray:
    return img if code is None else cv2.rotate(img, code)


def _safe_ocr(img: np.ndarray, timeout_s: int) -> Optional[str]:
    try:
        return _ocr_text(img, timeout_s)
    except RuntimeError:  # tesseract timeout
        return None


def read_passport(images: List[np.ndarray], timeout_s: int = 20,
                  prefetch_page: bool = False) -> Tuple[Optional[MRZResult], Optional[PageOCR]]:
    """
    Returns the best MRZ found across pages/orientations/crops/variants (None if no MRZ was read),
    and the whole-page OCR of the page it came from, turned upright (for the visual zone).

    All crops × variants of one orientation are OCR'd in parallel and judged in order: the first crop
    that yields a fully valid MRZ ends the search, after its other variants are compared to pick the
    cleanest name reading. prefetch_page starts the upright page read alongside the MRZ search.
    """
    best: Optional[MRZResult] = None
    best_page: Optional[PageOCR] = None
    for image in images:
        gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        for code in _ROTATIONS:
            rotated = _rotate(gray, code)
            page = PageOCR(_rotate(image, code), timeout_s)
            if prefetch_page and code is None:
                page.start()  # most photos are upright: read the page while the MRZ is searched
            jobs = [[POOL.submit(_safe_ocr, v, timeout_s) for v in _variants(crop)] for crop in _mrz_bands(rotated)]
            try:
                for crop_jobs in jobs:
                    found_valid = False
                    for job in crop_jobs:
                        text = job.result()
                        result = parse_mrz_text(text) if text else None
                        if result is None:
                            continue
                        if not result.valid and result.corrections:
                            result = _confirm(result, page)
                        if best is None or _rank(result) > _rank(best):
                            best, best_page = result, page
                        if result.valid:
                            found_valid = True
                            if _name_quality(result) == 0:
                                return result, page
                    if found_valid:
                        return best, best_page
            finally:
                for crop_jobs in jobs:  # drop OCR jobs that are no longer needed
                    for job in crop_jobs:
                        job.cancel()
    return best, best_page


def read_mrz(images: List[np.ndarray], timeout_s: int = 20) -> Optional[MRZResult]:
    return read_passport(images, timeout_s)[0]
