-- O.S.A. migration 005: skills + reflection
-- Skills = записанные последовательности tool calls, которые агент переиспользует.
-- Reflection = предложения по улучшению системного промпта от агента.

CREATE TABLE IF NOT EXISTS skills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    description TEXT NOT NULL,
    steps_json TEXT NOT NULL,           -- [{tool: "file_read", args: {...}}, ...]
    trigger_pattern TEXT,                -- что активирует skill (regex/keyword)
    status TEXT NOT NULL CHECK (status IN ('experimental', 'promoted', 'deprecated')) DEFAULT 'experimental',
    version INTEGER DEFAULT 1,
    success_count INTEGER DEFAULT 0,
    fail_count INTEGER DEFAULT 0,
    source_goal_id INTEGER REFERENCES goals(id),  -- откуда навык извлечён
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_skills_status ON skills(status);
CREATE INDEX IF NOT EXISTS idx_skills_name ON skills(name);

CREATE TABLE IF NOT EXISTS reflections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    goal_id INTEGER NOT NULL REFERENCES goals(id),
    analysis TEXT NOT NULL,                -- что агент увидел
    suggestion TEXT,                        -- что предлагает изменить
    applied INTEGER DEFAULT 0,               -- 0=pending review, 1=applied
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_reflections_goal ON reflections(goal_id);
CREATE INDEX IF NOT EXISTS idx_reflections_applied ON reflections(applied);
