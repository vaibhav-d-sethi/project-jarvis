-- Project JARVIS schema for MySQL 8.0+ (Aiven).
-- The app creates these tables automatically on first start (CREATE IF NOT EXISTS).
-- Keep semicolons out of comments: the app splits this file on semicolons.

CREATE TABLE IF NOT EXISTS users (
    id CHAR(36) NOT NULL,
    email VARCHAR(254) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    role ENUM('admin', 'user') NOT NULL DEFAULT 'user',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_users_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Metadata only. Document bytes and raw OCR text are never stored.
CREATE TABLE IF NOT EXISTS user_files (
    id CHAR(36) NOT NULL,
    user_id CHAR(36) NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    mime_type VARCHAR(127) NOT NULL,
    file_size_bytes BIGINT UNSIGNED NOT NULL,
    sha256_hash CHAR(64) NOT NULL,
    task ENUM('revision_notes', 'quiz_generation') NOT NULL,
    status ENUM('processing', 'completed', 'failed') NOT NULL DEFAULT 'processing',
    error_message VARCHAR(500) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_files_user_created (user_id, created_at),
    CONSTRAINT fk_files_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS revision_notes (
    id CHAR(36) NOT NULL,
    user_id CHAR(36) NOT NULL,
    file_id CHAR(36) NOT NULL,
    title VARCHAR(255) NOT NULL,
    content MEDIUMTEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_notes_user_created (user_id, created_at),
    CONSTRAINT fk_notes_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_notes_file FOREIGN KEY (file_id) REFERENCES user_files(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS quizzes (
    id CHAR(36) NOT NULL,
    user_id CHAR(36) NOT NULL,
    file_id CHAR(36) NOT NULL,
    title VARCHAR(255) NOT NULL,
    total_questions INT UNSIGNED NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_quizzes_user_created (user_id, created_at),
    CONSTRAINT fk_quizzes_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_quizzes_file FOREIGN KEY (file_id) REFERENCES user_files(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS quiz_questions (
    id CHAR(36) NOT NULL,
    quiz_id CHAR(36) NOT NULL,
    question_order INT UNSIGNED NOT NULL,
    question_text TEXT NOT NULL,
    option_a VARCHAR(1000) NOT NULL,
    option_b VARCHAR(1000) NOT NULL,
    option_c VARCHAR(1000) NOT NULL,
    option_d VARCHAR(1000) NOT NULL,
    correct_option ENUM('A', 'B', 'C', 'D') NOT NULL,
    explanation TEXT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_quiz_question_order (quiz_id, question_order),
    CONSTRAINT fk_questions_quiz FOREIGN KEY (quiz_id) REFERENCES quizzes(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS quiz_attempts (
    id CHAR(36) NOT NULL,
    user_id CHAR(36) NOT NULL,
    quiz_id CHAR(36) NOT NULL,
    score INT UNSIGNED NOT NULL,
    total_questions INT UNSIGNED NOT NULL,
    answers_json JSON NOT NULL,
    completed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_attempts_user_completed (user_id, completed_at),
    CONSTRAINT fk_attempts_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_attempts_quiz FOREIGN KEY (quiz_id) REFERENCES quizzes(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
