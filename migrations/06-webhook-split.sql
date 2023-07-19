CREATE TABLE IF NOT EXISTS webhooks (
    guild_id BIGINT PRIMARY KEY REFERENCES event_remind_subscriptions(guild_id) ON DELETE CASCADE,
    webhook_id BIGINT UNIQUE NOT NULL,
    webhook_url TEXT UNIQUE NOT NULL,
    webhook_token TEXT UNIQUE NOT NULL
);

ALTER TABLE event_remind_subscriptions DROP COLUMN webhook_url;
ALTER TABLE event_remind_subscriptions ADD COLUMN webhook_id BIGINT REFERENCES webhooks(webhook_id) ON DELETE CASCADE;
CREATE INDEX IF NOT EXISTS event_subscriptions_webhook_idx ON event_remind_subscriptions(webhook_id);
