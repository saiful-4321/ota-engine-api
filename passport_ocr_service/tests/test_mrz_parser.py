import datetime

from app.mrz_parser import check_digit, normalize_lines, parse_mrz_text, parse_td1, parse_td2, parse_td3
from tests.conftest import SPECIMEN, TD1_SPECIMEN, make_td3


def test_check_digit_icao_examples():
    assert check_digit("L898902C3") == "6"
    assert check_digit("740812") == "2"
    assert check_digit("120415") == "9"


def test_parse_icao_specimen():
    r = parse_td3(*SPECIMEN)
    assert r.valid, r.checks
    assert (r.surname, r.given_names) == ("ERIKSSON", "ANNA MARIA")
    assert r.document_number == "L898902C3" and r.issuing_country == "UTO" and r.nationality == "UTO"
    assert r.date_of_birth == datetime.date(1974, 8, 12) and r.expiry_date == datetime.date(2012, 4, 15)
    assert r.sex == "F" and r.personal_number == "ZE184226B"


def test_date_lookalikes_are_mapped_but_document_number_is_only_proposed():
    l1, l2 = SPECIMEN
    bad = "L8989O2C3" + l2[9:13] + "74O8I2" + l2[19:]   # O for 0 in doc number, O/I in DOB
    r = parse_td3(l1, bad)
    assert r.date_of_birth == datetime.date(1974, 8, 12) and r.checks["date_of_birth"]
    # A validating look-alike is not proof (1 in 10 variants pass): proposed, not applied
    assert r.checks["document_number"] is False and r.document_number == "L8989O2C3"
    assert ("document_number", "L898902C3") in [c[:2] for c in r.corrections]


def test_coincidental_check_digit_match_is_not_accepted():
    # Real case: cut-off 'B' read as '3'; '3OO591146' also satisfies the check digit
    l1, l2 = make_td3("ALAM", "SAIF", "B00591146", "BGD", "880504", "M", "350305", personal="9118734541")
    r = parse_td3(l1, "3" + l2[1:])
    assert not r.valid and r.document_number == "300591146"
    proposed = [v for f, v, _ in r.corrections if f == "document_number"]
    assert "B00591146" in proposed and "3OO591146" not in proposed  # fewest substitutions only


def test_cut_off_leading_p_is_restored():
    l1, l2 = make_td3("ALAM", "SAIF", "B00591146", "BGD", "880504", "M", "350305")
    for broken in (l1[1:] + "<", "M" + l1[1:]):
        r = parse_td3(broken, l2)
        assert (r.document_type, r.issuing_country, r.surname, r.given_names) == ("P", "BGD", "ALAM", "SAIF")


def test_wrong_digit_is_flagged_not_hidden():
    l1, l2 = SPECIMEN
    r = parse_td3(l1, l2[:13] + "740813" + l2[19:])   # real misread, no confusion possible
    assert r.checks["date_of_birth"] is False and not r.valid


def test_filler_misread_as_k_is_repaired_without_eating_names():
    l1 = ("P<BGDISLAM<<MICHAEL<<<KK<K<<KKK<<<<<<<<<<<<<")[:44]
    _, l2 = make_td3("ISLAM", "MICHAEL", "A01234567", "BGD", "860702", "M", "310630")
    r = parse_td3(l1, l2)
    assert (r.surname, r.given_names) == ("ISLAM", "MICHAEL")


def test_bangladesh_passport_century_and_noise_lines():
    l1, l2 = make_td3("RAHMAN", "MD SAIFUL", "EB0123456", "BGD", "990101", "M", "330101")
    text = "PEOPLE'S REPUBLIC OF BANGLADESH\nsome visual zone text\n" + l1 + "\n" + l2.replace("<", "«", 2) + "\n"
    lines = normalize_lines(text)
    r = parse_td3(*lines)
    assert r.valid and r.given_names == "MD SAIFUL" and r.date_of_birth.year == 1999 and r.expiry_date.year == 2033


def test_empty_personal_number_is_valid():
    l1, l2 = make_td3("DOE", "JOHN", "X1234567", "GBR", "010203", "M", "300101")
    assert parse_td3(l1, l2).checks["personal_number"] is True


# ICAO Doc 9303 Part 6 TD2 specimen
TD2_SPECIMEN = ("I<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<",
                "D231458907UTO7408122F1204159<<<<<<<6")


def test_td1_specimen():
    r = parse_td1(*TD1_SPECIMEN)
    assert r.valid, r.checks
    assert (r.format, r.document_number, r.surname, r.given_names) == ("TD1", "D23145890", "ERIKSSON", "ANNA MARIA")
    assert r.date_of_birth == datetime.date(1974, 8, 12) and r.nationality == "UTO"


def test_td2_specimen():
    r = parse_td2(*TD2_SPECIMEN)
    assert r.valid, r.checks
    assert (r.format, r.document_number, r.given_names) == ("TD2", "D23145890", "ANNA MARIA")


def test_format_auto_detection_from_raw_text():
    for lines, fmt in ((SPECIMEN, "TD3"), (TD2_SPECIMEN, "TD2"), (TD1_SPECIMEN, "TD1")):
        r = parse_mrz_text("REPUBLIC OF UTOPIA\nPASSPORT\n" + "\n".join(lines) + "\n")
        assert r is not None and r.format == fmt and r.valid, (fmt, r and r.checks)


def test_non_passport_document_warns():
    r = parse_td1(*TD1_SPECIMEN)
    assert any("not a passport" in w for w in r.warnings)


def test_misread_filler_after_given_names_is_not_part_of_the_name():
    _, l2 = make_td3("ISLAM", "MD SAIFUL", "A11127165", "BGD", "950401", "M", "330701", personal="9151912061")
    l1 = "P<BGDISLAM<<MD<SAIFUL<<<<<<<<<<ER<<EERERE<K<"
    r = parse_td3(l1, l2)
    assert (r.surname, r.given_names) == ("ISLAM", "MD SAIFUL")


def test_stray_character_before_document_code_is_ignored():
    l1, l2 = make_td3("ISLAM", "MD SAIFUL", "A11127165", "BGD", "950401", "M", "330701", personal="9151912061")
    r = parse_mrz_text("7" + l1 + "\n" + l2)
    assert r.valid and (r.issuing_country, r.surname) == ("BGD", "ISLAM")
