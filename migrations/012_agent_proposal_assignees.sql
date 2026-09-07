ALTER TABLE agent_action_proposals
    ADD COLUMN assigned_to BIGINT UNSIGNED NULL AFTER created_by,
    ADD CONSTRAINT fk_agent_proposal_assignee
        FOREIGN KEY (assigned_to) REFERENCES staff_users(id) ON DELETE SET NULL,
    ADD INDEX idx_agent_proposals_assignee_status (assigned_to, status);
