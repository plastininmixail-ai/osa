-- O.S.A. initial schema (migration 001)
-- Только таблицы, которые реально используются на M0:
--   goals     — поставленные цели
--   episodes  — каждое наблюдение/действие в рамках цели
--   schema_version — трекинг применённых миграций
-- Остальные таблицы (tasks, memory_facts, skills, prompt_versions) добавятся
-- миграциями 002+ после того, как архитектура проверена в M1a-M1c.

-- Goals
CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    description TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'planning', 'running', 'done', 'failed')),
    result TEXT,
    error TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_goals_status ON goals(status);
CREATE INDEX IF NOT EXISTS idx_goals_created ON goals(created_at);

-- Episodes
CREATE TABLE IF NOT EXISTS episodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    goal_id INTEGER NOT NULL REFERENCES goals(id),
    step_type TEXT NOT NULL CHECK (step_type IN ('think', 'act', 'observe', 'reflect')),
    content TEXT NOT NULL,
    tokens_used INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_episodes_goal ON episodes(goal_id);
CREATE INDEX IF NOT EXISTS idx_episodes_created ON episodes(created_at);

-- Schema version (создаётся также в db.py:migrate, но для полноты дублируем)
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
