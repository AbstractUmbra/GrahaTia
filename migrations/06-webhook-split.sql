CREATE TABLE IF NOT EXISTS webhooks (
    guild_id BIGINT PRIMARY KEY REFERENCES event_remind_subscriptions(guild_id),
    webhook_id BIGINT,
    webhook_url TEXT,
    webhook_token TEXT,
    CHECK ( COALESCE (webhook_url, webhook_token) IS NOT NULL)
);

WITH selected AS (SELECT webhook_url FROM event_remind_subscriptions)
INSERT INTO webhooks VALUES (
    regexp_substr((SELECT webhook_url FROM selected), '((?:https?://)?(?:(?:canary|ptb|dev)?\.)?discord\.com/api/webhooks/(\d+)/(.*))', 1, 1, 'i', 2)::BIGINT,
    regexp_substr((SELECT webhook_url FROM selected), '((?:https?://)?(?:(?:canary|ptb|dev)?\.)?discord\.com/api/webhooks/(\d+)/(.*))', 1, 1, 'i', 1),
    regexp_substr((SELECT webhook_url FROM selected), '((?:https?://)?(?:(?:canary|ptb|dev)?\.)?discord\.com/api/webhooks/(\d+)/(.*))', 1, 1, 'i', 3)
);

ALTER TABLE event_remind_subscriptions DROP COLUMN webhook_url;
ALTER TABLE event_remind_subscriptions ADD COLUMN webhook_id BIGINT REFERENCES webhooks(webhook_id);
CREATE INDEX IF NOT EXISTS event_subscriptions_webhook_idx ON event_remind_subscriptions(webhook_id);
