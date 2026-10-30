import base64
import importlib

import pytest
from fastapi.testclient import TestClient

from tests.conftest import SPECIMEN, TD1_SPECIMEN, make_td3, render_passport


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_KEY", "test-key")
    import app.main as main
    importlib.reload(main)
    return TestClient(main.app)


H = {"X-API-Key": "test-key"}


def test_requires_api_key(client):
    r = client.post("/v1/passport/ocr", files={"file": ("p.png", render_passport(SPECIMEN), "image/png")})
    assert r.status_code == 401 and r.json()["status"] == "error"


def test_reads_specimen_image(client):
    r = client.post("/v1/passport/ocr?include_mrz=true", headers=H,
                    files={"file": ("p.png", render_passport(SPECIMEN), "image/png")})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["status"] == "success", j
    assert j["data"]["document_number"] == "L898902C3" and j["data"]["surname"] == "ERIKSSON"
    # Raw MRZ is echoed exactly as read (OCR may show O as 0 there); the parsed data is corrected
    assert j["mrz"]["format"] == "TD3" and len(j["mrz"]["lines"]) == 2
    assert j["data"]["issuing_country"] == "UTO" and j["data"]["nationality"] == "UTO"


def test_bangladesh_passport_maps_to_booking_fields(client):
    lines = make_td3("ISLAM", "MD SAIFUL", "A01234567", "BGD", "860702", "M", "320630")
    r = client.post("/v1/passport/ocr?include_booking_passenger=true", headers=H,
                    files={"file": ("p.jpg", render_passport(lines, fmt="JPEG"), "image/jpeg")})
    assert r.status_code == 200, r.text
    p = r.json()["booking_passenger"]
    assert p == {"first_name": "MD SAIFUL", "last_name": "ISLAM", "gender": "M", "date_of_birth": "1986-07-02",
                 "passenger_type": "ADT", "document_number": "A01234567", "document_expiry": "2032-06-30",
                 "document_issue_country": "BD", "nationality": "BD"}
    assert "mrz" not in r.json() and "confidence" not in r.json()  # other sections only on request


def test_upside_down_photo(client):
    r = client.post("/v1/passport/ocr", headers=H,
                    files={"file": ("p.png", render_passport(SPECIMEN, rotate=180), "image/png")})
    assert r.status_code == 200 and r.json()["data"]["given_names"] == "ANNA MARIA"


def test_pdf_scan_via_base64(client):
    b64 = "data:application/pdf;base64," + base64.b64encode(render_passport(SPECIMEN, fmt="PDF")).decode()
    r = client.post("/v1/passport/ocr/base64", headers=H, json={"image_base64": b64})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "success"


def test_expired_passport_warns(client):
    r = client.post("/v1/passport/ocr?include_warnings=true", headers=H,
                    files={"file": ("p.png", render_passport(SPECIMEN), "image/png")})
    assert "Passport has expired" in r.json()["warnings"]


def test_no_mrz_is_422_with_hints(client):
    from PIL import Image
    import io
    buf = io.BytesIO(); Image.new("RGB", (800, 600), "white").save(buf, "PNG")
    r = client.post("/v1/passport/ocr", headers=H, files={"file": ("blank.png", buf.getvalue(), "image/png")})
    assert r.status_code == 422 and r.json()["hints"]


def test_garbage_file_is_415(client):
    r = client.post("/v1/passport/ocr", headers=H, files={"file": ("x.png", b"not an image", "image/png")})
    assert r.status_code == 415


def test_too_large_is_413(client, monkeypatch):
    import app.main as main
    monkeypatch.setattr(main, "MAX_UPLOAD_MB", 0.0001)
    r = client.post("/v1/passport/ocr", headers=H, files={"file": ("p.png", render_passport(SPECIMEN), "image/png")})
    assert r.status_code == 413


def test_passport_card_td1_image(client):
    r = client.post("/v1/passport/ocr", headers=H, files={"file": ("card.png", render_passport(TD1_SPECIMEN), "image/png")})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["data"]["mrz_format"] == "TD1"
    assert j["data"]["document_number"] == "D23145890"
    assert j["status"] == "success", j


def test_refuses_to_start_without_api_key(monkeypatch):
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.setenv("ALLOW_NO_AUTH", "false")
    import app.main as main
    with pytest.raises(RuntimeError):
        importlib.reload(main)
    monkeypatch.setenv("API_KEY", "test-key")
    importlib.reload(main)


def test_decompression_bomb_rejected(client):
    from PIL import Image
    import io
    buf = io.BytesIO(); Image.new("1", (12000, 12000)).save(buf, "PNG")   # 144 MP in a few KB
    r = client.post("/v1/passport/ocr", headers=H, files={"file": ("bomb.png", buf.getvalue(), "image/png")})
    assert r.status_code == 415


def test_correction_confirmed_only_against_printed_page():
    from app.mrz_parser import parse_td3
    from app.ocr import _confirm

    l1, l2 = make_td3("ALAM", "SAIF", "B00591146", "BGD", "880504", "M", "350305", personal="9118734541")
    misread = parse_td3(l1, "3" + l2[1:])

    class Page(list):
        pass

    assert not _confirm(misread, Page(["PASSPORTNUMBER", "NOTHINGPRINTED"])).valid
    fixed = _confirm(misread, Page(["PASSPORTNOB00591146SURNAMEALAM"]))
    assert fixed.valid and fixed.document_number == "B00591146"


def test_default_response_is_data_only(client):
    r = client.post("/v1/passport/ocr", headers=H, files={"file": ("p.png", render_passport(SPECIMEN), "image/png")})
    assert set(r.json()) == {"status", "message", "data", "processing_ms"}


def test_sections_are_opt_in_individually_and_all(client):
    img = render_passport(SPECIMEN)
    r = client.post("/v1/passport/ocr?include_confidence=true&include_checks=true", headers=H,
                    files={"file": ("p.png", img, "image/png")})
    j = r.json()
    assert {"confidence", "overall_confidence", "checks", "unverified_fields"} <= set(j)
    assert not {"booking_passenger", "visual_zone", "warnings", "mrz"} & set(j)
    assert j["confidence"]["document_number"] == 0.99

    r = client.post("/v1/passport/ocr?include_all=true", headers=H, files={"file": ("p.png", img, "image/png")})
    assert {"booking_passenger", "confidence", "visual_zone", "checks", "warnings", "mrz"} <= set(r.json())

    b64 = base64.b64encode(img).decode()
    r = client.post("/v1/passport/ocr/base64", headers=H, json={"image_base64": b64, "include_warnings": True})
    assert set(r.json()) == {"status", "message", "data", "processing_ms", "warnings"}
