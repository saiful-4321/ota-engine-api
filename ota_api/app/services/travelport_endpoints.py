class TravelportEndpoints:
    # Auth
    AUTH_TOKEN = "/oauth/token"
    
    # Search and Price
    CATALOG_SEARCH = "/air/catalog/search/catalogproductofferings"
    CATALOG_PRICE = "/air/price/offers/buildfromcatalogproductofferings"
    FARE_RULES = "/air/catalog/farerule"
    SEAT_MAP = "/air/catalog/search/seatmap"
    ANCILLARY_SHOP = "/air/catalog/search/ancillaryofferings"
    
    # Workbench / Booking
    WORKBENCH_CREATE = "/air/book/session/reservationworkbench"
    WORKBENCH_OFFERS = "/air/book/airoffer/reservationworkbench/{id}/offers/buildfromcatalogproductofferings"
    WORKBENCH_TRAVELERS = "/air/book/traveler/reservationworkbench/{id}/travelers"
    WORKBENCH_TRAVEL_AGENCY = "/air/ticket/travelagency/reservationworkbench/{id}/travelagency"
    WORKBENCH_REMARKS = "/air/book/remarks/reservationworkbench/{id}/reservationcomments/list"
    WORKBENCH_COMMIT = "/air/book/reservation/reservations/{id}"
    WORKBENCH_IGNORE = "/air/book/session/reservationworkbench/{id}"
    
    # Seats and Post-Booking
    SEAT_BOOK = "/air/book/airoffer/reservationworkbench/{id}/offers/buildseatoffers"
    PAYMENT_OFFER = "/air/book/airoffer/reservationworkbench/{id}/offers/buildpaymentoffer"
    
    # Retrieval and Management
    RESERVATION_GET = "/air/reservation/{id}"
    QUEUE_PLACE = "/air/queue/place"
    
    # Exchange and Void/Refund
    EXCHANGE_SEARCH = "/air/exchange/search/catalogproductofferings"
    REFUND_QUOTE = "/air/refund/quote"
    VOID_SINGLE = "/air/ticket/tickets/updatestatus/{id}"
    VOID_BATCH = "/documents/void"
