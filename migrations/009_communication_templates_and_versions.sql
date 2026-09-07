CREATE TABLE communication_templates (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    template_key VARCHAR(80) NOT NULL,
    name VARCHAR(120) NOT NULL,
    channel VARCHAR(24) NOT NULL DEFAULT 'email',
    subject_template VARCHAR(160) NOT NULL,
    body_template TEXT NOT NULL,
    version INT UNSIGNED NOT NULL DEFAULT 1,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by BIGINT UNSIGNED NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_communication_template_version (template_key, version),
    INDEX idx_communication_template_active (is_active, template_key),
    CONSTRAINT fk_communication_template_creator
        FOREIGN KEY (created_by) REFERENCES staff_users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO communication_templates(
    template_key, name, subject_template, body_template
) VALUES
(
    'trip-confirmation',
    '行程需求確認',
    '【行程確認】{{member_name}} 的旅遊需求',
    '{{member_name}} 您好，我們正在確認您的旅程安排。關於「{{reminder_title}}」，請回覆是否仍有餐食、住宿或接送需求需要調整。顧問確認後會再更新正式內容。'
),
(
    'payment-follow-up',
    '付款進度提醒',
    '【付款確認】{{member_name}} 的訂單進度',
    '{{member_name}} 您好，我們正在確認「{{reminder_title}}」的付款進度。{{recommended_action}}。如已完成或需要協助，請告知您的旅遊顧問。'
);

CREATE TABLE communication_draft_versions (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    communication_draft_id BIGINT UNSIGNED NOT NULL,
    version INT UNSIGNED NOT NULL,
    subject VARCHAR(160) NOT NULL,
    body TEXT NOT NULL,
    edited_by BIGINT UNSIGNED NOT NULL,
    source VARCHAR(32) NOT NULL,
    source_template_id BIGINT UNSIGNED NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_communication_draft_version (communication_draft_id, version),
    INDEX idx_communication_version_created (communication_draft_id, created_at),
    CONSTRAINT fk_communication_version_draft
        FOREIGN KEY (communication_draft_id) REFERENCES communication_drafts(id) ON DELETE CASCADE,
    CONSTRAINT fk_communication_version_editor
        FOREIGN KEY (edited_by) REFERENCES staff_users(id),
    CONSTRAINT fk_communication_version_template
        FOREIGN KEY (source_template_id) REFERENCES communication_templates(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO communication_draft_versions(
    communication_draft_id, version, subject, body, edited_by, source
)
SELECT id, version, subject, body, last_edited_by, 'migration_backfill'
FROM communication_drafts;
