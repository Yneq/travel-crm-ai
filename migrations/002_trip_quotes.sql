ALTER TABLE quotes
    ADD COLUMN version INT UNSIGNED NOT NULL DEFAULT 1 AFTER quote_number,
    ADD COLUMN parent_quote_id BIGINT UNSIGNED NULL AFTER trip_id,
    ADD COLUMN notes TEXT NULL AFTER expires_at,
    ADD CONSTRAINT fk_quote_parent FOREIGN KEY (parent_quote_id) REFERENCES quotes(id) ON DELETE SET NULL,
    ADD UNIQUE KEY uk_quote_trip_version (trip_id, version);

CREATE TABLE quote_items (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    quote_id BIGINT UNSIGNED NOT NULL,
    source_trip_item_id BIGINT UNSIGNED NULL,
    item_type VARCHAR(32) NOT NULL,
    title VARCHAR(160) NOT NULL,
    description TEXT NULL,
    unit_price DECIMAL(14, 2) NOT NULL,
    quantity SMALLINT UNSIGNED NOT NULL DEFAULT 1,
    line_total DECIMAL(14, 2) NOT NULL,
    sort_order INT UNSIGNED NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_quote_item_quote FOREIGN KEY (quote_id) REFERENCES quotes(id) ON DELETE CASCADE,
    CONSTRAINT fk_quote_item_source FOREIGN KEY (source_trip_item_id) REFERENCES trip_items(id) ON DELETE SET NULL,
    INDEX idx_quote_items_quote_sort (quote_id, sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
