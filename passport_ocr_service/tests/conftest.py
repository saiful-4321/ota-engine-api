import io

import pytest
from PIL import Image, ImageDraw, ImageFont

from app.mrz_parser import check_digit

# ICAO Doc 9303 Part 4 specimen passport
SPECIMEN = ("P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<",
            "L898902C36UTO7408122F1204159ZE184226B<<<<<10")


# ICAO Doc 9303 Part 5 TD1 specimen (ID-card size)
TD1_SPECIMEN = ("I<UTOD231458907<<<<<<<<<<<<<<<",
                "7408122F1204159UTO<<<<<<<<<<<6",
                "ERIKSSON<<ANNA<MARIA<<<<<<<<<<")


def make_td3(surname, given, number, nat, dob, sex, expiry, issuer=None, personal=""):
    """Builds a valid TD3 MRZ with correct check digits."""
    issuer = issuer or nat
    names = (surname + "<<" + given.replace(" ", "<")).upper()
    l1 = ("P<" + issuer + names + "<" * 44)[:44]
    num = (number + "<" * 9)[:9]
    pers = (personal + "<" * 14)[:14]
    pers_cd = check_digit(pers) if personal else "<"
    body = num + check_digit(num) + nat + dob + check_digit(dob) + sex + expiry + check_digit(expiry) + pers + pers_cd
    composite = check_digit(body[0:10] + body[13:20] + body[21:43])
    return l1, body + composite


def _mrz_font() -> str:
    """OCR-B (the real passport MRZ typeface, Debian fonts-ocr-b) when installed, else a monospace fallback."""
    import glob
    found = glob.glob("/usr/share/fonts/**/*[Oo][Cc][Rr]*[Bb]*.*tf", recursive=True)
    return found[0] if found else "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"


def render_passport(lines, rotate=0, fmt="PNG", noise=False):
    """Synthetic passport data page: some visual text on top, the MRZ in a monospace font at the bottom."""
    img = Image.new("RGB", (1500, 1050), (236, 232, 222))
    d = ImageDraw.Draw(img)
    big = ImageFont.truetype(_mrz_font(), 40)
    small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 30)
    d.text((80, 60), "PASSPORT / PASSEPORT", fill=(40, 40, 90), font=small)
    d.rectangle((80, 140, 420, 600), outline=(90, 90, 90), width=3)
    for i, label in enumerate(("Surname", "Given names", "Nationality", "Date of birth", "Date of expiry")):
        d.text((480, 150 + i * 80), label, fill=(60, 60, 60), font=small)
    top = 1000 - 70 * len(lines)
    for i, line in enumerate(lines):
        d.text((60, top + i * 70), line, fill=(10, 10, 10), font=big)
    if rotate:
        img = img.rotate(rotate, expand=True, fillcolor=(236, 232, 222))
    buf = io.BytesIO()
    if fmt == "PDF":
        img.save(buf, format="PDF", resolution=150)
    else:
        img.save(buf, format=fmt)
    return buf.getvalue()


@pytest.fixture
def specimen():
    return SPECIMEN
