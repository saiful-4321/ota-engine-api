# Passport OCR Service

Microservice that reads a passport photo or scan and returns the passenger's passport data,
verified against the ICAO 9303 check digits in the machine-readable zone (MRZ), plus the printed-only
fields (place of birth, issue date, authority, parents, address, phone, emergency contact) with a
confidence score for every field.

- **Offline**: OpenCV + Tesseract run inside the container; images never leave your servers.
- **Private**: images are processed in memory only. They are never stored, and passport data is never logged.
- **Verified**: every number and date in the MRZ has a check digit. Fields that fail are reported, never guessed.
- **Booking-ready**: `booking_passenger` uses the same field names as the OTA `/flights/book` passenger.

## Run

```bash
docker compose up -d --build passport_ocr      # http://localhost:7800/docs
```

| Env | Default | Meaning |
|---|---|---|
| `API_KEY` | **required** | Shared secret, sent by `ota_api` in `X-API-Key`. The service refuses to start without it. |
| `ALLOW_NO_AUTH` | `false` | `true` lets it start without a key. **Local development only.** |
| `DOCS_ENABLED` | `true` | Swagger UI at `/docs`. Disabled in docker-compose. |
| `MAX_UPLOAD_MB` | `10` | Upload size limit |
| `OCR_TIMEOUT_S` | `20` | Tesseract timeout per attempt |
| `WORKERS` | `2` | Uvicorn worker processes (OCR is CPU-bound, so roughly one per core) |

## API

### `POST /v1/passport/ocr` (multipart)

| Field | Type | Notes |
|---|---|---|
| `file` | file | JPEG, PNG, WEBP, TIFF, HEIC (iPhone) or PDF of the passport **data page** |


| Query param | Adds to the response | Default |
|---|---|---|
| *(none)* | `status`, `message`, `data`, `processing_ms` (always returned) | – |
| `include_booking_passenger` | `booking_passenger`: same field names as the `/flights/book` passenger | `false` |
| `include_confidence` | `confidence` (0–1 per field of `data`) + `overall_confidence` | `false` |
| `include_visual_zone` | `visual_zone`: printed-only fields (address, phone, parents, issue date…) | `false` |
| `include_checks` | `checks` (check digit per field) + `unverified_fields` | `false` |
| `include_warnings` | `warnings` (expired / expiring passport, non-passport document…) | `false` |
| `include_mrz` | `mrz`: raw machine-readable lines (support/debugging) | `false` |
| `include_all` | every section above | `false` |

`include_confidence` and `include_visual_zone` read the printed page too, which adds about 2–4 s.

```bash
curl -H "X-API-Key: $KEY" -F "file=@passport.jpg" http://localhost:7800/v1/passport/ocr
```

### `POST /v1/passport/ocr/base64` (JSON)

```json
{ "image_base64": "data:image/jpeg;base64,/9j/4AAQ...", "include_confidence": true, "include_booking_passenger": true }
```

The body takes the same `include_*` flags as booleans.

### Response (200, `include_all=true`; without flags only `status`, `message`, `data`, `processing_ms`)

```json
{
  "status": "success",
  "message": "Passport read and verified",
  "data": {
    "document_type": "P", "document_number": "A01234567",
    "issuing_country": "BGD", "issuing_country_iso2": "BD", "issuing_country_name": "Bangladesh",
    "surname": "ISLAM", "given_names": "MD SAIFUL",
    "nationality": "BGD", "nationality_iso2": "BD",
    "date_of_birth": "1986-07-02", "gender": "M", "expiry_date": "2032-06-30", "personal_number": null
  },
  "booking_passenger": {
    "first_name": "MD SAIFUL", "last_name": "ISLAM", "gender": "M", "date_of_birth": "1986-07-02",
    "passenger_type": "ADT", "document_number": "A01234567", "document_expiry": "2032-06-30",
    "document_issue_country": "BD", "nationality": "BD"
  },
  "confidence": { "surname": 0.99, "given_names": 0.99, "document_number": 0.99, "date_of_birth": 0.99,
                  "expiry_date": 0.99, "personal_number": 0.99, "gender": 0.95, "nationality": 0.97,
                  "issuing_country": 0.97 },
  "overall_confidence": 0.95,
  "visual_zone": {
    "full_name": { "value": "MD SAIFUL ISLAM", "confidence": 0.99 },
    "place_of_birth": { "value": "LAKSHMIPUR", "confidence": 0.74 },
    "date_of_issue": { "value": "2023-07-02", "confidence": 0.96 },
    "father_name": { "value": "NUR MOHAMMAD", "confidence": 0.72 },
    "emergency_contact_telephone": { "value": "+8801603535591", "confidence": 0.88 }
  },
  "checks": { "document_number": true, "date_of_birth": true, "expiry_date": true,
              "personal_number": true, "composite": true },
  "unverified_fields": [],
  "warnings": [],
  "mrz": null,
  "processing_ms": 840
}
```

- `status: "partial"`: the passport was read, but at least one check digit failed. `checks` and
  `unverified_fields` show which fields to have the user confirm.
- Names have **no check digit** in the MRZ. They are compared with the printed page: when both agree they
  score ≥ 0.95 and leave `unverified_fields`; otherwise the printed name repairs a damaged MRZ name, or a
  warning asks the user to confirm.
- `confidence` (0–1): ≥ 0.95 verified (check digit or MRZ = page), 0.80–0.94 read clearly, < 0.80 check it.
  `overall_confidence` is the weakest booking-critical field.
- `visual_zone` fields are plain OCR (no check digit). A field that could not be read is omitted, not guessed.
  The issue date is cross-checked against the 5/10-year validity, and found even when its caption is unreadable.
- `passenger_type` is based on age **today**. Re-check it against the travel date.
- `warnings` include *"Passport has expired"* and *"Passport expires within 6 months"*.

### Errors

All errors return `{ "status": "error", "message": "...", "hints": [] }`.

| HTTP | When |
|---|---|
| 401 | Missing or invalid `X-API-Key` |
| 413 | File larger than `MAX_UPLOAD_MB` |
| 415 | Not an image or PDF, or corrupt |
| 422 | No MRZ could be read (`hints` give photo tips) |

## How it works

1. Decode the upload (PDF pages rendered at 300 dpi; phone EXIF rotation applied).
2. For each orientation (0°/180°/90°/270°), locate the MRZ band with morphology, then OCR it with
   Tesseract limited to `A–Z 0–9 <`, using three preprocessing variants.
3. Parse the MRZ. Dates are digit-only, so letter look-alikes (O→0, I→1) are mapped directly.
   A document/personal number that fails its check digit is **not guessed**: a check digit has only
   10 values, so a look-alike variant validates by chance about 1 time in 10. Variants with the fewest
   substitutions are only accepted when that exact number is also printed on the page (visual zone);
   otherwise the field is returned unverified (`status: "partial"`).
4. Keep the best candidate, and stop as soon as all check digits pass.
5. Visual zone (`app/viz.py`): whole-page OCR on two variants (gray, darkest colour channel — security
   print fades), positioned lines matched to captions. Data-page values sit below their caption,
   personal-data-page values to the right; addresses span several lines. Values that agree across
   variants gain confidence.

## Tests

```bash
docker build --build-arg INSTALL_DEV=true -t passport_ocr_service:test .
docker run --rm passport_ocr_service:test python -m pytest -q
```

## Security

- **Not internet-facing.** Browsers call `ota_api` (`POST /api/v1/passport/ocr`, user JWT, rate-limited to 10/min per user),
  which forwards to this service over the internal Docker network with the shared `API_KEY`.
  See [FRONTEND_GUIDE.md](FRONTEND_GUIDE.md).
- The compose file binds the port to `127.0.0.1` for local testing only. Remove the `ports:` entry in production.
- The container runs as a non-root user with a read-only filesystem.
- Inputs are bounded: max upload size, max 60 MP decoded images (decompression bombs rejected), max 3 PDF pages,
  encrypted PDFs refused, and a Tesseract timeout per attempt.
- Images live only in memory. Logs contain only outcome metadata (format, status, check count, duration).

## Supported documents

| MRZ format | Documents |
|---|---|
| TD3 (2 × 44) | Passport books, i.e. virtually every passport issued worldwide |
| TD2 (2 × 36) | Older passports and some official travel documents |
| TD1 (3 × 30) | Passport cards (e.g. US, Irish) and ID-card-size travel documents |

The format is detected automatically. A non-passport document type (e.g. an ID card `I<`) is still read,
but returns a warning.

## Limits

- Documents without an MRZ cannot be read. This includes very old handwritten passports and some emergency travel documents.
- Visual-zone fields need English (or French) captions — which ICAO requires on every passport data page.
  They are best-effort: on photos with glare or folds some are omitted or come back with low confidence.
- Accuracy depends on photo quality: glare across the MRZ or heavy blur produces `partial` or 422.
