CREATE TABLE IF NOT EXISTS rejection_autopsies (
    id INT NOT NULL AUTO_INCREMENT,
    user_id INT NOT NULL,
    company_name VARCHAR(150) NOT NULL,
    target_role VARCHAR(150) NOT NULL,
    failed_round VARCHAR(100) NOT NULL,
    primary_failure_pattern VARCHAR(150) NULL,
    autopsy_json LONGTEXT NOT NULL,
    completed_days_json TEXT NOT NULL,
    status ENUM('In Progress', 'Completed') NOT NULL DEFAULT 'In Progress',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_rejection_autopsies_user_created (user_id, created_at),
    KEY idx_rejection_autopsies_user_pattern (user_id, primary_failure_pattern),
    CONSTRAINT fk_rejection_autopsies_user
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
