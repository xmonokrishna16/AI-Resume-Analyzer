CREATE TABLE IF NOT EXISTS project_defense_sessions (
    id INT NOT NULL AUTO_INCREMENT,
    user_id INT NOT NULL,
    project_name VARCHAR(150) NOT NULL,
    repo_url VARCHAR(255) NULL,
    tech_stack VARCHAR(255) NOT NULL,
    difficulty_level VARCHAR(50) NOT NULL,
    readiness_score INT NOT NULL,
    qa_transcript_json LONGTEXT NOT NULL,
    cheat_sheet_json LONGTEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_project_defense_user_created (user_id, created_at),
    CONSTRAINT fk_project_defense_user
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
