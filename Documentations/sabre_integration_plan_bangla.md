# Sabre REST API — সর্বোচ্চ বিস্তারিত রেফারেন্স গাইড
### SkyNovia OTA Engine · বাংলা সংস্করণ

---

## পরিভাষা — গুরুত্বপূর্ণ শব্দের সংজ্ঞা

| শব্দ | পূর্ণরূপ | সংজ্ঞা |
|---|---|---|
| **BFM** | Bargain Finder Max | Sabre-এর প্রধান low-fare বিমান সার্চ API |
| **PNR** | Passenger Name Record | Sabre GDS-এ বুকিং রেকর্ড — সব যাত্রী ও ফ্লাইটের তথ্য |
| **PCC** | Pseudo City Code | Sabre-এ তোমার এজেন্সির অনন্য আইডেন্টিফায়ার (যেমন `BDAC`) |
| **LNIATA** | Low-level Network Interface and Agency Travel Assignment | Sabre terminal/workstation-এর হার্ডওয়্যার আইডেন্টিফায়ার |
| **PQ** | Price Quote | PNR-এ সংরক্ষিত মূল্য রেকর্ড যা থেকে টিকেট ইস্যু হয় |
| **APIS** | Advance Passenger Information System | যাত্রার আগে সরকার/এয়ারলাইনে যাত্রীর তথ্য পাঠানোর আইনি প্রয়োজনীয়তা |
| **SSR** | Special Service Request | বিমান কোম্পানিকে বিশেষ সেবার কোডেড অনুরোধ (খাবার, হুইলচেয়ার, APIS) |
| **SecureFlight** | — | TSA-র মার্কিন প্রোগ্রাম — যুক্তরাষ্ট্রগামী ফ্লাইটে DOB ও Gender বাধ্যতামূলক |
| **ETA** | Electronic Ticketing Authority | একটি PCC-কে নির্দিষ্ট carrier-এর e-ticket ইস্যুর অনুমতি |
| **RBD** | Reservation Booking Designator | একক-অক্ষর booking class কোড (Y, K, L, ইত্যাদি) |
| **OTA** | Open Travel Alliance | Sabre-এর legacy schema-তে ব্যবহৃত XML মান (`OTA_AirLowFareSearchRQ`) |
| **EMD** | Electronic Miscellaneous Document | অ্যাঙ্কিলারির ইলেকট্রনিক ডকুমেন্ট |
| **RPH** | Reference Place Holder | Sabre array-এ আইটেম রেফারেন্সের ক্রমিক সংখ্যা (string হিসেবে) |
| `7TAW` | — | Sabre টিকেটিং সময়-সীমা কোড: "৭ দিনের মধ্যে টিকেট না করলে auto-cancel" |
| **ADM** | Agency Debit Memo | ভুল ভাড়া বা বুকিংয়ের জন্য এয়ারলাইন থেকে এজেন্সিকে আর্থিক জরিমানা |
| **IntelliSell** | — | Sabre-এর merchandising/caching layer যা BFM ফলাফল পরিচালনা করে |

---

## পর্ব ১ — অথেন্টিকেশন (Authentication)

### ১.১ Sabre অথেন্টিকেশন আর্কিটেকচার

Sabre **দুই-স্তরের** অথেন্টিকেশন ব্যবহার করে:
1. **Basic Auth** (Base64-encoded `client_id:client_secret`) — Token endpoint-এ পাঠানো হয়
2. **Bearer Token** — Token endpoint থেকে পাওয়া যায়, সব API কলে ব্যবহৃত হয়

Token **Redis**-এ cache করা হয় supplier-নির্দিষ্ট key দিয়ে।

---

### ১.২ Token Endpoint

**পদ্ধতি:** `POST`
**URL:** `{base_url}/v3/auth/token`
*(Pre-prod: `https://api.test.sabre.com/v3/auth/token`)*
*(Production: `https://api.sabre.com/v3/auth/token`)*

**উদ্দেশ্য:** Basic credentials দিয়ে Bearer access token পাওয়া। Token Redis-এ cache করা হয় supplier অনুযায়ী।

#### Request Headers

| Header | মান | বাধ্যতামূলক | বিবরণ |
|---|---|---|---|
| `Authorization` | `Basic {base64(client_id:client_secret)}` | ✅ হ্যাঁ | `clientId:clientSecret`-এর Base64 encoding। তোমার code `_get_encoded_credentials()` ব্যবহার করে — precomputed `auth_secret` থাকলে সেটা ব্যবহার করে, না হলে live compute |
| `Content-Type` | `application/x-www-form-urlencoded` | ✅ হ্যাঁ | Token endpoint-এ form-encoded body দরকার |
| `Accept` | `application/json` | পরামর্শ | JSON response চাই |

#### Request Body (Form Parameters)

| প্যারামিটার | ধরন | বাধ্যতামূলক | বিবরণ |
|---|---|---|---|
| `grant_type` | string | ✅ হ্যাঁ | সর্বদা `"password"` — Sabre-এ Travelport-এর `client_credentials`-এর বিপরীতে এটি ব্যবহার হয় |
| `username` | string | ✅ হ্যাঁ | তোমার Sabre agency username |
| `password` | string | ✅ হ্যাঁ | তোমার Sabre agency password |

> [!IMPORTANT]
> Sabre `grant_type=password` ব্যবহার করে — Travelport-এর `client_credentials`-এর থেকে আলাদা। Username + Password, Basic Auth header-এর পাশাপাশি পাঠাতে হয়।

#### Response ফিল্ড

| ফিল্ড | ধরন | বিবরণ |
|---|---|---|
| `access_token` | string | ⭐ Bearer token — সব API call-এ ব্যবহার |
| `token_type` | string | সর্বদা `"bearer"` |
| `expires_in` | integer | Token কতক্ষণ বৈধ থাকবে সেকেন্ডে (সাধারণত `3600` = ১ ঘণ্টা) |
| `scope` | string | অনুমতির পরিধি |

> [!NOTE]
> তোমার code token expiry-তে **৬০-সেকেন্ডের safety buffer** যোগ করে (`expires_in - 60`) — race condition এড়াতে। Redis TTL = `token_expiry_days × 24 × 60` মিনিট।

---

### ১.৩ Token Cache Key (তোমার Implementation)

```python
# প্রতি supplier instance-এর Redis key ফরম্যাট
cache_key = f"sabre_access_token:{supplier_id}:{pcc}"
```

`401` response আসলে token স্বয়ংক্রিয়ভাবে refresh হয় (threading lock দিয়ে concurrent refresh রোধ করা হয়)।

---

### ১.৪ সব API কলে Standard Headers

| Header | মান | বাধ্যতামূলক | বিবরণ |
|---|---|---|---|
| `Authorization` | `Bearer {access_token}` | ✅ হ্যাঁ | Token endpoint থেকে পাওয়া |
| `Content-Type` | `application/json` | ✅ POST-এ | POST/PUT request-এর জন্য |
| `Accept` | `application/json` | পরামর্শ | JSON response নিশ্চিত করে |

---

## পর্ব ২ — সব Endpoint রেফারেন্স

| ফিচার | পদ্ধতি | Endpoint | তোমার Code-এ |
|---|---|---|---|
| Auth Token | POST | `/v3/auth/token` | `SabreEndpoints.REST_AUTH_TOKEN` |
| ফ্লাইট সার্চ (BFM) | POST | `/v5/offers/shop` | `SabreEndpoints.BARGAIN_FINDER_MAX` |
| Pricing / FlightCheck | POST | `/v1/offers/flightCheck` | `SabreEndpoints.FLIGHT_CHECK` |
| সিট ম্যাপ | POST | `/v3/offers/seatmap` | `SabreEndpoints.SEAT_MAP` |
| ব্যাগেজ Allowance | POST | `/v4/offers/baggage` | `SabreEndpoints.BAGGAGE_ALLOWANCE` |
| Fare Rules | POST | `/v1/offers/fareRules` | `SabreEndpoints.STRUCTURE_FARE_RULES` |
| PNR তৈরি | POST | `/v2.4.0/passenger/records?mode=create` | `SabreEndpoints.CREATE_PNR` |
| PNR Reprice | POST | `/v2.4.0/passenger/records?mode=reprice` | `SabreEndpoints.CREATE_PNR` |
| টিকেট ইস্যু | POST | `/v1.3.0/air/ticket` | `SabreEndpoints.ISSUE_TICKET` |
| PNR বিবরণ | GET | `/v1/trip/orders/getBooking` | `SabreEndpoints.GET_PNR_DETAILS` |
| ইটিনারেরি বাতিল | POST | `/v1/trip/orders/cancelBooking` | `SabreEndpoints.CANCEL_ITINERARY` |
| Void টিকেট | POST | `/v1/trip/orders/voidFlightTickets` | `SabreEndpoints.VOID_TICKET` |
| Exchange টিকেট | POST | `/v1.3.0/air/ticket` | `SabreEndpoints.EXCHANGE_TICKET` |
| Queue স্থাপন | POST | `/v1/trip/orders/queue` | `SabreEndpoints.QUEUE_PLACE` |

---

## পর্ব ৩ — মডিউল ১: বিমান সার্চ (BFM)

### ৩.১ Bargain Finder Max — `POST /v5/offers/shop`

**উদ্দেশ্য:** প্রধান low-fare ফ্লাইট সার্চ। ATPCO, NDC এবং LCC কন্টেন্ট একসাথে দেয়।

**Schema root:** `OTA_AirLowFareSearchRQ` (OTA standard wrapper)

---

#### সম্পূর্ণ Request Body কাঠামো

```json
{
  "OTA_AirLowFareSearchRQ": {
    "Version": "4.3.0",
    "POS": { ... },
    "OriginDestinationInformation": [ ... ],
    "TravelerInfoSummary": { ... },
    "TravelPreferences": { ... },
    "TPA_Extensions": { ... }
  }
}
```

---

#### `POS` — Point of Sale (বিক্রয়ের স্থান)

| ফিল্ড | ধরন | বাধ্যতামূলক | বিবরণ |
|---|---|---|---|
| `POS.Source` | array | ✅ হ্যাঁ | Request করা এজেন্সি চিহ্নিত করে |
| `Source[].PseudoCityCode` | string | ✅ হ্যাঁ | তোমার এজেন্সির PCC (যেমন `"BDAC"`) — config-এর `self.pcc` থেকে |
| `Source[].RequestorID.Type` | string | ✅ হ্যাঁ | এজেন্সির জন্য সর্বদা `"1"` |
| `Source[].RequestorID.ID` | string | ✅ হ্যাঁ | সর্বদা `"1"` |
| `Source[].RequestorID.CompanyName.Code` | string | ✅ হ্যাঁ | সর্বদা `"TN"` (Travel Network) |

---

#### `OriginDestinationInformation` — যাত্রাখণ্ড

প্রতি O&D leg-এর জন্য একটি array element। Round-trip = ২ element। Multi-city = N element।

| ফিল্ড | ধরন | বাধ্যতামূলক | বিবরণ |
|---|---|---|---|
| `RPH` | string | ✅ হ্যাঁ | **Reference Place Holder** — string হিসেবে ক্রমিক সংখ্যা: `"1"`, `"2"`, ইত্যাদি। ফলাফলে cross-reference করতে ব্যবহার |
| `DepartureDateTime` | string | ✅ হ্যাঁ | ISO 8601 datetime: `"YYYY-MM-DDT00:00:00"`. সময়ের পছন্দ না থাকলে `T00:00:00` ব্যবহার করো |
| `OriginLocation.LocationCode` | string | ✅ হ্যাঁ | IATA ৩ অক্ষরের প্রস্থান বিমানবন্দর কোড (যেমন `"DAC"`) |
| `DestinationLocation.LocationCode` | string | ✅ হ্যাঁ | IATA ৩ অক্ষরের গন্তব্য বিমানবন্দর কোড (যেমন `"DXB"`) |

---

#### `TravelerInfoSummary` — যাত্রী তথ্য

| ফিল্ড | ধরন | বাধ্যতামূলক | বিবরণ |
|---|---|---|---|
| `SeatsRequested` | array[integer] | ✅ হ্যাঁ | মোট আসন প্রয়োজন। একক-element array: `[adults + children + infants]` |
| `AirTravelerAvail` | array | ✅ হ্যাঁ | যাত্রীর ধরন ও সংখ্যা |
| `AirTravelerAvail[].PassengerTypeQuantity` | array | ✅ হ্যাঁ | প্রতি element = একটি যাত্রীর ধরন + সংখ্যা |
| `PassengerTypeQuantity[].Code` | string | ✅ হ্যাঁ | PTC কোড — নিচে সম্পূর্ণ তালিকা দেখো |
| `PassengerTypeQuantity[].Quantity` | integer | ✅ হ্যাঁ | এই ধরনের যাত্রীর সংখ্যা |

**উদাহরণ:**
```json
"TravelerInfoSummary": {
  "SeatsRequested": [3],
  "AirTravelerAvail": [{
    "PassengerTypeQuantity": [
      { "Code": "ADT", "Quantity": 1 },
      { "Code": "CNN", "Quantity": 1 },
      { "Code": "INF", "Quantity": 1 }
    ]
  }]
}
```

---

#### Passenger Type Codes (PTC) — Sabre রেফারেন্স

| কোড | অর্থ | বয়সসীমা | নোট |
|---|---|---|---|
| `ADT` | প্রাপ্তবয়স্ক | ১২+ | ডিফল্ট — তোমার code-এ প্রধান যাত্রী |
| `CNN` | শিশু | ২–১১ | তোমার code-এ children-এর জন্য ব্যবহৃত |
| `INF` | কোলের শিশু (আসন নেই) | ২-এর নিচে | তোমার code-এ infants-এর জন্য |
| `INS` | শিশু (আসনসহ) | ২-এর নিচে | নিজের আসন আছে |
| `UMNR` | একা ভ্রমণকারী অপ্রাপ্তবয়স্ক | ৫–১৭ | SSR UMNR বাধ্যতামূলক |
| `STU` | ছাত্র | বিভিন্ন | ছাত্র ছাড়ের ভাড়া |
| `GVT` | সরকারি | — | সরকারি হার |
| `MIL` | সামরিক | — | সশস্ত্র বাহিনীর ছাড় |
| `SRC` | প্রবীণ নাগরিক | ৬৫+ | প্রবীণ ছাড় |

---

#### `TravelPreferences` — মডিফায়ার সম্পূর্ণ রেফারেন্স

| ফিল্ড | ধরন | বাধ্যতামূলক | কখন ব্যবহার | বিবরণ |
|---|---|---|---|---|
| `MaxStopsQuantity` | integer | ঐচ্ছিক | Direct ফ্লাইট ফিল্টার | `0` = nonstop শুধু। `direct_flights_only=true` বা `max_stops` নির্দিষ্ট হলে set করো |
| `CabinPref` | array | ঐচ্ছিক | কেবিন ক্লাস ফিল্টার | পছন্দনীয় কেবিন তালিকা |
| `CabinPref[].Cabin` | string | ঐচ্ছিক | — | **একক-অক্ষর কেবিন কোড** — নিচের টেবিল দেখো |
| `CabinPref[].PreferLevel` | string | ঐচ্ছিক | — | `"Only"` (কঠোর — শুধু এই কেবিন), `"Preferred"` (নরম পছন্দ) |
| `VendorPref` | array | ঐচ্ছিক | এয়ারলাইন ফিল্টার | এয়ারলাইন অন্তর্ভুক্তি/বাদ দেওয়ার তালিকা |
| `VendorPref[].Code` | string | ঐচ্ছিক | — | IATA ২ অক্ষরের এয়ারলাইন কোড |
| `VendorPref[].Type` | string | ঐচ্ছিক | — | `"Marketing"` (marketing carrier) |
| `VendorPref[].Exclude` | boolean | ঐচ্ছিক | এয়ারলাইন বাদ দিতে | `true` = এই এয়ারলাইন বাদ দাও |

---

#### Cabin Class কোড — Sabre BFM

| Sabre কোড | কেবিনের নাম | বিবরণ |
|---|---|---|
| `Y` | ইকোনমি | সাধারণ ইকোনমি ক্লাস |
| `S` | প্রিমিয়াম ইকোনমি | কিছু carrier-এ W-class সমতুল্য |
| `C` | বিজনেস | সাধারণ বিজনেস ক্লাস |
| `J` | প্রিমিয়াম বিজনেস | উচ্চ বিজনেস / উচ্চতর J ক্লাস |
| `F` | ফার্স্ট ক্লাস | সাধারণ ফার্স্ট ক্লাস |
| `P` | প্রিমিয়াম ফার্স্ট | সর্বোচ্চ ফার্স্ট (যেমন Emirates First) |

> [!NOTE]
> `cabin_class = "ALL"` হলে তোমার code সব ৬টি কেবিন কোড `"Preferred"` preference সহ পাঠায় — BFM সবচেয়ে সস্তা কেবিন-নির্বিশেষে দেয়।

---

#### `PriceRequestInformation` — Corporate ও মুদ্রা (`TravelerInfoSummary`-এর ভেতরে)

| ফিল্ড | ধরন | বাধ্যতামূলক | বিবরণ |
|---|---|---|---|
| `CurrencyCode` | string | ঐচ্ছিক | নির্দিষ্ট মুদ্রায় pricing-এর জন্য (যেমন `"USD"`, `"BDT"`) |
| `NegotiatedFareCode` | array | ঐচ্ছিক | Corporate/private negotiated fare কোড। **অবশ্যই `[A-Za-z]{3}[0-9]{2}` pattern-এ হতে হবে** (যেমন `"ABC12"`) — তোমার code regex দিয়ে validate করে, অবৈধ হলে skip করে |
| `NegotiatedFareCode[].Code` | string | ঐচ্ছিক | কর্পোরেট কোড |
| `AccountCode` | array | ঐচ্ছিক | Agency/corporate account code |
| `AccountCode[].Code` | string | ঐচ্ছিক | Account code string |

---

#### `TPA_Extensions` — IntelliSell ও Advanced Options

| ফিল্ড | ধরন | বাধ্যতামূলক | বিবরণ |
|---|---|---|---|
| `IntelliSellTransaction.RequestType.Name` | string | ✅ হ্যাঁ | Caching/result ধরন: `"50ITINS"` (standard ৫০ ফলাফল), `"ADRC"` (নমনীয় তারিখের জন্য Alternate Date Request) |

> [!NOTE]
> `flexible_dates=true` হলে তোমার code স্বয়ংক্রিয়ভাবে `"ADRC"` mode set করে। ±৩ দিনের মধ্যে সবচেয়ে সস্তা তারিখ দেয়।

---

#### BFM Response — গুরুত্বপূর্ণ ফিল্ড

| Response ফিল্ড | ধরন | বিবরণ |
|---|---|---|
| `OTA_AirLowFareSearchRS.PricedItineraries.PricedItinerary` | array | ফ্লাইট বিকল্পের তালিকা — দাম অনুযায়ী সাজানো |
| `PricedItinerary[].SequenceNumber` | integer | ফলাফলের অবস্থান/rank |
| `AirItinerary.OriginDestinationOptions.OriginDestinationOption[].FlightSegment` | array | ফ্লাইট সেগমেন্ট তালিকা |
| `FlightSegment[].DepartureAirport.LocationCode` | string | প্রস্থান বিমানবন্দর IATA কোড |
| `FlightSegment[].ArrivalAirport.LocationCode` | string | গন্তব্য বিমানবন্দর IATA কোড |
| `FlightSegment[].DepartureDateTime` | string | প্রস্থানের ISO 8601 datetime |
| `FlightSegment[].ArrivalDateTime` | string | আগমনের ISO 8601 datetime |
| `FlightSegment[].MarketingAirline.Code` | string | Marketing এয়ারলাইন IATA কোড |
| `FlightSegment[].OperatingAirline.Code` | string | Operating এয়ারলাইন IATA কোড (codeshare partner) |
| `FlightSegment[].FlightNumber` | string | ফ্লাইট নম্বর |
| `FlightSegment[].ResBookDesigCode` | string | Booking class (RBD). যেমন `"Y"`, `"K"` |
| `FlightSegment[].CabinClassCode` | string | কেবিন কোড |
| `FlightSegment[].ElapsedTime` | integer | ফ্লাইটের সময় মিনিটে |
| `FlightSegment[].StopQuantity` | integer | সেগমেন্টের মধ্যে থামার সংখ্যা |
| `FlightSegment[].Equipment.AirEquipType` | string | বিমানের ধরন (যেমন `"77W"` = Boeing 777-300ER) |
| `AirItineraryPricingInfo.ItinTotalFare.TotalFare.Amount` | number | মুদ্রায় মোট ভাড়া |
| `ItinTotalFare.TotalFare.CurrencyCode` | string | মুদ্রার কোড |
| `ItinTotalFare.BaseFare.Amount` | number | ট্যাক্স ছাড়া মূল ভাড়া |
| `ItinTotalFare.Taxes.Tax` | array | আইটেমাইজড ট্যাক্স তালিকা |
| `Tax[].TaxCode` | string | ট্যাক্স কোড (যেমন `"YQ"`, `"YR"`, `"BD"`) |
| `Tax[].Amount` | number | ট্যাক্সের পরিমাণ |
| `AirItineraryPricingInfo.FareInfos.FareInfo[].FareBasisCode` | string | Fare basis কোড |

---

### ৩.২ Booking Class (RBD) সাধারণ কোড

| ক্লাস | কেবিন | সাধারণ ভাড়ার ধরন |
|---|---|---|
| `F`, `A` | ফার্স্ট | ফার্স্ট ক্লাস ভাড়া |
| `P` | প্রিমিয়াম ফার্স্ট | প্রিমিয়াম ফার্স্ট |
| `J`, `C`, `D`, `I` | বিজনেস | বিজনেস ক্লাস ভাড়া |
| `W`, `S` | প্রিমিয়াম ইকোনমি | প্রিমিয়াম ইকোনমি |
| `Y`, `B` | ইকোনমি | পূর্ণ ইকোনমি ভাড়া |
| `K`, `M`, `L`, `V` | ইকোনমি | মধ্যম ইকোনমি |
| `Q`, `T`, `E`, `N`, `X` | ইকোনমি | ছাড়কৃত ইকোনমি |
| `G`, `O`, `U` | ইকোনমি | অত্যন্ত সীমাবদ্ধ ডিসকাউন্ট |

---

## পর্ব ৪ — মডিউল ২: ফ্লাইট প্রাইসিং (FlightCheck)

### ৪.১ FlightCheck — `POST /v1/offers/flightCheck`

**উদ্দেশ্য:** PNR তৈরির আগে নির্বাচিত ইটিনারেরির মূল্য ও প্রাপ্যতা পুনরায় যাচাই করো। ভাড়া এখনও বুকযোগ্য কিনা নিশ্চিত করে।

#### Request ফিল্ড

| ফিল্ড | ধরন | বাধ্যতামূলক | বিবরণ |
|---|---|---|---|
| `journeys` | array | ✅ হ্যাঁ | Journey object তালিকা (প্রতি O&D-এর জন্য একটি) |
| `journeys[].flights` | array | ✅ হ্যাঁ | এই journey-র পৃথক ফ্লাইট সেগমেন্ট |
| `flights[].departureDate` | string | ✅ হ্যাঁ | প্রস্থানের তারিখ `YYYY-MM-DD` |
| `flights[].departureTime` | string | ✅ হ্যাঁ | প্রস্থানের সময় `HH:MM` |
| `flights[].departureAirportCode` | string | ✅ হ্যাঁ | IATA প্রস্থান বিমানবন্দর |
| `flights[].arrivalDate` | string | ✅ হ্যাঁ | আগমনের তারিখ `YYYY-MM-DD` |
| `flights[].arrivalTime` | string | ✅ হ্যাঁ | আগমনের সময় `HH:MM` |
| `flights[].arrivalAirportCode` | string | ✅ হ্যাঁ | IATA গন্তব্য বিমানবন্দর |
| `flights[].marketingAirlineCode` | string | ✅ হ্যাঁ | IATA ২ অক্ষরের marketing এয়ারলাইন |
| `flights[].marketingFlightNumber` | integer | ✅ হ্যাঁ | **Integer** ফ্লাইট নম্বর — string নয়। যেমন `147` নয় `"147"` |
| `flights[].bookingClass` | string | ✅ হ্যাঁ | একক-অক্ষর RBD booking class |
| `flights[].operatingAirlineCode` | string | ঐচ্ছিক | Operating carrier কোড (codeshare ফ্লাইটের জন্য) |
| `travelers` | array | ✅ হ্যাঁ | যাত্রীর তালিকা (ধরন প্রতি নয়, ব্যক্তি প্রতি একটি) |
| `travelers[].passengerTypeCode` | string | ✅ হ্যাঁ | এই যাত্রীর PTC: `"ADT"`, `"CNN"`, `"INF"` |

> [!IMPORTANT]
> `marketingFlightNumber` অবশ্যই **integer** হতে হবে, string নয়। তোমার `_parse_sabre_segment()` helper `flight_number_int` দিয়ে এই conversion করে।

---

## পর্ব ৫ — মডিউল ৩: PNR তৈরি (বুকিং)

### ৫.১ Create PNR — `POST /v2.4.0/passenger/records?mode=create`

**উদ্দেশ্য:** Sabre GDS-এ live বুকিং তৈরি করে। এটি একটি orchestrated API যা একটি call-এ যাত্রী যোগ, সেগমেন্ট যোগ, মূল্য নির্ধারণ এবং End Transaction একসাথে করে।

---

#### `TravelItineraryAddInfo` — Agency ও যাত্রী তথ্য

##### Agency Info

| ফিল্ড | ধরন | বাধ্যতামূলক | বিবরণ |
|---|---|---|---|
| `AgencyInfo.Ticketing.TicketType` | string | ✅ হ্যাঁ | `"7TAW"` = standard auto-ticket time limit (৭ দিন)। সর্বদা এটি ব্যবহার করো |

##### CustomerInfo — যাত্রীর নাম

| ফিল্ড | ধরন | বাধ্যতামূলক | বিবরণ |
|---|---|---|---|
| `CustomerInfo.PersonName` | array | ✅ হ্যাঁ | প্রতি যাত্রীর জন্য একটি element |
| `PersonName[].NameNumber` | string | ✅ হ্যাঁ | ক্রমিক reference: `"1.1"`, `"2.1"`, `"3.1"` — ফরম্যাট: `"{n}.1"` |
| `PersonName[].GivenName` | string | ✅ হ্যাঁ | প্রথম নাম **UPPERCASE**-এ |
| `PersonName[].Surname` | string | ✅ হ্যাঁ | পদবি **UPPERCASE**-এ |

##### ContactNumbers — যোগাযোগ নম্বর

| ফিল্ড | ধরন | বাধ্যতামূলক | বিবরণ |
|---|---|---|---|
| `ContactNumbers.ContactNumber[].Phone` | string | পরামর্শ | ফোন নম্বর |
| `ContactNumber[].PhoneUseType` | string | ✅ | `"A"` = এজেন্সি, `"H"` = বাড়ি, `"B"` = ব্যবসা, `"M"` = মোবাইল |

---

#### `AirBook` — সেগমেন্ট বুকিং

| ফিল্ড | ধরন | বাধ্যতামূলক | বিবরণ |
|---|---|---|---|
| `AirBook.OriginDestinationInformation.FlightSegment` | array | ✅ হ্যাঁ | প্রতি ফ্লাইট সেগমেন্টের জন্য একটি element |
| `FlightSegment[].DepartureDateTime` | string | ✅ হ্যাঁ | ISO 8601 datetime: `"YYYY-MM-DDTHH:MM:SS"` |
| `FlightSegment[].FlightNumber` | string | ✅ হ্যাঁ | ফ্লাইট নম্বর **string** হিসেবে |
| `FlightSegment[].NumberInParty` | string | ✅ হ্যাঁ | মোট যাত্রী **string** হিসেবে (যেমন `"2"`) |
| `FlightSegment[].ResBookDesigCode` | string | ✅ হ্যাঁ | Booking class (RBD). যেমন `"Y"` |
| `FlightSegment[].Status` | string | ✅ হ্যাঁ | বুকিং status কোড — নিচে দেখো |
| `FlightSegment[].DestinationLocation.LocationCode` | string | ✅ হ্যাঁ | গন্তব্য বিমানবন্দর IATA কোড |
| `FlightSegment[].OriginLocation.LocationCode` | string | ✅ হ্যাঁ | প্রস্থান বিমানবন্দর IATA কোড |
| `FlightSegment[].MarketingAirline.Code` | string | ✅ হ্যাঁ | Marketing এয়ারলাইন IATA কোড |
| `FlightSegment[].MarketingAirline.FlightNumber` | string | ✅ হ্যাঁ | ফ্লাইট নম্বর (MarketingAirline-এর ভেতরে পুনরাবৃত্তি) |

#### সেগমেন্ট Status কোড

| কোড | অর্থ |
|---|---|
| `NN` | Need — নতুন বুকিং request করা (সাধারণত এটিই ব্যবহার হয়) |
| `SS` | Sold — বুকিং নিশ্চিত করা |
| `HK` | Holds Confirmed |
| `GK` | GDS Confirmed |
| `TK` | Ticketed |
| `UN` | Unable to confirm |

---

#### `AirPrice` — Fare সংরক্ষণ

| ফিল্ড | ধরন | বাধ্যতামূলক | বিবরণ |
|---|---|---|---|
| `AirPrice[].PriceRequestInformation.Retain` | boolean | ✅ হ্যাঁ | সর্বদা `true` — পরবর্তী টিকেটিং-এর জন্য PNR-এ price quote সংরক্ষণ করে |
| `OptionalQualifiers.PricingQualifiers.PassengerType` | array | ✅ হ্যাঁ | Pricing-এর জন্য যাত্রীর ধরন + সংখ্যা |
| `PassengerType[].Code` | string | ✅ হ্যাঁ | PTC কোড |
| `PassengerType[].Quantity` | string | ✅ হ্যাঁ | সংখ্যা **string** হিসেবে |
| `OptionalQualifiers.FlightQualifiers.ValidatingCarrier.Code` | string | ঐচ্ছিক | নির্দিষ্ট validating carrier জোর করে। তোমার PCC যে carrier-এর জন্য ETA রাখে সেক্ষেত্রে প্রয়োজন |

---

#### `SpecialReqDetails` — APIS / SecureFlight

আন্তর্জাতিক রুটে এয়ারলাইনে যাত্রীর তথ্য পাঠানোর জন্য বাধ্যতামূলক।

| ফিল্ড | ধরন | বাধ্যতামূলক | বিবরণ |
|---|---|---|---|
| `AdvancePassenger[].PersonName.NameNumber` | string | ✅ | উপরের `PersonName[].NameNumber`-এর সাথে মিলতে হবে |
| `AdvancePassenger[].PersonName.GivenName` | string | ✅ | পাসপোর্টে প্রথম নাম |
| `AdvancePassenger[].PersonName.Surname` | string | ✅ | পাসপোর্টে পদবি |
| `AdvancePassenger[].PersonName.DateOfBirth` | string | ✅ | `YYYY-MM-DD` |
| `AdvancePassenger[].PersonName.Gender` | string | ✅ | `"M"` বা `"F"` |
| `AdvancePassenger[].Document.Number` | string | ✅ | পাসপোর্ট নম্বর |
| `AdvancePassenger[].Document.IssueCountry` | string | ✅ | ইস্যুকারী দেশ ISO ২ অক্ষর (যেমন `"BD"`) |
| `AdvancePassenger[].Document.NationalityCountry` | string | ✅ | জাতীয়তা ISO ২ অক্ষর (যেমন `"BD"`) |
| `AdvancePassenger[].Document.ExpirationDate` | string | ✅ | `YYYY-MM-DD` — ভ্রমণের সময় বৈধ থাকতে হবে |
| `AdvancePassenger[].Document.Type` | string | ✅ | `"P"` = পাসপোর্ট — সর্বদা এটি ব্যবহার করো |
| `SecureFlight[].PersonName.NameNumber` | string | TSA/US ফ্লাইটে | TSA requirement — শুধু DOB ও Gender |

---

#### `PostProcessing` — End Transaction

| ফিল্ড | ধরন | বাধ্যতামূলক | বিবরণ |
|---|---|---|---|
| `EndTransaction.Source.ReceivedFrom` | string | ✅ হ্যাঁ | PNR কে submit করেছে তা রেকর্ড করে। Sabre history-তে থাকে। `"API"` বা তোমার system-এর নাম ব্যবহার করো। **Sabre-এর প্রয়োজনীয়তা — এটি ছাড়া PNR সংরক্ষিত হবে না** |

---

#### PNR তৈরির Response ফিল্ড

| ফিল্ড | ধরন | বিবরণ |
|---|---|---|
| `CreatePassengerNameRecordRS.ApplicationResults.status` | string | `"Complete"` = সফল। অন্য মান = ব্যর্থ |
| `CreatePassengerNameRecordRS.ItineraryRef.ID` | string | ⭐ **PNR Locator** — ৬ অক্ষরের Sabre record locator (যেমন `"ABCDEF"`) |
| `CreatePassengerNameRecordRS.AirBook.OriginDestinationOption` | array | বুক করা সেগমেন্ট নিশ্চিতকরণ |
| `CreatePassengerNameRecordRS.AirPrice.PriceQuote` | array | সংরক্ষিত price quotes |

> [!WARNING]
> তোমার code `status != "Complete"` হলে Redis token cache invalidate করে, তারপর exception raise করে। এটি Sabre-এর session-linked token সমস্যা handle করে।

---

### ৫.২ PNR Reprice — `POST /v2.4.0/passenger/records?mode=reprice`

**উদ্দেশ্য:** বিদ্যমান PNR-এর price quote মেয়াদ শেষ হলে নতুন করে মূল্য নির্ধারণ করো।

| ফিল্ড | বাধ্যতামূলক | বিবরণ |
|---|---|---|
| `Itinerary.ID` | ✅ হ্যাঁ | বিদ্যমান PNR locator |
| `AirPrice[].PriceRequestInformation.Retain` | ✅ | সর্বদা `true` |
| `PricingQualifiers.PassengerType` | ✅ | Repricing-এর জন্য যাত্রীর ধরন |
| `PricingQualifiers.ValidatingCarrier.Code` | ঐচ্ছিক | Validating carrier জোর করা |
| `EndTransaction.Source.ReceivedFrom` | ✅ | তোমার code `"{pcc} REPRICE"` ব্যবহার করে |

#### Reprice Response — তোমার `_extract_reprice_pricing` থেকে Parsed ফিল্ড

| Extracted ফিল্ড | বিবরণ |
|---|---|
| `total_fare` | মোট |
| `base_fare` | ট্যাক্স ছাড়া মূল ভাড়া |
| `tax_amount` | মোট ট্যাক্স |
| `currency` | মুদ্রার কোড |
| `quote_number` | টিকেটিং-এর জন্য price quote নম্বর |

---

## পর্ব ৬ — মডিউল ৪: টিকেটিং

### ৬.১ টিকেট ইস্যু — `POST /v1.3.0/air/ticket`

**উদ্দেশ্য:** PNR-এ সংরক্ষিত price quote থেকে আসল e-ticket ইস্যু করা।

#### Request ফিল্ড

| ফিল্ড | ধরন | বাধ্যতামূলক | বিবরণ |
|---|---|---|---|
| `AirTicketRQ.POS.Source.PseudoCityCode` | string | ✅ | তোমার PCC |
| `AirTicketRQ.Itinerary.ID` | string | ✅ হ্যাঁ | টিকেট করার PNR locator |
| `AirTicketRQ.Ticketing` | array | ✅ হ্যাঁ | টিকেটিং নির্দেশনা |
| `Ticketing[].@ElementName` | string | ✅ | ফ্লাইট টিকেটের জন্য `"Air"` |
| `Ticketing[].PriceQuoteRef.Record` | integer | ঐচ্ছিক | নির্দিষ্ট price quote নম্বর। বাদ দিলে সব |
| `Ticketing[].FOP_Collection.BasicFOP.Type` | string | ✅ | FOP ধরনের কোড — নিচে দেখো |
| `BasicFOP.CC_Info.PaymentCard.Code` | string | শর্তযুক্ত | কার্ডের ধরন: `"VI"`, `"CA"`, `"AX"` ইত্যাদি |
| `PaymentCard.Number` | string | শর্তযুক্ত | কার্ড নম্বর |
| `PaymentCard.ExpireDate` | string | শর্তযুক্ত | `"MM-YY"` ফরম্যাট |

#### Form of Payment (FOP) কোড

| ধরনের কোড | পেমেন্ট পদ্ধতি |
|---|---|
| `CA` | ক্যাশ |
| `CK` | চেক |
| `VI` | Visa |
| `AX` | American Express |
| `DS` | Discover |
| `DC` | Diners Club |
| `JCB` | JCB |
| `TP` | UATP |
| `MS` | বিবিধ |

#### টিকেটিং Response ফিল্ড

| ফিল্ড | বিবরণ |
|---|---|
| `AirTicketRS.ApplicationResults.status` | `"Complete"` = সফল |
| `AirTicketRS.Summary[].OriginalTicketNumber` | ১৩ সংখ্যার IATA টিকেট নম্বর |

---

## পর্ব ৭ — মডিউল ৫: PNR ম্যানেজমেন্ট

### ৭.১ PNR বিবরণ — `GET /v1/trip/orders/getBooking`

| Query Parameter | বাধ্যতামূলক | বিবরণ |
|---|---|---|
| `locator` | ✅ হ্যাঁ | ৬ অক্ষরের PNR locator |
| `pcc` | ঐচ্ছিক | PNR যে PCC-তে তৈরি হয়েছিল |

| Response ফিল্ড | বিবরণ |
|---|---|
| `getBookingRS.flight` | ফ্লাইট সেগমেন্টের array |
| `getBookingRS.traveler` | যাত্রীর বিস্তারিত array |
| `getBookingRS.ticket` | ইস্যু করা টিকেট array |
| `getBookingRS.priceQuote` | সংরক্ষিত price quotes |
| `getBookingRS.specialService` | SSR/APIS তথ্য |
| `getBookingRS.bookingDetails.confirmationId` | PNR locator |
| `getBookingRS.bookingDetails.status` | PNR status |

---

### ৭.২ ইটিনারেরি বাতিল — `POST /v1/trip/orders/cancelBooking`

| ফিল্ড | বাধ্যতামূলক | বিবরণ |
|---|---|---|
| `locator` | ✅ হ্যাঁ | বাতিল করার PNR locator |
| `cancelAll` | ঐচ্ছিক | `true` = সম্পূর্ণ ইটিনারেরি বাতিল |
| `segmentNumbers` | ঐচ্ছিক | নির্দিষ্ট সেগমেন্ট নম্বর বাতিল (সব নয়) |

---

### ৭.৩ Void টিকেট — `POST /v1/trip/orders/voidFlightTickets`

**উদ্দেশ্য:** ইস্যু করা টিকেট void window-এর মধ্যে (সাধারণত ইস্যুর দিনেই) void করা।

| ফিল্ড | বাধ্যতামূলক | বিবরণ |
|---|---|---|
| `locator` | ✅ হ্যাঁ | PNR locator |
| `ticketNumber` | ✅ হ্যাঁ | void করার ১৩ সংখ্যার টিকেট নম্বরের array |

---

## পর্ব ৮ — মডিউল ৬: সিট ম্যাপ

### ৮.১ সিট ম্যাপ — `POST /v3/offers/seatmap`

**উদ্দেশ্য:** নির্দিষ্ট ফ্লাইটের visual সিট availability দেখায়।

#### Request ফিল্ড

| ফিল্ড | বাধ্যতামূলক | বিবরণ |
|---|---|---|
| `SeatMapRQ.Flight[].origin` | ✅ | প্রস্থান বিমানবন্দর |
| `SeatMapRQ.Flight[].destination` | ✅ | গন্তব্য বিমানবন্দর |
| `SeatMapRQ.Flight[].date` | ✅ | `YYYY-MM-DD` |
| `SeatMapRQ.Flight[].carrier` | ✅ | Marketing এয়ারলাইন কোড |
| `SeatMapRQ.Flight[].flightNumber` | ✅ | ফ্লাইট নম্বর |
| `SeatMapRQ.Flight[].classOfService` | ঐচ্ছিক | Booking class |
| `SeatMapRQ.POS.Source.PseudoCityCode` | ✅ | তোমার PCC |

#### Response ফিল্ড

| ফিল্ড | বিবরণ |
|---|---|
| `SeatMapRS.SeatMap[].Cabin.CabinCode` | কেবিন কোড: `Y`, `C`, `F` |
| `Cabin.Row[].Number` | সারির নম্বর |
| `Row[].Seat[].Number` | আসন নম্বর (যেমন `"14A"`) |
| `Seat[].Occupancy` | `"F"` = খালি, `"C"` = Chargeable (পেইড), `"U"` = অনুপলব্ধ |
| `Seat[].SeatType` | `"W"` = জানালা, `"A"` = করিডোর, `"EXIT"`, `"BLK"` |
| `Seat[].Price.Total` | পেইড আসনের মূল্য |
| `Seat[].Price.Currency` | মুদ্রার কোড |

---

## পর্ব ৯ — মডিউল ৭: ব্যাগেজ Allowance

### ৯.১ ব্যাগেজ — `POST /v4/offers/baggage`

| Response ফিল্ড | বিবরণ |
|---|---|
| `BaggageRS.allowance[].passengerType` | কোন PTC-তে প্রযোজ্য |
| `allowance[].pieces` | অন্তর্ভুক্ত ব্যাগের সংখ্যা |
| `allowance[].weight` | প্রতি ব্যাগের সর্বোচ্চ ওজন |
| `allowance[].weightUnit` | `"KG"` বা `"LB"` |
| `allowance[].segment` | কোন সেগমেন্টে প্রযোজ্য |

---

## পর্ব ১০ — মডিউল ৮: Fare Rules

### ১০.১ Fare Rules — `POST /v1/offers/fareRules`

| Response ফিল্ড | বিবরণ |
|---|---|
| `fareRulesRS.fareRuleInfo[].category` | নিয়মের বিভাগ নম্বর: `16` = জরিমানা, `14` = ভ্রমণ সীমাবদ্ধতা |
| `fareRuleInfo[].rules` | নিয়মের free-text বিষয়বস্তু |
| `structured.changePenalty` | পরিবর্তনের ফি |
| `structured.cancelPenalty` | বাতিলের ফি |
| `structured.minStay` | ন্যূনতম থাকার প্রয়োজন |
| `structured.maxStay` | সর্বোচ্চ থাকা অনুমোদিত |
| `structured.advancePurchase` | যাত্রার কতদিন আগে কিনতে হবে |

---

## পর্ব ১১ — মডিউল ৯: Queue ম্যানেজমেন্ট

### ১১.১ Queue স্থাপন — `POST /v1/trip/orders/queue`

| ফিল্ড | বাধ্যতামূলক | বিবরণ |
|---|---|---|
| `queueRequest.locator` | ✅ হ্যাঁ | স্থাপন করার PNR locator |
| `queueRequest.queueNumber` | ✅ হ্যাঁ | সংখ্যামূলক queue (যেমন `"10"`) |
| `queueRequest.pcc` | ✅ হ্যাঁ | Queue যে PCC-তে আছে |
| `queueRequest.categoryNumber` | ঐচ্ছিক | Queue বিভাগ উপবিভাগ |

---

## পর্ব ১২ — SSR কোড (Sabre)

### হুইলচেয়ার কোড

| কোড | বিবরণ (বাংলা) |
|---|---|
| `WCHR` | হুইলচেয়ার — ramp, বিমানে হাঁটতে পারেন |
| `WCHS` | হুইলচেয়ার — সিঁড়িতে উঠতে পারেন না |
| `WCHC` | হুইলচেয়ার — সম্পূর্ণ স্থির |

### খাবারের কোড

| কোড | খাবারের ধরন |
|---|---|
| `AVML` | এশীয় ভেজিটেরিয়ান |
| `BBML` | শিশু খাবার |
| `BLML` | হালকা খাবার |
| `CHML` | শিশু খাবার |
| `DBML` | ডায়াবেটিক |
| `GFML` | গ্লুটেন-মুক্ত |
| `HNML` | হিন্দু মাংসাশী |
| `KSML` | কোশের |
| `LCML` | কম ক্যালোরি |
| `LFML` | কম চর্বি |
| `LSML` | কম লবণ |
| `MOML` | মুসলিম / হালাল |
| `NLML` | ল্যাকটোজ-মুক্ত |
| `SFML` | সামুদ্রিক খাবার |
| `SPML` | বিশেষ (free text) |
| `VGML` | ভেগান |
| `VLML` | ভেজিটেরিয়ান ল্যাকটো-ওভো |

### অন্যান্য SSR কোড

| কোড | বিবরণ (বাংলা) |
|---|---|
| `DOCS` | পাসপোর্ট/ভ্রমণ নথি প্রেরণ (APIS) |
| `DOCA` | সীমান্ত নিয়ন্ত্রণের জন্য ঠিকানা তথ্য |
| `DOCO` | ভিসা তথ্য |
| `UMNR` | একা ভ্রমণকারী অপ্রাপ্তবয়স্ক |
| `DEAF` | শ্রবণ প্রতিবন্ধী |
| `BLIND` | দৃষ্টি প্রতিবন্ধী |
| `MEDA` | চিকিৎসাজনিত |
| `PETC` | কেবিনে পোষা প্রাণী |
| `AVIH` | cargo-তে পোষা প্রাণী |

---

## পর্ব ১৩ — Error হ্যান্ডলিং

### HTTP Status কোড

| কোড | অর্থ | সাধারণ কারণ | পদক্ষেপ |
|---|---|---|---|
| `200` | সফল | — | Response স্বাভাবিকভাবে প্রক্রিয়া করো |
| `400` | খারাপ Request | ভুল schema, missing ফিল্ড, অবৈধ PTC | error body-র `message` দেখো |
| `401` | অননুমোদিত | মেয়াদোত্তীর্ণ token | তোমার code স্বয়ংক্রিয়ভাবে refresh করে এবং ১ বার retry করে |
| `403` | নিষিদ্ধ | PCC-এর carrier-এর ETA নেই | Sabre-এর সাথে PCC configuration যাচাই করো |
| `404` | পাওয়া যায়নি | PNR নেই, ভুল locator | PNR যাচাই করো |
| `429` | Rate Limited | অনেক বেশি request | তোমার `Retry` strategy এটি cover করে |
| `500` | Server Error | Sabre-এর অভ্যন্তরীণ সমস্যা | তোমার `Retry(status_forcelist=[500...])` দিয়ে auto-retry |

### Retry Strategy (তোমার Implementation)

```python
Retry(
    total=5,              # সর্বোচ্চ ৫ বার retry
    backoff_factor=0.5,   # 0.5s, 1s, 2s, 4s, 8s বিরতি
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["POST", "GET"]
)
```

### Sabre-নির্দিষ্ট Error ফিল্ড

| ফিল্ড | বিবরণ |
|---|---|
| `ApplicationResults.status` | `"Complete"` বা `"Incomplete"` |
| `ApplicationResults.Error` | Error object-এর array |
| `SystemSpecificResults.Message` | Sabre-নির্দিষ্ট error text |

---

## পর্ব ১৪ — সম্পূর্ণ সার্চ Request উদাহরণ

```json
POST https://api.sabre.com/v5/offers/shop
Authorization: Bearer eyJhbGciOiJSUzI1Ni...
Content-Type: application/json
Accept: application/json

{
  "OTA_AirLowFareSearchRQ": {
    "Version": "4.3.0",
    "POS": {
      "Source": [{
        "PseudoCityCode": "BDAC",
        "RequestorID": {
          "Type": "1",
          "ID": "1",
          "CompanyName": { "Code": "TN" }
        }
      }]
    },
    "OriginDestinationInformation": [
      {
        "RPH": "1",
        "DepartureDateTime": "2026-12-15T00:00:00",
        "OriginLocation": { "LocationCode": "DAC" },
        "DestinationLocation": { "LocationCode": "DXB" }
      },
      {
        "RPH": "2",
        "DepartureDateTime": "2026-12-25T00:00:00",
        "OriginLocation": { "LocationCode": "DXB" },
        "DestinationLocation": { "LocationCode": "DAC" }
      }
    ],
    "TravelerInfoSummary": {
      "SeatsRequested": [2],
      "AirTravelerAvail": [{
        "PassengerTypeQuantity": [
          { "Code": "ADT", "Quantity": 1 },
          { "Code": "CNN", "Quantity": 1 }
        ]
      }]
    },
    "TravelPreferences": {
      "MaxStopsQuantity": 1,
      "CabinPref": [{ "Cabin": "Y", "PreferLevel": "Preferred" }]
    },
    "TPA_Extensions": {
      "IntelliSellTransaction": {
        "RequestType": { "Name": "50ITINS" }
      }
    }
  }
}
```

---

## পর্ব ১৫ — Supplier Config (তোমার Codebase)

```json
{
  "name": "Sabre Bangladesh DAC",
  "code": "SABRE-BD-DAC",
  "integration_provider": "sabre",
  "type": "GDS",
  "credentials": {
    "client_id": "<base64 encoded>",
    "client_secret": "<base64 encoded>",
    "auth_secret": "<precomputed Basic auth string>",
    "username": "<Sabre username>",
    "password": "<Sabre password>"
  },
  "endpoints": {
    "base_url": "https://api.sabre.com",
    "pre_prod_base_url": "https://api.test.sabre.com"
  },
  "settings": {
    "pcc": "BDAC",
    "lniata": "<your lniata>",
    "token_expiry_days": 1,
    "default_currency": "BDT",
    "timeout_seconds": 20
  }
}
```

---

## পর্ব ১৬ — Sabre বনাম Travelport তুলনা

| বিষয় | Sabre (বাস্তবায়িত) | Travelport v11 (তৈরি করতে হবে) |
|---|---|---|
| Auth flow | Basic Auth → Bearer (password grant) | Client credentials OAuth2 |
| Token TTL | ~১ ঘণ্টা (3600s) | ২৪ ঘণ্টা (86400s) |
| Token cache | Redis per `supplier_id:pcc` | Redis per supplier |
| সার্চ schema | `OTA_AirLowFareSearchRQ` (OTA wrapper) | `CatalogProductOfferingsQueryRequest` |
| বুকিং মডেল | একক orchestrated call | Workbench session (বহু-ধাপ) |
| PNR commit | `EndTransaction.ReceivedFrom` | `POST .../commit` |
| Retry logic | ৫ বার retry, 0.5s backoff | একই implement করতে হবে |
| ৪০১ হ্যান্ডলিং | Auto-refresh + ১ retry | একই implement করতে হবে |

---

*এই ডকুমেন্ট SkyNovia OTA Engine-এর জন্য Sabre REST API সর্বোচ্চ বিস্তারিত রেফারেন্স হিসেবে প্রস্তুত*
*সরাসরি live codebase থেকে: sabre_service.py, sabre_auth_service.py, sabre_endpoints.py*
*সেপ্টেম্বর ২০২৬*
