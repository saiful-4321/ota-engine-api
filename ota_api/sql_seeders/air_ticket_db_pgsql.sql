#============Enums==============#
CREATE TYPE booking_status_enum AS ENUM (
    'PENDING',
    'HOLD',
    'CONFIRMED',
    'TICKETED',
    'CANCELLED',
    'FAILED',
    'EXPIRED'
);

CREATE TYPE payment_status_enum AS ENUM (
    'PENDING',
    'PAID',
    'FAILED',
    'REFUNDED',
    'PARTIAL_REFUND'
);

CREATE TYPE passenger_type_enum AS ENUM (
    'ADT',
    'CHD',
    'INF'
);

CREATE TYPE ticket_status_enum AS ENUM (
    'ISSUED',
    'VOID',
    'REFUNDED',
    'EXCHANGED'
);


#============Flight Search Requests Log============#
CREATE TABLE flight_search_requests_log (
    id               BIGSERIAL    PRIMARY KEY,
    search_id        UUID         NOT NULL UNIQUE,              -- client-facing reference ID
    user_id          UUID,                                       -- NULL for guests
    session_id       VARCHAR(100),                               -- optional frontend session token
    supplier         VARCHAR(20)  NOT NULL DEFAULT 'sabre',      -- GDS supplier key
    trip_type        VARCHAR(20)  NOT NULL,
    cabin_class      VARCHAR(20)  NOT NULL,
    adults           INTEGER      DEFAULT 1,
    children         INTEGER      DEFAULT 0,
    infants          INTEGER      DEFAULT 0,
    origin           VARCHAR(3)   NOT NULL,
    destination      VARCHAR(3)   NOT NULL,
    departure_date   DATE         NOT NULL,
    return_date      DATE,
    currency         VARCHAR(3)   DEFAULT 'USD',
    result_count     INTEGER,    -- number of flights returned
    request_metadata JSONB,      -- {supplier_response_time_ms, api_response_time_ms, ip_address, user_agent, ...}
    status           VARCHAR(20) NOT NULL DEFAULT 'success',     -- 'success' | 'error'
    created_at       TIMESTAMP   DEFAULT NOW()
);

CREATE INDEX idx_fsrl_user_id     ON flight_search_requests_log(user_id);
CREATE INDEX idx_fsrl_supplier    ON flight_search_requests_log(supplier);
CREATE INDEX idx_fsrl_route       ON flight_search_requests_log(origin, destination);
CREATE INDEX idx_fsrl_departure   ON flight_search_requests_log(departure_date);
CREATE INDEX idx_fsrl_created_at  ON flight_search_requests_log(created_at DESC);
CREATE INDEX idx_fsrl_status      ON flight_search_requests_log(status);
#============Flight Search Requests Log============#

#============Search Results============#


#============Bookings============#
CREATE TABLE bookings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    booking_reference VARCHAR(20) UNIQUE NOT NULL,

    user_id UUID NOT NULL,

    supplier_id BIGINT REFERENCES suppliers(id),

    booking_status booking_status_enum NOT NULL DEFAULT 'PENDING',

    payment_status payment_status_enum NOT NULL DEFAULT 'PENDING',

    pnr VARCHAR(20),

    supplier_booking_id VARCHAR(100),

    currency VARCHAR(3) NOT NULL,

    base_fare NUMERIC(12,2) NOT NULL DEFAULT 0,

    tax_amount NUMERIC(12,2) NOT NULL DEFAULT 0,

    service_fee NUMERIC(12,2) NOT NULL DEFAULT 0,

    discount_amount NUMERIC(12,2) NOT NULL DEFAULT 0,

    total_amount NUMERIC(12,2) NOT NULL DEFAULT 0,

    booking_expiry TIMESTAMP,

    issued_at TIMESTAMP,

    created_at TIMESTAMP DEFAULT NOW(),

    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_booking_reference
ON bookings(booking_reference);

CREATE INDEX idx_booking_user
ON bookings(user_id);

CREATE INDEX idx_booking_status
ON bookings(booking_status);

CREATE INDEX idx_booking_created
ON bookings(created_at DESC);

CREATE INDEX idx_booking_supplier
ON bookings(supplier_id);

CREATE INDEX idx_booking_pnr
ON bookings(pnr);
#============Bookings============#

#============Booking Segments============#
CREATE TABLE booking_segments (
    id BIGSERIAL PRIMARY KEY,

    booking_id UUID NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,

    segment_number INTEGER NOT NULL,

    airline_code VARCHAR(2) NOT NULL,

    flight_number VARCHAR(10) NOT NULL,

    origin VARCHAR(3) NOT NULL,

    destination VARCHAR(3) NOT NULL,

    departure_datetime TIMESTAMP NOT NULL,

    arrival_datetime TIMESTAMP NOT NULL,

    booking_class VARCHAR(10),

    cabin_class VARCHAR(20),

    baggage_info TEXT,

    fare_basis VARCHAR(50),

    segment_status VARCHAR(50),

    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_segments_booking
ON booking_segments(booking_id);

CREATE INDEX idx_segments_route
ON booking_segments(origin, destination);

CREATE INDEX idx_segments_departure
ON booking_segments(departure_datetime);

CREATE INDEX idx_segments_airline
ON booking_segments(airline_code);
#============Booking Segments============#

#============Booking Passengers============#
CREATE TABLE booking_passengers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    booking_id UUID NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,

    passenger_type passenger_type_enum NOT NULL,

    title VARCHAR(20),

    first_name VARCHAR(100) NOT NULL,

    last_name VARCHAR(100) NOT NULL,

    gender VARCHAR(10),

    date_of_birth DATE,

    nationality VARCHAR(2),

    passport_number VARCHAR(50),

    passport_expiry DATE,

    issuing_country VARCHAR(2),

    frequent_flyer_number VARCHAR(100),

    email VARCHAR(255),

    phone VARCHAR(50),

    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_passenger_booking
ON booking_passengers(booking_id);

CREATE INDEX idx_passenger_passport
ON booking_passengers(passport_number);

CREATE INDEX idx_passenger_name
ON booking_passengers(last_name, first_name);
#============Booking Passengers============#

#============Booking Tickets============#
CREATE TABLE tickets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    booking_id UUID NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,

    passenger_id UUID NOT NULL REFERENCES booking_passengers(id),

    ticket_number VARCHAR(20) UNIQUE NOT NULL,

    ticket_status ticket_status_enum NOT NULL DEFAULT 'ISSUED',

    validating_carrier VARCHAR(2),

    supplier_ticket_id VARCHAR(100),

    issue_date TIMESTAMP DEFAULT NOW(),

    created_at TIMESTAMP DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_ticket_number
ON tickets(ticket_number);

CREATE INDEX idx_ticket_booking
ON tickets(booking_id);

CREATE INDEX idx_ticket_passenger
ON tickets(passenger_id);
#============Booking Tickets============#

#============Booking Payments============#
CREATE TABLE payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    booking_id UUID NOT NULL REFERENCES bookings(id),

    payment_gateway VARCHAR(50),

    transaction_id VARCHAR(255),

    payment_status payment_status_enum NOT NULL DEFAULT 'PENDING',

    paid_amount NUMERIC(12,2) NOT NULL,

    currency VARCHAR(3) NOT NULL,

    gateway_response JSONB,

    created_at TIMESTAMP DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_payment_transaction
ON payments(transaction_id);

CREATE INDEX idx_payment_booking
ON payments(booking_id);

CREATE INDEX idx_payment_status
ON payments(payment_status);

CREATE INDEX idx_payment_created
ON payments(created_at DESC);
#============Booking Payments============#

#============Booking Refunds============#
CREATE TABLE refunds (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    booking_id UUID NOT NULL REFERENCES bookings(id),

    ticket_id UUID NOT NULL REFERENCES tickets(id),

    refund_status VARCHAR(50),

    refund_amount NUMERIC(12,2),

    airline_penalty NUMERIC(12,2),

    service_charge NUMERIC(12,2),

    supplier_reference VARCHAR(100),

    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_refund_booking
ON refunds(booking_id);

CREATE INDEX idx_refund_ticket
ON refunds(ticket_id);
#============Booking Refunds============#

#============Booking Status History============#
CREATE TABLE booking_status_history (
    id BIGSERIAL PRIMARY KEY,

    booking_id UUID NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,

    old_status booking_status_enum,

    new_status booking_status_enum,

    remarks TEXT,

    changed_by UUID,

    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_booking_history_booking
ON booking_status_history(booking_id);

CREATE INDEX idx_booking_history_created
ON booking_status_history(created_at DESC);
#============Booking Status History============#

#============Supplier Logs============#
CREATE TABLE supplier_logs (
    id BIGSERIAL PRIMARY KEY,

    supplier_id BIGINT REFERENCES suppliers(id),

    endpoint TEXT,

    request_payload JSONB,

    response_payload JSONB,

    response_time_ms INTEGER,

    status_code INTEGER,

    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_supplier_logs_supplier
ON supplier_logs(supplier_id);

CREATE INDEX idx_supplier_logs_created
ON supplier_logs(created_at DESC);
#============Supplier Logs============#