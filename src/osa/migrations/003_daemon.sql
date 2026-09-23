-- O.S.A. migration 003: daemon_state
-- Состояние демона для мониторинга (PID, heartbeat, started_at).
-- Используется на M1a.5+ (демон).

CREATE TABLE IF NOT EXISTS daemon_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),  -- всегда одна строка
    pid INTEGER,
    started_at TIMESTAMP,
    last_heartbeat TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'stopped' CHECK (status IN ('stopped', 'starting', 'running', 'stopping'))
);
