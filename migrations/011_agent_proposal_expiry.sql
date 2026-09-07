ALTER TABLE agent_action_proposals
    ADD COLUMN expires_at DATETIME NULL AFTER status;

UPDATE agent_action_proposals
SET expires_at = DATE_ADD(created_at, INTERVAL 24 HOUR)
WHERE expires_at IS NULL;

ALTER TABLE agent_action_proposals
    MODIFY expires_at DATETIME NOT NULL,
    ADD INDEX idx_agent_proposals_status_expiry (status, expires_at);
