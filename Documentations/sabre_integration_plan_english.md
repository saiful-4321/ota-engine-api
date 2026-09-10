# Sabre REST API — Ultra-Comprehensive Reference Guide
### SkyNovia OTA Engine · English Edition

---

## GLOSSARY OF KEY TERMS

| Term | Full Form | Definition |
|---|---|---|
| **BFM** | Bargain Finder Max | Sabre's primary low-fare air search API |
| **PNR** | Passenger Name Record | A booking record in the Sabre GDS containing all travel and passenger data |
| **PCC** | Pseudo City Code | Your agency's unique identifier in Sabre (e.g., `BDAC`) |
| **LNIATA** | Low-level Network Interface and Agency Travel Assignment | A hardware/logical identifier for a Sabre terminal/workstation |
| **PQ** | Price Quote | A stored pricing record within a PNR from which a ticket is issued |
| **APIS** | Advance Passenger Information System | Regulatory requirement to transmit passenger data to airline/government before travel |
| **SSR** | Special Service Request | Coded request to carrier for special service (meals, wheelchair, APIS, etc.) |
| **SecureFlight** | — | TSA (US Transport Security Administration) program requiring DOB and gender for US flights |
| **ETA** | Electronic Ticketing Authority | Permission for an agency (PCC) to issue e-tickets on behalf of a specific carrier |
| **RBD** | Reservation Booking Designator | Single-letter booking class code (Y, K, L, etc.) used to map to a fare |
| **OTA** | Open Travel Alliance | Industry XML standard used in legacy Sabre SOAP/REST schemas (`OTA_AirLowFareSearchRQ`) |
| **EMD** | Electronic Miscellaneous Document | Electronic document for ancillaries (baggage, seat upgrades, etc.) |
| **RPH** | Reference Place Holder | Sequential numeric identifier used in Sabre arrays to reference items |
| **TTY** | Teletype | Sabre's legacy terminal text protocol — some REST APIs mirror TTY command logic |
| **7TAW** | — | Sabre ticketing time-limit code: "ticket in 7 days or auto-cancel" |
| **ADM** | Agency Debit Memo | Financial penalty from airline to agency for incorrect fare or booking |
| `PriceLevel` | — | Sabre concept — indicates quality of cached fare data |
| `IntelliSell` | — | Sabre's merchandising/caching layer that powers BFM results |

---

## PART 1 — AUTHENTICATION

### 1.1 Authentication Architecture Overview

Sabre uses a **two-layer** authentication:
1. **Basic Auth** (Base64-encoded `client_id:client_secret`) to call the Token endpoint
2. **Bearer Token** returned from the Token endpoint, used in all subsequent API calls

Tokens are cached in **Redis** with a supplier-specific cache key.

---

### 1.2 Token Endpoint

**Method:** `POST`
**URL:** `{base_url}/v3/auth/token`
*(Pre-prod: `https://api.test.sabre.com/v3/auth/token`)*
*(Production: `https://api.sabre.com/v3/auth/token`)*

**Purpose:** Exchange Basic credentials for a Bearer access token. Token is cached in Redis per supplier.

#### Request Headers

| Header | Value | Required | Description |
|---|---|---|---|
| `Authorization` | `Basic {base64(client_id:client_secret)}` | ✅ REQUIRED | Base64 encoding of `clientId:clientSecret`. Your code uses `_get_encoded_credentials()` which can accept a precomputed `auth_secret` or compute it live |
| `Content-Type` | `application/x-www-form-urlencoded` | ✅ REQUIRED | Token endpoint requires form-encoded body |
| `Accept` | `application/json` | Recommended | Request JSON response |

#### Request Body (Form Parameters)

| Parameter | Type | Required | Description |
|---|---|---|---|
| `grant_type` | string | ✅ REQUIRED | Must be `"password"` for Sabre (unlike Travelport which uses `client_credentials`) |
| `username` | string | ✅ REQUIRED | Your Sabre agency username (often PCC-based) |
| `password` | string | ✅ REQUIRED | Your Sabre agency password |

> [!IMPORTANT]
> Sabre uses `grant_type=password` — this is different from Travelport's `client_credentials`. Your username + password are sent alongside the Basic Auth header.

#### Response Fields

| Field | Type | Description |
|---|---|---|
| `access_token` | string | ⭐ Bearer token used in all API calls |
| `token_type` | string | Always `"bearer"` |
| `expires_in` | integer | Token lifetime in seconds (typically `3600` = 1 hour) |
| `scope` | string | Granted permission scope |

> [!NOTE]
> Your code adds a **60-second safety buffer** (`expires_in - 60`) before considering a token expired, to prevent race conditions. Redis TTL is set to `token_expiry_days * 24 * 60` minutes.

---

### 1.3 Token Cache Keys (Your Implementation)

```python
# Redis key format per supplier instance
cache_key = f"sabre_access_token:{supplier_id}:{pcc}"
```

On 401 responses, the token is refreshed automatically (double-checked with a threading lock to prevent concurrent refreshes).

---

### 1.4 Standard API Headers

| Header | Value | Required | Description |
|---|---|---|---|
| `Authorization` | `Bearer {access_token}` | ✅ REQUIRED | From the token endpoint response |
| `Content-Type` | `application/json` | ✅ REQUIRED | For POST/PUT requests |
| `Accept` | `application/json` | Recommended | Ensures JSON response |

---

## PART 2 — ALL ENDPOINTS REFERENCE

| Feature | Method | Endpoint | Your Code |
|---|---|---|---|
| Auth Token | POST | `/v3/auth/token` | `SabreEndpoints.REST_AUTH_TOKEN` |
| Flight Search (BFM) | POST | `/v5/offers/shop` | `SabreEndpoints.BARGAIN_FINDER_MAX` |
| Pricing / FlightCheck | POST | `/v1/offers/flightCheck` | `SabreEndpoints.FLIGHT_CHECK` |
| Seat Map | POST | `/v3/offers/seatmap` | `SabreEndpoints.SEAT_MAP` |
| Baggage Allowance | POST | `/v4/offers/baggage` | `SabreEndpoints.BAGGAGE_ALLOWANCE` |
| Fare Rules | POST | `/v1/offers/fareRules` | `SabreEndpoints.STRUCTURE_FARE_RULES` |
| Create PNR | POST | `/v2.4.0/passenger/records?mode=create` | `SabreEndpoints.CREATE_PNR` |
| Reprice PNR | POST | `/v2.4.0/passenger/records?mode=reprice` | `SabreEndpoints.CREATE_PNR` |
| Issue Ticket | POST | `/v1.3.0/air/ticket` | `SabreEndpoints.ISSUE_TICKET` |
| Get PNR Details | GET | `/v1/trip/orders/getBooking` | `SabreEndpoints.GET_PNR_DETAILS` |
| Cancel Itinerary | POST | `/v1/trip/orders/cancelBooking` | `SabreEndpoints.CANCEL_ITINERARY` |
| Void Ticket | POST | `/v1/trip/orders/voidFlightTickets` | `SabreEndpoints.VOID_TICKET` |
| Exchange Ticket | POST | `/v1.3.0/air/ticket` | `SabreEndpoints.EXCHANGE_TICKET` |
| Queue Placement | POST | `/v1/trip/orders/queue` | `SabreEndpoints.QUEUE_PLACE` |

---

## PART 3 — MODULE 1: AIR SEARCH (BFM)

### 3.1 Bargain Finder Max — `POST /v5/offers/shop`

**Purpose:** Primary low-fare flight search. Returns itinerary options combining ATPCO, NDC, and LCC content. Uses Sabre's IntelliSell caching and merchandising engine.

**Schema root:** `OTA_AirLowFareSearchRQ` (OTA standard wrapper)

---

#### Full Request Body Structure

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

#### `POS` — Point of Sale

| Field | Type | Required | Description |
|---|---|---|---|
| `POS.Source` | array | ✅ REQUIRED | Identifies the agency making the request |
| `Source[].PseudoCityCode` | string | ✅ REQUIRED | Your agency's PCC (e.g., `"BDAC"`) — from `self.pcc` in config |
| `Source[].RequestorID.Type` | string | ✅ REQUIRED | Always `"1"` for agency |
| `Source[].RequestorID.ID` | string | ✅ REQUIRED | Always `"1"` |
| `Source[].RequestorID.CompanyName.Code` | string | ✅ REQUIRED | Always `"TN"` (Travel Network) |

---

#### `OriginDestinationInformation` — Journey Legs

One array element per O&D leg. Round-trip = 2 elements. Multi-city = N elements.

| Field | Type | Required | Description |
|---|---|---|---|
| `RPH` | string | ✅ REQUIRED | **Reference Place Holder** — sequential number as string: `"1"`, `"2"`, etc. Used to cross-reference results |
| `DepartureDateTime` | string | ✅ REQUIRED | ISO 8601 datetime: `"YYYY-MM-DDT00:00:00"`. Time portion can be `T00:00:00` if no time preference |
| `OriginLocation.LocationCode` | string | ✅ REQUIRED | IATA 3-letter departure airport code (e.g., `"DAC"`) |
| `DestinationLocation.LocationCode` | string | ✅ REQUIRED | IATA 3-letter arrival airport code (e.g., `"DXB"`) |

---

#### `TravelerInfoSummary` — Passengers

| Field | Type | Required | Description |
|---|---|---|---|
| `SeatsRequested` | array[integer] | ✅ REQUIRED | Total seats needed. Single-element array: `[adults + children + infants]` |
| `AirTravelerAvail` | array | ✅ REQUIRED | Passenger type breakdown |
| `AirTravelerAvail[].PassengerTypeQuantity` | array | ✅ REQUIRED | Each element = one passenger type + count |
| `PassengerTypeQuantity[].Code` | string | ✅ REQUIRED | PTC code — see full list below |
| `PassengerTypeQuantity[].Quantity` | integer | ✅ REQUIRED | Number of this passenger type |

**Example:**
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

#### Passenger Type Codes (PTC) — Sabre Reference

| Code | Meaning | Age Range | Notes |
|---|---|---|---|
| `ADT` | Adult | 12+ | Default. Used in your code as primary passenger |
| `CNN` | Child | 2–11 | Used in your code for children |
| `INF` | Infant (no seat) | Under 2 | Lap infant. Used in your code |
| `INS` | Infant (with seat) | Under 2 | Seat-occupying infant |
| `UMNR` | Unaccompanied Minor | 5–17 | Requires SSR UMNR at booking |
| `STU` | Student | Varies | Student discount fare |
| `GVT` | Government | — | Government rate |
| `MIL` | Military | — | Armed forces discount |
| `SRC` | Senior | 65+ | Senior discount |

---

#### `TravelPreferences` — Modifiers

| Field | Type | Required | When to Use | Description |
|---|---|---|---|---|
| `MaxStopsQuantity` | integer | Optional | Direct flight filter | `0` = nonstop only. Set when `direct_flights_only=true` or `max_stops` is specified |
| `CabinPref` | array | Optional | Cabin class filter | Preferred cabin list |
| `CabinPref[].Cabin` | string | Optional | — | **Single-letter cabin code** — see table below |
| `CabinPref[].PreferLevel` | string | Optional | — | `"Only"` (strict — return only this cabin), `"Preferred"` (soft preference with fallback) |
| `VendorPref` | array | Optional | Airline filtering | Airline include/exclude list |
| `VendorPref[].Code` | string | Optional | — | IATA 2-letter airline code |
| `VendorPref[].Type` | string | Optional | — | `"Marketing"` (marketing carrier) |
| `VendorPref[].Exclude` | boolean | Optional | — | `true` = exclude this airline |

---

#### Cabin Class Codes — Sabre BFM

| Sabre Code | Cabin Name | Notes |
|---|---|---|
| `Y` | Economy | Standard economy class |
| `S` | Premium Economy | Some carriers — used for W-class equivalent |
| `C` | Business | Standard business class |
| `J` | Premium Business | Upper business / higher J class |
| `F` | First | Standard first class |
| `P` | Premium First | Top-tier first class (e.g., Emirates First) |

> [!NOTE]
> When `cabin_class = "ALL"` in your request, your code sends ALL 6 cabin codes with `"Preferred"` preference level so BFM returns the cheapest regardless of cabin.

---

#### `PriceRequestInformation` — Corporate & Currency (Under `TravelerInfoSummary`)

| Field | Type | Required | Description |
|---|---|---|---|
| `CurrencyCode` | string | Optional | Force pricing in a specific currency (e.g., `"USD"`, `"BDT"`) |
| `NegotiatedFareCode` | array | Optional | Corporate/private negotiated fare codes. **Must match pattern `[A-Za-z]{3}[0-9]{2}`** (e.g., `"ABC12"`) — your code validates this with a regex and skips if invalid |
| `NegotiatedFareCode[].Code` | string | Optional | The actual corporate code |
| `AccountCode` | array | Optional | Agency/corporate account code for private fares |
| `AccountCode[].Code` | string | Optional | The account code string |

---

#### `TPA_Extensions` — IntelliSell & Advanced Options

| Field | Type | Required | Description |
|---|---|---|---|
| `IntelliSellTransaction.RequestType.Name` | string | ✅ REQUIRED | Caching/result type: `"50ITINS"` (standard 50 results), `"ADRC"` (Alternate Date Request for flexible dates) |

> [!NOTE]
> `"ADRC"` mode is set automatically when `flexible_dates=true` in your request. It returns cheapest fares across a ±3 day window.

---

#### BFM Response — Key Fields

| Response Field | Type | Description |
|---|---|---|
| `OTA_AirLowFareSearchRS` | object | Root response object |
| `OTA_AirLowFareSearchRS.PricedItineraries` | object | Container for all priced itinerary results |
| `PricedItineraries.PricedItinerary` | array | List of flight options sorted by price |
| `PricedItinerary[].SequenceNumber` | integer | Result position/rank |
| `PricedItinerary[].AirItinerary` | object | The flight itinerary |
| `AirItinerary.OriginDestinationOptions` | object | O&D combinations |
| `OriginDestinationOptions.OriginDestinationOption` | array | One element per O&D pair |
| `OriginDestinationOption[].FlightSegment` | array | Flight segments in this O&D |
| `FlightSegment[].DepartureAirport.LocationCode` | string | Departure airport IATA code |
| `FlightSegment[].ArrivalAirport.LocationCode` | string | Arrival airport IATA code |
| `FlightSegment[].DepartureDateTime` | string | Departure datetime ISO 8601 |
| `FlightSegment[].ArrivalDateTime` | string | Arrival datetime ISO 8601 |
| `FlightSegment[].MarketingAirline.Code` | string | Marketing airline IATA code |
| `FlightSegment[].OperatingAirline.Code` | string | Operating airline IATA code |
| `FlightSegment[].FlightNumber` | string | Flight number |
| `FlightSegment[].ResBookDesigCode` | string | Booking class (RBD). E.g., `"Y"`, `"K"` |
| `FlightSegment[].CabinClassCode` | string | Cabin code from response |
| `FlightSegment[].ElapsedTime` | integer | Flight duration in minutes |
| `FlightSegment[].StopQuantity` | integer | Stops within this segment |
| `FlightSegment[].Equipment.AirEquipType` | string | Aircraft type code (e.g., `"77W"` = Boeing 777-300ER) |
| `PricedItinerary[].AirItineraryPricingInfo` | object | Pricing information |
| `AirItineraryPricingInfo.ItinTotalFare` | object | Total price block |
| `ItinTotalFare.TotalFare.Amount` | number | Grand total in currency |
| `ItinTotalFare.TotalFare.CurrencyCode` | string | Currency code |
| `ItinTotalFare.BaseFare.Amount` | number | Base fare before taxes |
| `ItinTotalFare.Taxes.Tax` | array | Individual tax items |
| `Tax[].TaxCode` | string | Tax code (e.g., `"YQ"`, `"YR"`, `"BD"`) |
| `Tax[].Amount` | number | Tax amount |
| `AirItineraryPricingInfo.FareInfos.FareInfo` | array | Fare basis codes per segment |
| `FareInfo[].FareBasisCode` | string | Fare basis code |
| `FareInfo[].FilingAirline.Code` | string | Airline that filed this fare |
| `FareInfo[].MarketingAirline.Code` | string | Marketing carrier for this fare |
| `PricedItinerary[].TPA_Extensions` | object | Extended data: bag allowance, brand info |

---

### 3.2 Booking Class (RBD) Common Codes

| Class | Cabin | Typical Fare Type |
|---|---|---|
| `F`, `A` | First | First class fares |
| `P` | Premium First | Premium first |
| `J`, `C`, `D`, `I` | Business | Business class fares |
| `W`, `S` | Premium Economy | Premium economy |
| `Y`, `B` | Economy | Full-fare economy |
| `K`, `M`, `L`, `V` | Economy | Mid-range economy |
| `Q`, `T`, `E`, `N`, `X` | Economy | Discounted economy |
| `G`, `O`, `U` | Economy | Heavily restricted discount fares |

---

## PART 4 — MODULE 2: FLIGHT PRICING (FLIGHT CHECK)

### 4.1 FlightCheck — `POST /v1/offers/flightCheck`

**Purpose:** Revalidates price and availability for a specific selected itinerary before creating a PNR. Confirms the fare is still bookable. Always call this between search and booking.

#### Request Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `journeys` | array | ✅ REQUIRED | List of journey objects (one per O&D) |
| `journeys[].flights` | array | ✅ REQUIRED | Individual flight segments for this journey |
| `flights[].departureDate` | string | ✅ REQUIRED | `YYYY-MM-DD` departure date |
| `flights[].departureTime` | string | ✅ REQUIRED | `HH:MM` departure time |
| `flights[].departureAirportCode` | string | ✅ REQUIRED | IATA departure airport code |
| `flights[].arrivalDate` | string | ✅ REQUIRED | `YYYY-MM-DD` arrival date |
| `flights[].arrivalTime` | string | ✅ REQUIRED | `HH:MM` arrival time |
| `flights[].arrivalAirportCode` | string | ✅ REQUIRED | IATA arrival airport code |
| `flights[].marketingAirlineCode` | string | ✅ REQUIRED | IATA 2-letter marketing airline code |
| `flights[].marketingFlightNumber` | integer | ✅ REQUIRED | **Integer** flight number (not string) — e.g., `147` not `"147"` |
| `flights[].bookingClass` | string | ✅ REQUIRED | Single-letter RBD booking class |
| `flights[].operatingAirlineCode` | string | Optional | Operating carrier code (for codeshare flights) |
| `travelers` | array | ✅ REQUIRED | List of traveler records (one per passenger, not per type) |
| `travelers[].passengerTypeCode` | string | ✅ REQUIRED | PTC for this traveler: `"ADT"`, `"CNN"`, `"INF"` |

> [!IMPORTANT]
> `marketingFlightNumber` must be an **integer**, not a string. Your `_parse_sabre_segment()` helper handles this conversion via `flight_number_int`.

**Example Request:**
```json
{
  "journeys": [
    {
      "flights": [
        {
          "departureDate": "2026-12-15",
          "departureTime": "06:00",
          "departureAirportCode": "DAC",
          "arrivalDate": "2026-12-15",
          "arrivalTime": "09:20",
          "arrivalAirportCode": "DXB",
          "marketingAirlineCode": "BG",
          "marketingFlightNumber": 147,
          "bookingClass": "Y"
        }
      ]
    }
  ],
  "travelers": [
    { "passengerTypeCode": "ADT" },
    { "passengerTypeCode": "CNN" }
  ]
}
```

---

## PART 5 — MODULE 3: CREATE PNR (BOOKING)

### 5.1 Create PNR — `POST /v2.4.0/passenger/records?mode=create`

**Purpose:** Creates a live booking in the Sabre GDS. This is an orchestrated API that combines: Add Passenger, Add Segment, Price Itinerary, and End Transaction in a single call.

---

#### `TravelItineraryAddInfo` — Agency & Passenger Info

##### Agency Info

| Field | Type | Required | Description |
|---|---|---|---|
| `AgencyInfo.Ticketing.TicketType` | string | ✅ REQUIRED | `"7TAW"` = standard auto-ticket time limit (7 days). Always use this |

##### CustomerInfo — Passenger Names

| Field | Type | Required | Description |
|---|---|---|---|
| `CustomerInfo.PersonName` | array | ✅ REQUIRED | One element per passenger |
| `PersonName[].NameNumber` | string | ✅ REQUIRED | Sequential reference: `"1.1"`, `"2.1"`, `"3.1"` — format: `"{n}.1"` |
| `PersonName[].GivenName` | string | ✅ REQUIRED | First/given name in UPPERCASE |
| `PersonName[].Surname` | string | ✅ REQUIRED | Last/family name in UPPERCASE |

##### ContactNumbers

| Field | Type | Required | Description |
|---|---|---|---|
| `ContactNumbers.ContactNumber` | array | Recommended | Phone numbers |
| `ContactNumber[].Phone` | string | Required | Phone number (any format) |
| `ContactNumber[].PhoneUseType` | string | Required | `"A"` = Agency, `"H"` = Home, `"B"` = Business, `"M"` = Mobile |

---

#### `AirBook` — Segment Booking

| Field | Type | Required | Description |
|---|---|---|---|
| `AirBook.OriginDestinationInformation.FlightSegment` | array | ✅ REQUIRED | One element per flight segment to book |
| `FlightSegment[].DepartureDateTime` | string | ✅ REQUIRED | ISO 8601 datetime: `"YYYY-MM-DDTHH:MM:SS"` |
| `FlightSegment[].FlightNumber` | string | ✅ REQUIRED | Flight number as **string** |
| `FlightSegment[].NumberInParty` | string | ✅ REQUIRED | Total passengers as **string** (e.g., `"2"`) |
| `FlightSegment[].ResBookDesigCode` | string | ✅ REQUIRED | Booking class (RBD). E.g., `"Y"` |
| `FlightSegment[].Status` | string | ✅ REQUIRED | Booking status code: `"NN"` (Need — request to book). Most common for new bookings |
| `FlightSegment[].DestinationLocation.LocationCode` | string | ✅ REQUIRED | Arrival airport IATA code |
| `FlightSegment[].OriginLocation.LocationCode` | string | ✅ REQUIRED | Departure airport IATA code |
| `FlightSegment[].MarketingAirline.Code` | string | ✅ REQUIRED | Marketing airline IATA code |
| `FlightSegment[].MarketingAirline.FlightNumber` | string | ✅ REQUIRED | Flight number (string) — duplicated under MarketingAirline |

#### Segment Status Codes

| Code | Meaning |
|---|---|
| `NN` | Need — standard request to book |
| `SS` | Sold — confirms booking |
| `HK` | Holds Confirmed |
| `GK` | GDS Confirmed |
| `TK` | Ticketed |
| `UN` | Unable to confirm |

---

#### `AirPrice` — Fare Storage

| Field | Type | Required | Description |
|---|---|---|---|
| `AirPrice[].PriceRequestInformation.Retain` | boolean | ✅ REQUIRED | Always `true` — stores the price quote in the PNR for later ticketing |
| `OptionalQualifiers.PricingQualifiers.PassengerType` | array | ✅ REQUIRED | Passenger type + quantity for pricing |
| `PassengerType[].Code` | string | ✅ REQUIRED | PTC code |
| `PassengerType[].Quantity` | string | ✅ REQUIRED | Count as **string** |
| `OptionalQualifiers.FlightQualifiers.ValidatingCarrier.Code` | string | Optional | Forces a specific validating carrier. Required when your PCC has Electronic Ticketing Authority (ETA) for specific carriers only |

---

#### `SpecialReqDetails` — APIS / SecureFlight

These are required for international routes to transmit passenger data to airlines.

| Field | Type | Required | Description |
|---|---|---|---|
| `SpecialService.SpecialServiceInfo.AdvancePassenger` | array | For international | APIS — Advance Passenger Information |
| `AdvancePassenger[].PersonName.NameNumber` | string | ✅ | Matches the `PersonName[].NameNumber` above |
| `AdvancePassenger[].PersonName.GivenName` | string | ✅ | First name as on passport |
| `AdvancePassenger[].PersonName.Surname` | string | ✅ | Last name as on passport |
| `AdvancePassenger[].PersonName.DateOfBirth` | string | ✅ | `YYYY-MM-DD` |
| `AdvancePassenger[].PersonName.Gender` | string | ✅ | `"M"` or `"F"` |
| `AdvancePassenger[].Document.Number` | string | ✅ | Passport number |
| `AdvancePassenger[].Document.IssueCountry` | string | ✅ | 2-letter ISO country code of issue (e.g., `"BD"`) |
| `AdvancePassenger[].Document.NationalityCountry` | string | ✅ | 2-letter nationality code |
| `AdvancePassenger[].Document.ExpirationDate` | string | ✅ | `YYYY-MM-DD` — must be valid at travel time |
| `AdvancePassenger[].Document.Type` | string | ✅ | `"P"` = Passport (always use this) |
| `SecureFlight[].PersonName.NameNumber` | string | TSA/US flights | TSA requirement for US-bound flights. DOB + Gender only |

---

#### `PostProcessing` — End Transaction

| Field | Type | Required | Description |
|---|---|---|---|
| `EndTransaction.Source.ReceivedFrom` | string | ✅ REQUIRED | Who submitted this PNR. Recorded in Sabre history. Use `"API"` or your system name. **Required by Sabre** — PNR won't save without it |

---

#### PNR Creation Response Fields

| Field | Type | Description |
|---|---|---|
| `CreatePassengerNameRecordRS.ApplicationResults.status` | string | `"Complete"` = success. Any other value = failure |
| `CreatePassengerNameRecordRS.ItineraryRef.ID` | string | ⭐ **The PNR Locator** — 6-character Sabre record locator (e.g., `"ABCDEF"`) |
| `CreatePassengerNameRecordRS.AirBook.OriginDestinationOption` | array | Booked segment confirmation |
| `CreatePassengerNameRecordRS.AirPrice.PriceQuote` | array | Stored price quotes |
| `PriceQuote[].PricedItinerary.AirItineraryPricingInfo.ItinTotalFare` | object | Stored fare amount |

> [!WARNING]
> Your code invalidates the Redis token cache if `status != "Complete"`, then raises an exception. This handles the Sabre session-linked token issue where a failed PNR can corrupt the session.

---

### 5.2 Reprice PNR — `POST /v2.4.0/passenger/records?mode=reprice`

**Purpose:** Re-generates the price quote on an existing PNR when the original quote has expired. Returns new total with current pricing.

| Field | Type | Required | Description |
|---|---|---|---|
| `Itinerary.ID` | string | ✅ REQUIRED | The existing PNR locator |
| `AirPrice[].PriceRequestInformation.Retain` | boolean | ✅ | Always `true` |
| `PricingQualifiers.PassengerType` | array | ✅ | Passenger types for repricing |
| `PricingQualifiers.ValidatingCarrier.Code` | string | Optional | Force validating carrier |
| `EndTransaction.Source.ReceivedFrom` | string | ✅ | Must include PNR identifier: your code uses `"{pcc} REPRICE"` |

#### Reprice Response — Parsed Fields (Your `_extract_reprice_pricing`)

| Extracted Field | Description |
|---|---|
| `total_fare` | Grand total |
| `base_fare` | Base fare before taxes |
| `tax_amount` | Total taxes |
| `currency` | Currency code |
| `quote_number` | Price quote number for ticketing |

---

## PART 6 — MODULE 4: TICKETING

### 6.1 Issue Ticket — `POST /v1.3.0/air/ticket`

**Purpose:** Issues the actual e-ticket from a stored price quote in the PNR.

#### Request Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `AirTicketRQ.POS.Source.PseudoCityCode` | string | ✅ | Your PCC |
| `AirTicketRQ.DesignatePrinter.TicketingPrinterDesignator` | object | Optional | Printer designation for EMD/ticket output |
| `AirTicketRQ.Itinerary.ID` | string | ✅ REQUIRED | The PNR locator to ticket |
| `AirTicketRQ.Ticketing` | array | ✅ REQUIRED | Ticketing instructions |
| `Ticketing[].@ElementName` | string | ✅ | `"Air"` for flight tickets |
| `Ticketing[].PriceQuoteRef.Record` | integer | Optional | Specific price quote number to issue. Omit to issue all |
| `Ticketing[].FOP_Collection.BasicFOP` | object | ✅ | Form of Payment |
| `BasicFOP.Type` | string | ✅ | FOP type code — see table below |
| `BasicFOP.CC_Info.PaymentCard` | object | Conditional | Credit card details |
| `PaymentCard.Code` | string | Conditional | Card type: `"VI"`, `"CA"`, `"AX"`, etc. |
| `PaymentCard.Number` | string | Conditional | Card number |
| `PaymentCard.ExpireDate` | string | Conditional | `"MM-YY"` format |
| `PaymentCard.ExtendedPayment` | string | Optional | Installment months if applicable |

#### Form of Payment (FOP) Type Codes

| Type Code | Payment Method |
|---|---|
| `CA` | Cash |
| `CK` | Check |
| `VI` | Visa credit card |
| `CA` (card context) | Mastercard |
| `AX` | American Express |
| `DS` | Discover |
| `DC` | Diners Club |
| `JCB` | JCB |
| `TP` | UATP |
| `MS` | Miscellaneous |

#### Ticketing Response Fields

| Field | Type | Description |
|---|---|---|
| `AirTicketRS.ApplicationResults.status` | string | `"Complete"` = success |
| `AirTicketRS.Summary` | array | Summary of issued documents |
| `Summary[].OriginalTicketNumber` | string | 13-digit IATA ticket number |
| `Summary[].DocumentNumber` | string | Document number |

---

## PART 7 — MODULE 5: PNR MANAGEMENT

### 7.1 Get PNR Details — `GET /v1/trip/orders/getBooking`

**Purpose:** Retrieves complete details of an existing PNR.

#### Query Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `locator` | string | ✅ REQUIRED | The 6-character PNR locator |
| `pcc` | string | Optional | PCC where the PNR was created |

#### Response Key Fields

| Field | Description |
|---|---|
| `getBookingRS.flight` | Array of flight segments |
| `getBookingRS.traveler` | Array of passenger details |
| `getBookingRS.ticket` | Array of issued tickets |
| `getBookingRS.priceQuote` | Stored price quotes |
| `getBookingRS.specialService` | SSR/APIS data |
| `getBookingRS.remark` | PNR remarks |
| `getBookingRS.bookingDetails.confirmationId` | The PNR locator |
| `getBookingRS.bookingDetails.status` | PNR status |

---

### 7.2 Cancel Itinerary — `POST /v1/trip/orders/cancelBooking`

**Purpose:** Cancels all or specific segments in a booking.

| Field | Type | Required | Description |
|---|---|---|---|
| `locator` | string | ✅ REQUIRED | PNR locator to cancel |
| `cancelAll` | boolean | Optional | `true` = cancel entire itinerary |
| `segmentNumbers` | array[integer] | Optional | Specific segment numbers to cancel (if not cancelling all) |

---

### 7.3 Void Ticket — `POST /v1/trip/orders/voidFlightTickets`

**Purpose:** Voids an issued ticket within the void window (same day of issue for most carriers).

| Field | Type | Required | Description |
|---|---|---|---|
| `locator` | string | ✅ REQUIRED | PNR locator |
| `ticketNumber` | array[string] | ✅ REQUIRED | 13-digit ticket numbers to void |

---

### 7.4 Exchange Ticket — `POST /v1.3.0/air/ticket`

**Purpose:** Processes a ticket exchange (change of itinerary for an already-ticketed booking).

The exchange flow uses `ExchangeBookingRQ` or the same `AirTicketRQ` with an exchange-specific price quote (PQR).

---

## PART 8 — MODULE 6: SEAT MAP

### 8.1 Seat Map — `POST /v3/offers/seatmap`

**Purpose:** Returns visual seat availability for a specific flight.

#### Request Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `SeatMapRQ.RequestType` | string | ✅ | `"Payload"` |
| `SeatMapRQ.Flight` | array | ✅ | Flight(s) to get seat maps for |
| `Flight[].origin` | string | ✅ | Departure airport IATA |
| `Flight[].destination` | string | ✅ | Arrival airport IATA |
| `Flight[].date` | string | ✅ | `YYYY-MM-DD` |
| `Flight[].carrier` | string | ✅ | Marketing airline code |
| `Flight[].flightNumber` | string | ✅ | Flight number |
| `Flight[].classOfService` | string | Optional | Booking class |
| `SeatMapRQ.POS.Source.PseudoCityCode` | string | ✅ | Your PCC |

#### Response Fields

| Field | Description |
|---|---|
| `SeatMapRS.SeatMap` | Array of seat map objects |
| `SeatMap[].Cabin` | Cabin details |
| `Cabin.CabinCode` | Cabin code: `Y`, `C`, `F` |
| `Cabin.Column` | Column definitions (A-K) |
| `Cabin.Row` | Array of rows |
| `Row[].Number` | Row number |
| `Row[].Seat` | Array of seats in row |
| `Seat[].Number` | Seat number (e.g., `"14A"`) |
| `Seat[].Occupancy` | `"F"` = Free, `"C"` = Chargeable, `"U"` = Unavailable |
| `Seat[].SeatType` | Type flags: `"W"` = Window, `"A"` = Aisle, `"EXIT"`, `"BLK"` |
| `Seat[].Price.Total` | Price for paid seat |
| `Seat[].Price.Currency` | Currency code |

---

## PART 9 — MODULE 7: BAGGAGE ALLOWANCE

### 9.1 Baggage Allowance — `POST /v4/offers/baggage`

**Purpose:** Returns checked and carry-on baggage allowance details for a specific itinerary.

#### Request Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `BaggageRQ.itinerary` | array | ✅ | Flight segments |
| `itinerary[].origin` | string | ✅ | Origin airport |
| `itinerary[].destination` | string | ✅ | Destination airport |
| `itinerary[].carrier` | string | ✅ | Marketing airline |
| `itinerary[].flightNumber` | string | ✅ | Flight number |
| `itinerary[].date` | string | ✅ | Departure date `YYYY-MM-DD` |
| `itinerary[].classOfService` | string | ✅ | Booking class |
| `BaggageRQ.passengerTypes` | array | ✅ | Passenger types |

#### Response Fields

| Field | Description |
|---|---|
| `BaggageRS.allowance` | List of baggage rules |
| `allowance[].passengerType` | PTC this applies to |
| `allowance[].pieces` | Number of included bags (piece concept) |
| `allowance[].weight` | Max weight per bag |
| `allowance[].weightUnit` | `"KG"` or `"LB"` |
| `allowance[].segment` | Which segment(s) this applies to |

---

## PART 10 — MODULE 8: FARE RULES

### 10.1 Fare Rules — `POST /v1/offers/fareRules`

**Purpose:** Returns structured fare conditions for a selected itinerary.

#### Request Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `fareRulesRQ.pricingRecord` | object | ✅ | Pricing record reference from BFM |
| `fareRulesRQ.fareComponents` | array | ✅ | Fare components to get rules for |

#### Response Fields

| Field | Description |
|---|---|
| `fareRulesRS.fareRuleInfo` | Array of rule categories |
| `fareRuleInfo[].category` | Category number: `16` = Penalties, `14` = Travel restrictions |
| `fareRuleInfo[].rules` | Free-text rule content |
| `fareRuleInfo[].structured` | Structured rule data when available |
| `structured.changePenalty` | Change fee amount |
| `structured.cancelPenalty` | Cancellation fee amount |
| `structured.minStay` | Minimum stay requirement |
| `structured.maxStay` | Maximum stay allowed |
| `structured.advancePurchase` | Days before departure to book |

---

## PART 11 — MODULE 9: QUEUE MANAGEMENT

### 11.1 Queue Placement — `POST /v1/trip/orders/queue`

**Purpose:** Places a PNR into a specified GDS queue for agent review.

| Field | Type | Required | Description |
|---|---|---|---|
| `queueRequest.locator` | string | ✅ REQUIRED | PNR locator to place |
| `queueRequest.queueNumber` | string | ✅ REQUIRED | Numeric queue (e.g., `"10"`) |
| `queueRequest.pcc` | string | ✅ REQUIRED | PCC where the queue lives |
| `queueRequest.categoryNumber` | string | Optional | Queue category subdivision |

---

## PART 12 — SSR CODES (Sabre)

### Wheelchair Codes

| Code | Description |
|---|---|
| `WCHR` | Wheelchair — ramp, can walk on plane |
| `WCHS` | Wheelchair — stairs, cannot climb steps |
| `WCHC` | Wheelchair — completely immobile |

### Meal Codes

| Code | Meal Type |
|---|---|
| `AVML` | Asian Vegetarian |
| `BBML` | Baby Meal |
| `BLML` | Bland Meal |
| `CHML` | Child Meal |
| `DBML` | Diabetic |
| `GFML` | Gluten-Free |
| `HNML` | Hindu Non-Veg |
| `KSML` | Kosher |
| `LCML` | Low Calorie |
| `LFML` | Low Fat |
| `LSML` | Low Salt |
| `MOML` | Muslim / Halal |
| `NLML` | Non-Lactose |
| `SFML` | Seafood |
| `SPML` | Special (free text) |
| `VGML` | Vegan |
| `VLML` | Vegetarian Lacto-Ovo |

### Other SSR Codes

| Code | Description |
|---|---|
| `DOCS` | Passport/travel document transmission (APIS) |
| `DOCA` | Address information for border control |
| `DOCO` | Visa information |
| `UMNR` | Unaccompanied Minor |
| `DEAF` | Hearing-impaired |
| `BLIND` | Visually-impaired |
| `MEDA` | Medical case |
| `PETC` | Carry-on pet |
| `AVIH` | Pet in cargo hold |

---

## PART 13 — ERROR HANDLING

### HTTP Status Codes

| Code | Meaning | Common Causes | Action |
|---|---|---|---|
| `200` | Success | — | Process response |
| `400` | Bad Request | Wrong schema, missing required field, invalid PTC | Check error body for `message` |
| `401` | Unauthorized | Expired token | Your code auto-refreshes and retries once |
| `403` | Forbidden | PCC doesn't have ETA for carrier, permission issue | Check PCC configuration with Sabre |
| `404` | Not Found | PNR doesn't exist, wrong locator | Verify PNR |
| `429` | Rate Limited | Too many requests | Exponential backoff — your `Retry` strategy covers this |
| `500` | Server Error | Sabre internal issue | Auto-retried per your `Retry(status_forcelist=[500, 502, 503, 504])` |

### Retry Strategy (Your Implementation)

```python
Retry(
    total=5,              # Max 5 total retries
    backoff_factor=0.5,   # Wait 0.5s, 1s, 2s, 4s, 8s between retries
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["POST", "GET"]
)
```

### Sabre-Specific Error Fields

| Field | Description |
|---|---|
| `ApplicationResults.status` | `"Complete"` or `"Incomplete"` |
| `ApplicationResults.Error` | Array of error objects |
| `Error[].type` | Error category |
| `Error[].timeStamp` | When error occurred |
| `SystemSpecificResults.Message` | Sabre-specific error text |

---

## PART 14 — REAL FULL EXAMPLE: SEARCH REQUEST

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

## PART 15 — SUPPLIER CONFIG (YOUR CODEBASE)

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

## PART 16 — KEY DIFFERENCES: YOUR SABRE vs TRAVELPORT IMPLEMENTATION

| Aspect | Sabre (Implemented) | Travelport v11 (To Build) |
|---|---|---|
| Auth flow | Basic Auth → Bearer token (password grant) | Client credentials OAuth2 |
| Token TTL | ~1 hour (3600s) | 24 hours (86400s) |
| Token cached | Redis per `supplier_id:pcc` | Redis per supplier |
| Search schema | `OTA_AirLowFareSearchRQ` (OTA wrapper) | `CatalogProductOfferingsQueryRequest` |
| Booking model | Single orchestrated call (Create PNR) | Workbench session pattern (multi-step) |
| PNR commit | `EndTransaction.ReceivedFrom` | `POST .../commit` |
| Retry logic | 5 retries, backoff 0.5s | Must implement same |
| 401 handling | Auto-refresh + 1 retry | Must implement same |

---

*Document prepared for SkyNovia OTA Engine — Sabre REST API Maximum Detail Reference*
*Derived directly from live codebase: sabre_service.py, sabre_auth_service.py, sabre_endpoints.py*
*September 2026*
