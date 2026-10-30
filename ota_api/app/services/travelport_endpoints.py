class TravelportEndpoints:
    """
    Travelport+ JSON API v11 paths, relative to the configured base_url (e.g. https://api.pp.travelport.net/11).
    Most Air APIs live under /air; a few (batch void, GDS exchange search) do not.
    Reference: support.travelport.com → JSON APIs → Air v11 → Air Endpoints.
    """
    # Auth
    AUTH_TOKEN = "/oauth/token"

    # Search and Price
    CATALOG_SEARCH = "/air/catalog/search/catalogproductofferings"
    CATALOG_PRICE = "/air/price/offers/buildfromcatalogproductofferings"

    # Workbench / Booking
    WORKBENCH_CREATE = "/air/book/session/reservationworkbench"
    WORKBENCH_FROM_LOCATOR = "/air/book/session/reservationworkbench/buildfromlocator"   # ?Locator={pnr}
    WORKBENCH_OFFERS = "/air/book/airoffer/reservationworkbench/{id}/offers/buildfromcatalogproductofferings"
    WORKBENCH_TRAVELERS = "/air/book/traveler/reservationworkbench/{id}/travelers"
    WORKBENCH_TRAVEL_AGENCY = "/air/ticket/travelagency/reservationworkbench/{id}/travelagency"
    WORKBENCH_REMARKS = "/air/book/remarks/reservationworkbench/{id}/reservationcomments/list"
    WORKBENCH_COMMIT = "/air/book/reservation/reservations/{id}"
    WORKBENCH_IGNORE = "/air/book/session/reservationworkbench/{id}"

    # Payment / Ticketing (post-commit workbench)
    WORKBENCH_FOP = "/air/payment/reservationworkbench/{id}/formofpayment"
    WORKBENCH_PAYMENT = "/air/paymentoffer/reservationworkbench/{id}/payments"
    RESERVATION_RECEIPTS = "/air/receipt/reservations/{locator}/receipts"   # GET = list tickets, POST = cancel (GDS)

    # Seats and fare rules
    SEAT_AVAILABILITY = "/air/search/seat/catalogofferingsancillaries/seatavailabilities"
    FARE_RULES_FROM_SEARCH = "/air/farerule/farerules/fromcatalogproductofferings"   # GET
    FARE_RULES_FROM_RESERVATION = "/air/farerule/farerules/fromreservation"          # GET

    # Retrieval and Management
    RESERVATION_GET = "/air/book/reservation/reservations/{id}"
    QUEUE_PLACE = "/air/queue/queue"

    # GDS Exchange
    EXCHANGE_SEARCH = "/exchangesearch/catalogofferingsairchange"
    EXCHANGE_ADD_OFFER = "/air/book/offer/reservationworkbench/{id}/offers/buildfromcatalogofferings"

    # GDS Refund
    DOCUMENT_REFUND_QUOTE = "/air/book/airoffer/offers/documentrefundquote"
    DOCUMENT_REFUND_COMMIT = "/air/receipt/receipts/documentrefundfromofferlist"

    # Void
    VOID_SINGLE = "/air/ticket/tickets/updatestatus/{id}"
    VOID_BATCH = "/documents/void"
