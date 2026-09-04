ALTER TABLE reminders
    ADD COLUMN reminder_type VARCHAR(40) NOT NULL DEFAULT 'manual' AFTER member_id,
    ADD COLUMN source_type VARCHAR(40) NULL AFTER reminder_type,
    ADD COLUMN source_id BIGINT UNSIGNED NULL AFTER source_type,
    ADD COLUMN dedup_key VARCHAR(160) NULL AFTER source_id,
    ADD COLUMN title VARCHAR(160) NOT NULL DEFAULT 'Operational reminder' AFTER dedup_key,
    ADD COLUMN reviewed_by BIGINT UNSIGNED NULL AFTER last_error,
    ADD COLUMN reviewed_at DATETIME NULL AFTER reviewed_by,
    ADD COLUMN updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP AFTER created_at,
    ADD UNIQUE KEY uk_reminders_dedup (dedup_key),
    ADD INDEX idx_reminders_source (source_type, source_id),
    ADD CONSTRAINT fk_reminder_reviewer FOREIGN KEY (reviewed_by) REFERENCES staff_users(id) ON DELETE SET NULL;
