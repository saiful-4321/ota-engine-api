# Travelport JSON API v11 — Ultra-Comprehensive Reference Guide
### SkyNovia OTA Engine · English Edition (Maximum Detail)

---

## GLOSSARY OF KEY TERMS

| Term | Full Form | Definition |
|---|---|---|
| **GDS** | Global Distribution System | A central reservation system used by travel agencies to access airline, hotel, and car inventory (e.g., Galileo, Apollo, Worldspan) |
| **NDC** | New Distribution Capability | IATA standard for direct airline-to-agency distribution, bypassing traditional GDS fare filing |
| **PCC** | Pseudo City Code | A unique alphanumeric identifier assigned by Travelport to an agency/office. Used to authenticate and route requests |
| **PTC** | Passenger Type Code | 3-character IATA code identifying the type of traveler (ADT, CNN, INF, etc.) |
| **PNR** | Passenger Name Record | A booking record in the GDS that holds all travel and passenger data |
| **EMD** | Electronic Miscellaneous Document | Electronic equivalent of a paper document for ancillaries (seats, baggage, etc.) |
| **SSR** | Special Service Request | A coded request sent to an airline for a specific service (meals, wheelchairs, etc.) |
| **OSI** | Other Service Information | Informational remarks sent to the airline that require no action |
| **FOP** | Form of Payment | The payment method used to purchase a ticket (credit card, cash, etc.) |
| **O&D** | Origin and Destination | A single city pair in an itinerary |
| **Workbench** | Reservation Workbench | A Travelport v11 concept — a temporary session container where all booking steps happen before a PNR is committed |
| **Offer** | CatalogProductOffering | A flight product returned by the search API — includes itinerary + fare + ancillary details |
| **FBC** | Fare Basis Code | An alphanumeric code that defines a specific fare's rules, restrictions, and class |
| **Branded Fare** | — | An airline-defined fare bundle with a name/brand (e.g., "Flex", "Basic", "Business Plus") |
| **IATA** | International Air Transport Association | Global aviation authority that defines industry codes and standards |
| **BSP** | Billing and Settlement Plan | IATA's financial settlement system between airlines and agents (most countries) |
| **ARC** | Airlines Reporting Corporation | US-based ticket settlement system (alternative to BSP in USA) |
| **OAuth 2.0** | Open Authorization 2.0 | Industry-standard protocol for API authentication via access tokens |
| **TTL** | Time to Live | Duration for which a cached value (e.g., access token) remains valid |

---

## PART 1 — AUTHENTICATION

### 1.1 OAuth 2.0 Token Endpoint

**Method:** `POST`
**URL:** `https://auth.travelport.net/oauth/token`
*(Pre-prod: `https://auth.pp.travelport.net/oauth/token`)*

**Purpose:** Obtain a Bearer access token to authorize all subsequent API calls. This must be called first. The token is valid for **24 hours** and should be cached (Redis recommended) for reuse — **do not request a new token on every API call.**

---

#### Request: Form Parameters (`application/x-www-form-urlencoded`)

| Parameter | Type | Required | Description |
|---|---|---|---|
| `grant_type` | string | ✅ REQUIRED | Must always be `client_credentials`. This tells the server you are using the machine-to-machine flow (no user login required) |
| `client_id` | string | ✅ REQUIRED | Your Travelport-issued API client identifier. Obtained from the Travelport Developer Portal after registration |
| `client_secret` | string | ✅ REQUIRED | Your Travelport-issued API client secret. Treat like a password — never expose in frontend code |

**Example Request:**
```http
POST https://auth.travelport.net/oauth/token
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&client_id=YOUR_CLIENT_ID&client_secret=YOUR_CLIENT_SECRET
```

---

#### Response Fields

| Field | Type | Description |
|---|---|---|
| `access_token` | string | The Bearer token to include in every API request header. Example: `eyJhbGciOiJSU...` |
| `token_type` | string | Always `"Bearer"`. Used to construct the Authorization header |
| `expires_in` | integer | Token lifetime in seconds. Typically `86400` (= 24 hours) |
| `scope` | string | The permission scope granted to this token |

**Example Response:**
```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6...",
  "token_type": "Bearer",
  "expires_in": 86400,
  "scope": "read write"
}
```

---

### 1.2 Required HTTP Headers (Every API Call)

| Header | Value / Format | Required | When to Send | Why |
|---|---|---|---|---|
| `Authorization` | `Bearer {access_token}` | ✅ REQUIRED | Every request | Authenticates who you are |
| `XAUTH_TRAVELPORT_ACCESSGROUP` | Your PCC (e.g., `BDAC`) | ✅ REQUIRED | Every request | Identifies which agency office the request belongs to |
| `Content-Type` | `application/json` | ✅ REQUIRED (POST/PATCH) | POST, PATCH, PUT requests | Tells the server the body format. Do NOT send for some NDC Cancel and Post-Commit endpoints |
| `Accept` | `application/json` | Recommended | All requests | Tells the server to return JSON |
| `Accept-Encoding` | `gzip, deflate` | ✅ REQUIRED (Production) | All production requests | Compresses responses, required for production traffic |
| `Cache-Control` | `no-cache` | Recommended | All requests | Ensures you receive fresh data, not a stale cached response |
| `TraceId` | UUID string (e.g., `550e8400-e29b-41d4-a716-446655440000`) | Optional | Multi-step flows | A custom identifier you generate to correlate related API calls (search → book → ticket). Travelport may generate one if absent |
| `TVP-PCC-CORE` | `{PCC}_{GDS}` (e.g., `BDAC_1G`) | Optional | Alternative to XAUTH header | An alternate way to specify PCC and GDS system. Format: PCC underscore GDS code |
| `travelportPlusSessionIdentifier` | Session ID string | Specific flows | Traveler update workflows | Maintains an established agency GDS session across multiple calls |

---

### 1.3 GDS Source Codes

| Code | GDS Name | Region |
|---|---|---|
| `1G` | Galileo / Travelport+ | Global (preferred) |
| `1V` | Apollo | Americas |
| `1P` | Worldspan | Americas |

---

## PART 2 — MODULE 1: AIR SHOPPING

### 2.1 Core Search — `POST /catalog/search/catalogproductofferings`

**Purpose:** The primary flight search endpoint. Returns a list of available flights combining GDS and NDC content in a single response. Called every time a user searches for flights.

**Base URL (append to):** `https://api.travelport.net/11/air/`
**Full URL:** `POST https://api.travelport.net/11/air/catalog/search/catalogproductofferings`

---

#### Full Request Body Schema

```json
{
  "CatalogProductOfferingsQueryRequest": {
    "@type": "CatalogProductOfferingsQueryRequest",
    "QuerySearchCriteriaFlights": {
      "@type": "QuerySearchCriteriaFlights",
      "SearchPriorityCode": "string",
      "PassengerCriteria": [ ... ],
      "SearchCriteriaFlight": [ ... ],
      "SearchModifiersAir": { ... }
    }
  }
}
```

---

#### `@type` Field — Critical Polymorphism Note

> [!IMPORTANT]
> Travelport API v11 uses **polymorphism**. Almost every object has an `@type` field. This tells the API which exact class/schema variant you are sending. Always include `@type` exactly as documented — missing or wrong values will cause `400` errors.

---

#### `PassengerCriteria` — Passenger Configuration

| Field | Type | Required | Description | Example |
|---|---|---|---|---|
| `@type` | string | ✅ REQUIRED | Always `"PassengerCriteria"` | `"PassengerCriteria"` |
| `PassengerQuantityCode` | array | ✅ REQUIRED | List of passenger counts per type | See below |
| `PassengerQuantityCode[].code` | string (PTC) | ✅ REQUIRED | The passenger type. See full PTC list below | `"ADT"` |
| `PassengerQuantityCode[].quantity` | integer | ✅ REQUIRED | Number of this type of passenger. Max total: 9 | `2` |
| `PassengerQuantityCode[].age` | integer | Conditional | Age of the child/infant in years. **Required for CNN and INF** to get accurate fare | `8` (for child) |

**Example:**
```json
"PassengerCriteria": [
  {
    "@type": "PassengerCriteria",
    "PassengerQuantityCode": [
      { "code": "ADT", "quantity": 2 },
      { "code": "CNN", "quantity": 1, "age": 8 },
      { "code": "INF", "quantity": 1, "age": 0 }
    ]
  }
]
```

---

#### Passenger Type Codes (PTC) — Complete Reference

| Code | Meaning | Age Range | Notes |
|---|---|---|---|
| `ADT` | Adult | 12+ years | Default passenger type. No age attribute needed |
| `CNN` / `CHD` | Child | 2–11 years | Always include `age` attribute. Some carriers use CHD, Travelport prefers CNN |
| `INF` | Infant (no seat) | Under 2 | Travels on adult lap. No separate seat. Include `age` attribute |
| `INS` | Infant with seat | Under 2 | Has own seat. Charged at child or full fare depending on carrier |
| `UMNR` | Unaccompanied Minor | 5–17 | Child traveling alone. SSR UMNR required at booking |
| `STU` | Student | Varies | Requires proof of enrollment. Availability varies by route and carrier |
| `SEA` / `MAR` | Seaman | — | Crew/seaman discount fare. Requires documentation |
| `GVT` | Government | — | Government official fare. Requires agency code |
| `MIL` | Military | — | Armed forces discount. Requires ID verification |
| `SRC` / `S65` | Senior Citizen | 60–65+ | Senior discount fares. Age threshold varies by carrier |
| `YTH` | Youth | 12–25 | Youth discount fares on certain carriers/routes |

> [!NOTE]
> Always send the actual passenger count. Max 9 passengers total per search request. Split into multiple requests if needed.

---

#### `SearchCriteriaFlight` — Journey / Itinerary Definition

Each element in this array defines one leg of the journey. For round-trip: 2 elements. For one-way: 1. For multi-city: up to 6 (GDS) or 3 (NDC).

| Field | Type | Required | Description | Example |
|---|---|---|---|---|
| `@type` | string | ✅ REQUIRED | `"SearchCriteriaFlight"` | `"SearchCriteriaFlight"` |
| `From` | object | ✅ REQUIRED | Departure airport/city | `{ "value": "DAC" }` |
| `From.value` | string | ✅ REQUIRED | IATA 3-letter airport code. Can also be a city code (e.g., LON = London city area) | `"DAC"` |
| `To` | object | ✅ REQUIRED | Arrival airport/city | `{ "value": "DXB" }` |
| `To.value` | string | ✅ REQUIRED | IATA 3-letter airport code or city code | `"DXB"` |
| `DepartureDate` | string (date) | ✅ REQUIRED | Travel date in `YYYY-MM-DD` format. Never ISO datetime — date only | `"2026-12-15"` |
| `DepartureTime` | string (time) | Optional | Preferred departure time window in `HH:MM` format. Used as a soft preference, not a hard filter | `"06:00"` |
| `DepartureTimeWindow` | integer | Optional | Number of hours +/- the preferred DepartureTime to search within | `3` |

**One-Way Example:**
```json
"SearchCriteriaFlight": [
  {
    "@type": "SearchCriteriaFlight",
    "From": { "value": "DAC" },
    "To": { "value": "DXB" },
    "DepartureDate": "2026-12-15"
  }
]
```

**Round-Trip Example:**
```json
"SearchCriteriaFlight": [
  { "@type": "SearchCriteriaFlight", "From": { "value": "DAC" }, "To": { "value": "DXB" }, "DepartureDate": "2026-12-15" },
  { "@type": "SearchCriteriaFlight", "From": { "value": "DXB" }, "To": { "value": "DAC" }, "DepartureDate": "2026-12-22" }
]
```

---

#### `SearchModifiersAir` — Complete Modifiers Reference

| Field | Type | Required | When to Use | Description |
|---|---|---|---|---|
| `@type` | string | ✅ REQUIRED | Always | `"SearchModifiersAir"` |
| `SearchRepresentation` | string | ✅ REQUIRED | Always | `"Journey"` (returns full itinerary offers) or `"Leg"` (returns one leg at a time — use with multi-city). Journey is most common |
| `MaxNumberOfStops` | integer | Optional | Filter direct/nonstop | Max number of connecting stops. `0` = nonstop only, `1` = max 1 stop, etc. |
| `CabinPreference` | array | Optional | When cabin class matters | Ordered list of preferred cabins. See Cabin Class codes below |
| `CabinPreference[].cabin` | string | Optional | — | Cabin code: `Economy`, `PremiumEconomy`, `Business`, `First` |
| `CabinPreference[].preference` | string | Optional | — | `Preferred` (try to return but fallback) or `Permitted` (strict — only return this cabin) |
| `CarrierPreference` | object | Optional | Airline filtering | Preferred or excluded airlines |
| `CarrierPreference.includedAirlineCodes` | array[string] | Optional | Prefer specific airlines | IATA 2-letter airline codes to include. E.g., `["BG", "EK"]` |
| `CarrierPreference.excludedAirlineCodes` | array[string] | Optional | Block specific airlines | Airlines to completely exclude from results |
| `AlliancePreference` | array[string] | Optional | Alliance filtering | Filter by alliance: `"StarAlliance"`, `"Oneworld"`, `"SkyTeam"` |
| `MaxConnectionTime` | integer | Optional | Reduce long layovers | Max connection time in minutes between segments |
| `MinConnectionTime` | integer | Optional | Ensure enough connection | Min connection time in minutes |
| `NonStopPreferred` | boolean | Optional | Prefer direct flights | `true` = try to return nonstop first, then connecting if none |
| `offersPerPage` | integer | Optional | **CRITICAL for booking** | Number of results to cache per page. Set this if you intend to book using reference payload — enables result caching. Recommended: `10`–`50` |
| `NumberOfResultsInGroup` | integer | Optional | Reduce response size | Limits results per journey group |
| `PrivateFareSearchType` | string | Optional | Corporate/private fares | `"AccountCode"` or `"ContractCode"` |
| `AccountCode` | array | Optional | Corporate fares | List of corporate account codes (CLIDs) to activate negotiated fare pricing |
| `AccountCode[].value` | string | Optional | — | The actual corporate code string. E.g., `"SKYNOVIA2024"` |
| `LoyaltyIdentifier` | array | Optional | Frequent flyer pricing | FFP numbers per carrier to activate loyalty-based pricing |
| `ExcludeGroundTransportation` | boolean | Optional | Rail filters | `true` = exclude non-air ground transport options |

---

#### Cabin Class Codes

| API Value | Human Name | Description |
|---|---|---|
| `Economy` | Economy | Standard economy class (Y class bucket) |
| `PremiumEconomy` | Premium Economy | Upgraded economy with more space (W class) |
| `Business` | Business | Business/club class with lie-flat seats (C class) |
| `First` | First | First class, highest service tier (F class) |

---

#### Search Response — Key Fields

| Field | Type | Description |
|---|---|---|
| `CatalogProductOfferingsResponse` | object | Root response object |
| `CatalogProductOffering` | array | List of flight offers. Each offer = one complete itinerary + fare combination |
| `CatalogProductOffering[].id` | string | **Unique Offer ID** — required to build a booking from this offer (reference payload mode) |
| `CatalogProductOffering[].ProductBrandOffering` | array | Branded fare variants of this offer (if airline uses fare families) |
| `CatalogProductOffering[].Product` | object | Flight itinerary details |
| `Product.FlightSegment` | array | Individual flight segments in the itinerary |
| `FlightSegment[].DepartureAirport.value` | string | IATA code of departure airport |
| `FlightSegment[].ArrivalAirport.value` | string | IATA code of arrival airport |
| `FlightSegment[].DepartureDate` | string | Departure date `YYYY-MM-DD` |
| `FlightSegment[].DepartureTime` | string | Departure time `HH:MM` |
| `FlightSegment[].ArrivalDate` | string | Arrival date `YYYY-MM-DD` |
| `FlightSegment[].ArrivalTime` | string | Arrival time `HH:MM` |
| `FlightSegment[].MarketingCarrier.value` | string | IATA code of marketing airline (the one on the ticket). E.g., `"BG"` |
| `FlightSegment[].OperatingCarrier.value` | string | IATA code of the airline actually operating the flight (codeshare partner) |
| `FlightSegment[].FlightNumber` | string | Flight number digits (e.g., `"147"`) |
| `FlightSegment[].ClassOfService` | string | Booking class (RBD). E.g., `"Y"`, `"K"`, `"L"` |
| `FlightSegment[].CabinAir` | string | Actual cabin name: `Economy`, `Business`, etc. |
| `FlightSegment[].Duration` | string | Segment flight duration in ISO 8601 format (e.g., `"PT3H20M"` = 3h 20m) |
| `FlightSegment[].Equipment` | string | Aircraft type IATA code (e.g., `"73H"` = Boeing 737-800) |
| `FlightSegment[].NumberOfStops` | integer | Number of stops within this segment |
| `CatalogProductOffering[].Price` | object | Pricing block |
| `Price.TotalPrice.value` | number | Grand total fare in the currency specified |
| `Price.TotalPrice.code` | string | Currency code. E.g., `"BDT"`, `"USD"`, `"EUR"` |
| `Price.BaseAirPrice` | object | Base fare before taxes and surcharges |
| `Price.Taxes` | object | Total tax amount |
| `Price.TaxBreakdown` | array | Itemized list of individual taxes |
| `TaxBreakdown[].code` | string | Tax code. E.g., `"YQ"` (fuel surcharge), `"YR"` (carrier-imposed), `"BD"` (Bangladesh departure tax) |
| `TaxBreakdown[].amount` | number | Amount of this individual tax |
| `TaxBreakdown[].description` | string | Human-readable name of the tax |
| `CatalogProductOffering[].ContentSource` | string | `"GDS"` or `"NDC"` — indicates where this offer came from |
| `CatalogProductOffering[].BaggageAllowance` | array | Baggage allowance per segment per passenger type |
| `BaggageAllowance[].PieceCount` | integer | Number of checked bags included (piece concept). `0` = no free bag |
| `BaggageAllowance[].Weight` | object | Weight-based allowance (weight concept). Fields: `value` (number) + `unit` (`"kg"` or `"lb"`) |
| `CatalogProductOffering[].FareBasisCode` | string | The raw fare basis code for this offer |
| `CatalogProductOffering[].FareFamily` | string | Branded fare name if airline uses fare families (e.g., `"LIGHT"`, `"FLEX"`, `"BUSINESS"`) |
| `CatalogProductOffering[].IsRefundable` | boolean | `true` if the fare has a refund option |
| `CatalogProductOffering[].IsExchangeable` | boolean | `true` if changes are permitted |
| `CatalogProductOffering[].PenaltyInformation` | array | Change/cancel penalty details |
| `PenaltyInformation[].type` | string | `"Change"` or `"Cancel"` |
| `PenaltyInformation[].penaltyAmount` | number | Penalty fee amount. `0` = free changes/cancels |

---

### 2.2 Low Fare Search (Flexible Dates)

Same endpoint as core search. Add `SearchRepresentation: "LowFare"` or use a date range modifier in `SearchCriteriaFlight`.

**Extra Fields for Low Fare:**

| Field | Type | Description |
|---|---|---|
| `DateRangeEnd` | string (date) | End of the flexible date range (YYYY-MM-DD). API returns cheapest date in range |
| `DateRangeStart` | string (date) | Start of flexible date range |

---

### 2.3 Offer Pricing — `POST /catalog/price/catalogproductofferings`

**Purpose:** After a user selects a flight, reprice it to confirm the current price before booking. Prices can change between search and booking. **Always call this before building a booking.**

#### Request Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `@type` | string | ✅ | `"CatalogProductOfferingsQueryRequest"` |
| `requestedOffer.id` | string | ✅ | The `id` from the search response (CatalogProductOffering ID) |
| `requestedOffer.@type` | string | ✅ | `"OfferRequest"` |
| `PassengerCriteria` | array | ✅ | Same structure as search — must match the original search passenger config |
| `SearchCriteriaFlight` | array | ✅ for Full Payload | Required for NDC full-payload pricing. The complete segment details |
| `PricingModifiers` | object | Optional | Additional pricing controls |
| `PricingModifiers.FareBasisCode` | string | Optional | Force a specific fare basis code |
| `PricingModifiers.AccountCode` | string | Optional | Corporate account code for private fare pricing |
| `PricingModifiers.CurrencyCode` | string | Optional | Request pricing in a specific currency (e.g., `"USD"`) |

#### Response — Additional Fields Beyond Search

| Field | Type | Description |
|---|---|---|
| `PriceBreakdown` | array | Per-passenger fare breakdown |
| `PriceBreakdown[].ptc` | string | Passenger type code this breakdown applies to |
| `PriceBreakdown[].quantity` | integer | Number of passengers of this type |
| `PriceBreakdown[].baseFare` | object | Base fare per passenger |
| `PriceBreakdown[].taxes` | object | Tax per passenger |
| `PriceBreakdown[].totalFare` | object | Total per passenger |
| `ValidatingCarrier` | string | The airline responsible for ticket validation (usually the primary marketing carrier) |
| `TicketingDeadline` | string | Datetime by which the ticket must be issued (ISO 8601) |
| `FareRuleReference` | string | Reference ID to retrieve full fare rules |

---

### 2.4 Fare Rules — `POST /catalog/farerule`

**Purpose:** Returns the full text or structured conditions of a fare. Always show this to users before they confirm a booking.

#### Request Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `FareRuleKey` | string | ✅ | The fare rule reference key from the pricing response |
| `@type` | string | ✅ | `"FareRuleQueryRequest"` |

#### Response Fields

| Field | Type | Description |
|---|---|---|
| `FareRule` | array | List of rule categories |
| `FareRule[].ruleCategory` | string | Category name: `"Penalties"`, `"MinStay"`, `"MaxStay"`, `"AdvancePurchase"`, `"Blackouts"`, `"Combinability"` |
| `FareRule[].ruleText` | string | Full free-text rule (often in airline tariff language) |
| `FareRule[].StructuredRule` | object | Parsed structured rule (when available) |
| `StructuredRule.penaltyAmount` | number | Numeric penalty value |
| `StructuredRule.penaltyCurrency` | string | Currency of penalty |
| `StructuredRule.minStayDays` | integer | Minimum night stay requirement |
| `StructuredRule.maxStayDays` | integer | Maximum stay allowed |
| `StructuredRule.advancePurchaseDays` | integer | Must book N days before departure |
| `StructuredRule.isRefundable` | boolean | Whether any refund is possible |
| `StructuredRule.isChangeable` | boolean | Whether itinerary changes are allowed |

---

## PART 3 — MODULE 2: BOOKING & WORKBENCH

### 3.1 Create Reservation Workbench

**Method:** `POST`
**URL:** `https://api.travelport.net/11/air/book/airoffer/reservationworkbench`

**Purpose:** Opens a new booking session. Think of it as "adding items to a shopping cart". Everything goes in here before you "checkout" (Commit). Must be the first booking step.

#### Request Body

| Field | Type | Required | Description |
|---|---|---|---|
| `@type` | string | ✅ | `"ReservationWorkbench"` |
| `AgencyCode` | string | Optional | Your agency's IATA code. Defaults to PCC's registered agency if not provided |
| `AgencyName` | string | Optional | Your agency's name |
| `TransactionDateTime` | string | Optional | ISO 8601 datetime of when this workbench is initiated |

#### Response Fields

| Field | Type | Description |
|---|---|---|
| `Identifier.value` | string | ⭐ **The `workbenchID`** — save this! Used in ALL subsequent booking calls |
| `Identifier.authority` | string | The system that issued this ID |
| `WorkbenchStatus` | string | Current workbench state. Should be `"Open"` after creation |

---

### 3.2 Build Offer (Add Flights) — `POST /book/airoffer/reservationworkbench/{workbenchID}/offers/build`

**Purpose:** Takes the selected flight offer from search and adds it to the workbench. This is the "select flight" step.

| Path Parameter | Type | Required | Description |
|---|---|---|---|
| `workbenchID` | string | ✅ | The ID from the Create Workbench response |

#### Request Body — Reference Payload Mode (Preferred)

```json
{
  "@type": "BuildFromCatalogProductOffering",
  "CatalogProductOfferingIdentifier": {
    "id": "OFFER_ID_FROM_SEARCH",
    "Identifier": {
      "authority": "Travelport",
      "value": "OFFER_ID_FROM_SEARCH"
    }
  }
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `@type` | string | ✅ | `"BuildFromCatalogProductOffering"` for reference mode |
| `CatalogProductOfferingIdentifier.id` | string | ✅ | The offer `id` from search response |

#### Request Body — Full Payload Mode (Required for some NDC)

```json
{
  "@type": "BuildFromCatalogProductOfferingFull",
  "CatalogProductOffering": { /* complete offer object from search */ }
}
```

---

### 3.3 Add Travelers — `POST /book/traveler/reservationworkbench/{workbenchID}/travelers`

**Purpose:** Adds passenger details to the workbench. Must be done before commit.

#### Traveler Object — Complete Field Reference

| Field | Type | Required | Description |
|---|---|---|---|
| `@type` | string | ✅ | `"Traveler"` |
| `NamePrefix` | string | Optional | Title: `"Mr"`, `"Mrs"`, `"Ms"`, `"Dr"`, `"Prof"` |
| `GivenName` | string | ✅ | First name(s) of the traveler — must match passport |
| `Surname` | string | ✅ | Last name / family name — must match passport |
| `BirthDate` | string | ✅ for children/infants | Date of birth in `YYYY-MM-DD`. Required for CNN and INF to verify age |
| `Gender` | string | Optional | `"Male"`, `"Female"`, `"Unspecified"`. Some carriers require |
| `PassengerTypeCode` | string | ✅ | The PTC for this traveler: `"ADT"`, `"CNN"`, `"INF"`, etc. |
| `ContactInformation` | array | ✅ | At least one contact method required |
| `ContactInformation[].@type` | string | ✅ | `"ContactInformationPhone"` or `"ContactInformationEmail"` |
| `ContactInformation[].EmailAddress` | string | Conditional | Valid email. Required by most airlines for e-ticket delivery |
| `ContactInformation[].PhoneNumber` | string | Conditional | Full phone with country code. E.g., `"+8801712345678"` |
| `ContactInformation[].CountryDialingCode` | string | Conditional | Dialing prefix. E.g., `"880"` for Bangladesh |

---

#### Travel Documents (Passport) — Nested in Traveler

| Field | Type | Required | Description |
|---|---|---|---|
| `TravelDocument` | array | ✅ for international | Passport/travel document array |
| `TravelDocument[].@type` | string | ✅ | `"TravelDocumentPassport"` |
| `TravelDocument[].DocumentNumber` | string | ✅ | Passport number |
| `TravelDocument[].ExpiryDate` | string | ✅ | Passport expiry in `YYYY-MM-DD`. Must be valid beyond travel |
| `TravelDocument[].IssuingCountry.value` | string | ✅ | ISO 2-letter country code of issuing authority. E.g., `"BD"` |
| `TravelDocument[].NationalityCountry.value` | string | ✅ | Traveler's nationality code. E.g., `"BD"` |
| `TravelDocument[].BirthCountry.value` | string | Optional | Country of birth ISO code |
| `TravelDocument[].BirthDate` | string | ✅ | Must match traveler's BirthDate above |
| `TravelDocument[].GivenName` | string | ✅ | As printed on passport |
| `TravelDocument[].Surname` | string | ✅ | As printed on passport |
| `TravelDocument[].Gender` | string | ✅ | `"M"` or `"F"` as on passport |

---

#### Loyalty / Frequent Flyer — Nested in Traveler

| Field | Type | Required | Description |
|---|---|---|---|
| `CustomerLoyalty` | array | Optional | Frequent flyer programs for this traveler |
| `CustomerLoyalty[].@type` | string | ✅ | `"CustomerLoyalty"` |
| `CustomerLoyalty[].ProgramID` | string | ✅ | Airline IATA code for the loyalty program. E.g., `"EK"` for Emirates Skywards |
| `CustomerLoyalty[].MembershipID` | string | ✅ | The frequent flyer number |
| `CustomerLoyalty[].LoyaltyLevel` | string | Optional | Elite tier if known (e.g., `"Gold"`, `"Platinum"`). Helps with free seat eligibility |

---

### 3.4 Add SSR / Remarks — `POST /book/remarks/reservationworkbench/{workbenchID}/reservationcomments/list`

**Purpose:** Add special service requests and informational remarks to the booking.

#### Special Service Request (SSR) — Complete Code Reference

##### Wheelchair Codes

| Code | Full Name | Description |
|---|---|---|
| `WCHR` | Wheelchair — Ramp | Can walk on/off plane, needs wheelchair for long distances |
| `WCHS` | Wheelchair — Steps | Cannot climb stairs but can walk to seat |
| `WCHC` | Wheelchair — Completely Immobile | Needs full assistance, brought to seat |
| `WCMP` | Manual Wheelchair | Traveling with own manual wheelchair |
| `WCBD` | Dry Battery Wheelchair | Traveling with dry-cell powered wheelchair |
| `WCBW` | Wet Battery Wheelchair | Traveling with wet-cell powered wheelchair |
| `WCOB` | Onboard Wheelchair | Requesting airline's onboard wheelchair |

##### Meal Request Codes

| Code | Meal Type | When to Use |
|---|---|---|
| `AVML` | Asian Vegetarian | South/Southeast Asian vegetarian (no meat, eggs, or dairy) |
| `BBML` | Baby Meal | For infants/toddlers (pureed, soft foods) |
| `BLML` | Bland Meal | Low-spice, easily digestible — for medical conditions |
| `CHML` | Child Meal | Age-appropriate portions for children |
| `DBML` | Diabetic Meal | Low-sugar, controlled carbohydrate meal |
| `FPML` | Fruit Platter | Fresh fruit only |
| `GFML` | Gluten-Free | No wheat, barley, rye. For celiac disease |
| `HNML` | Hindu Non-Vegetarian | No beef. May contain chicken, lamb, seafood |
| `KSML` | Kosher | Prepared according to Jewish dietary laws (pre-packaged) |
| `LCML` | Low Calorie | Calorie-controlled meal |
| `LFML` | Low Fat | Low cholesterol and fat |
| `LSML` | Low Salt | No/low sodium |
| `MOML` | Muslim Meal | Halal-certified. No pork, alcohol |
| `NLML` | Non-Lactose | No dairy products |
| `RVML` | Raw Vegetarian | Uncooked fruits and vegetables only |
| `SFML` | Seafood | Fish and seafood only |
| `SPML` | Special Meal | Custom — requires free-text description of specific needs |
| `VGML` | Vegan | No animal products whatsoever |
| `VLML` | Vegetarian Lacto-Ovo | Vegetarian that includes eggs and dairy |

##### Other SSR Codes

| Code | Description |
|---|---|
| `UMNR` | Unaccompanied Minor — child traveling alone. Triggers airline's UM service protocol |
| `DEAF` | Hearing-impaired passenger |
| `BLIND` | Visually-impaired passenger |
| `MEDA` | Medical case — used when passenger needs special medical attention onboard |
| `DOCA` | Travel document info (API-DOCS) for countries requiring advance passenger data |
| `DOCS` | Passport information transmitted to airline. Required for APIS (Advance Passenger Information System) |
| `DOCO` | Visa information transmitted to airline |
| `PNUT` | Peanut allergy alert |
| `PETC` | Carry-on pet (in cabin) |
| `AVIH` | Animal in hold (checked pet) |
| `EXST` | Extra seat (e.g., for large passenger or cello) |
| `BIKE` | Bicycle in cargo |
| `STCR` | Stretcher case — passenger must travel lying down |
| `OXYG` | Oxygen required onboard |

#### SSR Request Structure

```json
{
  "@type": "ReservationCommentSSR",
  "SSRCode": "VGML",
  "SegmentNumber": 1,
  "PassengerIdentifier": "PAX1",
  "FreeText": ""
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `@type` | string | ✅ | `"ReservationCommentSSR"` |
| `SSRCode` | string | ✅ | 4-letter SSR code from above list |
| `SegmentNumber` | integer | Optional | Which flight segment this SSR applies to. Omit for all segments |
| `PassengerIdentifier` | string | Optional | Internal reference to link SSR to a specific traveler |
| `FreeText` | string | Conditional | Required for `SPML`, `MEDA` — free-text description of requirement |

---

#### OSI (Other Service Information) Structure

```json
{
  "@type": "ReservationCommentOSI",
  "CarrierCode": "EK",
  "FreeText": "CORPORATE ID SKYNOVIACO2024"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `CarrierCode` | string | ✅ | Airline code this OSI is for |
| `FreeText` | string | ✅ | The informational text sent to the carrier |

---

### 3.5 Commit Workbench (Create PNR)

**Method:** `POST`
**URL:** `https://api.travelport.net/11/air/book/airoffer/reservationworkbench/{workbenchID}/commit`

**Purpose:** Finalizes everything in the workbench and creates the actual PNR. This is the point of no return — after commit, the booking is live in the GDS/airline system.

#### Request Body

```json
{
  "@type": "ReservationWorkbench",
  "QueueOnCommit": { "queueNumber": "10", "pccCode": "BDAC" }
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `QueueOnCommit` | object | Optional | If provided, places the created PNR into a specified queue immediately after commit |
| `QueueOnCommit.queueNumber` | string | Optional | The queue number in your PCC |
| `QueueOnCommit.pccCode` | string | Optional | The PCC where the queue lives |

#### Response Fields

| Field | Type | Description |
|---|---|---|
| `Reservation.Locator` | array | List of locators for this booking |
| `Locator[].value` | string | **The PNR Code** (e.g., `"ABCDEF"`) — 6-letter alphanumeric GDS locator |
| `Locator[].source` | string | The system that holds this locator: `"1G"`, `"1V"`, `"1P"`, or airline code for NDC |
| `Reservation.@type` | string | `"ReservationResponse"` |
| `Reservation.id` | string | Internal reservation UUID |
| `PassengerIdentifier` | array | Assigned internal IDs for each traveler in this PNR |

---

## PART 4 — MODULE 3: SEAT MAP

### 4.1 Get Seat Map — `POST /catalog/search/seatmap`

**Purpose:** Retrieves an interactive seat map for a specific flight. Shows which seats are available, their type, price, and whether they are complimentary or paid.

#### Request Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `@type` | string | ✅ | `"SeatAvailabilityQueryRequest"` |
| `FlightSegment` | object | ✅ | The specific flight segment to get the seat map for |
| `FlightSegment.MarketingCarrier.value` | string | ✅ | IATA airline code |
| `FlightSegment.FlightNumber` | string | ✅ | Flight number digits |
| `FlightSegment.DepartureDate` | string | ✅ | `YYYY-MM-DD` |
| `FlightSegment.DepartureAirport.value` | string | ✅ | IATA departure airport code |
| `FlightSegment.ArrivalAirport.value` | string | ✅ | IATA arrival airport code |
| `FlightSegment.ClassOfService` | string | Optional | Booking class — helps return relevant seat availability |
| `PassengerCriteria` | array | ✅ | Same passenger structure as search |
| `ReservationIdentifier` | string | For NDC | The workbenchID or reservationID — required for NDC seat maps |

#### Seat Map Response Fields

| Field | Type | Description |
|---|---|---|
| `SeatMap` | object | Root seat map object |
| `SeatMap.Cabin` | array | List of cabins on this aircraft |
| `Cabin[].CabinAir` | string | Cabin name: `"Economy"`, `"Business"`, `"First"` |
| `Cabin[].Row` | array | Aircraft seat rows |
| `Row[].rowNumber` | integer | Row number on the aircraft |
| `Row[].Seat` | array | Individual seats in this row |
| `Seat[].column` | string | Seat column letter: `"A"`, `"B"`, `"C"`, `"D"`, `"E"`, `"F"` |
| `Seat[].status` | string | `"Available"`, `"Occupied"`, `"Blocked"`, `"Reserved"` |
| `Seat[].SeatCharacteristic` | array | Characteristics of this seat |
| `SeatCharacteristic[].value` | string | Characteristic code — see table below |
| `Seat[].Price` | object | Pricing for this seat (empty if complimentary) |
| `Seat[].Price.TotalPrice.value` | number | Price to select this seat. `0.00` = free seat |
| `Seat[].Price.TotalPrice.code` | string | Currency code |
| `Seat[].isChargeable` | boolean | `true` = paid seat, `false` = complimentary (free) |
| `Seat[].HeldAncillary` | object | Present if a passenger already has this seat — prevents double booking |

#### Seat Characteristic Codes

| Code | Meaning |
|---|---|
| `W` | Window seat |
| `A` | Aisle seat |
| `M` | Middle seat |
| `E` | Exit row — extra legroom, restrictions on who can sit here |
| `B` | Bulkhead row — front of cabin section, often more legroom |
| `L` | Extra legroom seat |
| `O` | Overwing — over the wing |
| `RS` | Rear seat (back of aircraft) |
| `CH` | Chargeable seat — requires payment |
| `NW` | No window seat |
| `IW` | Inoperative window |
| `1A` | First row |
| `UP` | Upper deck (e.g., A380) |

---

### 4.2 Book Seat — `POST /book/airoffer/reservationworkbench/{workbenchID}/offers/buildseatoffers`

**Purpose:** Assigns a specific seat to a passenger within the workbench session.

#### Request Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `@type` | string | ✅ | `"BuildSeatOffersFromSeatMap"` |
| `SeatAssignment` | array | ✅ | List of seat assignments |
| `SeatAssignment[].SeatIdentifier` | object | ✅ | References the seat from the seat map |
| `SeatAssignment[].PassengerIdentifier` | string | ✅ | Which traveler gets this seat |
| `SeatAssignment[].SegmentIdentifier` | string | ✅ | Which flight segment |

---

## PART 5 — MODULE 4: DOCUMENT PRODUCTION & TICKETING

### 5.1 Issue Ticket — Post-Commit Workbench Flow

**Purpose:** After a PNR exists, issue the actual airline ticket (e-ticket). Generates the ticket number that passengers use to board.

#### Step 1 — Create Post-Commit Workbench

**Method:** `POST`
**URL:** `https://api.travelport.net/11/air/book/airoffer/reservationworkbench`

```json
{
  "@type": "ReservationWorkbench",
  "Reservation": {
    "Locator": [{ "value": "ABCDEF", "source": "1G" }]
  }
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `Reservation.Locator[].value` | string | ✅ | The PNR code from the booking commit |
| `Reservation.Locator[].source` | string | ✅ | GDS source: `"1G"`, `"1V"`, or `"1P"` |

---

#### Step 2 — Add Form of Payment

**Method:** `POST`
**URL:** `.../offers/buildpaymentoffer`

| Field | Type | Required | Description |
|---|---|---|---|
| `@type` | string | ✅ | `"BuildPaymentOfferFromFormOfPayment"` |
| `FormOfPayment` | object | ✅ | Payment method details |
| `FormOfPayment.@type` | string | ✅ | `"FormOfPaymentPaymentCard"` (credit card) or `"FormOfPaymentCash"` |
| `FormOfPayment.CardType` | string | Conditional | Credit card type code — see table below |
| `FormOfPayment.CardNumber` | string | Conditional | Card number (typically tokenized) |
| `FormOfPayment.ExpiryDate` | string | Conditional | Card expiry in `MM/YY` |
| `FormOfPayment.CardholderName` | string | Conditional | Name on card |
| `FormOfPayment.Amount.value` | number | ✅ | Payment amount |
| `FormOfPayment.Amount.code` | string | ✅ | Currency code |

#### Credit Card Type Codes

| Code | Card Network |
|---|---|
| `VI` | Visa |
| `CA` | Mastercard |
| `AX` | American Express |
| `DS` | Discover |
| `TP` | UATP (Universal Air Travel Plan) |
| `JCB` | JCB |
| `DC` | Diners Club |

#### Step 3 — Commit (Issue Ticket)
Same commit endpoint as booking. Returns ticket numbers.

#### Ticketing Response Fields

| Field | Type | Description |
|---|---|---|
| `TicketNumber` | array | List of issued ticket numbers |
| `TicketNumber[].value` | string | 13-digit IATA ticket number (e.g., `"2321234567890"`) |
| `TicketNumber[].ticketStatus` | string | `"Issued"`, `"Voided"`, `"Refunded"`, `"Exchanged"` |
| `TicketNumber[].passengerRef` | string | Which passenger this ticket belongs to |

---

## PART 6 — MODULE 5: PNR MANAGEMENT

### 6.1 Retrieve Reservation — `GET /reservation/{reservationID}`

**Purpose:** Fetch the full current state of a PNR. Used by agents to view booking details, or by the system before any modification.

| Response Field | Type | Description |
|---|---|---|
| `Reservation.@type` | string | `"Reservation"` |
| `Reservation.id` | string | Internal UUID |
| `Reservation.Locator` | array | GDS and NDC locator codes |
| `Reservation.Traveler` | array | Full traveler records |
| `Reservation.Offer` | array | Flight offers in this booking |
| `Reservation.Payment` | array | Payments applied |
| `Reservation.Ticket` | array | Issued ticket information |
| `Reservation.RemarkList` | array | All SSR, OSI, and agency remarks |
| `Reservation.StatusCode` | string | `"Confirmed"`, `"Ticketed"`, `"Cancelled"`, `"Voided"` |
| `Reservation.CreatedDateTime` | string | When the PNR was created |
| `Reservation.TicketingDeadline` | string | Time limit for ticketing before auto-cancel |

---

### 6.2 Queue Management

#### Queue Placement — `POST /queue/place`

| Field | Type | Required | Description |
|---|---|---|---|
| `QueueIdentifier.queueNumber` | string | ✅ | Target queue number |
| `QueueIdentifier.pccCode` | string | ✅ | PCC where the queue lives |
| `ReservationIdentifier.value` | string | ✅ | The PNR locator to place in queue |

#### Queue List — `GET /queue/list`

| Query Parameter | Type | Description |
|---|---|---|
| `queueNumber` | string | Queue to retrieve |
| `pccCode` | string | PCC of the queue |
| `maxResults` | integer | Max records to return |

---

## PART 7 — MODULE 6: EXCHANGE, REFUND & VOID

### 7.1 Exchange Search — `POST /exchange/search/catalogproductofferings`

**Purpose:** Find alternative flights to replace an existing booked itinerary. Returns options with price differences calculated.

| Field | Type | Required | Description |
|---|---|---|---|
| `ExchangeRequest.TicketNumber` | string | ✅ | Ticket being exchanged |
| `ExchangeRequest.Locator` | string | Conditional | PNR locator (can use instead of ticket number) |
| `SearchCriteriaFlight` | array | ✅ | New desired itinerary |
| `PassengerCriteria` | array | ✅ | Passenger configuration |

#### Exchange Response — Extra Fields

| Field | Type | Description |
|---|---|---|
| `ExchangeOffer.PriceDifference` | object | Net amount owed (`+` = add-collect, `-` = refund) |
| `ExchangeOffer.ChangePenalty` | object | The carrier's change fee |
| `ExchangeOffer.PriceAfterExchange` | object | New total after exchange |
| `ExchangeOffer.FareDifference` | object | Difference in base fare only |
| `ExchangeOffer.TaxDifference` | object | Difference in taxes |
| `ExchangeOffer.isExchangeable` | boolean | Whether this specific offer can be exchanged for this ticket |

---

### 7.2 Void Ticket

#### Single Void — `PUT /ticket/tickets/updatestatus/{ticketID}`

| Parameter | Description |
|---|---|
| `ticketID` (path) | The 13-digit ticket number to void |
| Request body `status` | `"Voided"` |

> [!WARNING]
> Void is typically only available on the same day of ticket issuance. After the void window closes, you must use Refund.

#### Batch Void — `POST https://api.travelport.net/11/documents/void`

> [!WARNING]
> Note: This endpoint does NOT have `/air/` in the path. Base URL is `https://api.travelport.net/11/` — NOT `https://api.travelport.net/11/air/`

| Field | Type | Required | Description |
|---|---|---|---|
| `locator` | string | ✅ | PNR locator code |
| `documentVoid` | array | ✅ | List of documents to void |
| `documentVoid[].documentType` | string | ✅ | `"Ticket"` or `"EMD"` |
| `documentVoid[].number` | string | Optional | Specific ticket number. Omit to void all tickets on the PNR |

---

### 7.3 Refund Quote — `POST /refund/quote`

**Purpose:** Before actually processing a refund, get a quote showing exactly how much the passenger will receive back. Show this to the customer for approval.

| Field | Type | Required | Description |
|---|---|---|---|
| `TicketNumber` | string | ✅ | Ticket to refund |
| `Locator` | string | Conditional | PNR locator (alternative to ticket number) |

#### Refund Quote Response

| Field | Type | Description |
|---|---|---|
| `RefundQuote.TotalRefundAmount` | object | Total refund to be returned to passenger |
| `RefundQuote.Penalty` | object | Cancellation penalty applied |
| `RefundQuote.NetRefund` | object | Refund after penalty deduction |
| `RefundQuote.RefundableTaxes` | object | Tax amount that will be refunded |
| `RefundQuote.NonRefundableTaxes` | object | Taxes that cannot be refunded (YQ/YR typically) |
| `RefundQuote.BaseFareRefund` | object | Refund of base fare after penalty |
| `RefundQuote.IsRefundable` | boolean | `false` means the fare is completely non-refundable |
| `RefundQuote.RefundDeadline` | string | Date after which refund eligibility may change |

---

## PART 8 — MODULE 7: ANCILLARY SHOPPING

### 8.1 Ancillary Shop — `POST /catalog/search/ancillaryofferings`

**Purpose:** Browse all available paid extras for a booked itinerary or selected flights before booking.

| Field | Type | Required | Description |
|---|---|---|---|
| `FlightSegment` | array | ✅ | Segments to get ancillaries for |
| `Traveler` | array | ✅ | Traveler references |
| `ReservationIdentifier` | string | Optional | For post-booking ancillary shopping |

#### Ancillary Response Fields

| Field | Type | Description |
|---|---|---|
| `AncillaryOffering` | array | List of available ancillary offers |
| `AncillaryOffering[].AncillaryType` | string | Category: `"Baggage"`, `"Seat"`, `"Meal"`, `"PriorityBoarding"`, `"Lounge"` |
| `AncillaryOffering[].Name` | string | Human-readable name (e.g., `"Extra 23kg Bag"`) |
| `AncillaryOffering[].Price.TotalPrice.value` | number | Price for this ancillary |
| `AncillaryOffering[].SubCode` | string | IATA RFIC sub-code identifying the ancillary type |
| `AncillaryOffering[].RFIC` | string | Revenue Filing Identification Code. Industry code for ancillary category |
| `AncillaryOffering[].BookingInstructions` | string | Notes on how/when to book this item |
| `AncillaryOffering[].MaxQuantity` | integer | Max units of this item per passenger |

#### RFIC Codes (Ancillary Categories)

| Code | Category |
|---|---|
| `A` | Air transportation |
| `B` | Surface transportation |
| `C` | Baggage |
| `D` | Financial impact |
| `E` | Airport services |
| `F` | Merchandise |
| `G` | In-flight services |
| `H` | Other services |

---

## PART 9 — ERROR HANDLING REFERENCE

### HTTP Status Codes

| Code | Status | Common Causes | What To Do |
|---|---|---|---|
| `200` | OK | Success | Process response normally |
| `201` | Created | Resource created (e.g., workbench) | Capture the ID in response |
| `400` | Bad Request | Missing required field, wrong `@type`, invalid date format, wrong PTC | Check `Result.Error.Message` for specific cause |
| `401` | Unauthorized | Expired token, wrong credentials, missing XAUTH header | Refresh OAuth token, check PCC header |
| `403` | Forbidden | Not provisioned for NDC carrier, permission restriction | Contact Travelport to check provisioning |
| `404` | Not Found | Invalid workbenchID, expired offer ID, wrong locator | Re-search, or verify IDs |
| `409` | Conflict | Workbench session conflict, duplicate booking attempt | Wait and retry, check for existing PNR |
| `429` | Too Many Requests | Rate limit exceeded | Implement exponential backoff, contact Travelport |
| `500` | Internal Server Error | Travelport/GDS system issue | Retry with backoff, check Travelport status page |
| `503` | Service Unavailable | Travelport maintenance or airline downtime | Retry later |

### Error Response Structure

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
    ],
    "Warning": []
  }
}
```

| Error Field | Description |
|---|---|
| `StatusCode` | HTTP-equivalent error code |
| `Message` | Human-readable description of what went wrong |
| `SourceID` | Who generated the error: `"API"` (business validation), `"1G"` (Galileo GDS), carrier IATA code (NDC) |
| `SourceCode` | Numeric category: `1` = impairment, `1000` = validation, `2000` = system-wide |
| `Category` | `"Validation"`, `"System"`, `"Business"` |

---

## PART 10 — BRANDED FARES & FARE FAMILIES

### Branded Fare Response Fields

| Field | Type | Description |
|---|---|---|
| `ProductBrandOffering[].BrandTier` | string | Tier code: `BF1` (basic/cheapest) through `BF5` (most premium) |
| `ProductBrandOffering[].BrandName` | string | Airline's commercial brand name (e.g., `"ECONOMY LIGHT"`, `"BUSINESS FLEX"`) |
| `ProductBrandOffering[].BrandCode` | string | Internal code for the brand |
| `ProductBrandOffering[].BrandAttribute` | array | List of included/excluded services with this brand |
| `BrandAttribute[].serviceCode` | string | IATA ancillary code (e.g., `"0GO"` = 23kg bag) |
| `BrandAttribute[].commercialName` | string | Name of the included item (e.g., `"FREE 23KG BAG"`) |
| `BrandAttribute[].application` | string | `"Included"`, `"Available"`, `"NotAvailable"` |

---

## PART 11 — NDC-SPECIFIC DIFFERENCES

| Aspect | GDS Behavior | NDC Behavior |
|---|---|---|
| Ticket issuance | Travelport issues ticket | Airline issues ticket (Travelport confirms) |
| Seat map access | Pre-booking OK | Must be within a workbench session |
| Payload mode | Reference payload OK | Full payload may be required |
| Exchange | Via Travelport exchange endpoints | Via airline's own order management |
| PNR locator | Single GDS locator | GDS passive locator + Airline Order ID |
| Ancillary shop | Pre-booking OK | Session-bound |
| Max O&D pairs | 6 | 3 |
| Price cache | Longer TTL | Shorter or no cache — reprice before book |
| Fare rules | Structured | Often free text from airline |

### NDC Response Locator Fields

| Field | Description |
|---|---|
| `Locator[].source = "1G"` | The passive Travelport/GDS record locator |
| `Locator[].source = "AA"` | Airline's own Order ID (e.g., AA = American Airlines NDC) |
| `Locator[].OrderID` | NDC airline-side order identifier |

---

## PART 12 — REAL FULL EXAMPLE: COMPLETE SEARCH REQUEST

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

## PART 13 — REAL FULL EXAMPLE: COMPLETE BOOKING SEQUENCE

```
Step 1: POST /oauth/token → access_token
Step 2: POST /catalog/search/catalogproductofferings → offer.id
Step 3: POST /catalog/price/catalogproductofferings → confirm price
Step 4: POST /book/airoffer/reservationworkbench → workbenchID
Step 5: POST /book/airoffer/reservationworkbench/{id}/offers/build → flight added
Step 6: POST /book/traveler/reservationworkbench/{id}/travelers → travelers added
Step 7: POST /catalog/search/seatmap → seat map (optional)
Step 8: POST .../offers/buildseatoffers → seat selected (optional)
Step 9: POST .../offers/buildancillaryoffersfromcatalogofferings → ancillary (optional)
Step 10: POST /book/remarks/.../reservationcomments/list → SSR/OSI (optional)
Step 11: POST /book/airoffer/reservationworkbench/{id}/commit → PNR locator
Step 12: POST /book/airoffer/reservationworkbench → (post-commit, for ticketing)
Step 13: POST .../offers/buildpaymentoffer → FOP added
Step 14: POST .../commit → TICKET ISSUED → ticket number
```

---

## PART 14 — SUPPLIER CONFIG FOR YOUR CODEBASE

```json
{
  "name": "Travelport Bangladesh",
  "code": "TP-BD-DAC",
  "integration_provider": "travelport",
  "type": "GDS",
  "credentials": {
    "client_id": "<from portal>",
    "client_secret": "<from portal>",
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

*Document prepared for SkyNovia OTA Engine — Travelport JSON API v11 Maximum Detail Reference*
*Covers: Auth · Search · Price · Fare Rules · Booking · Travelers · SSR · OSI · Seats · Ancillaries · Ticketing · PNR Retrieve · Queue · Exchange · Refund · Void · NDC · Branded Fares · Error Handling*
*September 2026*
