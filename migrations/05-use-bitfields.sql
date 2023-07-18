ALTER TABLE event_remind_subscriptions ALTER COLUMN subscriptions TYPE BIT(6) USING subscriptions::BIT(6);
