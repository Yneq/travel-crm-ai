ALTER TABLE orders
    ADD COLUMN idempotency_key VARCHAR(128) NOT NULL AFTER order_number,
    ADD COLUMN version INT UNSIGNED NOT NULL DEFAULT 1 AFTER status,
    ADD COLUMN paid_at DATETIME NULL AFTER total,
    ADD COLUMN cancelled_at DATETIME NULL AFTER paid_at,
    ADD UNIQUE KEY uk_orders_idempotency (idempotency_key),
    ADD UNIQUE KEY uk_orders_quote (quote_id);

ALTER TABLE payments
    ADD COLUMN attempt_number SMALLINT UNSIGNED NOT NULL DEFAULT 1 AFTER order_id,
    ADD COLUMN initiated_by BIGINT UNSIGNED NULL AFTER currency,
    ADD COLUMN processed_at DATETIME NULL AFTER failure_message,
    ADD CONSTRAINT fk_payment_initiator FOREIGN KEY (initiated_by) REFERENCES staff_users(id) ON DELETE SET NULL,
    ADD INDEX idx_payments_status (status);
