ALTER TABLE communication_drafts
    ADD COLUMN last_edited_by BIGINT UNSIGNED NULL AFTER created_by;

UPDATE communication_drafts
SET last_edited_by = created_by
WHERE last_edited_by IS NULL;

ALTER TABLE communication_drafts
    MODIFY last_edited_by BIGINT UNSIGNED NOT NULL,
    ADD CONSTRAINT fk_communication_last_editor
        FOREIGN KEY (last_edited_by) REFERENCES staff_users(id);
