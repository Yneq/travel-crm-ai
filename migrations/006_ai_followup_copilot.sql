ALTER TABLE reminders
    ADD COLUMN ai_idempotency_key VARCHAR(128) NULL AFTER reviewed_at,
    ADD COLUMN ai_provider VARCHAR(100) NULL AFTER ai_idempotency_key,
    ADD COLUMN ai_draft JSON NULL AFTER ai_provider,
    ADD COLUMN ai_draft_status VARCHAR(30) NULL AFTER ai_draft,
    ADD COLUMN ai_generated_at DATETIME NULL AFTER ai_draft_status,
    ADD COLUMN ai_reviewed_by BIGINT UNSIGNED NULL AFTER ai_generated_at,
    ADD COLUMN ai_reviewed_at DATETIME NULL AFTER ai_reviewed_by,
    ADD COLUMN ai_review_notes TEXT NULL AFTER ai_reviewed_at,
    ADD UNIQUE KEY uk_reminders_ai_idempotency (ai_idempotency_key),
    ADD CONSTRAINT fk_reminder_ai_reviewer FOREIGN KEY (ai_reviewed_by) REFERENCES staff_users(id) ON DELETE SET NULL;
