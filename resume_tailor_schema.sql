CREATE TABLE IF NOT EXISTS tailored_resumes (
    id INT NOT NULL AUTO_INCREMENT,
    user_id INT NOT NULL,
    target_role VARCHAR(150) NOT NULL,
    company_name VARCHAR(150) NULL,
    original_ats_score INT NOT NULL,
    tailored_ats_score INT NOT NULL,
    added_keywords TEXT NOT NULL,
    tailored_content_json LONGTEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_tailored_resumes_user_created (user_id, created_at),
    CONSTRAINT fk_tailored_resumes_user
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
