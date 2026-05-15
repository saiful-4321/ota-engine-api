-- ============================================================
-- Air Ticket DB - MySQL Schema
-- Converted from PostgreSQL (air_ticket_db_pgsql.sql)
-- Requires: MySQL 8.0+ (for UUID() defaults and DESC indexes)
-- ============================================================

-- Use utf8mb4 for full Unicode support
SET NAMES utf8mb4;
SET time_zone = '+00:00';


-- ============Suppliers============ --
CREATE TABLE IF NOT EXISTS suppliers (
    id          BIGINT          NOT NULL AUTO_INCREMENT,
    name        VARCHAR(100)    NOT NULL UNIQUE,
    code        VARCHAR(20)     NOT NULL UNIQUE,  -- 'sabre', 'amadeus', etc.
    description VARCHAR(255),
    is_active   TINYINT(1)      NOT NULL DEFAULT 1,
    created_at  TIMESTAMP       NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMP       NOT NULL DEFAULT NOW() ON UPDATE NOW(),
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO suppliers (name, code) VALUES ('Sabre GDS', 'sabre');
-- ============Suppliers============ --


-- ============Flight Search Requests Log============ --
CREATE TABLE flight_search_requests_log (
    id               BIGINT       NOT NULL AUTO_INCREMENT,
    search_id        CHAR(36)     NOT NULL,                   -- client-facing reference ID
    user_id          CHAR(36),                                 -- NULL for guests
    session_id       VARCHAR(100),                             -- optional frontend session token
    supplier         VARCHAR(20)  NOT NULL DEFAULT 'sabre',    -- GDS supplier key
    trip_type        VARCHAR(20)  NOT NULL,
    cabin_class      VARCHAR(20)  NOT NULL,
    adults           INT          NOT NULL DEFAULT 1,
    children         INT          NOT NULL DEFAULT 0,
    infants          INT          NOT NULL DEFAULT 0,
    origin           VARCHAR(3)   NOT NULL,
    destination      VARCHAR(3)   NOT NULL,
    departure_date   DATE         NOT NULL,
    return_date      DATE,
    currency         VARCHAR(3)   NOT NULL DEFAULT 'BDT',
    result_count     INT,    -- number of flights returned
    request_metadata JSON,   -- {supplier_response_time_ms, api_response_time_ms, ip_address, user_agent, ...}
    status           VARCHAR(20) NOT NULL DEFAULT 'success',   -- 'success' | 'error'
    created_at       TIMESTAMP    NOT NULL DEFAULT NOW(),

    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE UNIQUE INDEX idx_fsrl_search_id    ON flight_search_requests_log (search_id);
CREATE INDEX idx_fsrl_user_id            ON flight_search_requests_log (user_id);
CREATE INDEX idx_fsrl_supplier           ON flight_search_requests_log (supplier);
CREATE INDEX idx_fsrl_route              ON flight_search_requests_log (origin, destination);
CREATE INDEX idx_fsrl_departure          ON flight_search_requests_log (departure_date);
CREATE INDEX idx_fsrl_created_at         ON flight_search_requests_log (created_at DESC);
CREATE INDEX idx_fsrl_status             ON flight_search_requests_log (status);
-- ============Flight Search Requests Log============ --


-- ============Search Results============ --
-- (Reserved for future use, mirroring the PostgreSQL file)
-- ============Search Results============ --


-- ============Bookings============ --
CREATE TABLE bookings (
    id                  CHAR(36)        NOT NULL DEFAULT (UUID()),
    booking_reference   VARCHAR(20)     NOT NULL,
    user_id             CHAR(36)        NOT NULL,
    supplier_id         BIGINT,
    booking_status      ENUM(
                            'PENDING',
                            'HOLD',
                            'CONFIRMED',
                            'TICKETED',
                            'CANCELLED',
                            'FAILED',
                            'EXPIRED'
                        )               NOT NULL DEFAULT 'PENDING',
    payment_status      ENUM(
                            'PENDING',
                            'PAID',
                            'FAILED',
                            'REFUNDED',
                            'PARTIAL_REFUND'
                        )               NOT NULL DEFAULT 'PENDING',
    pnr                 VARCHAR(20),
    supplier_booking_id VARCHAR(100),
    currency            VARCHAR(3)      NOT NULL,
    base_fare           DECIMAL(12,2)   NOT NULL DEFAULT 0.00,
    tax_amount          DECIMAL(12,2)   NOT NULL DEFAULT 0.00,
    service_fee         DECIMAL(12,2)   NOT NULL DEFAULT 0.00,
    discount_amount     DECIMAL(12,2)   NOT NULL DEFAULT 0.00,
    total_amount        DECIMAL(12,2)   NOT NULL DEFAULT 0.00,
    booking_expiry      TIMESTAMP       NULL DEFAULT NULL,
    issued_at           TIMESTAMP       NULL DEFAULT NULL,
    created_at          TIMESTAMP       NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP       NOT NULL DEFAULT NOW() ON UPDATE NOW(),

    PRIMARY KEY (id),
    UNIQUE KEY idx_booking_reference (booking_reference),

    CONSTRAINT fk_bookings_supplier
        FOREIGN KEY (supplier_id) REFERENCES suppliers (id)
        ON DELETE SET NULL
        ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_booking_user     ON bookings (user_id);
CREATE INDEX idx_booking_status   ON bookings (booking_status);
CREATE INDEX idx_booking_created  ON bookings (created_at DESC);
CREATE INDEX idx_booking_supplier ON bookings (supplier_id);
CREATE INDEX idx_booking_pnr      ON bookings (pnr);
-- ============Bookings============ --


-- ============Booking Segments============ --
CREATE TABLE booking_segments (
    id                  BIGINT          NOT NULL AUTO_INCREMENT,
    booking_id          CHAR(36)        NOT NULL,
    segment_number      INT             NOT NULL,
    airline_code        VARCHAR(2)      NOT NULL,
    flight_number       VARCHAR(10)     NOT NULL,
    origin              VARCHAR(3)      NOT NULL,
    destination         VARCHAR(3)      NOT NULL,
    departure_datetime  TIMESTAMP       NOT NULL,
    arrival_datetime    TIMESTAMP       NOT NULL,
    booking_class       VARCHAR(10),
    cabin_class         VARCHAR(20),
    baggage_info        TEXT,
    fare_basis          VARCHAR(50),
    segment_status      VARCHAR(50),
    created_at          TIMESTAMP       NOT NULL DEFAULT NOW(),

    PRIMARY KEY (id),

    CONSTRAINT fk_segments_booking
        FOREIGN KEY (booking_id) REFERENCES bookings (id)
        ON DELETE CASCADE
        ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_segments_booking   ON booking_segments (booking_id);
CREATE INDEX idx_segments_route     ON booking_segments (origin, destination);
CREATE INDEX idx_segments_departure ON booking_segments (departure_datetime);
CREATE INDEX idx_segments_airline   ON booking_segments (airline_code);
-- ============Booking Segments============ --


-- ============Booking Passengers============ --
CREATE TABLE booking_passengers (
    id                      CHAR(36)    NOT NULL DEFAULT (UUID()),
    booking_id              CHAR(36)    NOT NULL,
    passenger_type          ENUM('ADT', 'CHD', 'INF') NOT NULL,
    title                   VARCHAR(20),
    first_name              VARCHAR(100) NOT NULL,
    last_name               VARCHAR(100) NOT NULL,
    gender                  VARCHAR(10),
    date_of_birth           DATE,
    nationality             VARCHAR(2),
    passport_number         VARCHAR(50),
    passport_expiry         DATE,
    issuing_country         VARCHAR(2),
    frequent_flyer_number   VARCHAR(100),
    email                   VARCHAR(255),
    phone                   VARCHAR(50),
    created_at              TIMESTAMP   NOT NULL DEFAULT NOW(),

    PRIMARY KEY (id),

    CONSTRAINT fk_passengers_booking
        FOREIGN KEY (booking_id) REFERENCES bookings (id)
        ON DELETE CASCADE
        ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_passenger_booking  ON booking_passengers (booking_id);
CREATE INDEX idx_passenger_passport ON booking_passengers (passport_number);
CREATE INDEX idx_passenger_name     ON booking_passengers (last_name, first_name);
-- ============Booking Passengers============ --


-- ============Booking Tickets============ --
CREATE TABLE tickets (
    id                  CHAR(36)    NOT NULL DEFAULT (UUID()),
    booking_id          CHAR(36)    NOT NULL,
    passenger_id        CHAR(36)    NOT NULL,
    ticket_number       VARCHAR(20) NOT NULL,
    ticket_status       ENUM(
                            'ISSUED',
                            'VOID',
                            'REFUNDED',
                            'EXCHANGED'
                        )           NOT NULL DEFAULT 'ISSUED',
    validating_carrier  VARCHAR(2),
    supplier_ticket_id  VARCHAR(100),
    issue_date          TIMESTAMP   NOT NULL DEFAULT NOW(),
    created_at          TIMESTAMP   NOT NULL DEFAULT NOW(),

    PRIMARY KEY (id),
    UNIQUE KEY idx_ticket_number (ticket_number),

    CONSTRAINT fk_tickets_booking
        FOREIGN KEY (booking_id) REFERENCES bookings (id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    CONSTRAINT fk_tickets_passenger
        FOREIGN KEY (passenger_id) REFERENCES booking_passengers (id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_ticket_booking   ON tickets (booking_id);
CREATE INDEX idx_ticket_passenger ON tickets (passenger_id);
-- ============Booking Tickets============ --


-- ============Booking Payments============ --
CREATE TABLE payments (
    id               CHAR(36)      NOT NULL DEFAULT (UUID()),
    booking_id       CHAR(36)      NOT NULL,
    payment_gateway  VARCHAR(50),
    transaction_id   VARCHAR(255),
    payment_status   ENUM(
                         'PENDING',
                         'PAID',
                         'FAILED',
                         'REFUNDED',
                         'PARTIAL_REFUND'
                     )             NOT NULL DEFAULT 'PENDING',
    paid_amount      DECIMAL(12,2) NOT NULL,
    currency         VARCHAR(3)    NOT NULL,
    gateway_response JSON,
    created_at       TIMESTAMP     NOT NULL DEFAULT NOW(),

    PRIMARY KEY (id),
    UNIQUE KEY idx_payment_transaction (transaction_id),

    CONSTRAINT fk_payments_booking
        FOREIGN KEY (booking_id) REFERENCES bookings (id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_payment_booking ON payments (booking_id);
CREATE INDEX idx_payment_status  ON payments (payment_status);
CREATE INDEX idx_payment_created ON payments (created_at DESC);
-- ============Booking Payments============ --


-- ============Booking Refunds============ --
CREATE TABLE refunds (
    id                  CHAR(36)      NOT NULL DEFAULT (UUID()),
    booking_id          CHAR(36)      NOT NULL,
    ticket_id           CHAR(36)      NOT NULL,
    refund_status       VARCHAR(50),
    refund_amount       DECIMAL(12,2),
    airline_penalty     DECIMAL(12,2),
    service_charge      DECIMAL(12,2),
    supplier_reference  VARCHAR(100),
    created_at          TIMESTAMP     NOT NULL DEFAULT NOW(),

    PRIMARY KEY (id),

    CONSTRAINT fk_refunds_booking
        FOREIGN KEY (booking_id) REFERENCES bookings (id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE,

    CONSTRAINT fk_refunds_ticket
        FOREIGN KEY (ticket_id) REFERENCES tickets (id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_refund_booking ON refunds (booking_id);
CREATE INDEX idx_refund_ticket  ON refunds (ticket_id);
-- ============Booking Refunds============ --


-- ============Booking Status History============ --
CREATE TABLE booking_status_history (
    id          BIGINT  NOT NULL AUTO_INCREMENT,
    booking_id  CHAR(36) NOT NULL,
    old_status  ENUM(
                    'PENDING',
                    'HOLD',
                    'CONFIRMED',
                    'TICKETED',
                    'CANCELLED',
                    'FAILED',
                    'EXPIRED'
                ),
    new_status  ENUM(
                    'PENDING',
                    'HOLD',
                    'CONFIRMED',
                    'TICKETED',
                    'CANCELLED',
                    'FAILED',
                    'EXPIRED'
                ),
    remarks     TEXT,
    changed_by  CHAR(36),
    created_at  TIMESTAMP NOT NULL DEFAULT NOW(),

    PRIMARY KEY (id),

    CONSTRAINT fk_status_history_booking
        FOREIGN KEY (booking_id) REFERENCES bookings (id)
        ON DELETE CASCADE
        ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_booking_history_booking ON booking_status_history (booking_id);
CREATE INDEX idx_booking_history_created ON booking_status_history (created_at DESC);
-- ============Booking Status History============ --


-- ============Supplier Logs============ --
CREATE TABLE supplier_logs (
    id                  BIGINT  NOT NULL AUTO_INCREMENT,
    supplier_id         BIGINT,
    endpoint            TEXT,
    request_payload     JSON,
    response_payload    JSON,
    response_time_ms    INT,
    status_code         INT,
    created_at          TIMESTAMP NOT NULL DEFAULT NOW(),

    PRIMARY KEY (id),

    CONSTRAINT fk_supplier_logs_supplier
        FOREIGN KEY (supplier_id) REFERENCES suppliers (id)
        ON DELETE SET NULL
        ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_supplier_logs_supplier ON supplier_logs (supplier_id);
CREATE INDEX idx_supplier_logs_created  ON supplier_logs (created_at DESC);
-- ============Supplier Logs============ --
