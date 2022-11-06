CREATE EXTENSION IF NOT EXISTS pg_tgrm;
CREATE TABLE IF NOT EXISTS event_remind_subscription (
    guild_id BIGINT PRIMARY KEY,
    webhook_url TEXT NOT NULL,
    subscriptions INT NOT NULL DEFAULT 0,
    daily_role_id BIGINT,
    weekly_role_id BIGINT,
    fashion_report_role_id BIGINT
);
CREATE TABLE IF NOT EXISTS reminders (
    id SERIAL PRIMARY KEY,
    expires TIMESTAMP WITH TIME ZONE,
    created TIMESTAMP WITH TIME ZONE DEFAULT (NOW() AT TIME ZONE 'utc'),
    event TEXT,
    extra JSONB DEFAULT '{}'::JSONB
);
CREATE INDEX IF NOT EXISTS reminders_expires_idx ON reminders (expires);
CREATE TABLE IF NOT EXISTS commands (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT,
    channel_id BIGINT,
    author_id BIGINT,
    used TIMESTAMP WITH TIME ZONE,
    prefix TEXT,
    command TEXT,
    app_command BOOLEAN NOT NULL DEFAULT FALSE,
    failed BOOLEAN
);
CREATE INDEX IF NOT EXISTS commands_guild_id_idx ON commands (guild_id);
CREATE INDEX IF NOT EXISTS commands_author_id_idx ON commands (author_id);
CREATE INDEX IF NOT EXISTS commands_used_idx ON commands (used);
CREATE INDEX IF NOT EXISTS commands_command_idx ON commands (command);
CREATE INDEX IF NOT EXISTS commands_app_command_idx ON commands (app_command);
CREATE INDEX IF NOT EXISTS commands_failed_idx ON commands (failed);
