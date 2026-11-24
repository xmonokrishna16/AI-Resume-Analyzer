CREATE TABLE IF NOT EXISTS outreach_kits (
    id INT NOT NULL AUTO_INCREMENT,
    user_id INT NOT NULL,
    company_name VARCHAR(150) NOT NULL,
    target_role VARCHAR(150) NOT NULL,
    recipient_type VARCHAR(50) NOT NULL,
    tone VARCHAR(50) NOT NULL,
    highlighted_project VARCHAR(255) NOT NULL,
    kit_json LONGTEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_outreach_kits_user_created (user_id, created_at),
    CONSTRAINT fk_outreach_kits_user
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
