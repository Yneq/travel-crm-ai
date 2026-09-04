ALTER TABLE ai_runs
    ADD COLUMN idempotency_key VARCHAR(128) NOT NULL AFTER request_id,
    ADD COLUMN reviewed_by BIGINT UNSIGNED NULL AFTER completed_at,
    ADD COLUMN reviewed_at DATETIME NULL AFTER reviewed_by,
    ADD COLUMN review_notes TEXT NULL AFTER reviewed_at,
    ADD COLUMN applied_trip_id BIGINT UNSIGNED NULL AFTER review_notes,
    ADD UNIQUE KEY uk_ai_runs_idempotency (idempotency_key),
    ADD CONSTRAINT fk_ai_run_reviewer FOREIGN KEY (reviewed_by) REFERENCES staff_users(id) ON DELETE SET NULL,
    ADD CONSTRAINT fk_ai_run_trip FOREIGN KEY (applied_trip_id) REFERENCES trips(id) ON DELETE SET NULL;
