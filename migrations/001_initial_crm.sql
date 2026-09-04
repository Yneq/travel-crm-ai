CREATE TABLE IF NOT EXISTS roles (
    id SMALLINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(32) NOT NULL UNIQUE,
    name VARCHAR(64) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO roles (code, name) VALUES
    ('admin', 'Administrator'),
    ('advisor', 'Travel Advisor'),
    ('finance', 'Finance');

CREATE TABLE IF NOT EXISTS staff_users (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    role_id SMALLINT UNSIGNED NOT NULL,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_staff_role FOREIGN KEY (role_id) REFERENCES roles(id),
    INDEX idx_staff_role (role_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS members (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    owner_id BIGINT UNSIGNED NULL,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(255) NULL,
    phone VARCHAR(32) NULL,
    locale VARCHAR(16) NOT NULL DEFAULT 'zh-TW',
    tier VARCHAR(24) NOT NULL DEFAULT 'standard',
    status VARCHAR(24) NOT NULL DEFAULT 'active',
    source VARCHAR(64) NULL,
    notes TEXT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP NULL,
    CONSTRAINT fk_member_owner FOREIGN KEY (owner_id) REFERENCES staff_users(id) ON DELETE SET NULL,
    INDEX idx_members_owner (owner_id),
    INDEX idx_members_status (status),
    INDEX idx_members_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS member_preferences (
    member_id BIGINT UNSIGNED PRIMARY KEY,
    travel_styles JSON NULL,
    dietary_restrictions JSON NULL,
    room_preferences JSON NULL,
    accessibility_needs JSON NULL,
    other_notes TEXT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_preference_member FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS travel_requests (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    member_id BIGINT UNSIGNED NOT NULL,
    advisor_id BIGINT UNSIGNED NULL,
    title VARCHAR(160) NOT NULL,
    destination VARCHAR(160) NOT NULL,
    start_date DATE NULL,
    end_date DATE NULL,
    party_size SMALLINT UNSIGNED NOT NULL DEFAULT 1,
    budget_currency CHAR(3) NOT NULL DEFAULT 'TWD',
    budget_amount DECIMAL(14, 2) NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'new',
    requirements JSON NULL,
    ai_summary TEXT NULL,
    version INT UNSIGNED NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_request_member FOREIGN KEY (member_id) REFERENCES members(id),
    CONSTRAINT fk_request_advisor FOREIGN KEY (advisor_id) REFERENCES staff_users(id) ON DELETE SET NULL,
    INDEX idx_requests_member (member_id),
    INDEX idx_requests_advisor_status (advisor_id, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS trips (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    request_id BIGINT UNSIGNED NOT NULL,
    name VARCHAR(160) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'draft',
    start_date DATE NULL,
    end_date DATE NULL,
    version INT UNSIGNED NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_trip_request FOREIGN KEY (request_id) REFERENCES travel_requests(id),
    INDEX idx_trips_request (request_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS trip_items (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    trip_id BIGINT UNSIGNED NOT NULL,
    item_type VARCHAR(32) NOT NULL,
    title VARCHAR(160) NOT NULL,
    supplier_name VARCHAR(160) NULL,
    starts_at DATETIME NULL,
    ends_at DATETIME NULL,
    location VARCHAR(255) NULL,
    unit_price DECIMAL(14, 2) NULL,
    quantity SMALLINT UNSIGNED NOT NULL DEFAULT 1,
    source_payload JSON NULL,
    sort_order INT UNSIGNED NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_trip_item_trip FOREIGN KEY (trip_id) REFERENCES trips(id) ON DELETE CASCADE,
    INDEX idx_trip_items_trip_sort (trip_id, sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS quotes (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    trip_id BIGINT UNSIGNED NOT NULL,
    quote_number VARCHAR(40) NOT NULL UNIQUE,
    status VARCHAR(32) NOT NULL DEFAULT 'draft',
    currency CHAR(3) NOT NULL DEFAULT 'TWD',
    subtotal DECIMAL(14, 2) NOT NULL DEFAULT 0,
    tax DECIMAL(14, 2) NOT NULL DEFAULT 0,
    total DECIMAL(14, 2) NOT NULL DEFAULT 0,
    expires_at DATETIME NULL,
    approved_by BIGINT UNSIGNED NULL,
    approved_at DATETIME NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_quote_trip FOREIGN KEY (trip_id) REFERENCES trips(id),
    CONSTRAINT fk_quote_approver FOREIGN KEY (approved_by) REFERENCES staff_users(id) ON DELETE SET NULL,
    INDEX idx_quotes_trip (trip_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS orders (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    quote_id BIGINT UNSIGNED NOT NULL,
    member_id BIGINT UNSIGNED NOT NULL,
    order_number VARCHAR(40) NOT NULL UNIQUE,
    status VARCHAR(32) NOT NULL DEFAULT 'pending_payment',
    currency CHAR(3) NOT NULL DEFAULT 'TWD',
    total DECIMAL(14, 2) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_order_quote FOREIGN KEY (quote_id) REFERENCES quotes(id),
    CONSTRAINT fk_order_member FOREIGN KEY (member_id) REFERENCES members(id),
    INDEX idx_orders_member (member_id),
    INDEX idx_orders_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS payments (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    order_id BIGINT UNSIGNED NOT NULL,
    provider VARCHAR(32) NOT NULL,
    provider_transaction_id VARCHAR(128) NULL,
    idempotency_key VARCHAR(128) NOT NULL UNIQUE,
    status VARCHAR(32) NOT NULL DEFAULT 'created',
    amount DECIMAL(14, 2) NOT NULL,
    currency CHAR(3) NOT NULL,
    failure_code VARCHAR(64) NULL,
    failure_message VARCHAR(255) NULL,
    provider_payload JSON NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_payment_order FOREIGN KEY (order_id) REFERENCES orders(id),
    UNIQUE KEY uk_payment_provider_transaction (provider, provider_transaction_id),
    INDEX idx_payments_order (order_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS documents (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    member_id BIGINT UNSIGNED NOT NULL,
    request_id BIGINT UNSIGNED NULL,
    document_type VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'draft',
    storage_key VARCHAR(512) NULL,
    content_hash VARCHAR(64) NULL,
    version INT UNSIGNED NOT NULL DEFAULT 1,
    created_by BIGINT UNSIGNED NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_document_member FOREIGN KEY (member_id) REFERENCES members(id),
    CONSTRAINT fk_document_request FOREIGN KEY (request_id) REFERENCES travel_requests(id) ON DELETE SET NULL,
    CONSTRAINT fk_document_creator FOREIGN KEY (created_by) REFERENCES staff_users(id) ON DELETE SET NULL,
    INDEX idx_documents_member (member_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS tasks (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    member_id BIGINT UNSIGNED NULL,
    request_id BIGINT UNSIGNED NULL,
    assignee_id BIGINT UNSIGNED NULL,
    created_by BIGINT UNSIGNED NOT NULL,
    title VARCHAR(160) NOT NULL,
    description TEXT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'open',
    priority VARCHAR(16) NOT NULL DEFAULT 'normal',
    due_at DATETIME NULL,
    completed_at DATETIME NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_task_member FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE SET NULL,
    CONSTRAINT fk_task_request FOREIGN KEY (request_id) REFERENCES travel_requests(id) ON DELETE SET NULL,
    CONSTRAINT fk_task_assignee FOREIGN KEY (assignee_id) REFERENCES staff_users(id) ON DELETE SET NULL,
    CONSTRAINT fk_task_creator FOREIGN KEY (created_by) REFERENCES staff_users(id),
    INDEX idx_tasks_assignee_status_due (assignee_id, status, due_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS reminders (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    task_id BIGINT UNSIGNED NULL,
    member_id BIGINT UNSIGNED NULL,
    channel VARCHAR(24) NOT NULL,
    scheduled_at DATETIME NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'scheduled',
    payload JSON NOT NULL,
    sent_at DATETIME NULL,
    last_error VARCHAR(255) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_reminder_task FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE SET NULL,
    CONSTRAINT fk_reminder_member FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE SET NULL,
    INDEX idx_reminders_status_schedule (status, scheduled_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS ai_runs (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    request_id BIGINT UNSIGNED NULL,
    initiated_by BIGINT UNSIGNED NULL,
    workflow_name VARCHAR(80) NOT NULL,
    workflow_version VARCHAR(32) NOT NULL,
    model_name VARCHAR(80) NOT NULL,
    status VARCHAR(24) NOT NULL,
    input_data JSON NOT NULL,
    output_data JSON NULL,
    error_data JSON NULL,
    prompt_tokens INT UNSIGNED NULL,
    completion_tokens INT UNSIGNED NULL,
    started_at DATETIME NOT NULL,
    completed_at DATETIME NULL,
    CONSTRAINT fk_ai_run_request FOREIGN KEY (request_id) REFERENCES travel_requests(id) ON DELETE SET NULL,
    CONSTRAINT fk_ai_run_user FOREIGN KEY (initiated_by) REFERENCES staff_users(id) ON DELETE SET NULL,
    INDEX idx_ai_runs_request (request_id),
    INDEX idx_ai_runs_status_started (status, started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS integration_events (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    provider VARCHAR(64) NOT NULL,
    event_type VARCHAR(80) NOT NULL,
    external_id VARCHAR(128) NULL,
    idempotency_key VARCHAR(128) NOT NULL UNIQUE,
    status VARCHAR(24) NOT NULL DEFAULT 'received',
    payload JSON NOT NULL,
    attempts SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    next_attempt_at DATETIME NULL,
    processed_at DATETIME NULL,
    last_error VARCHAR(255) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_integration_events_retry (status, next_attempt_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    actor_id BIGINT UNSIGNED NULL,
    entity_type VARCHAR(64) NOT NULL,
    entity_id VARCHAR(64) NOT NULL,
    action VARCHAR(64) NOT NULL,
    before_data JSON NULL,
    after_data JSON NULL,
    correlation_id VARCHAR(64) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_audit_actor FOREIGN KEY (actor_id) REFERENCES staff_users(id) ON DELETE SET NULL,
    INDEX idx_audit_entity (entity_type, entity_id),
    INDEX idx_audit_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
