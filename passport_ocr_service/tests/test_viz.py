"""Visual-zone field mapping on synthetic OCR lines (layout logic only, no Tesseract)."""
import datetime

from app.viz import _Line, _extract, parse_date


def L(text, left, top, right=None, h=40, conf=0.95):
    return _Line(text=text, conf=conf, left=left, top=top, right=right or left + 20 * len(text), bottom=top + h)


def personal_page():
    return [
        L("PERSONAL DATA AND EMERGENCY CONTACT", 450, 100),
        L("Name:", 100, 300), L("MD SAIFUL ISLAM", 700, 295),
        L("Father's Name:", 100, 370), L("NUR MOHAMMAD", 700, 365),
        L("Permanent Address:", 100, 440), L("SOUTH KALIKAPUR, H-309,", 700, 435), L("RAMGANJ - 3720, LAKSHMIPUR", 700, 485),
        L("Emergency Contact:", 100, 600),
        L("Name:", 100, 660), L("NUR MOHAMMAD", 700, 655),
        L("Relationship:", 100, 720), L("FATHER", 700, 715),
        L("Telephone No:", 100, 790), L("+8801603535591", 700, 785),
    ]


def test_personal_page_values_right_of_captions_and_emergency_section():
    f = _extract(personal_page())
    assert f["full_name"].value == "MD SAIFUL ISLAM"
    assert f["father_name"].value == "NUR MOHAMMAD"
    assert f["permanent_address"].value == "SOUTH KALIKAPUR, H-309, RAMGANJ - 3720, LAKSHMIPUR"
    assert f["emergency_contact_name"].value == "NUR MOHAMMAD"
    assert f["emergency_contact_relationship"].value == "FATHER"
    assert f["emergency_contact_telephone"].value == "+8801603535591"


def test_data_page_values_below_bilingual_captions():
    lines = [
        L("PASSPORT", 100, 1000),                                   # page title, not "Passport No"
        L("xyz /Place of Birth", 900, 1100), L("M", 740, 1145, 770), L("LAKSHMIPUR", 960, 1145),
        L("ab /Date of Issue", 830, 1240), L("02 JUL 2023", 725, 1285),
        L("Date of Expiry / Holder's Signature", 830, 1380), L("01 JUL 2033", 725, 1425),
    ]
    f = _extract(lines, dob=datetime.date(1995, 4, 1), expiry=datetime.date(2033, 7, 1))
    assert f["place_of_birth"].value == "LAKSHMIPUR"
    assert f["date_of_issue"].value == "2023-07-02"
    assert "passport_number" not in f and "issuing_authority" not in f   # captions are never values


def test_issue_date_and_authority_found_without_readable_captions():
    lines = [L("S44 garbled", 830, 1240), L("14 JUL 2026", 725, 1285), L("OTTAWA", 1200, 1290)]
    f = _extract(lines, dob=datetime.date(1986, 6, 16), expiry=datetime.date(2036, 7, 14))
    assert f["date_of_issue"].value == "2026-07-14" and f["issuing_authority"].value == "OTTAWA"


def test_date_formats():
    assert parse_date("16 JUN/JUIN 1986") == datetime.date(1986, 6, 16)
    assert parse_date("01 APR 1995") == datetime.date(1995, 4, 1)
    assert parse_date("04.05.1988") == datetime.date(1988, 5, 4)
