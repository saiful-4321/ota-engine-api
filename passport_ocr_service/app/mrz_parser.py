"""
ICAO 9303 machine-readable zone parsing and validation for every travel-document size:

  TD3 (2 x 44) — passports (the vast majority worldwide)
      P<ISSUER SURNAME<<GIVEN<NAMES<<<...
      DOCNUMBER C NAT YYMMDD C S YYMMDD C PERSONALNUMBER C C
  TD2 (2 x 36) — older passports and official travel documents
      P<ISSUER SURNAME<<GIVEN<NAMES<<<
      DOCNUMBER C NAT YYMMDD C S YYMMDD C OPTIONAL C
  TD1 (3 x 30) — passport cards / ID-card-size travel documents
      I<ISSUER DOCNUMBER C OPTIONAL
      YYMMDD C S YYMMDD C NAT OPTIONAL C
      SURNAME<<GIVEN<NAMES<<<

Every numeric field is protected by a check digit, so OCR mistakes are detected rather than
returned silently. Dates are digit-only, so letter look-alikes (O→0, I→1 ...) are mapped directly.
Document/personal numbers mix letters and digits: a check digit has only 10 values, so a variant
that happens to validate proves nothing on its own. Such variants are only *proposed*
(MRZResult.corrections) and must be confirmed elsewhere (the number printed on the page).
"""

import datetime
import itertools
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

TD3_LENGTH = 44
_ALLOWED = re.compile(r"[^A-Z0-9<]")

# OCR confusions: letter -> digit (for numeric fields) and digit -> letter (for alphabetic fields)
_TO_DIGIT = {"O": "0", "Q": "0", "D": "0", "U": "0", "I": "1", "L": "1", "T": "1", "Z": "2",
             "S": "5", "B": "8", "G": "6", "A": "4"}
_TO_ALPHA = {"0": "O", "1": "I", "2": "Z", "4": "A", "5": "S", "6": "G", "8": "B"}
# Look-alike groups for alphanumeric fields ('3' is what a 'B' with its left half cut off reads as)
_LOOKALIKES = ("0OQD", "1IL", "2Z", "5S", "8B3", "6G", "4A")
_ALTERNATIVES = {c: g.replace(c, "") for g in _LOOKALIKES for c in g}
_MAX_SWAPS = 2
_MAX_CANDIDATES = 12


def check_digit(data: str) -> str:
    """ICAO 9303 check digit: weights 7-3-1, A=10..Z=35, '<'=0."""
    total = 0
    for i, ch in enumerate(data):
        if ch.isdigit():
            value = int(ch)
        elif "A" <= ch <= "Z":
            value = ord(ch) - 55
        else:
            value = 0
        total += value * (7, 3, 1)[i % 3]
    return str(total % 10)


def _digits(text: str) -> str:
    return "".join(_TO_DIGIT.get(c, c) for c in text)


def _alpha(text: str) -> str:
    return "".join(_TO_ALPHA.get(c, c) for c in text)


def _validated(value: str, check: str, numeric: bool) -> Tuple[str, str, bool]:
    """Returns (value, check, valid). Numeric fields (dates) are digit-mapped first; nothing is guessed."""
    check = _digits(check)
    if numeric:
        value = _digits(value)
    return value, check, check.isdigit() and check_digit(value) == check


def _candidates(value: str, check: str) -> List[str]:
    """
    Look-alike variants of an alphanumeric field that satisfy its check digit, with the fewest
    substitutions. These are unconfirmed proposals: roughly 1 in 10 random variants validates.
    """
    check = _digits(check)
    if not check.isdigit():
        return []
    positions = [i for i, c in enumerate(value) if c in _ALTERNATIVES]
    for swaps in range(1, _MAX_SWAPS + 1):
        found = []
        for picked in itertools.combinations(positions, swaps):
            for repl in itertools.product(*(_ALTERNATIVES[value[i]] for i in picked)):
                chars = list(value)
                for i, c in zip(picked, repl):
                    chars[i] = c
                candidate = "".join(chars)
                if check_digit(candidate) == check:
                    found.append(candidate)
        if found:
            return found[:_MAX_CANDIDATES]
    return []


def _propose(result: "MRZResult", field_name: str, line: int, start: int, end: int, check: str) -> None:
    """Records corrected MRZ line sets for a failed alphanumeric field, for outside confirmation."""
    for candidate in _candidates(result.lines[line][start:end], check):
        lines = list(result.lines)
        lines[line] = lines[line][:start] + candidate + lines[line][end:]
        result.corrections.append((field_name, candidate.replace("<", ""), lines))


def _date(yymmdd: str, future: bool) -> Optional[datetime.date]:
    """YYMMDD → date. Birth dates are never in the future; expiry dates are this century."""
    if not re.fullmatch(r"\d{6}", yymmdd):
        return None
    yy, mm, dd = int(yymmdd[:2]), int(yymmdd[2:4]), int(yymmdd[4:])
    this_year = datetime.date.today().year % 100
    century = 2000 if (future or yy <= this_year) else 1900
    try:
        return datetime.date(century + yy, mm, dd)
    except ValueError:
        return None


def _clean_filler(text: str) -> str:
    """Tesseract sometimes reads the '<' filler as K/C/L; repair runs that are mostly filler."""
    run = len(text) - len(text.rstrip("<KCL"))
    tail = text[len(text) - run:]
    first = tail.find("<")  # filler starts at a real '<' — never eat a name's last letter (MICHAEL<<<)
    if first == -1:
        return text
    filler = tail[first:]
    if len(filler) >= 3 and filler.count("<") * 2 >= len(filler):
        return text[:len(text) - len(filler)] + "<" * len(filler)
    return text


def _names(field_text: str) -> Tuple[str, str]:
    field_text = _alpha(_clean_filler(field_text))
    surname, _, given = field_text.partition("<<")
    # ICAO: '<<' appears once, between surname and given names; the next '<<' starts the filler.
    # Anything after it is misread filler (K/E/R/C), never part of the name.
    given = given.split("<<", 1)[0]
    clean = lambda s: " ".join(p for p in s.split("<") if p).strip()
    return clean(surname), clean(given)


def normalize_lines(raw_text: str) -> Optional[Tuple[str, str]]:
    """Picks the two MRZ lines out of raw OCR text and normalizes them to 44 characters."""
    lines = []
    for line in raw_text.upper().replace("«", "<").replace(" ", "").splitlines():
        line = _ALLOWED.sub("", line)
        if len(line) >= 30:
            lines.append(line)
    if len(lines) < 2:
        return None

    # Line 1 starts with P (passport); take it and the line right after it
    start = next((i for i, l in enumerate(lines[:-1]) if l.startswith("P")), len(lines) - 2)
    l1, l2 = lines[start], lines[start + 1]
    fit = lambda l: (l + "<" * TD3_LENGTH)[:TD3_LENGTH]
    return fit(l1), fit(l2)


@dataclass
class MRZResult:
    format: str
    document_type: str
    issuing_country: str
    surname: str
    given_names: str
    document_number: str
    nationality: str
    date_of_birth: Optional[datetime.date]
    sex: str
    expiry_date: Optional[datetime.date]
    personal_number: str
    checks: Dict[str, bool]
    lines: List[str]
    warnings: List[str] = field(default_factory=list)
    # (field, proposed value, corrected MRZ lines) for failed alphanumeric fields — unconfirmed
    corrections: List[Tuple[str, str, List[str]]] = field(default_factory=list)

    @property
    def score(self) -> float:
        """Share of check digits that validated (formats have 4 or 5 checks)."""
        return sum(self.checks.values()) / float(len(self.checks) or 1)

    @property
    def valid(self) -> bool:
        return all(self.checks.values())


def parse_td3(line1: str, line2: str) -> MRZResult:
    l1, l2 = line1, line2
    if l1[0] == "<" and l1[1:4].isalpha() and l1[-1] == "<":
        # OCR dropped the leading 'P' (glyph cut at the image edge): every field would shift by one
        l1 = "P" + l1[:-1]
    elif l1[0] not in "PV" and l1[1] == "<":
        l1 = "P" + l1[1:]  # a TD3 document code always starts with P (or V for visas); M/E = a cut-off P

    doc_number, doc_check, doc_ok = _validated(l2[0:9], l2[9], numeric=False)
    dob_raw, dob_check, dob_ok = _validated(l2[13:19], l2[19], numeric=True)
    exp_raw, exp_check, exp_ok = _validated(l2[21:27], l2[27], numeric=True)
    personal, pers_check, pers_ok = _validated(l2[28:42], l2[42], numeric=False)
    if personal.strip("<") == "" and _digits(l2[42]) in ("0", "<"):
        pers_ok = True  # empty optional field may carry '<' or '0' as its check digit

    composite_data = doc_number + doc_check + dob_raw + dob_check + exp_raw + exp_check + personal + pers_check
    composite_ok = check_digit(composite_data) == _digits(l2[43])

    sex = _alpha(l2[20])
    if sex == "<":
        sex = "X"  # unspecified
    surname, given = _names(l1[5:44])

    result = MRZResult(
        format="TD3",
        document_type=_alpha(l1[0]) + (l1[1] if l1[1] != "<" else ""),
        issuing_country=_alpha(l1[2:5]).replace("<", ""),
        surname=surname,
        given_names=given,
        document_number=doc_number.replace("<", ""),
        nationality=_alpha(l2[10:13]).replace("<", ""),
        date_of_birth=_date(dob_raw, future=False),
        sex=sex,
        expiry_date=_date(exp_raw, future=True),
        personal_number=personal.replace("<", ""),
        checks={
            "document_number": doc_ok,
            "date_of_birth": dob_ok,
            "expiry_date": exp_ok,
            "personal_number": pers_ok,
            "composite": composite_ok,
        },
        lines=[l1, l2],
    )
    if not doc_ok:
        _propose(result, "document_number", 1, 0, 9, l2[9])
    if not pers_ok:
        _propose(result, "personal_number", 1, 28, 42, l2[42])
    return _finish(result)


def _finish(result: MRZResult, propose=()) -> MRZResult:
    for args in propose:
        _propose(result, *args)
    if not result.document_type.startswith("P"):
        result.warnings.append(
            f"Document type '{result.document_type}' is not a passport (P) — check the traveller has a valid travel document")
    if result.date_of_birth is None:
        result.checks["date_of_birth"] = False
    if result.expiry_date is None:
        result.checks["expiry_date"] = False
    return result


def _sex(ch: str) -> str:
    sex = _alpha(ch)
    return "X" if sex == "<" else sex


def parse_td2(line1: str, line2: str) -> MRZResult:
    l1, l2 = line1, line2
    doc_number, doc_check, doc_ok = _validated(l2[0:9], l2[9], numeric=False)
    dob_raw, dob_check, dob_ok = _validated(l2[13:19], l2[19], numeric=True)
    exp_raw, exp_check, exp_ok = _validated(l2[21:27], l2[27], numeric=True)
    optional = l2[28:35]
    composite_ok = check_digit(doc_number + doc_check + dob_raw + dob_check + exp_raw + exp_check + optional) == _digits(l2[35])
    surname, given = _names(l1[5:36])
    return _finish(MRZResult(
        format="TD2",
        document_type=_alpha(l1[0]) + (l1[1] if l1[1] != "<" else ""),
        issuing_country=_alpha(l1[2:5]).replace("<", ""),
        surname=surname, given_names=given,
        document_number=doc_number.replace("<", ""),
        nationality=_alpha(l2[10:13]).replace("<", ""),
        date_of_birth=_date(dob_raw, future=False), sex=_sex(l2[20]),
        expiry_date=_date(exp_raw, future=True),
        personal_number=optional.replace("<", ""),
        checks={"document_number": doc_ok, "date_of_birth": dob_ok, "expiry_date": exp_ok, "composite": composite_ok},
        lines=[l1, l2],
    ), propose=[("document_number", 1, 0, 9, l2[9])] if not doc_ok else [])


def parse_td1(line1: str, line2: str, line3: str) -> MRZResult:
    l1, l2, l3 = line1, line2, line3
    if l1[14] == "<" and l1[15:30].strip("<"):
        # Long document number: continues in the optional field, its check digit is the last char there
        tail = l1[15:30].split("<", 1)[0]
        doc_number, doc_check, doc_ok = _validated(l1[5:14] + tail[:-1], tail[-1:] or "<", numeric=False)
    else:
        doc_number, doc_check, doc_ok = _validated(l1[5:14], l1[14], numeric=False)
    dob_raw, dob_check, dob_ok = _validated(l2[0:6], l2[6], numeric=True)
    exp_raw, exp_check, exp_ok = _validated(l2[8:14], l2[14], numeric=True)
    composite_ok = check_digit(l1[5:30] + dob_raw + dob_check + exp_raw + exp_check + l2[18:29]) == _digits(l2[29])
    surname, given = _names(l3)
    return _finish(MRZResult(
        format="TD1",
        document_type=_alpha(l1[0]) + (l1[1] if l1[1] != "<" else ""),
        issuing_country=_alpha(l1[2:5]).replace("<", ""),
        surname=surname, given_names=given,
        document_number=doc_number.replace("<", ""),
        nationality=_alpha(l2[15:18]).replace("<", ""),
        date_of_birth=_date(dob_raw, future=False), sex=_sex(l2[7]),
        expiry_date=_date(exp_raw, future=True),
        personal_number=l1[15:30].replace("<", "") if l1[14] != "<" else "",
        checks={"document_number": doc_ok, "date_of_birth": dob_ok, "expiry_date": exp_ok, "composite": composite_ok},
        lines=[l1, l2, l3],
    ), propose=[("document_number", 0, 5, 14, l1[14])] if not doc_ok and l1[14] != "<" else [])


def _plausible(line: str, length: int) -> bool:
    """
    A line fits a format if its length is close — or if it is shorter but ends in filler:
    OCR often shortens trailing '<<<<' runs, which padding restores safely.
    """
    if abs(len(line) - length) <= 6:
        return True
    return len(line) < length and line.endswith("<")


_FORMATS = (("TD3", 2, 44, parse_td3), ("TD2", 2, 36, parse_td2), ("TD1", 3, 30, parse_td1))


def reparse(fmt: str, lines: List[str]) -> MRZResult:
    """Parses corrected MRZ lines of a known format (used once a correction is confirmed)."""
    parser = next(p for name, _, _, p in _FORMATS if name == fmt)
    return parser(*lines)


def parse_mrz_text(raw_text: str) -> Optional[MRZResult]:
    """
    Tries every MRZ format the OCR text plausibly fits and returns the candidate with the best
    check-digit score (a fully valid one wins immediately).
    """
    lines = [l for l in (
        _ALLOWED.sub("", ln) for ln in raw_text.upper().replace("«", "<").replace(" ", "").splitlines()
    ) if len(l) >= 10]
    # Stray characters before the document code ('7P<BGD…') would shift every field of line 1
    lines = [l[m.start(1):] if (m := re.match(r"^[^P]{1,3}(P[A-Z<][A-Z<]{3})", l)) else l for l in lines]
    best: Optional[MRZResult] = None
    for _, count, length, parser in _FORMATS:
        for i in range(len(lines) - count + 1):
            group = lines[i:i + count]
            if not all(_plausible(l, length) for l in group):
                continue
            fitted = [(l + "<" * length)[:length] for l in group]
            try:
                result = parser(*fitted)
            except (IndexError, ValueError):
                continue
            if result.valid:
                return result
            if best is None or result.score > best.score:
                best = result
    return best
