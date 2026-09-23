-- O.S.A. migration 004: расширение статусов
-- Добавляем 'paused' и 'blocked' в goals.tasks для replanning и возобновления.

-- Пересоздаём CHECK constraints (SQLite не позволяет ALTER, поэтому пересоздаём таблицы).
-- Безопасный путь: создаём новую таблицу, копируем, удаляем старую, переименовываем.
-- Но проще: используем более мягкий constraint через "OR".

-- Goals: расширяем CHECK
CREATE TABLE goals_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    description TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'planning', 'running', 'paused', 'done', 'failed')),
    result TEXT,
    error TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP
);
INSERT INTO goals_new SELECT * FROM goals;
DROP TABLE goals;
ALTER TABLE goals_new RENAME TO goals;
CREATE INDEX IF NOT EXISTS idx_goals_status ON goals(status);
CREATE INDEX IF NOT EXISTS idx_goals_created ON goals(created_at);

-- Tasks: расширяем CHECK (добавляем 'blocked')
CREATE TABLE tasks_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    goal_id INTEGER NOT NULL REFERENCES goals(id),
    parent_id INTEGER REFERENCES tasks(id),
    description TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'done', 'failed', 'blocked')),
    result TEXT,
    attempts INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP
);
INSERT INTO tasks_new SELECT * FROM tasks;
DROP TABLE tasks;
ALTER TABLE tasks_new RENAME TO tasks;
CREATE INDEX IF NOT EXISTS idx_tasks_goal ON tasks(goal_id);
CREATE INDEX IF NOT EXISTS idx_tasks_parent ON tasks(parent_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
