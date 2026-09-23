-- O.S.A. migration 006: episodes расширение
-- Добавляем tool_name и tool_args для skill_detector и аналитики.
-- SQLite поддерживает ADD COLUMN. Колонки nullable для обратной совместимости.

ALTER TABLE episodes ADD COLUMN tool_name TEXT;
ALTER TABLE episodes ADD COLUMN tool_args TEXT;
CREATE INDEX IF NOT EXISTS idx_episodes_tool ON episodes(tool_name);
