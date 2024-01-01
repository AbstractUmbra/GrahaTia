CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS event_remind_subscriptions (
    guild_id BIGINT PRIMARY KEY,
    channel_id BIGINT,
    thread_id BIGINT,
    webhook_id BIGINT NOT NULL,
    subscriptions BIT(6) NOT NULL DEFAULT '000000'::bit(6),
    daily_role_id BIGINT,
    weekly_role_id BIGINT,
    fashion_report_role_id BIGINT
);

CREATE TABLE IF NOT EXISTS webhooks (
    guild_id BIGINT PRIMARY KEY,
    webhook_id BIGINT UNIQUE NOT NULL,
    webhook_url TEXT UNIQUE NOT NULL,
    webhook_token TEXT UNIQUE NOT NULL
);

CREATE INDEX IF NOT EXISTS event_subscriptions_webhook_idx ON event_remind_subscriptions(webhook_id);

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
