"""
This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import discord
from discord import Guild, Role
from discord.utils import MISSING

from utilities.flags import SubscribedEventsFlags
from utilities.shared.cache import cache

if TYPE_CHECKING:
    from typing import Self

    from bot import Graha
    from utilities.shared._types.xiv.record_aliases.subscription import EventRecord
    from utilities.shared._types.xiv.record_aliases.webhooks import WebhooksRecord

__all__ = ("EventSubConfig",)


class MisconfiguredSubscription(Exception):
    __slots__ = ("subscription_config",)

    def __init__(self, subscription_config: EventSubConfig, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.subscription_config = subscription_config


class EventSubConfig:
    __slots__ = (
        "_bot",
        "channel_id",
        "daily_role_id",
        "fashion_report_role_id",
        "gate_role_id",
        "guild_id",
        "jumbo_cactpot_role_id",
        "ocean_fishing_role_id",
        "open_tournament_role_id",
        "subscriptions",
        "thread_id",
        "webhook_id",
        "weekly_role_id",
    )

    def __init__(
        self,
        bot: Graha,
        /,
        *,
        guild_id: int,
        channel_id: int | None = None,
        thread_id: int | None = None,
        subscriptions: int = 0,
        daily_role_id: int | None = None,
        weekly_role_id: int | None = None,
        fashion_report_role_id: int | None = None,
        jumbo_cactpot_role_id: int | None = None,
        ocean_fishing_role_id: int | None = None,
        gate_role_id: int | None = None,
        open_tournament_role_id: int | None = None,
        webhook_id: int | None = None,
    ) -> None:
        self._bot: Graha = bot
        self.guild_id: int = guild_id
        self.channel_id: int | None = channel_id
        self.thread_id: int | None = thread_id
        self.subscriptions: SubscribedEventsFlags = SubscribedEventsFlags._from_value(subscriptions)
        self.daily_role_id: int | None = daily_role_id
        self.weekly_role_id: int | None = weekly_role_id
        self.fashion_report_role_id: int | None = fashion_report_role_id
        self.jumbo_cactpot_role_id: int | None = jumbo_cactpot_role_id
        self.ocean_fishing_role_id: int | None = ocean_fishing_role_id
        self.gate_role_id: int | None = gate_role_id
        self.open_tournament_role_id: int | None = open_tournament_role_id
        self.webhook_id: int | None = webhook_id

    def __repr__(self) -> str:
        return f"<EventSubConfig guild_id={self.guild_id}>"

    @classmethod
    def from_record(cls, bot: Graha, /, *, record: EventRecord) -> Self:
        return cls(
            bot,
            guild_id=record["guild_id"],
            channel_id=record["channel_id"],
            thread_id=record["thread_id"],
            subscriptions=record["subscriptions"].to_int(),
            daily_role_id=record["daily_role_id"],
            weekly_role_id=record["weekly_role_id"],
            fashion_report_role_id=record["fashion_report_role_id"],
            jumbo_cactpot_role_id=record["jumbo_cactpot_role_id"],
            ocean_fishing_role_id=record["ocean_fishing_role_id"],
            gate_role_id=record["gate_role_id"],
            open_tournament_role_id=record["open_tournament_role_id"],
            webhook_id=record["webhook_id"],
        )

    @classmethod
    def with_webhook(cls, bot: Graha, /, *, guild_id: int, webhook: discord.Webhook) -> Self:
        return cls(bot, guild_id=guild_id, webhook_id=webhook.id)

    @property
    def guild(self) -> Guild | None:
        if self.guild_id:
            return self._bot.get_guild(self.guild_id)

        return None

    def is_thread(self) -> bool:
        return bool(self.thread_id)

    @property
    def channel(self) -> discord.TextChannel | None:
        if not self.channel_id:
            return None

        if self.guild:
            return self.guild.get_channel(self.channel_id)  # pyright: ignore[reportReturnType] # guarded by outer machinery, only TextChannel input accepted
        return self._bot.get_channel(self.channel_id)  # pyright: ignore[reportReturnType] # see above

    @property
    def thread(self) -> discord.Thread:
        if not self.channel_id or not self.thread_id:
            return MISSING

        assert self.channel  # guarded above

        return self.channel.get_thread(self.thread_id) or MISSING

    @property
    def daily_role(self) -> Role | None:
        if self.guild and self.daily_role_id:
            return self.guild.get_role(self.daily_role_id)

        return None

    @property
    def weekly_role(self) -> Role | None:
        if self.guild and self.weekly_role_id:
            return self.guild.get_role(self.weekly_role_id)

        return None

    @property
    def fashion_report_role(self) -> Role | None:
        if self.guild and self.fashion_report_role_id:
            return self.guild.get_role(self.fashion_report_role_id)

        return None

    @property
    def ocean_fishing_role(self) -> Role | None:
        if self.guild and self.ocean_fishing_role_id:
            return self.guild.get_role(self.ocean_fishing_role_id)

        return None

    @property
    def jumbo_cactpot_role(self) -> Role | None:
        if self.guild and self.jumbo_cactpot_role_id:
            return self.guild.get_role(self.jumbo_cactpot_role_id)

        return None

    @property
    def gate_role(self) -> Role | None:
        if self.guild and self.gate_role_id:
            return self.guild.get_role(self.gate_role_id)

        return None

    @property
    def open_tournament_role(self) -> Role | None:
        if self.guild and self.open_tournament_role_id:
            return self.guild.get_role(self.open_tournament_role_id)

        return None

    async def _create_or_replace_webhook(self) -> discord.Webhook:
        if not self.channel:
            raise MisconfiguredSubscription(self)

        fetch_query = """
                      SELECT webhook_id
                      FROM webhooks
                      WHERE guild_id = $1;
                      """

        existing_webhook_id: int = await self._bot.pool.fetchval(fetch_query, self.guild_id)
        try:
            existing_webhook = await self._bot.fetch_webhook(existing_webhook_id)
        except discord.HTTPException:
            # no webhook clearly
            pass
        else:
            try:
                await existing_webhook.delete(reason="Deleted by G'raha Tia due to misconfiguration.")
            except discord.Forbidden as err:
                # we can't do anything here.
                raise MisconfiguredSubscription(self, "Unable to delete webhooks within guild.") from err

        webhook = await self.channel.create_webhook(name="XIV Timers", reason="Created via G'raha Tia subscriptions!")
        query = """
                INSERT INTO webhooks (guild_id, webhook_id, webhook_url, webhook_token)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (guild_id)
                    DO UPDATE SET
                        webhook_id = $2,
                        webhook_url = $3,
                        webhook_token = $4
                    WHERE webhooks.guild_id = $1;
                """
        await self._bot.pool.execute(query, self.guild_id, webhook.id, webhook.url, webhook.token)

        self.webhook_id = webhook.id

        return webhook

    @cache()
    async def get_webhook(self) -> discord.Webhook:
        if self.guild_id or self.webhook_id:
            query = "SELECT * FROM webhooks WHERE guild_id = $1 OR webhook_id = $2;"
            record: WebhooksRecord | None = await self._bot.pool.fetchrow(query, self.guild_id, self.webhook_id)  # pyright: ignore[reportAssignmentType] # stubs
            if not record:
                return await self._create_or_replace_webhook()

            url = record["webhook_url"] or (
                f"https://discord.com/api/webhooks/{record['webhook_id']}/" + record["webhook_token"]
            )

            return discord.Webhook.from_url(url, client=self._bot)
        return await self._create_or_replace_webhook()

    async def delete(self) -> bool:
        query = """
                DELETE FROM event_remind_subscriptions
                WHERE guild_id = $1;
                """

        ret = await self._bot.pool.execute(query, self.guild_id)
        return ret != "DELETE 0"

    async def update_webhook_channel(self, channel: discord.TextChannel | discord.Thread) -> discord.Webhook:
        webhook = await self.get_webhook()

        return await webhook.edit(channel=channel)
