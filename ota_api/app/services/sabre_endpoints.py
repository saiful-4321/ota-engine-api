class SabreEndpoints:
    # Authentication
    REST_AUTH_TOKEN = "/v3/auth/token"

    # Search and Pricing
    BARGAIN_FINDER_MAX = "/v5/offers/shop"
    FLIGHT_CHECK = "/v1/offers/flightCheck"
    SEAT_MAP = "/v3/offers/seatmap"
    BAGGAGE_ALLOWANCE = "/v4/offers/baggage"
    STRUCTURE_FARE_RULES = "/v1/offers/fareRules"

    # AtBooking and Ticketing
    CREATE_PNR = "/v2.4.0/passenger/records"
    ISSUE_TICKET = "/v1.3.0/air/ticket"
    GET_PNR_DETAILS = "/v1/trip/orders/getBooking"
    CANCEL_ITINERARY = "/v1/trip/orders/cancelBooking"
    VOID_TICKET = "/v1/trip/orders/voidFlightTickets"
    EXCHANGE_TICKET = "/v1.3.0/air/ticket"

    # Queues
    QUEUE_PLACE = "/v1/trip/orders/queue"
