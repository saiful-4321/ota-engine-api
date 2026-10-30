class SabreEndpoints:
    # Authentication
    REST_AUTH_TOKEN = "/v3/auth/token"

    # Search and Pricing
    BARGAIN_FINDER_MAX = "/v5/offers/shop"
    FLIGHT_CHECK = "/v1/offers/flightCheck"
    # Get Seats (seat map + seat prices). Baggage allowance and fare rules of a booked PNR come
    # from GET_PNR_DETAILS; Sabre has no REST fare-rules lookup before booking.
    GET_SEATS = "/v1/offers/getseats"

    # AtBooking and Ticketing
    CREATE_PNR = "/v2.4.0/passenger/records"
    UPDATE_PNR = "/v1.1.0/passenger/records?mode=update"
    ISSUE_TICKET = "/v1.3.0/air/ticket"
    GET_PNR_DETAILS = "/v1/trip/orders/getBooking"
    CANCEL_ITINERARY = "/v1/trip/orders/cancelBooking"
    VOID_TICKET = "/v1/trip/orders/voidFlightTickets"
    EXCHANGE_BOOKING = "/v1.1.0/exchange/booking"
    CHECK_FLIGHT_TICKETS = "/v1/trip/orders/checkFlightTickets"
    REFUND_FLIGHT_TICKETS = "/v1/trip/orders/refundFlightTickets"

    # Queues
    QUEUE_PLACE = "/v1/trip/orders/queue"
