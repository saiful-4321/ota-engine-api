class TravelportEndpoints:
    # Auth
    AUTH_TOKEN = "/oauth/token"
    
    # Search and Price
    CATALOG_SEARCH = "/air/catalog/search/catalogproductofferings"
    CATALOG_PRICE = "/air/catalog/price/catalogproductofferings"
    FARE_RULES = "/air/catalog/farerule"
    SEAT_MAP = "/air/catalog/search/seatmap"
    ANCILLARY_SHOP = "/air/catalog/search/ancillaryofferings"
    
    # Workbench / Booking
    WORKBENCH_CREATE = "/air/book/airoffer/reservationworkbench"
    WORKBENCH_OFFERS = "/air/book/airoffer/reservationworkbench/{id}/offers/build"
    WORKBENCH_TRAVELERS = "/air/book/traveler/reservationworkbench/{id}/travelers"
    WORKBENCH_REMARKS = "/air/book/remarks/reservationworkbench/{id}/reservationcomments/list"
    WORKBENCH_COMMIT = "/air/book/airoffer/reservationworkbench/{id}/commit"
    
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
