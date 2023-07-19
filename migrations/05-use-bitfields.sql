ALTER TABLE event_remind_subscriptions ALTER COLUMN subscriptions DROP DEFAULT;
ALTER TABLE event_remind_subscriptions ALTER COLUMN subscriptions TYPE BIT(6) USING subscriptions::BIT(6);
ALTER TABLE event_remind_subscriptions ALTER COLUMN subscriptions SET DEFAULT '000000'::bit(6);
