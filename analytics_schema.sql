CREATE TABLE IF NOT EXISTS interview_sessions (
    id INT NOT NULL AUTO_INCREMENT,
    source_interview_id INT NOT NULL,
    user_id INT NOT NULL,
    category VARCHAR(50) NOT NULL DEFAULT 'mixed',
    questions_answered INT NOT NULL DEFAULT 0,
    total_questions INT NOT NULL DEFAULT 0,
    overall_score DECIMAL(5, 2) NULL,
    status ENUM('In Progress', 'Completed') NOT NULL DEFAULT 'In Progress',
    feedback_summary TEXT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_interview_sessions_source (source_interview_id),
    KEY idx_interview_sessions_user_created (user_id, created_at),
    CONSTRAINT fk_interview_sessions_source
        FOREIGN KEY (source_interview_id) REFERENCES mock_interviews (id) ON DELETE CASCADE,
    CONSTRAINT fk_interview_sessions_user
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
