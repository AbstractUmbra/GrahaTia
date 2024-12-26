ALTER TABLE event_remind_subscriptions
    ALTER COLUMN subscriptions TYPE BIT(64)
        USING subscriptions::bit(64),
    ALTER COLUMN subscriptions SET DEFAULT '0000000000000000000000000000000000000000000000000000000000000000'::bit(64);

ALTER TABLE event_remind_subscriptions
    ADD COLUMN tt_open_tournament_role_id BIGINT;
