# Travelport JSON API v11 — সর্বোচ্চ বিস্তারিত রেফারেন্স গাইড
### SkyNovia OTA Engine · বাংলা সংস্করণ (Maximum Detail)

---

## পরিভাষা — গুরুত্বপূর্ণ শব্দের সংজ্ঞা

| শব্দ | পূর্ণরূপ | সংজ্ঞা |
|---|---|---|
| **GDS** | Global Distribution System | বিশ্বব্যাপী রিজার্ভেশন সিস্টেম — এয়ারলাইন, হোটেল, গাড়ির ইনভেন্টরি ধারণ করে (Galileo, Apollo, Worldspan) |
| **NDC** | New Distribution Capability | IATA-নির্ধারিত স্ট্যান্ডার্ড যা এয়ারলাইন সরাসরি এজেন্সিকে কন্টেন্ট দিতে পারে, GDS বাদ দিয়ে |
| **PCC** | Pseudo City Code | Travelport কর্তৃক প্রতিটি এজেন্সি অফিসকে দেওয়া অনন্য আলফানিউমেরিক কোড। API-তে পাঠানো হয় হেডারে |
| **PTC** | Passenger Type Code | ৩ অক্ষরের IATA কোড যা যাত্রীর ধরন চিহ্নিত করে (ADT=বড়, CNN=শিশু, INF=শিশু কোলে) |
| **PNR** | Passenger Name Record | GDS-এ বুকিং রেকর্ড। সব যাত্রী ও ফ্লাইটের তথ্য থাকে |
| **EMD** | Electronic Miscellaneous Document | অ্যাঙ্কিলারি (আসন, ব্যাগ ইত্যাদি) পেমেন্টের ইলেকট্রনিক ডকুমেন্ট |
| **SSR** | Special Service Request | এয়ারলাইনকে বিশেষ সেবার কোডেড অনুরোধ (খাবার, হুইলচেয়ার ইত্যাদি) |
| **OSI** | Other Service Information | এয়ারলাইনকে তথ্যমূলক রিমার্ক যা কোনো কার্যক্রম প্রয়োজন করে না |
| **FOP** | Form of Payment | টিকেট কেনার পেমেন্ট পদ্ধতি (ক্রেডিট কার্ড, ক্যাশ ইত্যাদি) |
| **O&D** | Origin and Destination | যাত্রাপথের একটি শহর-জোড়া |
| **Workbench** | Reservation Workbench | Travelport v11-এর বুকিং সেশন — সব পদক্ষেপ এখানে হয় PNR তৈরির আগে |
| **Offer** | CatalogProductOffering | সার্চ API থেকে পাওয়া একটি ফ্লাইট পণ্য — যাত্রাপথ + ভাড়া + অ্যাঙ্কিলারি সহ |
| **FBC** | Fare Basis Code | আলফানিউমেরিক কোড যা একটি নির্দিষ্ট ভাড়ার নিয়ম ও শ্রেণী নির্ধারণ করে |
| **Branded Fare** | — | এয়ারলাইন-সংজ্ঞায়িত ভাড়া বান্ডেল যার নাম আছে (যেমন "Flex", "Basic", "Business Plus") |
| **IATA** | International Air Transport Association | বৈশ্বিক বিমান সংস্থা যা কোড ও মান নির্ধারণ করে |
| **BSP** | Billing and Settlement Plan | এয়ারলাইন ও এজেন্টের মধ্যে IATA-র আর্থিক নিষ্পত্তি সিস্টেম (বেশিরভাগ দেশে) |
| **ARC** | Airlines Reporting Corporation | যুক্তরাষ্ট্র-ভিত্তিক টিকেট নিষ্পত্তি সিস্টেম (BSP-র বিকল্প) |
| **OAuth 2.0** | Open Authorization 2.0 | API অথেন্টিকেশনের মানদণ্ড — access token ব্যবহার করে |
| **TTL** | Time to Live | একটি cached মানের বৈধতার সময়সীমা (যেমন access token) |
| **Polymorphism** | — | একই ফিল্ডে ভিন্ন ধরনের অবজেক্ট পাঠানোর ক্ষমতা — `@type` ফিল্ড দিয়ে নিয়ন্ত্রিত |

---

## পর্ব ১ — অথেন্টিকেশন (Authentication)

### ১.১ OAuth 2.0 Token Endpoint

**পদ্ধতি:** `POST`
**URL:** `https://auth.travelport.net/oauth/token`
*(Pre-production / টেস্ট: `https://auth.pp.travelport.net/oauth/token`)*

**উদ্দেশ্য:** Bearer access token পাওয়া — এটি দিয়েই সব API কল অনুমোদিত হয়। এটিই প্রথম কল। Token **২৪ ঘণ্টা** বৈধ — Redis-এ cache করো। **প্রতি API কলে নতুন token চাইও না।**

---

#### Request — Form Parameters (`application/x-www-form-urlencoded`)

| প্যারামিটার | ধরন | বাধ্যতামূলক | বিবরণ | উদাহরণ |
|---|---|---|---|---|
| `grant_type` | string | ✅ হ্যাঁ | সর্বদা `client_credentials` হবে। এটি machine-to-machine flow নির্দেশ করে — কোনো ব্যবহারকারী লগিন দরকার নেই | `"client_credentials"` |
| `client_id` | string | ✅ হ্যাঁ | Travelport Developer Portal থেকে পাওয়া তোমার API Client ID | `"your_client_id"` |
| `client_secret` | string | ✅ হ্যাঁ | Travelport থেকে পাওয়া Secret — পাসওয়ার্ডের মতো সুরক্ষিত রাখো, frontend-এ কখনো দেখাবে না | `"your_secret"` |

**উদাহরণ Request:**
```http
POST https://auth.travelport.net/oauth/token
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&client_id=YOUR_ID&client_secret=YOUR_SECRET
```

---

#### Response ফিল্ড

| ফিল্ড | ধরন | বিবরণ |
|---|---|---|
| `access_token` | string | ⭐ Bearer token — প্রতিটি API request-এর Authorization header-এ পাঠাতে হয় |
| `token_type` | string | সর্বদা `"Bearer"` |
| `expires_in` | integer | Token কতক্ষণ চলবে সেকেন্ডে। সাধারণত `86400` (২৪ ঘণ্টা) |
| `scope` | string | এই token-এর অনুমতির পরিধি |

**উদাহরণ Response:**
```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6...",
  "token_type": "Bearer",
  "expires_in": 86400,
  "scope": "read write"
}
```

---

### ১.২ প্রতিটি API কলে পাঠাতে হবে — HTTP Headers সম্পূর্ণ তালিকা

| Header নাম | মান / ফরম্যাট | বাধ্যতামূলক | কখন পাঠাবে | কেন দরকার |
|---|---|---|---|---|
| `Authorization` | `Bearer {access_token}` | ✅ বাধ্যতামূলক | সব request-এ | তুমি কে তা নিশ্চিত করে |
| `XAUTH_TRAVELPORT_ACCESSGROUP` | তোমার PCC (যেমন `BDAC`) | ✅ বাধ্যতামূলক | সব request-এ | কোন এজেন্সি অফিসের request তা চিহ্নিত করে |
| `Content-Type` | `application/json` | ✅ POST/PATCH-এ | POST, PATCH, PUT request-এ | Body-র format বলে। কিছু NDC Cancel ও Post-Commit endpoint-এ পাঠাবে না |
| `Accept` | `application/json` | পরামর্শ দেওয়া | সব request-এ | Server-কে বলে JSON ফরম্যাটে data ফেরত দিতে |
| `Accept-Encoding` | `gzip, deflate` | ✅ Production-এ বাধ্যতামূলক | সব Production request-এ | Response compress করে — Production-এ required |
| `Cache-Control` | `no-cache` | পরামর্শ দেওয়া | সব request-এ | পুরনো cached data এড়িয়ে সতেজ data নিশ্চিত করে |
| `TraceId` | UUID string (যেমন `550e8400-e29b-41d4-a716-446655440000`) | ঐচ্ছিক | Multi-step flow-এ | তুমি নিজে তৈরি করো — সব related API call (search→book→ticket) একসাথে ট্র্যাক করতে সাহায্য করে |
| `TVP-PCC-CORE` | `{PCC}_{GDS}` (যেমন `BDAC_1G`) | ঐচ্ছিক | XAUTH header-এর বিকল্প | PCC এবং GDS একসাথে নির্দিষ্ট করার বিকল্প পদ্ধতি |
| `travelportPlusSessionIdentifier` | Session ID | নির্দিষ্ট flow-এ | Traveler update workflow-এ | একটি স্থাপিত GDS session একাধিক call জুড়ে বজায় রাখে |

---

### ১.৩ GDS Source কোড

| কোড | GDS নাম | অঞ্চল |
|---|---|---|
| `1G` | Galileo / Travelport+ | বৈশ্বিক (পছন্দনীয়) |
| `1V` | Apollo | আমেরিকা |
| `1P` | Worldspan | আমেরিকা |

---

## পর্ব ২ — মডিউল ১: এয়ার শপিং (ফ্লাইট অনুসন্ধান)

### ২.১ মূল ফ্লাইট সার্চ — `POST /catalog/search/catalogproductofferings`

**উদ্দেশ্য:** প্রধান ফ্লাইট সার্চ endpoint। GDS ও NDC উভয় কন্টেন্ট একটি response-এ দেয়। ব্যবহারকারী যখনই ফ্লাইট খোঁজেন তখন এটি কল করো।

**পূর্ণ URL:** `POST https://api.travelport.net/11/air/catalog/search/catalogproductofferings`

---

#### `@type` ফিল্ড — Polymorphism বোঝা

> [!IMPORTANT]
> Travelport API v11 **polymorphism** ব্যবহার করে। প্রায় প্রতিটি object-এ `@type` ফিল্ড আছে। এটি API-কে বলে কোন schema variant পাঠানো হচ্ছে। সঠিক `@type` না দিলে `400` error আসবে।

---

#### `PassengerCriteria` — যাত্রী কনফিগারেশন

| ফিল্ড | ধরন | বাধ্যতামূলক | বিবরণ | উদাহরণ |
|---|---|---|---|---|
| `@type` | string | ✅ হ্যাঁ | সর্বদা `"PassengerCriteria"` | `"PassengerCriteria"` |
| `PassengerQuantityCode` | array | ✅ হ্যাঁ | প্রতি ধরনের যাত্রীর সংখ্যার তালিকা | নিচে দেখো |
| `PassengerQuantityCode[].code` | string (PTC) | ✅ হ্যাঁ | যাত্রীর ধরন কোড — সম্পূর্ণ তালিকা নিচে | `"ADT"` |
| `PassengerQuantityCode[].quantity` | integer | ✅ হ্যাঁ | এই ধরনের যাত্রীর সংখ্যা। মোট সর্বোচ্চ ৯ | `2` |
| `PassengerQuantityCode[].age` | integer | শর্তযুক্ত | শিশু/শিশুর বয়স বছরে। **CNN ও INF-এর জন্য বাধ্যতামূলক** — না দিলে ভুল ভাড়া আসতে পারে | `8` |

**উদাহরণ (১ বড়, ১ শিশু, ১ কোলের শিশু):**
```json
"PassengerCriteria": [
  {
    "@type": "PassengerCriteria",
    "PassengerQuantityCode": [
      { "code": "ADT", "quantity": 1 },
      { "code": "CNN", "quantity": 1, "age": 8 },
      { "code": "INF", "quantity": 1, "age": 0 }
    ]
  }
]
```

---

#### Passenger Type Codes (PTC) — সম্পূর্ণ রেফারেন্স তালিকা

| কোড | অর্থ | বয়সসীমা | বিশেষ নোট |
|---|---|---|---|
| `ADT` | প্রাপ্তবয়স্ক (Adult) | ১২+ বছর | ডিফল্ট যাত্রী ধরন। age attribute লাগে না |
| `CNN` | শিশু (Child) | ২–১১ বছর | সর্বদা `age` attribute দিও। কিছু carrier CHD ব্যবহার করে |
| `CHD` | শিশু (Child) — বিকল্প | ২–১১ বছর | কিছু carrier-এ CNN-এর পরিবর্তে ব্যবহৃত |
| `INF` | কোলের শিশু (Infant No Seat) | ২ বছরের নিচে | প্রাপ্তবয়স্কের কোলে ভ্রমণ। আলাদা আসন নেই |
| `INS` | আসনসহ শিশু (Infant With Seat) | ২ বছরের নিচে | নিজের আসন আছে। carrier অনুযায়ী শিশু বা পূর্ণ ভাড়া |
| `UMNR` | একা ভ্রমণকারী অপ্রাপ্তবয়স্ক | ৫–১৭ বছর | একা শিশু — এয়ারলাইন বিশেষ UM সেবা দেয়। SSR UMNR বাধ্যতামূলক |
| `STU` | ছাত্র (Student) | বিভিন্ন | ছাত্র ছাড়ের ভাড়া। নথি প্রয়োজন |
| `SEA` / `MAR` | সমুদ্রকর্মী (Seaman) | — | নাবিক ছাড়ের ভাড়া। নথি প্রয়োজন |
| `GVT` | সরকারি কর্মকর্তা | — | সরকারি ভাড়া |
| `MIL` | সামরিক (Military) | — | সশস্ত্র বাহিনী ছাড়ের ভাড়া |
| `SRC` / `S65` | প্রবীণ নাগরিক (Senior) | ৬০–৬৫+ | প্রবীণ ছাড়ের ভাড়া। বয়সসীমা carrier অনুযায়ী |
| `YTH` | তরুণ (Youth) | ১২–২৫ | কিছু carrier-এ তরুণ ছাড়ের ভাড়া |

> [!NOTE]
> সর্বোচ্চ ৯ যাত্রী একসাথে সার্চ করা যাবে। বেশি হলে আলাদা request করতে হবে।

---

#### `SearchCriteriaFlight` — যাত্রাপথ সংজ্ঞা

প্রতিটি array element একটি leg/যাত্রাখণ্ড। Round-trip = ২ element। One-way = ১। Multi-city = সর্বোচ্চ ৬ (GDS) বা ৩ (NDC)।

| ফিল্ড | ধরন | বাধ্যতামূলক | বিবরণ | উদাহরণ |
|---|---|---|---|---|
| `@type` | string | ✅ হ্যাঁ | সর্বদা `"SearchCriteriaFlight"` | `"SearchCriteriaFlight"` |
| `From` | object | ✅ হ্যাঁ | যাত্রা শুরুর বিমানবন্দর | `{ "value": "DAC" }` |
| `From.value` | string | ✅ হ্যাঁ | IATA ৩ অক্ষরের বিমানবন্দর কোড। শহরের কোডও দেওয়া যায় (যেমন LON = লন্ডন এলাকা) | `"DAC"` |
| `To` | object | ✅ হ্যাঁ | গন্তব্য বিমানবন্দর | `{ "value": "DXB" }` |
| `To.value` | string | ✅ হ্যাঁ | IATA ৩ অক্ষরের বিমানবন্দর বা শহর কোড | `"DXB"` |
| `DepartureDate` | string (তারিখ) | ✅ হ্যাঁ | `YYYY-MM-DD` ফরম্যাটে ভ্রমণের তারিখ। কখনো সময় (datetime) পাঠাবে না — শুধু তারিখ | `"2026-12-15"` |
| `DepartureTime` | string (সময়) | ঐচ্ছিক | পছন্দনীয় প্রস্থানের সময় `HH:MM` ফরম্যাটে। Soft preference — কঠোর ফিল্টার নয় | `"06:00"` |
| `DepartureTimeWindow` | integer | ঐচ্ছিক | DepartureTime-এর ±কতঘণ্টার মধ্যে সার্চ করবে | `3` |

---

#### `SearchModifiersAir` — সার্চ মডিফায়ার সম্পূর্ণ রেফারেন্স

| ফিল্ড | ধরন | বাধ্যতামূলক | কখন ব্যবহার করবে | বিবরণ |
|---|---|---|---|---|
| `@type` | string | ✅ হ্যাঁ | সর্বদা | `"SearchModifiersAir"` |
| `SearchRepresentation` | string | ✅ হ্যাঁ | সর্বদা | `"Journey"` (সম্পূর্ণ যাত্রাপথের অফার) বা `"Leg"` (একটি leg-এর অফার — multi-city-এ ব্যবহার করো) |
| `MaxNumberOfStops` | integer | ঐচ্ছিক | Direct flight চাইলে | সর্বোচ্চ ট্রানজিট সংখ্যা। `0` = nonstop শুধু, `1` = সর্বোচ্চ ১ ট্রানজিট |
| `CabinPreference` | array | ঐচ্ছিক | কেবিন ক্লাস ফিল্টার করতে | পছন্দনীয় কেবিন তালিকা |
| `CabinPreference[].cabin` | string | ঐচ্ছিক | — | `"Economy"`, `"PremiumEconomy"`, `"Business"`, `"First"` |
| `CabinPreference[].preference` | string | ঐচ্ছিক | — | `"Preferred"` (পছন্দনীয় কিন্তু fallback দেয়) বা `"Permitted"` (কঠোর — শুধু এই কেবিন) |
| `CarrierPreference` | object | ঐচ্ছিক | নির্দিষ্ট এয়ারলাইন ফিল্টার | এয়ারলাইন অন্তর্ভুক্তি বা বাদ দেওয়া |
| `CarrierPreference.includedAirlineCodes` | array[string] | ঐচ্ছিক | নির্দিষ্ট এয়ারলাইন দেখাতে | IATA ২ অক্ষরের কোড তালিকা। যেমন `["BG", "EK"]` |
| `CarrierPreference.excludedAirlineCodes` | array[string] | ঐচ্ছিক | এয়ারলাইন বাদ দিতে | বাদ দেওয়ার এয়ারলাইন কোড |
| `AlliancePreference` | array[string] | ঐচ্ছিক | Alliance ফিল্টার | `"StarAlliance"`, `"Oneworld"`, `"SkyTeam"` |
| `MaxConnectionTime` | integer | ঐচ্ছিক | দীর্ঘ transit এড়াতে | সংযোগ সময়ের সর্বোচ্চ মিনিট |
| `MinConnectionTime` | integer | ঐচ্ছিক | পর্যাপ্ত সংযোগ নিশ্চিত করতে | সংযোগ সময়ের ন্যূনতম মিনিট |
| `NonStopPreferred` | boolean | ঐচ্ছিক | Nonstop পছন্দ করতে | `true` = আগে nonstop দেখাও, না পেলে connecting |
| `offersPerPage` | integer | ⭐ বুকিং করতে গেলে গুরুত্বপূর্ণ | বুকিং-এর আগের সার্চে | প্রতি পৃষ্ঠায় ক্যাশ করা ফলাফলের সংখ্যা। Reference payload mode-এ বুকিং করতে এটি লাগবে। সুপারিশ: `20` |
| `AccountCode` | array | ঐচ্ছিক | Corporate ভাড়ার জন্য | কর্পোরেট একাউন্ট কোড তালিকা |
| `AccountCode[].value` | string | ঐচ্ছিক | — | কর্পোরেট কোড স্ট্রিং। যেমন `"SKYNOVIA2024"` |
| `LoyaltyIdentifier` | array | ঐচ্ছিক | Loyalty-based pricing | FFP নম্বর per carrier লয়্যালটি-ভিত্তিক মূল্য সক্রিয় করতে |
| `PrivateFareSearchType` | string | ঐচ্ছিক | Private fare খুঁজতে | `"AccountCode"` বা `"ContractCode"` |

---

#### Cabin Class কোড — সম্পূর্ণ তালিকা

| API Value | বাংলা নাম | বিবরণ | GDS Class Bucket |
|---|---|---|---|
| `Economy` | ইকোনমি | সাধারণ ইকোনমি ক্লাস | Y, K, L, M, N, Q, T, V, X ইত্যাদি |
| `PremiumEconomy` | প্রিমিয়াম ইকোনমি | বেশি জায়গা সহ ইকোনমি | W, S |
| `Business` | বিজনেস | সম্পূর্ণ lie-flat আসন সহ | C, D, J, Z |
| `First` | ফার্স্ট ক্লাস | সর্বোচ্চ সেবার স্তর | F, A, P |

---

#### সার্চ Response — গুরুত্বপূর্ণ ফিল্ড

| ফিল্ড | ধরন | বিবরণ |
|---|---|---|
| `CatalogProductOffering` | array | ফ্লাইট অফারের তালিকা — প্রতিটি অফার = একটি সম্পূর্ণ যাত্রাপথ + ভাড়ার সমন্বয় |
| `CatalogProductOffering[].id` | string | ⭐ **অনন্য Offer ID** — এই অফার দিয়ে বুকিং করতে লাগবে (Reference Payload Mode) |
| `CatalogProductOffering[].Product.FlightSegment` | array | ব্যক্তিগত ফ্লাইট সেগমেন্ট তালিকা |
| `FlightSegment[].DepartureAirport.value` | string | যাত্রা শুরুর বিমানবন্দর IATA কোড |
| `FlightSegment[].ArrivalAirport.value` | string | গন্তব্য বিমানবন্দর IATA কোড |
| `FlightSegment[].DepartureDate` | string | প্রস্থানের তারিখ `YYYY-MM-DD` |
| `FlightSegment[].DepartureTime` | string | প্রস্থানের সময় `HH:MM` |
| `FlightSegment[].ArrivalDate` | string | আগমনের তারিখ `YYYY-MM-DD` |
| `FlightSegment[].ArrivalTime` | string | আগমনের সময় `HH:MM` |
| `FlightSegment[].MarketingCarrier.value` | string | Marketing এয়ারলাইনের IATA কোড (টিকেটে যার নাম থাকে) |
| `FlightSegment[].OperatingCarrier.value` | string | Operating এয়ারলাইনের IATA কোড (আসলে যে plane চালায় — codeshare partner) |
| `FlightSegment[].FlightNumber` | string | ফ্লাইট নম্বর। যেমন `"147"` |
| `FlightSegment[].ClassOfService` | string | Booking class (RBD) কোড। যেমন `"Y"`, `"K"`, `"L"` |
| `FlightSegment[].CabinAir` | string | প্রকৃত কেবিন নাম: `"Economy"`, `"Business"` ইত্যাদি |
| `FlightSegment[].Duration` | string | সেগমেন্টের ফ্লাইট সময় ISO 8601 ফরম্যাটে। যেমন `"PT3H20M"` = ৩ ঘণ্টা ২০ মিনিট |
| `FlightSegment[].Equipment` | string | বিমানের ধরন IATA কোড। যেমন `"73H"` = Boeing 737-800 |
| `FlightSegment[].NumberOfStops` | integer | এই সেগমেন্টের মধ্যে থামার সংখ্যা |
| `CatalogProductOffering[].Price.TotalPrice.value` | number | মুদ্রায় মোট ভাড়া |
| `CatalogProductOffering[].Price.TotalPrice.code` | string | মুদ্রার কোড। যেমন `"BDT"`, `"USD"`, `"EUR"` |
| `CatalogProductOffering[].Price.BaseAirPrice` | object | ট্যাক্স ও সারচার্জ ছাড়া মূল ভাড়া |
| `CatalogProductOffering[].Price.Taxes` | object | মোট ট্যাক্স পরিমাণ |
| `CatalogProductOffering[].Price.TaxBreakdown` | array | আইটেমাইজড ট্যাক্স তালিকা |
| `TaxBreakdown[].code` | string | ট্যাক্স কোড। যেমন `"YQ"` (জ্বালানি surcharge), `"YR"` (carrier-imposed), `"BD"` (বাংলাদেশ departure tax) |
| `TaxBreakdown[].amount` | number | এই ট্যাক্সের পরিমাণ |
| `TaxBreakdown[].description` | string | ট্যাক্সের পঠনযোগ্য নাম |
| `CatalogProductOffering[].ContentSource` | string | `"GDS"` বা `"NDC"` — এই অফার কোথা থেকে এসেছে |
| `CatalogProductOffering[].BaggageAllowance` | array | প্রতি সেগমেন্টে প্রতি PTC-র ব্যাগেজ allowance |
| `BaggageAllowance[].PieceCount` | integer | অন্তর্ভুক্ত checked bag-এর সংখ্যা। `0` = বিনামূল্যে ব্যাগ নেই |
| `BaggageAllowance[].Weight.value` | number | ওজন-ভিত্তিক allowance (যেমন `23`) |
| `BaggageAllowance[].Weight.unit` | string | ওজনের একক: `"kg"` বা `"lb"` |
| `CatalogProductOffering[].FareBasisCode` | string | এই অফারের Fare Basis Code |
| `CatalogProductOffering[].FareFamily` | string | Branded fare নাম (যদি এয়ারলাইন fare family ব্যবহার করে) |
| `CatalogProductOffering[].IsRefundable` | boolean | `true` = ভাড়া ফেরতযোগ্য |
| `CatalogProductOffering[].IsExchangeable` | boolean | `true` = পরিবর্তন অনুমোদিত |
| `CatalogProductOffering[].PenaltyInformation` | array | পরিবর্তন/বাতিলের জরিমানা |
| `PenaltyInformation[].type` | string | `"Change"` (পরিবর্তন) বা `"Cancel"` (বাতিল) |
| `PenaltyInformation[].penaltyAmount` | number | জরিমানার পরিমাণ। `0` = বিনামূল্যে |

---

### ২.২ Low Fare Search (নমনীয় তারিখ সার্চ)

একই endpoint, `"LowFare"` SearchRepresentation বা date range modifier সহ।

| অতিরিক্ত ফিল্ড | ধরন | বিবরণ |
|---|---|---|
| `DateRangeStart` | string (তারিখ) | নমনীয় তারিখ পরিসরের শুরু `YYYY-MM-DD` |
| `DateRangeEnd` | string (তারিখ) | নমনীয় তারিখ পরিসরের শেষ — এই পরিসরে সবচেয়ে সস্তা তারিখ দেখায় |

---

### ২.৩ Offer Pricing — `POST /catalog/price/catalogproductofferings`

**উদ্দেশ্য:** ব্যবহারকারী ফ্লাইট নির্বাচনের পর বর্তমান মূল্য ও প্রাপ্যতা নিশ্চিত করো। সার্চ ও বুকিং-এর মাঝে দাম পরিবর্তন হতে পারে। **বুকিং তৈরির আগে সর্বদা এটি কল করো।**

#### Request ফিল্ড

| ফিল্ড | ধরন | বাধ্যতামূলক | বিবরণ |
|---|---|---|---|
| `requestedOffer.id` | string | ✅ হ্যাঁ | সার্চ response থেকে CatalogProductOffering ID |
| `requestedOffer.@type` | string | ✅ হ্যাঁ | `"OfferRequest"` |
| `PassengerCriteria` | array | ✅ হ্যাঁ | সার্চের মতো একই যাত্রী কনফিগারেশন |
| `PricingModifiers.FareBasisCode` | string | ঐচ্ছিক | নির্দিষ্ট FBC জোর করতে |
| `PricingModifiers.AccountCode` | string | ঐচ্ছিক | Corporate ভাড়ার জন্য কর্পোরেট কোড |
| `PricingModifiers.CurrencyCode` | string | ঐচ্ছিক | নির্দিষ্ট মুদ্রায় মূল্য চাইতে |

#### সার্চের অতিরিক্ত Response ফিল্ড

| ফিল্ড | ধরন | বিবরণ |
|---|---|---|
| `PriceBreakdown` | array | প্রতি যাত্রীর ভাড়া বিভাজন |
| `PriceBreakdown[].ptc` | string | এই বিভাজন কোন PTC-র জন্য |
| `PriceBreakdown[].quantity` | integer | এই ধরনের যাত্রীর সংখ্যা |
| `PriceBreakdown[].baseFare` | object | প্রতি যাত্রীর মূল ভাড়া |
| `PriceBreakdown[].taxes` | object | প্রতি যাত্রীর ট্যাক্স |
| `PriceBreakdown[].totalFare` | object | প্রতি যাত্রীর মোট |
| `ValidatingCarrier` | string | টিকেট validation-এর দায়িত্বে থাকা এয়ারলাইন |
| `TicketingDeadline` | string | কোন সময়ের মধ্যে টিকেট করতে হবে (ISO 8601) |

---

### ২.৪ Fare Rules — `POST /catalog/farerule`

**উদ্দেশ্য:** ভাড়ার সম্পূর্ণ শর্তাবলী। বুকিং নিশ্চিতের আগে ব্যবহারকারীকে এটি দেখাও।

#### Response ফিল্ড

| ফিল্ড | ধরন | বিবরণ |
|---|---|---|
| `FareRule[].ruleCategory` | string | নিয়মের বিভাগ: `"Penalties"` (জরিমানা), `"MinStay"` (ন্যূনতম থাকা), `"MaxStay"` (সর্বোচ্চ থাকা), `"AdvancePurchase"` (অগ্রিম কেনা), `"Blackouts"` (নিষিদ্ধ তারিখ) |
| `FareRule[].ruleText` | string | সম্পূর্ণ নিয়মের টেক্সট (এয়ারলাইন tariff ভাষায়) |
| `StructuredRule.penaltyAmount` | number | জরিমানার পরিমাণ |
| `StructuredRule.penaltyCurrency` | string | জরিমানার মুদ্রা |
| `StructuredRule.minStayDays` | integer | ন্যূনতম রাত থাকার প্রয়োজন |
| `StructuredRule.maxStayDays` | integer | সর্বোচ্চ থাকা অনুমোদিত |
| `StructuredRule.advancePurchaseDays` | integer | যাত্রার N দিন আগে কিনতে হবে |
| `StructuredRule.isRefundable` | boolean | কোনো রিফান্ড সম্ভব কিনা |
| `StructuredRule.isChangeable` | boolean | পরিবর্তন অনুমোদিত কিনা |

---

## পর্ব ৩ — মডিউল ২: বুকিং ও ওয়ার্কবেঞ্চ সেশন

### ৩.১ ওয়ার্কবেঞ্চ তৈরি করা

**পদ্ধতি:** `POST`
**URL:** `https://api.travelport.net/11/air/book/airoffer/reservationworkbench`

**উদ্দেশ্য:** বুকিং সেশন খোলে। Shopping cart-এর মতো — সব কিছু এখানে রাখো checkout (Commit) করার আগে।

#### Request Body

| ফিল্ড | ধরন | বাধ্যতামূলক | বিবরণ |
|---|---|---|---|
| `@type` | string | ✅ হ্যাঁ | `"ReservationWorkbench"` |
| `AgencyCode` | string | ঐচ্ছিক | তোমার এজেন্সির IATA কোড |
| `AgencyName` | string | ঐচ্ছিক | এজেন্সির নাম |

#### Response ফিল্ড

| ফিল্ড | ধরন | বিবরণ |
|---|---|---|
| `Identifier.value` | string | ⭐ **`workbenchID`** — এটি সংরক্ষণ করো! পরবর্তী সব বুকিং কলে ব্যবহার হবে |
| `WorkbenchStatus` | string | বর্তমান workbench অবস্থা। তৈরির পর `"Open"` হওয়া উচিত |

---

### ৩.২ ফ্লাইট Offer যোগ করা — `POST .../offers/build`

**উদ্দেশ্য:** সার্চ থেকে নির্বাচিত ফ্লাইট workbench-এ যোগ করা।

#### Request Body — Reference Payload Mode (সুপারিশকৃত)

```json
{
  "@type": "BuildFromCatalogProductOffering",
  "CatalogProductOfferingIdentifier": {
    "id": "SEARCH_OFFER_ID",
    "Identifier": {
      "authority": "Travelport",
      "value": "SEARCH_OFFER_ID"
    }
  }
}
```

| ফিল্ড | বাধ্যতামূলক | বিবরণ |
|---|---|---|
| `@type` | ✅ হ্যাঁ | `"BuildFromCatalogProductOffering"` |
| `CatalogProductOfferingIdentifier.id` | ✅ হ্যাঁ | সার্চ response থেকে offer `id` |

#### Full Payload Mode (কিছু NDC-র জন্য প্রয়োজন)

```json
{
  "@type": "BuildFromCatalogProductOfferingFull",
  "CatalogProductOffering": { /* সার্চের সম্পূর্ণ offer object */ }
}
```

---

### ৩.৩ যাত্রী যোগ করা — `POST /book/traveler/reservationworkbench/{workbenchID}/travelers`

**উদ্দেশ্য:** workbench-এ যাত্রীর বিস্তারিত যোগ। Commit-এর আগে করতে হবে।

#### Traveler Object — সম্পূর্ণ ফিল্ড রেফারেন্স

| ফিল্ড | ধরন | বাধ্যতামূলক | বিবরণ |
|---|---|---|---|
| `@type` | string | ✅ হ্যাঁ | `"Traveler"` |
| `NamePrefix` | string | ঐচ্ছিক | উপাধি: `"Mr"`, `"Mrs"`, `"Ms"`, `"Dr"`, `"Prof"` |
| `GivenName` | string | ✅ হ্যাঁ | যাত্রীর নাম — পাসপোর্টের সাথে হুবহু মিলতে হবে |
| `Surname` | string | ✅ হ্যাঁ | পদবি — পাসপোর্টের সাথে হুবহু মিলতে হবে |
| `BirthDate` | string | শিশু/শিশুর জন্য ✅ | জন্মতারিখ `YYYY-MM-DD` ফরম্যাটে। CNN ও INF-এর জন্য বাধ্যতামূলক |
| `Gender` | string | ঐচ্ছিক | `"Male"`, `"Female"`, `"Unspecified"`. কিছু carrier প্রয়োজন করে |
| `PassengerTypeCode` | string | ✅ হ্যাঁ | এই যাত্রীর PTC: `"ADT"`, `"CNN"`, `"INF"` ইত্যাদি |
| `ContactInformation` | array | ✅ হ্যাঁ | কমপক্ষে একটি যোগাযোগ পদ্ধতি |
| `ContactInformation[].@type` | string | ✅ হ্যাঁ | `"ContactInformationPhone"` বা `"ContactInformationEmail"` |
| `ContactInformation[].EmailAddress` | string | শর্তযুক্ত | বৈধ ইমেইল। e-ticket ডেলিভারির জন্য বেশিরভাগ এয়ারলাইনে প্রয়োজন |
| `ContactInformation[].PhoneNumber` | string | শর্তযুক্ত | দেশ কোড সহ ফোন। যেমন `"+8801712345678"` |
| `ContactInformation[].CountryDialingCode` | string | শর্তযুক্ত | Dialing prefix। যেমন বাংলাদেশের জন্য `"880"` |

---

#### পাসপোর্ট / ভ্রমণ নথি — Traveler-এর ভেতরে Nested

| ফিল্ড | ধরন | বাধ্যতামূলক | বিবরণ |
|---|---|---|---|
| `TravelDocument[].@type` | string | ✅ হ্যাঁ | `"TravelDocumentPassport"` |
| `TravelDocument[].DocumentNumber` | string | ✅ হ্যাঁ | পাসপোর্ট নম্বর |
| `TravelDocument[].ExpiryDate` | string | ✅ হ্যাঁ | মেয়াদ শেষের তারিখ `YYYY-MM-DD`. ভ্রমণের পরও বৈধ থাকতে হবে |
| `TravelDocument[].IssuingCountry.value` | string | ✅ হ্যাঁ | ইস্যুকারী দেশের ISO ২ অক্ষর কোড। বাংলাদেশ = `"BD"` |
| `TravelDocument[].NationalityCountry.value` | string | ✅ হ্যাঁ | জাতীয়তার দেশ কোড। বাংলাদেশ = `"BD"` |
| `TravelDocument[].GivenName` | string | ✅ হ্যাঁ | পাসপোর্টে ছাপানো নাম |
| `TravelDocument[].Surname` | string | ✅ হ্যাঁ | পাসপোর্টে ছাপানো পদবি |
| `TravelDocument[].Gender` | string | ✅ হ্যাঁ | `"M"` বা `"F"` — পাসপোর্টের মতো |

---

#### লয়্যালটি / Frequent Flyer — Traveler-এর ভেতরে

| ফিল্ড | ধরন | বাধ্যতামূলক | বিবরণ |
|---|---|---|---|
| `CustomerLoyalty[].@type` | string | ✅ হ্যাঁ | `"CustomerLoyalty"` |
| `CustomerLoyalty[].ProgramID` | string | ✅ হ্যাঁ | লয়্যালটি প্রোগ্রামের এয়ারলাইন IATA কোড। যেমন `"EK"` = Emirates Skywards |
| `CustomerLoyalty[].MembershipID` | string | ✅ হ্যাঁ | ফ্রিকোয়েন্ট ফ্লায়ার নম্বর |
| `CustomerLoyalty[].LoyaltyLevel` | string | ঐচ্ছিক | Elite tier (যেমন `"Gold"`, `"Platinum"`) — বিনামূল্যে আসন নির্বাচনে সাহায্য করে |

---

### ৩.৪ SSR ও Remarks যোগ করা

**URL:** `POST .../reservationcomments/list`

#### SSR কোড সম্পূর্ণ তালিকা

##### হুইলচেয়ার সহায়তা কোড

| কোড | বিবরণ (বাংলা) |
|---|---|
| `WCHR` | হুইলচেয়ার দরকার — সিঁড়ি উঠতে পারেন কিন্তু দূরে হাঁটতে পারেন না |
| `WCHS` | হুইলচেয়ার দরকার — সিঁড়ি উঠতে পারেন না কিন্তু নিজে আসনে যেতে পারেন |
| `WCHC` | হুইলচেয়ার দরকার — সম্পূর্ণ স্থির, সব জায়গায় সাহায্য প্রয়োজন |
| `WCMP` | নিজের ম্যানুয়াল হুইলচেয়ার নিয়ে ভ্রমণ |
| `WCBD` | Dry battery চালিত হুইলচেয়ার নিয়ে ভ্রমণ |
| `WCBW` | Wet battery চালিত হুইলচেয়ার নিয়ে ভ্রমণ |
| `WCOB` | এয়ারলাইনের onboard হুইলচেয়ার অনুরোধ (বিমানের ভেতরে) |

##### খাবারের অনুরোধ কোড

| কোড | খাবারের ধরন | কখন ব্যবহার করবে |
|---|---|---|
| `AVML` | এশীয় ভেজিটেরিয়ান | দক্ষিণ/দক্ষিণ-পূর্ব এশীয় নিরামিষ — মাংস, ডিম, দুগ্ধজাত নেই |
| `BBML` | শিশু খাবার | শিশু/পিচ্চিদের জন্য (নরম, পিউরি) |
| `BLML` | হালকা খাবার | কম মশলা, সহজে হজম — চিকিৎসাজনিত কারণে |
| `CHML` | শিশু খাবার | শিশুদের জন্য বয়স-উপযুক্ত পরিমাণ |
| `DBML` | ডায়াবেটিক খাবার | কম চিনি, নিয়ন্ত্রিত কার্বোহাইড্রেট |
| `FPML` | ফলের থালা | শুধু তাজা ফল |
| `GFML` | গ্লুটেন-মুক্ত | গম, যব, রাই নেই — Celiac রোগের জন্য |
| `HNML` | হিন্দু মাংসাশী | গরু নেই — মুরগি, ভেড়া, সামুদ্রিক মাছ থাকতে পারে |
| `KSML` | কোশের | ইহুদি খাদ্যবিধি অনুযায়ী (pre-packaged) |
| `LCML` | কম ক্যালোরি | ক্যালোরি-নিয়ন্ত্রিত |
| `LFML` | কম চর্বি | কম কোলেস্টেরল ও চর্বি |
| `LSML` | কম লবণ | কম সোডিয়াম |
| `MOML` | মুসলিম খাবার | হালাল সার্টিফাইড — শুকর ও অ্যালকোহল নেই |
| `NLML` | ল্যাকটোজ-মুক্ত | দুগ্ধজাত পণ্য নেই |
| `RVML` | কাঁচা ভেজিটেরিয়ান | রান্না করা নয় — শুধু তাজা ফল ও সবজি |
| `SFML` | সামুদ্রিক খাবার | শুধু মাছ ও সামুদ্রিক খাবার |
| `SPML` | বিশেষ খাবার | কাস্টম — free-text বিবরণ প্রয়োজন |
| `VGML` | ভেগান | কোনো পশুজাত পণ্য নেই |
| `VLML` | ল্যাকটো-ওভো ভেজিটেরিয়ান | ডিম ও দুগ্ধজাত সহ নিরামিষ |

##### অন্যান্য SSR কোড

| কোড | বিবরণ (বাংলা) |
|---|---|
| `UMNR` | একা ভ্রমণকারী অপ্রাপ্তবয়স্ক — এয়ারলাইন UM প্রোটোকল চালু করে |
| `DEAF` | শ্রবণ প্রতিবন্ধী যাত্রী |
| `BLIND` | দৃষ্টি প্রতিবন্ধী যাত্রী |
| `MEDA` | চিকিৎসাজনিত — বিমানে বিশেষ চিকিৎসা সেবা দরকার |
| `DOCS` | পাসপোর্ট তথ্য এয়ারলাইনে পাঠানো (APIS — Advance Passenger Info) |
| `DOCA` | ভ্রমণ নথি info (API-DOCS) |
| `DOCO` | ভিসা তথ্য এয়ারলাইনে পাঠানো |
| `PNUT` | চিনাবাদামে অ্যালার্জি সতর্কতা |
| `PETC` | কেবিনে পোষা প্রাণী (cabin-এ) |
| `AVIH` | hold-এ পোষা প্রাণী (checked pet) |
| `EXST` | অতিরিক্ত আসন (বড় যাত্রী বা বাদ্যযন্ত্র বহনের জন্য) |
| `BIKE` | সাইকেল cargo-তে |
| `STCR` | stretcher case — শুয়ে ভ্রমণ করতে হবে |
| `OXYG` | বিমানে অক্সিজেন প্রয়োজন |

#### SSR Request কাঠামো

```json
{
  "@type": "ReservationCommentSSR",
  "SSRCode": "MOML",
  "SegmentNumber": 1,
  "PassengerIdentifier": "PAX1",
  "FreeText": ""
}
```

| ফিল্ড | বিবরণ |
|---|---|
| `SSRCode` | ৪ অক্ষরের SSR কোড |
| `SegmentNumber` | কোন ফ্লাইট সেগমেন্টে — বাদ দিলে সব সেগমেন্টে |
| `PassengerIdentifier` | কোন যাত্রীর জন্য |
| `FreeText` | SPML, MEDA-র জন্য বিস্তারিত বর্ণনা বাধ্যতামূলক |

---

#### OSI Request কাঠামো

```json
{
  "@type": "ReservationCommentOSI",
  "CarrierCode": "EK",
  "FreeText": "CORPORATE ID SKYNOVIACO2024"
}
```

---

### ৩.৫ Workbench চূড়ান্ত করা (PNR তৈরি) — `POST .../commit`

**উদ্দেশ্য:** workbench চূড়ান্ত করে সক্রিয় PNR তৈরি করে। এর পর ফিরে যাওয়া নেই — বুকিং live।

| ঐচ্ছিক ফিল্ড | বিবরণ |
|---|---|
| `QueueOnCommit.queueNumber` | Commit-এর সাথে সাথে কোন queue-তে রাখবে |
| `QueueOnCommit.pccCode` | Queue-এর PCC কোড |

#### Response ফিল্ড

| ফিল্ড | ধরন | বিবরণ |
|---|---|---|
| `Reservation.Locator[].value` | string | ⭐ **PNR কোড** — ৬ অক্ষরের আলফানিউমেরিক GDS locator (যেমন `"ABCDEF"`) |
| `Reservation.Locator[].source` | string | কোন সিস্টেমে এই locator: `"1G"`, `"1V"`, `"1P"`, বা NDC-র জন্য এয়ারলাইন কোড |
| `Reservation.id` | string | Internal reservation UUID |

---

## পর্ব ৪ — মডিউল ৩: সিট ম্যাপ

### ৪.১ সিট ম্যাপ দেখা — `POST /catalog/search/seatmap`

**উদ্দেশ্য:** নির্দিষ্ট ফ্লাইটের interactive সিট ম্যাপ — কোন আসন খালি, ধরন, মূল্য।

#### Request ফিল্ড

| ফিল্ড | ধরন | বাধ্যতামূলক | বিবরণ |
|---|---|---|---|
| `FlightSegment.MarketingCarrier.value` | string | ✅ হ্যাঁ | IATA এয়ারলাইন কোড |
| `FlightSegment.FlightNumber` | string | ✅ হ্যাঁ | ফ্লাইট নম্বর |
| `FlightSegment.DepartureDate` | string | ✅ হ্যাঁ | `YYYY-MM-DD` |
| `FlightSegment.DepartureAirport.value` | string | ✅ হ্যাঁ | প্রস্থান বিমানবন্দর |
| `FlightSegment.ArrivalAirport.value` | string | ✅ হ্যাঁ | গন্তব্য বিমানবন্দর |
| `FlightSegment.ClassOfService` | string | ঐচ্ছিক | Booking class — প্রাসঙ্গিক সিট availability দেখাতে সাহায্য করে |
| `ReservationIdentifier` | string | NDC-র জন্য | NDC-তে workbenchID বা reservationID দিতে হবে |

#### সিট ম্যাপ Response ফিল্ড

| ফিল্ড | ধরন | বিবরণ |
|---|---|---|
| `SeatMap.Cabin` | array | বিমানের কেবিন তালিকা |
| `Cabin[].CabinAir` | string | কেবিন নাম: `"Economy"`, `"Business"`, `"First"` |
| `Cabin[].Row` | array | বিমানের সারি তালিকা |
| `Row[].rowNumber` | integer | সারির নম্বর |
| `Row[].Seat` | array | এই সারির আসন তালিকা |
| `Seat[].column` | string | আসনের কলাম অক্ষর: `"A"`, `"B"`, `"C"`, `"D"`, `"E"`, `"F"` |
| `Seat[].status` | string | আসনের অবস্থা: `"Available"` (খালি), `"Occupied"` (দখলকৃত), `"Blocked"` (অবরুদ্ধ), `"Reserved"` (সংরক্ষিত) |
| `Seat[].SeatCharacteristic[].value` | string | আসনের বৈশিষ্ট্য কোড — নিচে দেখো |
| `Seat[].Price.TotalPrice.value` | number | আসনের মূল্য। `0.00` = বিনামূল্যে |
| `Seat[].isChargeable` | boolean | `true` = পেইড আসন, `false` = বিনামূল্যে |
| `Seat[].HeldAncillary` | object | যদি কোনো যাত্রী এই আসনে আগে থেকে থাকেন |

#### আসন বৈশিষ্ট্য কোড

| কোড | বাংলা অর্থ |
|---|---|
| `W` | জানালার আসন |
| `A` | করিডোরের আসন |
| `M` | মাঝখানের আসন |
| `E` | Exit Row — অতিরিক্ত পায়ের জায়গা, বসার সীমাবদ্ধতা |
| `B` | Bulkhead — কেবিন সেকশনের সামনের সারি |
| `L` | অতিরিক্ত legroom |
| `O` | Overwing — ডানার উপরে |
| `CH` | Chargeable — পেইড আসন |
| `UP` | Upper deck (যেমন A380 বিমানে) |

---

## পর্ব ৫ — মডিউল ৪: ডকুমেন্ট প্রডাকশন ও টিকেটিং

### ৫.১ টিকেট ইস্যু — Post-Commit Workbench Flow

**উদ্দেশ্য:** PNR তৈরির পর আসল e-ticket ইস্যু করা।

#### ধাপ ১ — Post-Commit Workbench তৈরি

```json
{
  "@type": "ReservationWorkbench",
  "Reservation": {
    "Locator": [{ "value": "ABCDEF", "source": "1G" }]
  }
}
```

#### ধাপ ২ — পেমেন্ট যোগ (FOP)

#### Form of Payment (FOP) ফিল্ড

| ফিল্ড | বাধ্যতামূলক | বিবরণ |
|---|---|---|
| `FormOfPayment.@type` | ✅ হ্যাঁ | `"FormOfPaymentPaymentCard"` (ক্রেডিট কার্ড) বা `"FormOfPaymentCash"` |
| `FormOfPayment.CardType` | শর্তযুক্ত | ক্রেডিট কার্ড ধরনের কোড — নিচে দেখো |
| `FormOfPayment.CardNumber` | শর্তযুক্ত | কার্ড নম্বর (সাধারণত tokenized) |
| `FormOfPayment.ExpiryDate` | শর্তযুক্ত | কার্ডের মেয়াদ `MM/YY` ফরম্যাটে |
| `FormOfPayment.CardholderName` | শর্তযুক্ত | কার্ডে লেখা নাম |
| `FormOfPayment.Amount.value` | ✅ হ্যাঁ | পেমেন্টের পরিমাণ |
| `FormOfPayment.Amount.code` | ✅ হ্যাঁ | মুদ্রার কোড |

#### ক্রেডিট কার্ড ধরনের কোড

| কোড | কার্ড নেটওয়ার্ক |
|---|---|
| `VI` | Visa |
| `CA` | Mastercard |
| `AX` | American Express |
| `DS` | Discover |
| `TP` | UATP (Universal Air Travel Plan) |
| `JCB` | JCB |
| `DC` | Diners Club |

#### টিকেটিং Response ফিল্ড

| ফিল্ড | বিবরণ |
|---|---|
| `TicketNumber[].value` | ১৩ সংখ্যার IATA টিকেট নম্বর (যেমন `"2321234567890"`) |
| `TicketNumber[].ticketStatus` | `"Issued"` (ইস্যু হয়েছে), `"Voided"`, `"Refunded"`, `"Exchanged"` |
| `TicketNumber[].passengerRef` | কোন যাত্রীর টিকেট |

---

## পর্ব ৬ — মডিউল ৫: PNR ম্যানেজমেন্ট

### ৬.১ রিজার্ভেশন দেখা — `GET /reservation/{reservationID}`

| Response ফিল্ড | বিবরণ |
|---|---|
| `Reservation.Locator` | GDS ও NDC locator কোড তালিকা |
| `Reservation.Traveler` | সম্পূর্ণ যাত্রী রেকর্ড |
| `Reservation.Offer` | বুকিং-এ ফ্লাইট অফার |
| `Reservation.Payment` | প্রযোজ্য পেমেন্ট |
| `Reservation.Ticket` | ইস্যু করা টিকেট তথ্য |
| `Reservation.RemarkList` | সব SSR, OSI ও এজেন্সি রিমার্ক |
| `Reservation.StatusCode` | `"Confirmed"`, `"Ticketed"`, `"Cancelled"`, `"Voided"` |
| `Reservation.CreatedDateTime` | PNR কখন তৈরি হয়েছিল |
| `Reservation.TicketingDeadline` | টিকেটের সময়সীমা — এর আগে টিকেট না করলে auto-cancel |

---

### ৬.২ Queue ম্যানেজমেন্ট

#### Queue Placement ফিল্ড

| ফিল্ড | বাধ্যতামূলক | বিবরণ |
|---|---|---|
| `QueueIdentifier.queueNumber` | ✅ হ্যাঁ | লক্ষ্য queue নম্বর |
| `QueueIdentifier.pccCode` | ✅ হ্যাঁ | Queue-এর PCC কোড |
| `ReservationIdentifier.value` | ✅ হ্যাঁ | Queue-তে রাখার PNR locator |

---

## পর্ব ৭ — মডিউল ৬: বিনিময়, রিফান্ড ও বাতিলকরণ

### ৭.১ Exchange Search ফিল্ড

| ফিল্ড | বাধ্যতামূলক | বিবরণ |
|---|---|---|
| `ExchangeRequest.TicketNumber` | ✅ হ্যাঁ | বিনিময়যোগ্য টিকেট |
| `SearchCriteriaFlight` | ✅ হ্যাঁ | নতুন পছন্দনীয় যাত্রাপথ |

#### Exchange Response অতিরিক্ত ফিল্ড

| ফিল্ড | বিবরণ |
|---|---|
| `ExchangeOffer.PriceDifference` | নেট পরিমাণ (`+` = অতিরিক্ত সংগ্রহ, `-` = রিফান্ড) |
| `ExchangeOffer.ChangePenalty` | carrier-এর পরিবর্তন ফি |
| `ExchangeOffer.PriceAfterExchange` | বিনিময়ের পরে নতুন মোট |
| `ExchangeOffer.FareDifference` | শুধু base fare-এর পার্থক্য |
| `ExchangeOffer.TaxDifference` | ট্যাক্সের পার্থক্য |

---

### ৭.২ Void টিকেট

#### Single Void — `PUT /ticket/tickets/updatestatus/{ticketID}`

| প্যারামিটার | বিবরণ |
|---|---|
| `ticketID` (path) | ১৩ সংখ্যার void করার টিকেট নম্বর |
| Body `status` | `"Voided"` |

> [!WARNING]
> Void সাধারণত টিকেট ইস্যুর একই দিনে সম্ভব। Void window বন্ধ হলে Refund ব্যবহার করতে হবে।

#### Batch Void — `POST https://api.travelport.net/11/documents/void`

> [!WARNING]
> এই endpoint-এর পাথে `/air/` নেই! `https://api.travelport.net/11/documents/void` — `/air/` যোগ করবে না।

| ফিল্ড | বাধ্যতামূলক | বিবরণ |
|---|---|---|
| `locator` | ✅ হ্যাঁ | PNR locator কোড |
| `documentVoid[].documentType` | ✅ হ্যাঁ | `"Ticket"` বা `"EMD"` |
| `documentVoid[].number` | ঐচ্ছিক | নির্দিষ্ট টিকেট নম্বর — না দিলে PNR-এর সব টিকেট void হয় |

---

### ৭.৩ Refund Quote ফিল্ড ও Response

| ফিল্ড | বিবরণ |
|---|---|
| `RefundQuote.TotalRefundAmount` | যাত্রী মোট কত ফেরত পাবেন |
| `RefundQuote.Penalty` | প্রযোজ্য বাতিলের জরিমানা |
| `RefundQuote.NetRefund` | জরিমানা বাদ দিয়ে রিফান্ড |
| `RefundQuote.RefundableTaxes` | ফেরতযোগ্য ট্যাক্স |
| `RefundQuote.NonRefundableTaxes` | অ-ফেরতযোগ্য ট্যাক্স (YQ/YR সাধারণত ফেরত আসে না) |
| `RefundQuote.BaseFareRefund` | জরিমানা বাদে base fare রিফান্ড |
| `RefundQuote.IsRefundable` | `false` = ভাড়া সম্পূর্ণ নন-রিফান্ডেবল |
| `RefundQuote.RefundDeadline` | এই তারিখের পর রিফান্ড যোগ্যতা পরিবর্তন হতে পারে |

---

## পর্ব ৮ — মডিউল ৭: অ্যাঙ্কিলারি শপিং

### ৮.১ Ancillary Shop Response ফিল্ড

| ফিল্ড | বিবরণ |
|---|---|
| `AncillaryOffering[].AncillaryType` | বিভাগ: `"Baggage"`, `"Seat"`, `"Meal"`, `"PriorityBoarding"`, `"Lounge"` |
| `AncillaryOffering[].Name` | পঠনযোগ্য নাম (যেমন `"Extra 23kg Bag"`) |
| `AncillaryOffering[].Price.TotalPrice.value` | অ্যাঙ্কিলারির মূল্য |
| `AncillaryOffering[].SubCode` | IATA RFIC sub-code |
| `AncillaryOffering[].RFIC` | Revenue Filing Identification Code — অ্যাঙ্কিলারি বিভাগের industry কোড |
| `AncillaryOffering[].MaxQuantity` | প্রতি যাত্রীতে সর্বোচ্চ কতটি কিনতে পারবে |

#### RFIC কোড (অ্যাঙ্কিলারি বিভাগ)

| কোড | বিভাগ (বাংলা) |
|---|---|
| `A` | বিমান পরিবহন |
| `B` | স্থল পরিবহন |
| `C` | ব্যাগেজ |
| `D` | আর্থিক প্রভাব |
| `E` | বিমানবন্দর সেবা |
| `F` | পণ্যদ্রব্য |
| `G` | উড়ানে সেবা |
| `H` | অন্যান্য সেবা |

---

## পর্ব ৯ — Error হ্যান্ডলিং রেফারেন্স

### HTTP Status কোড

| কোড | অবস্থা | সাধারণ কারণ | কী করবে |
|---|---|---|---|
| `200` | সফল | সফল প্রক্রিয়া | Response স্বাভাবিকভাবে প্রক্রিয়া করো |
| `201` | তৈরি | Resource তৈরি হয়েছে (workbench) | Response-এর ID capture করো |
| `400` | খারাপ Request | প্রয়োজনীয় ফিল্ড নেই, ভুল `@type`, ভুল তারিখ ফরম্যাট | `Result.Error.Message` দেখো |
| `401` | অননুমোদিত | মেয়াদোত্তীর্ণ token, ভুল credentials, XAUTH header নেই | OAuth token refresh করো |
| `403` | নিষিদ্ধ | NDC carrier-এ provisioned নয়, অনুমতি নেই | Travelport-এর সাথে provisioning যাচাই করো |
| `404` | পাওয়া যায়নি | ভুল workbenchID, মেয়াদোত্তীর্ণ offer ID | পুনরায় সার্চ করো |
| `409` | সংঘাত | Workbench session conflict | অপেক্ষা করে retry করো |
| `429` | অনেক বেশি Request | Rate limit অতিক্রম | Exponential backoff, Travelport-এ যোগাযোগ করো |
| `500` | Server Error | Travelport/GDS সিস্টেম সমস্যা | পরে retry করো |
| `503` | সেবা অনুপলব্ধ | Travelport রক্ষণাবেক্ষণ বা এয়ারলাইন ডাউনটাইম | পরে retry করো |

### Error Response কাঠামো

```json
{
  "Result": {
    "Error": [
      {
        "StatusCode": 400,
        "Message": "SearchCriteriaFlight is required",
        "SourceID": "API",
        "SourceCode": "1000",
        "Category": "Validation"
      }
    ]
  }
}
```

| Error ফিল্ড | বিবরণ |
|---|---|
| `Message` | কী ভুল হয়েছে তার পঠনযোগ্য বিবরণ |
| `SourceID` | কে error তৈরি করেছে: `"API"` (business validation), `"1G"` (Galileo GDS), বা এয়ারলাইন কোড (NDC) |
| `SourceCode` | সংখ্যামূলক বিভাগ: `1` = দুর্বলতা, `1000` = validation, `2000` = system-wide |
| `Category` | `"Validation"`, `"System"`, `"Business"` |

---

## পর্ব ১০ — Branded Fares ও Fare Family

| ফিল্ড | বিবরণ |
|---|---|
| `ProductBrandOffering[].BrandTier` | Tier কোড: `BF1` (সস্তা) থেকে `BF5` (সবচেয়ে প্রিমিয়াম) |
| `ProductBrandOffering[].BrandName` | এয়ারলাইনের বাণিজ্যিক ব্র্যান্ড নাম (যেমন `"ECONOMY LIGHT"`) |
| `ProductBrandOffering[].BrandAttribute[].commercialName` | অন্তর্ভুক্ত সেবার নাম |
| `BrandAttribute[].application` | `"Included"` (অন্তর্ভুক্ত), `"Available"` (কিনতে পারবে), `"NotAvailable"` (নেই) |

---

## পর্ব ১১ — NDC বনাম GDS তুলনা (বিস্তারিত)

| বিষয় | GDS আচরণ | NDC আচরণ |
|---|---|---|
| টিকেট ইস্যু | Travelport টিকেট ইস্যু করে | এয়ারলাইন নিজে টিকেট ইস্যু করে |
| সিট ম্যাপ | বুকিং-এর আগেও দেখা যায় | অবশ্যই workbench সেশনের মধ্যে |
| Payload mode | Reference payload যথেষ্ট | Full payload লাগতে পারে |
| বিনিময় | Travelport exchange endpoint | এয়ারলাইনের নিজস্ব order management |
| PNR locator | একটি GDS locator | GDS passive locator + এয়ারলাইন Order ID |
| সর্বোচ্চ O&D | ৬ | ৩ |
| মূল্য cache | দীর্ঘ TTL | সংক্ষিপ্ত বা cache নেই — বুকিং-এর আগে reprice করো |

### NDC Response Locator ফিল্ড

| ফিল্ড | বিবরণ |
|---|---|
| `Locator[].source = "1G"` | Travelport/GDS passive record locator |
| `Locator[].source = "AA"` | এয়ারলাইনের নিজস্ব Order ID (AA = American Airlines) |

---

## পর্ব ১২ — সম্পূর্ণ সার্চ Request উদাহরণ

```json
POST https://api.travelport.net/11/air/catalog/search/catalogproductofferings
Authorization: Bearer eyJhbGciOiJSUzI1Ni...
XAUTH_TRAVELPORT_ACCESSGROUP: BDAC
Content-Type: application/json
Accept: application/json
Accept-Encoding: gzip, deflate
TraceId: 550e8400-e29b-41d4-a716-446655440000

{
  "CatalogProductOfferingsQueryRequest": {
    "@type": "CatalogProductOfferingsQueryRequest",
    "QuerySearchCriteriaFlights": {
      "@type": "QuerySearchCriteriaFlights",
      "PassengerCriteria": [
        {
          "@type": "PassengerCriteria",
          "PassengerQuantityCode": [
            { "code": "ADT", "quantity": 1 },
            { "code": "CNN", "quantity": 1, "age": 7 }
          ]
        }
      ],
      "SearchCriteriaFlight": [
        {
          "@type": "SearchCriteriaFlight",
          "From": { "value": "DAC" },
          "To": { "value": "DXB" },
          "DepartureDate": "2026-12-15"
        },
        {
          "@type": "SearchCriteriaFlight",
          "From": { "value": "DXB" },
          "To": { "value": "DAC" },
          "DepartureDate": "2026-12-25"
        }
      ],
      "SearchModifiersAir": {
        "@type": "SearchModifiersAir",
        "SearchRepresentation": "Journey",
        "MaxNumberOfStops": 1,
        "CabinPreference": [
          { "cabin": "Economy", "preference": "Preferred" }
        ],
        "offersPerPage": 20,
        "AccountCode": [{ "value": "CORP2024" }]
      }
    }
  }
}
```

---

## পর্ব ১৩ — সম্পূর্ণ বুকিং ক্রম (১৪টি ধাপ)

```
ধাপ ১:  POST /oauth/token → access_token পাওয়া
ধাপ ২:  POST /catalog/search/catalogproductofferings → offer.id পাওয়া
ধাপ ৩:  POST /catalog/price/catalogproductofferings → মূল্য নিশ্চিতকরণ
ধাপ ৪:  POST /book/airoffer/reservationworkbench → workbenchID পাওয়া
ধাপ ৫:  POST /book/airoffer/reservationworkbench/{id}/offers/build → ফ্লাইট যোগ
ধাপ ৬:  POST /book/traveler/reservationworkbench/{id}/travelers → যাত্রী যোগ
ধাপ ৭:  POST /catalog/search/seatmap → সিট ম্যাপ দেখা (ঐচ্ছিক)
ধাপ ৮:  POST .../offers/buildseatoffers → আসন নির্বাচন (ঐচ্ছিক)
ধাপ ৯:  POST .../offers/buildancillaryoffersfromcatalogofferings → অ্যাঙ্কিলারি (ঐচ্ছিক)
ধাপ ১০: POST /book/remarks/.../reservationcomments/list → SSR/OSI (ঐচ্ছিক)
ধাপ ১১: POST .../commit → PNR locator পাওয়া
ধাপ ১২: POST /book/airoffer/reservationworkbench → টিকেটিং workbench তৈরি
ধাপ ১৩: POST .../offers/buildpaymentoffer → পেমেন্ট FOP যোগ
ধাপ ১৪: POST .../commit → টিকেট ইস্যু → টিকেট নম্বর পাওয়া ✅
```

---

## পর্ব ১৪ — তোমার Codebase-এর Supplier Config

```json
{
  "name": "Travelport Bangladesh",
  "code": "TP-BD-DAC",
  "integration_provider": "travelport",
  "type": "GDS",
  "credentials": {
    "client_id": "<portal থেকে>",
    "client_secret": "<portal থেকে>",
    "access_group": "BDAC"
  },
  "endpoints": {
    "base_url": "https://api.travelport.net/11/air/",
    "auth_url": "https://auth.travelport.net/oauth/token",
    "void_url": "https://api.travelport.net/11/",
    "pre_prod_base_url": "https://api.pp.travelport.net/11/air/",
    "pre_prod_auth_url": "https://auth.pp.travelport.net/oauth/token"
  },
  "settings": {
    "gds_code": "1G",
    "ndc_enabled": true,
    "corporate_enabled": false,
    "default_currency": "BDT",
    "token_ttl_seconds": 86000,
    "timeout_seconds": 30,
    "max_passengers": 9
  }
}
```

---

*এই ডকুমেন্ট SkyNovia OTA Engine-এর জন্য সর্বোচ্চ বিস্তারিত Travelport JSON API v11 রেফারেন্স হিসেবে প্রস্তুত*
*কভার করে: Auth · Search · Price · Fare Rules · Booking · Travelers · SSR · OSI · Seats · Ancillaries · Ticketing · PNR · Queue · Exchange · Refund · Void · NDC · Branded Fares · Error Codes*
*সেপ্টেম্বর ২০২৬*
