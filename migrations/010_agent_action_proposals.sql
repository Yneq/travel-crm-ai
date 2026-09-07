CREATE TABLE IF NOT EXISTS agent_action_proposals (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    ai_run_id BIGINT UNSIGNED NOT NULL,
    idempotency_key VARCHAR(128) NOT NULL UNIQUE,
    action_type VARCHAR(64) NOT NULL,
    action_payload JSON NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'pending',
    created_by BIGINT UNSIGNED NOT NULL,
    reviewed_by BIGINT UNSIGNED NULL,
    review_notes TEXT NULL,
    reviewed_at DATETIME NULL,
    executed_entity_type VARCHAR(64) NULL,
    executed_entity_id BIGINT UNSIGNED NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_agent_proposal_run FOREIGN KEY (ai_run_id) REFERENCES ai_runs(id) ON DELETE CASCADE,
    CONSTRAINT fk_agent_proposal_creator FOREIGN KEY (created_by) REFERENCES staff_users(id),
    CONSTRAINT fk_agent_proposal_reviewer FOREIGN KEY (reviewed_by) REFERENCES staff_users(id) ON DELETE SET NULL,
    INDEX idx_agent_proposals_status_created (status, created_at),
    INDEX idx_agent_proposals_run (ai_run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

