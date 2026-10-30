# Passport Scan: Frontend Integration Guide

Let travellers fill in passenger details by photographing their passport instead of typing.

## 1. Which endpoint to call

Call **`ota_api`**, never the OCR service directly:

```
POST {OTA_API_BASE}/api/v1/passport/ocr
Authorization: Bearer <user access token>      ← same token as every other OTA API call
Content-Type: multipart/form-data
```

| Part | Type | Required | Notes |
|---|---|---|---|
| `file` | file | ✅ | Passport **data page** (the page with the photo and the `<<<` lines). JPEG, PNG, WEBP, TIFF, HEIC or PDF, max **10 MB** |


### Choosing what comes back

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

```
POST {OTA_API_BASE}/api/v1/passport/ocr                                         → data only
POST {OTA_API_BASE}/api/v1/passport/ocr?include_booking_passenger=true&include_confidence=true&include_warnings=true
POST {OTA_API_BASE}/api/v1/passport/ocr?include_all=true                        → everything
```

> The OCR service sits on the server's internal network and needs a secret key. Anything shipped to a
> browser is public, so the browser must only ever talk to `ota_api` with the user's own token.

## 2. Minimal call

```ts
export async function scanPassport(file: File, token: string): Promise<PassportScanResult> {
  const form = new FormData();
  form.append("file", file);

  const params = new URLSearchParams({
    include_booking_passenger: "true", include_confidence: "true", include_checks: "true", include_warnings: "true",
  });
  const res = await fetch(`${OTA_API_BASE}/api/v1/passport/ocr?${params}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },   // do NOT set Content-Type; the browser adds the boundary
    body: form,
  });

  const body = await res.json();
  if (!res.ok) throw new PassportScanError(res.status, body.message, body.hints ?? []);
  return body as PassportScanResult;
}

export class PassportScanError extends Error {
  constructor(public status: number, message: string, public hints: string[]) { super(message); }
}
```

## 3. Response types

```ts
export interface PassportScanResult {
  status: "success" | "partial";          // partial = read, but some fields failed verification
  message: string;
  data: {
    mrz_format: "TD3" | "TD2" | "TD1";    // TD3 = passport book, TD1 = passport card
    document_type: string;                 // "P" for passports
    document_number: string;
    issuing_country: string;               // ICAO 3-letter, e.g. "BGD"
    issuing_country_iso2: string | null;   // e.g. "BD"
    issuing_country_name: string | null;
    surname: string;
    given_names: string;
    nationality: string;
    nationality_iso2: string | null;
    date_of_birth: string | null;          // YYYY-MM-DD
    gender: "M" | "F" | "X";
    expiry_date: string | null;            // YYYY-MM-DD
    personal_number: string | null;
  };
  // ---- optional sections: present only when requested with include_<section>=true ----
  booking_passenger?: {                    // include_booking_passenger; same names as /flights/book
    first_name: string;
    last_name: string;
    gender: "M" | "F" | "X";
    date_of_birth: string | null;
    passenger_type: "ADT" | "CNN" | "INF" | null;   // by age TODAY; re-check against the travel date
    document_number: string;
    document_expiry: string | null;
    document_issue_country: string | null;           // ISO-2
    nationality: string | null;                      // ISO-2
  };
  confidence?: Record<string, number>;     // include_confidence; 0–1 per field of data
  overall_confidence?: number;             // include_confidence; weakest booking-critical field
  visual_zone?: VisualZone;                // include_visual_zone; only fields that could be read
  checks?: Record<"document_number" | "date_of_birth" | "expiry_date" | "composite" | "personal_number", boolean>; // include_checks
  unverified_fields?: string[];            // include_checks; failed check digits + unconfirmed names
  warnings?: string[];                     // include_warnings;                      // e.g. "Passport has expired", "Passport expires within 6 months…"
  mrz?: { format: string; lines: string[] };   // include_mrz
  processing_ms: number;
}
```

```ts
export interface FieldValue { value: string; confidence: number }   // 0–1

// Every field is optional: present only if the passport prints it AND it could be read
export interface VisualZone {
  full_name?: FieldValue;
  place_of_birth?: FieldValue;
  date_of_issue?: FieldValue;              // YYYY-MM-DD
  issuing_authority?: FieldValue;
  previous_passport_number?: FieldValue;
  father_name?: FieldValue;
  mother_name?: FieldValue;
  spouse_name?: FieldValue;
  legal_guardian_name?: FieldValue;
  permanent_address?: FieldValue;
  present_address?: FieldValue;
  address?: FieldValue;
  telephone?: FieldValue;
  emergency_contact_name?: FieldValue;
  emergency_contact_relationship?: FieldValue;
  emergency_contact_address?: FieldValue;
  emergency_contact_telephone?: FieldValue;
}
```

### What the confidence numbers mean

| Range | Meaning | UI |
|---|---|---|
| **≥ 0.95** | Verified: check digit passed, or the MRZ and printed page agree | Prefill normally |
| **0.80–0.94** | Read clearly, but not cross-verified | Prefill, light highlight |
| **< 0.80** | OCR was unsure (glare, folds, small print) | Prefill **and** ask the user to check |

- Booking fields (`data`, `booking_passenger`) come from the MRZ and are usually ≥ 0.95.
- Printed-only fields (`visual_zone`) are plain OCR with no check digit. Addresses on a photo are typically 0.6–0.7, so always let the user edit them.
- A field the scanner could not read is **left out**, never guessed.

## 4. Recommended UX flow

```
[Scan passport] ──▶ upload ──▶ 200 success ──▶ Review screen (prefilled, all fields editable) ──▶ Confirm
                           ├─▶ 200 partial ──▶ Review screen + highlight fields in unverified_fields
                           ├─▶ 422 ─────────▶ "Couldn't read it" + show hints + [Retake] [Type manually]
                           └─▶ 429/503/5xx ─▶ Fall back to manual entry
```

1. **Always show a review screen.** Never submit a booking straight from the scan. Names have no check digit,
   so let the traveller confirm them.
2. **Highlight** every field listed in `unverified_fields`, any field whose `checks[...]` is `false`,
   and any value with `confidence < 0.8`.
3. **Show `warnings` prominently.** An expired passport, or one expiring within 6 months, is a common reason for denied boarding.
4. **Recompute `passenger_type`** from `date_of_birth` and the **travel date**. A 1-year-old today may be 2 on the travel date.
5. Always offer **"Enter manually"** as a fallback.

### Prefilling the booking passenger

```ts
// Needs include_booking_passenger=true
function toBookingPassenger(scan: PassportScanResult, contact: { email?: string; phone?: string }) {
  const p = scan.booking_passenger!;
  return {
    first_name: p.first_name,
    last_name: p.last_name,
    gender: p.gender === "X" ? "" : p.gender,        // /flights/book accepts M or F; ask the user if X
    date_of_birth: p.date_of_birth ?? "",
    passenger_type: p.passenger_type ?? "ADT",
    document_number: p.document_number,
    document_expiry: p.document_expiry ?? "",
    document_issue_country: p.document_issue_country ?? "",
    nationality: p.nationality ?? "",
    email: contact.email,
    phone: contact.phone,
  };
}
```

## 5. Capturing a good image

```html
<!-- Opens the rear camera on phones, the file picker on desktop -->
<input type="file" accept="image/*,application/pdf" capture="environment" />
```

Tips to show next to the button:

- Photograph the **whole data page**, including the two lines of `<<<<` characters at the bottom.
- Lay the passport flat on a dark surface, in good light, **no flash glare** on the bottom lines.
- Hold the phone parallel to the page, and fill the frame.

**Optional: shrink large photos before upload.** Phone photos can be 5–12 MB. Scaling the long side
to about 2400 px keeps OCR quality and uploads much faster:

```ts
async function downscale(file: File, maxSide = 2400): Promise<Blob> {
  if (file.type === "application/pdf") return file;
  const bmp = await createImageBitmap(file, { imageOrientation: "from-image" });
  const scale = Math.min(1, maxSide / Math.max(bmp.width, bmp.height));
  const canvas = new OffscreenCanvas(Math.round(bmp.width * scale), Math.round(bmp.height * scale));
  canvas.getContext("2d")!.drawImage(bmp, 0, 0, canvas.width, canvas.height);
  return canvas.convertToBlob({ type: "image/jpeg", quality: 0.9 });
}
// form.append("file", await downscale(file), "passport.jpg");
```

Don't go below about 1000 px across the data page, or the bottom lines become unreadable.

## 6. Errors

All errors have the same shape: `{ "status": "error", "message": string, "hints": string[] }`.

| HTTP | Meaning | What to show |
|---|---|---|
| 401 | User's token missing or expired | Your normal re-login flow |
| 413 | File over 10 MB | "Photo too large". Downscale (section 5) and retry. |
| 415 | Not an image or PDF, corrupt, or password-protected PDF | "Please upload a photo or PDF of the passport page" |
| 422 | Image read, but no passport lines found | `message` + `hints` + **Retake** / **Enter manually** |
| 429 | More than 10 scans per minute for this user | "Too many attempts, please wait a minute" |
| 503 | Scanner unavailable | "Scanning is unavailable. Please enter the details manually." |

A `200` with `status: "partial"` is **not an error**. Prefill the form and highlight the unverified fields.

## 7. Privacy rules for the frontend

- Don't keep the image after upload: no `localStorage`, IndexedDB or analytics events.
- `visual_zone` contains **home addresses, phone numbers and family names**. Only show or store what your
  flow needs (e.g. the emergency contact for an airline APIS/SSR), and never log the response.
- Don't send passport fields to analytics or error trackers (Sentry etc.). Scrub them.
- Only send the confirmed values onward to `/flights/book`.
- The server stores nothing from a scan. Data is only saved when the booking is created.

## 8. Quick test with curl

```bash
curl -H "Authorization: Bearer $TOKEN" \
     -F "file=@passport.jpg" \
     "$OTA_API_BASE/api/v1/passport/ocr"
```
