-- ============================================================
-- OTA Domain Model v2 — Migration Script
-- Non-destructive: ADD only (no DROP column / DROP table)
-- Requires: MySQL 8.0+
-- Run against the OTA database AFTER the existing schema is in place.
-- ============================================================

SET NAMES utf8mb4;
SET time_zone = '+00:00';


-- ============================================================
-- 1. ALTER suppliers — add supplier_type
-- ============================================================
ALTER TABLE suppliers
    ADD COLUMN IF NOT EXISTS supplier_type VARCHAR(20) DEFAULT 'GDS' AFTER description;
    -- Values: GDS | NDC | DIRECT | CONSOLIDATOR


-- ============================================================
-- 2. ALTER at_bookings — add journey_type, primary_pnr
-- ============================================================
ALTER TABLE at_bookings
    ADD COLUMN IF NOT EXISTS journey_type VARCHAR(20) DEFAULT NULL AFTER status,
    ADD COLUMN IF NOT EXISTS primary_pnr  VARCHAR(10) DEFAULT NULL AFTER supplier_booking_id;

-- Index on primary_pnr if not already present
CREATE INDEX IF NOT EXISTS idx_at_bookings_primary_pnr ON at_bookings (primary_pnr);


-- ============================================================
-- 3. NEW TABLE: at_booking_journeys
-- ============================================================
CREATE TABLE IF NOT EXISTS at_booking_journeys (
    id                  BIGINT          NOT NULL AUTO_INCREMENT,
    booking_id          BIGINT          NOT NULL,
    journey_sequence    INT             NOT NULL DEFAULT 1,
    direction           VARCHAR(10)     DEFAULT NULL,        -- OUTBOUND | INBOUND | NULL (multi-city)
    origin              CHAR(3)         NOT NULL,
    destination         CHAR(3)         NOT NULL,
    departure_date      DATE            NOT NULL,
    created_at          TIMESTAMP       NOT NULL DEFAULT NOW(),

    PRIMARY KEY (id),

    UNIQUE KEY uq_journey_booking_seq (booking_id, journey_sequence),

    CONSTRAINT fk_journeys_booking
        FOREIGN KEY (booking_id) REFERENCES at_bookings (id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX IF NOT EXISTS idx_journeys_booking  ON at_booking_journeys (booking_id);
CREATE INDEX IF NOT EXISTS idx_journeys_origin   ON at_booking_journeys (origin);
CREATE INDEX IF NOT EXISTS idx_journeys_dest     ON at_booking_journeys (destination);


-- ============================================================
-- 4. ALTER at_booking_segments — add journey_id FK
-- ============================================================
ALTER TABLE at_booking_segments
    ADD COLUMN IF NOT EXISTS journey_id BIGINT DEFAULT NULL AFTER booking_id;

-- FK to journeys (nullable for backward compat during migration)
-- Only add if not exists — MySQL doesn't have IF NOT EXISTS for constraints,
-- so we wrap in a procedure.
DELIMITER //
CREATE PROCEDURE add_fk_if_not_exists()
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.TABLE_CONSTRAINTS
        WHERE CONSTRAINT_SCHEMA = DATABASE()
          AND TABLE_NAME = 'at_booking_segments'
          AND CONSTRAINT_NAME = 'fk_segments_journey'
    ) THEN
        ALTER TABLE at_booking_segments
            ADD CONSTRAINT fk_segments_journey
            FOREIGN KEY (journey_id) REFERENCES at_booking_journeys (id)
            ON DELETE CASCADE ON UPDATE CASCADE;
    END IF;
END //
DELIMITER ;
CALL add_fk_if_not_exists();
DROP PROCEDURE IF EXISTS add_fk_if_not_exists;

CREATE INDEX IF NOT EXISTS idx_segments_journey ON at_booking_segments (journey_id);


-- ============================================================
-- 5. ALTER at_booking_passengers — add INS support, clean naming
-- ============================================================
-- The `type` column already allows ADT/CHD/INF as VARCHAR(10).
-- Widen it to safely hold 'INS' (already fits). No ALTER needed for values.
-- Add is_lead if not present
ALTER TABLE at_booking_passengers
    ADD COLUMN IF NOT EXISTS passport_issuing_country CHAR(2) DEFAULT NULL AFTER passport_expiry;


-- ============================================================
-- 6. ALTER at_flight_tickets — add original_ticket_id, voided_at, exchanged_at
-- ============================================================
ALTER TABLE at_flight_tickets
    ADD COLUMN IF NOT EXISTS original_ticket_id BIGINT DEFAULT NULL AFTER status,
    ADD COLUMN IF NOT EXISTS voided_at          TIMESTAMP NULL DEFAULT NULL AFTER issued_at,
    ADD COLUMN IF NOT EXISTS exchanged_at       TIMESTAMP NULL DEFAULT NULL AFTER voided_at;

-- Self-referencing FK for reissued tickets
DELIMITER //
CREATE PROCEDURE add_fk_ticket_original()
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.TABLE_CONSTRAINTS
        WHERE CONSTRAINT_SCHEMA = DATABASE()
          AND TABLE_NAME = 'at_flight_tickets'
          AND CONSTRAINT_NAME = 'fk_ticket_original'
    ) THEN
        ALTER TABLE at_flight_tickets
            ADD CONSTRAINT fk_ticket_original
            FOREIGN KEY (original_ticket_id) REFERENCES at_flight_tickets (id)
            ON DELETE SET NULL ON UPDATE CASCADE;
    END IF;
END //
DELIMITER ;
CALL add_fk_ticket_original();
DROP PROCEDURE IF EXISTS add_fk_ticket_original;

CREATE INDEX IF NOT EXISTS idx_ticket_original ON at_flight_tickets (original_ticket_id);


-- ============================================================
-- 7. NEW TABLE: at_ticket_coupons
-- ============================================================
CREATE TABLE IF NOT EXISTS at_ticket_coupons (
    id              BIGINT      NOT NULL AUTO_INCREMENT,
    ticket_id       BIGINT      NOT NULL,
    segment_id      BIGINT      DEFAULT NULL,
    coupon_number   INT         NOT NULL,                   -- 1–4 per IATA
    coupon_status   VARCHAR(20) NOT NULL DEFAULT 'OPEN',    -- OPEN|USED|VOID|REFUNDED|EXCHANGED|AIRPORT_CONTROL|SUSPENDED
    not_valid_before DATE       DEFAULT NULL,
    not_valid_after  DATE       DEFAULT NULL,
    created_at      TIMESTAMP   NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP   NOT NULL DEFAULT NOW() ON UPDATE NOW(),

    PRIMARY KEY (id),

    UNIQUE KEY uq_coupon_ticket_num (ticket_id, coupon_number),

    CONSTRAINT fk_coupons_ticket
        FOREIGN KEY (ticket_id) REFERENCES at_flight_tickets (id)
        ON DELETE CASCADE ON UPDATE CASCADE,

    CONSTRAINT fk_coupons_segment
        FOREIGN KEY (segment_id) REFERENCES at_booking_segments (id)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX IF NOT EXISTS idx_coupons_ticket  ON at_ticket_coupons (ticket_id);
CREATE INDEX IF NOT EXISTS idx_coupons_segment ON at_ticket_coupons (segment_id);
CREATE INDEX IF NOT EXISTS idx_coupons_status  ON at_ticket_coupons (coupon_status);


-- ============================================================
-- 8. ALTER at_pricing_snapshots — add search_currency, conversion_rate, commission_total
-- ============================================================
ALTER TABLE at_pricing_snapshots
    ADD COLUMN IF NOT EXISTS search_currency   CHAR(3)        DEFAULT NULL AFTER base_currency,
    ADD COLUMN IF NOT EXISTS conversion_rate   DECIMAL(18,6)  DEFAULT 1.000000 AFTER search_currency,
    ADD COLUMN IF NOT EXISTS commission_total  DECIMAL(16,4)  NOT NULL DEFAULT 0.0000 AFTER customer_total;


-- ============================================================
-- 9. ALTER at_pricing_components — add component_subtype, description, is_refundable, journey_id
-- ============================================================
ALTER TABLE at_pricing_components
    ADD COLUMN IF NOT EXISTS component_subtype VARCHAR(30) DEFAULT NULL AFTER component_type,
    ADD COLUMN IF NOT EXISTS description       VARCHAR(255) DEFAULT NULL AFTER currency_code,
    ADD COLUMN IF NOT EXISTS is_refundable     TINYINT(1) DEFAULT 1 AFTER description,
    ADD COLUMN IF NOT EXISTS journey_id        BIGINT DEFAULT NULL AFTER segment_id;

-- FK to journeys
DELIMITER //
CREATE PROCEDURE add_fk_component_journey()
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.TABLE_CONSTRAINTS
        WHERE CONSTRAINT_SCHEMA = DATABASE()
          AND TABLE_NAME = 'at_pricing_components'
          AND CONSTRAINT_NAME = 'fk_component_journey'
    ) THEN
        ALTER TABLE at_pricing_components
            ADD CONSTRAINT fk_component_journey
            FOREIGN KEY (journey_id) REFERENCES at_booking_journeys (id)
            ON DELETE SET NULL ON UPDATE CASCADE;
    END IF;
END //
DELIMITER ;
CALL add_fk_component_journey();
DROP PROCEDURE IF EXISTS add_fk_component_journey;

CREATE INDEX IF NOT EXISTS idx_component_journey ON at_pricing_components (journey_id);
CREATE INDEX IF NOT EXISTS idx_component_type    ON at_pricing_components (pricing_snapshot_id, component_type);
CREATE INDEX IF NOT EXISTS idx_component_pax     ON at_pricing_components (pricing_snapshot_id, passenger_id);


-- ============================================================
-- 10. NEW TABLE: at_ancillaries
-- ============================================================
CREATE TABLE IF NOT EXISTS at_ancillaries (
    id                  BIGINT          NOT NULL AUTO_INCREMENT,
    uuid                CHAR(36)        NOT NULL,
    booking_id          BIGINT          NOT NULL,
    passenger_id        BIGINT          DEFAULT NULL,
    segment_id          BIGINT          DEFAULT NULL,
    ancillary_type      VARCHAR(30)     NOT NULL,            -- SEAT|BAGGAGE|MEAL|LOUNGE|INSURANCE|OTHER
    description         VARCHAR(255)    DEFAULT NULL,
    quantity            INT             NOT NULL DEFAULT 1,
    status              VARCHAR(20)     NOT NULL DEFAULT 'CONFIRMED',  -- REQUESTED|CONFIRMED|CANCELLED|REFUNDED
    supplier_reference  VARCHAR(100)    DEFAULT NULL,
    amount              DECIMAL(16,4)   NOT NULL DEFAULT 0.0000,
    currency_code       CHAR(3)         NOT NULL DEFAULT 'BDT',
    created_at          TIMESTAMP       NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP       NOT NULL DEFAULT NOW() ON UPDATE NOW(),

    PRIMARY KEY (id),

    UNIQUE KEY idx_ancillary_uuid (uuid),

    CONSTRAINT fk_ancillaries_booking
        FOREIGN KEY (booking_id) REFERENCES at_bookings (id)
        ON DELETE CASCADE ON UPDATE CASCADE,

    CONSTRAINT fk_ancillaries_passenger
        FOREIGN KEY (passenger_id) REFERENCES at_booking_passengers (id)
        ON DELETE SET NULL ON UPDATE CASCADE,

    CONSTRAINT fk_ancillaries_segment
        FOREIGN KEY (segment_id) REFERENCES at_booking_segments (id)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX IF NOT EXISTS idx_ancillaries_booking  ON at_ancillaries (booking_id);
CREATE INDEX IF NOT EXISTS idx_ancillaries_pax      ON at_ancillaries (passenger_id);
CREATE INDEX IF NOT EXISTS idx_ancillaries_type     ON at_ancillaries (ancillary_type);


-- ============================================================
-- 11. ALTER at_refunds — add refund_type, totals, completed_at
-- ============================================================
ALTER TABLE at_refunds
    ADD COLUMN IF NOT EXISTS refund_type         VARCHAR(20) DEFAULT 'VOLUNTARY' AFTER `type`,
    ADD COLUMN IF NOT EXISTS total_refund_amount DECIMAL(16,4) DEFAULT NULL AFTER status,
    ADD COLUMN IF NOT EXISTS total_penalty       DECIMAL(16,4) DEFAULT 0.0000 AFTER total_refund_amount,
    ADD COLUMN IF NOT EXISTS completed_at        TIMESTAMP NULL DEFAULT NULL AFTER supplier_reference;


-- ============================================================
-- 12. NEW TABLE: at_refund_items
-- ============================================================
CREATE TABLE IF NOT EXISTS at_refund_items (
    id              BIGINT          NOT NULL AUTO_INCREMENT,
    refund_id       BIGINT          NOT NULL,
    ticket_id       BIGINT          DEFAULT NULL,
    coupon_id       BIGINT          DEFAULT NULL,
    refund_amount   DECIMAL(16,4)   NOT NULL DEFAULT 0.0000,
    penalty_amount  DECIMAL(16,4)   NOT NULL DEFAULT 0.0000,
    tax_refund_amount DECIMAL(16,4) NOT NULL DEFAULT 0.0000,
    created_at      TIMESTAMP       NOT NULL DEFAULT NOW(),

    PRIMARY KEY (id),

    CONSTRAINT fk_refund_items_refund
        FOREIGN KEY (refund_id) REFERENCES at_refunds (id)
        ON DELETE CASCADE ON UPDATE CASCADE,

    CONSTRAINT fk_refund_items_ticket
        FOREIGN KEY (ticket_id) REFERENCES at_flight_tickets (id)
        ON DELETE SET NULL ON UPDATE CASCADE,

    CONSTRAINT fk_refund_items_coupon
        FOREIGN KEY (coupon_id) REFERENCES at_ticket_coupons (id)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX IF NOT EXISTS idx_refund_items_refund ON at_refund_items (refund_id);
CREATE INDEX IF NOT EXISTS idx_refund_items_ticket ON at_refund_items (ticket_id);


-- ============================================================
-- 13. ALTER at_flight_reissues — add original_ticket_id, fare/penalty/tax diff
-- ============================================================
ALTER TABLE at_flight_reissues
    ADD COLUMN IF NOT EXISTS original_ticket_id BIGINT DEFAULT NULL AFTER booking_id,
    ADD COLUMN IF NOT EXISTS fare_difference    DECIMAL(16,4) DEFAULT NULL AFTER status,
    ADD COLUMN IF NOT EXISTS change_penalty     DECIMAL(16,4) DEFAULT 0.0000 AFTER fare_difference,
    ADD COLUMN IF NOT EXISTS tax_difference     DECIMAL(16,4) DEFAULT 0.0000 AFTER change_penalty,
    ADD COLUMN IF NOT EXISTS supplier_reference VARCHAR(100) DEFAULT NULL AFTER tax_difference,
    ADD COLUMN IF NOT EXISTS actioned_by        BIGINT DEFAULT NULL AFTER supplier_reference;

-- FK for original_ticket_id
DELIMITER //
CREATE PROCEDURE add_fk_reissue_original_ticket()
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.TABLE_CONSTRAINTS
        WHERE CONSTRAINT_SCHEMA = DATABASE()
          AND TABLE_NAME = 'at_flight_reissues'
          AND CONSTRAINT_NAME = 'fk_reissue_original_ticket'
    ) THEN
        ALTER TABLE at_flight_reissues
            ADD CONSTRAINT fk_reissue_original_ticket
            FOREIGN KEY (original_ticket_id) REFERENCES at_flight_tickets (id)
            ON DELETE SET NULL ON UPDATE CASCADE;
    END IF;
END //
DELIMITER ;
CALL add_fk_reissue_original_ticket();
DROP PROCEDURE IF EXISTS add_fk_reissue_original_ticket;

ALTER TABLE at_flight_reissues
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT NOW() ON UPDATE NOW();


-- ============================================================
-- 14. ALTER payments — add payment_type, payment_method, refund_id, settled_at
-- ============================================================
ALTER TABLE payments
    ADD COLUMN IF NOT EXISTS payment_type   VARCHAR(20)   DEFAULT 'COLLECTION' AFTER booking_id,
    ADD COLUMN IF NOT EXISTS payment_method VARCHAR(50)   DEFAULT NULL AFTER payment_type,
    ADD COLUMN IF NOT EXISTS refund_id      BIGINT        DEFAULT NULL AFTER payment_method,
    ADD COLUMN IF NOT EXISTS settled_at     TIMESTAMP     NULL DEFAULT NULL AFTER gateway_response,
    ADD COLUMN IF NOT EXISTS updated_at     TIMESTAMP     NOT NULL DEFAULT NOW() ON UPDATE NOW() AFTER created_at;

-- FK to refunds
DELIMITER //
CREATE PROCEDURE add_fk_payment_refund()
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.TABLE_CONSTRAINTS
        WHERE CONSTRAINT_SCHEMA = DATABASE()
          AND TABLE_NAME = 'payments'
          AND CONSTRAINT_NAME = 'fk_payment_refund'
    ) THEN
        ALTER TABLE payments
            ADD CONSTRAINT fk_payment_refund
            FOREIGN KEY (refund_id) REFERENCES at_refunds (id)
            ON DELETE SET NULL ON UPDATE CASCADE;
    END IF;
END //
DELIMITER ;
CALL add_fk_payment_refund();
DROP PROCEDURE IF EXISTS add_fk_payment_refund;

CREATE INDEX IF NOT EXISTS idx_payment_refund ON payments (refund_id);


-- ============================================================
-- 15. ALTER supplier_transactions — add supplier-specific fields
-- ============================================================
ALTER TABLE supplier_transactions
    ADD COLUMN IF NOT EXISTS supplier_order_id    VARCHAR(100)  DEFAULT NULL AFTER supplier_booking_ref,
    ADD COLUMN IF NOT EXISTS pcc                  VARCHAR(20)   DEFAULT NULL AFTER supplier_order_id,
    ADD COLUMN IF NOT EXISTS office_id            VARCHAR(50)   DEFAULT NULL AFTER pcc,
    ADD COLUMN IF NOT EXISTS gds_source           VARCHAR(10)   DEFAULT NULL AFTER office_id,
    ADD COLUMN IF NOT EXISTS http_status_code     INT           DEFAULT NULL AFTER gds_source,
    ADD COLUMN IF NOT EXISTS response_time_ms     INT           DEFAULT NULL AFTER http_status_code,
    ADD COLUMN IF NOT EXISTS supplier_metadata    JSON          DEFAULT NULL AFTER res_payload_uri,
    ADD COLUMN IF NOT EXISTS error_message        TEXT          DEFAULT NULL AFTER supplier_metadata;

CREATE INDEX IF NOT EXISTS idx_stxn_booking_op ON supplier_transactions (booking_id, operation);
CREATE INDEX IF NOT EXISTS idx_stxn_ref        ON supplier_transactions (supplier_booking_ref);


-- ============================================================
-- 16. NEW TABLE: at_audit_events
-- ============================================================
CREATE TABLE IF NOT EXISTS at_audit_events (
    id              BIGINT          NOT NULL AUTO_INCREMENT,
    booking_id      BIGINT          NOT NULL,
    event_type      VARCHAR(50)     NOT NULL,                -- STATUS_CHANGE|PRICE_CHANGE|PAYMENT|REFUND|REISSUE|TICKET_ISSUED|TICKET_VOIDED|SUPPLIER_CALLBACK|USER_ACTION|SYSTEM
    old_value       VARCHAR(255)    DEFAULT NULL,
    new_value       VARCHAR(255)    DEFAULT NULL,
    details         JSON            DEFAULT NULL,
    actor_type      VARCHAR(20)     DEFAULT NULL,            -- USER|SYSTEM|SUPPLIER|SCHEDULER
    actor_id        VARCHAR(50)     DEFAULT NULL,
    ip_address      VARCHAR(45)     DEFAULT NULL,
    created_at      TIMESTAMP       NOT NULL DEFAULT NOW(),

    PRIMARY KEY (id),

    CONSTRAINT fk_audit_booking
        FOREIGN KEY (booking_id) REFERENCES at_bookings (id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX IF NOT EXISTS idx_audit_booking     ON at_audit_events (booking_id);
CREATE INDEX IF NOT EXISTS idx_audit_type        ON at_audit_events (booking_id, event_type);
CREATE INDEX IF NOT EXISTS idx_audit_created     ON at_audit_events (booking_id, created_at);


-- ============================================================
-- DONE. All changes are additive. No data loss.
-- ============================================================

-- ============================================================
-- 17. ALTER financial columns for precision & traceability
-- ============================================================
-- Increase precision across the board
ALTER TABLE at_pricing_snapshots
    MODIFY COLUMN conversion_rate DECIMAL(18,6) DEFAULT 1.000000,
    MODIFY COLUMN supplier_total DECIMAL(18,4) NOT NULL DEFAULT 0.0000,
    MODIFY COLUMN customer_total DECIMAL(18,4) NOT NULL DEFAULT 0.0000,
    MODIFY COLUMN commission_total DECIMAL(18,4) NOT NULL DEFAULT 0.0000;

ALTER TABLE at_pricing_components
    MODIFY COLUMN amount DECIMAL(18,4) NOT NULL DEFAULT 0.0000,
    MODIFY COLUMN original_amount DECIMAL(18,4) DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS code VARCHAR(20) DEFAULT NULL AFTER component_subtype,
    ADD COLUMN IF NOT EXISTS source VARCHAR(50) DEFAULT NULL AFTER direction,
    ADD COLUMN IF NOT EXISTS original_currency CHAR(3) DEFAULT NULL AFTER original_amount,
    ADD COLUMN IF NOT EXISTS exchange_rate DECIMAL(18,6) DEFAULT 1.000000 AFTER original_currency,
    ADD COLUMN IF NOT EXISTS converted_amount DECIMAL(18,4) DEFAULT NULL AFTER exchange_rate,
    ADD COLUMN IF NOT EXISTS converted_currency CHAR(3) DEFAULT 'BDT' AFTER converted_amount,
    ADD COLUMN IF NOT EXISTS quantity INT DEFAULT 1 AFTER converted_currency,
    ADD COLUMN IF NOT EXISTS percentage DECIMAL(8,4) DEFAULT NULL AFTER quantity,
    ADD COLUMN IF NOT EXISTS calculation_basis DECIMAL(18,4) DEFAULT NULL AFTER percentage,
    ADD COLUMN IF NOT EXISTS supplier_id BIGINT DEFAULT NULL AFTER calculation_basis,
    ADD COLUMN IF NOT EXISTS ticket_id BIGINT DEFAULT NULL AFTER supplier_id;

-- Add FKs for supplier_id and ticket_id on at_pricing_components
DELIMITER //
CREATE PROCEDURE add_fk_component_supplier_ticket()
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.TABLE_CONSTRAINTS
        WHERE CONSTRAINT_SCHEMA = DATABASE()
          AND TABLE_NAME = 'at_pricing_components'
          AND CONSTRAINT_NAME = 'fk_component_supplier'
    ) THEN
        ALTER TABLE at_pricing_components
            ADD CONSTRAINT fk_component_supplier FOREIGN KEY (supplier_id) REFERENCES suppliers (id) ON DELETE SET NULL ON UPDATE CASCADE;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.TABLE_CONSTRAINTS
        WHERE CONSTRAINT_SCHEMA = DATABASE()
          AND TABLE_NAME = 'at_pricing_components'
          AND CONSTRAINT_NAME = 'fk_component_ticket'
    ) THEN
        ALTER TABLE at_pricing_components
            ADD CONSTRAINT fk_component_ticket FOREIGN KEY (ticket_id) REFERENCES at_flight_tickets (id) ON DELETE SET NULL ON UPDATE CASCADE;
    END IF;
END //
DELIMITER ;
CALL add_fk_component_supplier_ticket();
DROP PROCEDURE IF EXISTS add_fk_component_supplier_ticket;

ALTER TABLE at_ancillaries
    MODIFY COLUMN amount DECIMAL(18,4) NOT NULL DEFAULT 0.0000;

ALTER TABLE at_refunds
    MODIFY COLUMN total_refund_amount DECIMAL(18,4) DEFAULT NULL,
    MODIFY COLUMN total_penalty DECIMAL(18,4) DEFAULT 0.0000;

ALTER TABLE at_refund_items
    MODIFY COLUMN refund_amount DECIMAL(18,4) NOT NULL DEFAULT 0.0000,
    MODIFY COLUMN penalty_amount DECIMAL(18,4) NOT NULL DEFAULT 0.0000,
    MODIFY COLUMN tax_refund_amount DECIMAL(18,4) NOT NULL DEFAULT 0.0000;

ALTER TABLE at_flight_reissues
    MODIFY COLUMN fare_difference DECIMAL(18,4) DEFAULT NULL,
    MODIFY COLUMN change_penalty DECIMAL(18,4) DEFAULT 0.0000,
    MODIFY COLUMN tax_difference DECIMAL(18,4) DEFAULT 0.0000;

ALTER TABLE payments
    MODIFY COLUMN paid_amount DECIMAL(18,4) NOT NULL DEFAULT 0.0000,
    MODIFY COLUMN original_amount DECIMAL(18,4) DEFAULT NULL,
    MODIFY COLUMN conversion_rate DECIMAL(18,6) DEFAULT 1.000000;

-- ===========================================================================
-- Phase 7: Pricing Lifecycle & Versioning Expansion
-- ===========================================================================
ALTER TABLE at_pricing_snapshots
CHANGE COLUMN snapshot_type operation VARCHAR(30) NOT NULL,
ADD COLUMN source VARCHAR(50) DEFAULT 'SYSTEM' AFTER operation,
ADD COLUMN supplier_id BIGINT AFTER source,
ADD COLUMN created_by VARCHAR(100) DEFAULT 'SYSTEM' AFTER supplier_id,
ADD COLUMN status VARCHAR(20) DEFAULT 'ACTIVE' AFTER created_by;

ALTER TABLE at_pricing_snapshots
ADD CONSTRAINT fk_pricing_snapshots_supplier 
FOREIGN KEY (supplier_id) REFERENCES suppliers(id) ON DELETE SET NULL;

-- ===========================================================================
-- Phase 8: Post-Booking Financial Strict Ledger Refactor
-- ===========================================================================
ALTER TABLE at_refunds
DROP COLUMN total_refund_amount,
DROP COLUMN total_penalty;

ALTER TABLE at_flight_reissues
DROP COLUMN fare_difference,
DROP COLUMN change_penalty,
DROP COLUMN tax_difference;

-- ===========================================================================
-- Phase 9: Booking Contact Details
-- ===========================================================================
ALTER TABLE at_bookings
ADD COLUMN contact_email VARCHAR(255) AFTER is_domestic,
ADD COLUMN contact_phone VARCHAR(50) AFTER contact_email;
