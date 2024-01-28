ALTER TABLE event_remind_subscriptions
    ALTER COLUMN subscriptions TYPE BIT(10)
        USING
            subscriptions::bit(10),
    ALTER COLUMN subscriptions SET DEFAULT '0000000000'::bit(10);
