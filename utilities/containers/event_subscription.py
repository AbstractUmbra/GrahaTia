"""
This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import Guild, Role
from typing_extensions import Self

from utilities.flags import SubscribedEventsFlags


if TYPE_CHECKING:
    from _types.xiv.record_aliases.subscription import EventRecord

    from bot import Graha

__all__ = ("EventSubConfig",)


class EventSubConfig:
    __slots__ = (
        "_bot",
        "guild_id",
        "channel_id",
        "thread_id",
        "webhook_url",
        "subscriptions",
        "daily_role_id",
        "weekly_role_id",
        "fashion_report_role_id",
    )

    def __init__(
        self,
        bot: Graha,
        /,
        *,
        guild_id: int | None,
        channel_id: int | None = None,
        thread_id: int | None = None,
        subscriptions: int = 0,
        webhook_url: str | None = None,
        daily_role_id: int | None = None,
        weekly_role_id: int | None = None,
        fashion_report_role_id: int | None = None,
    ) -> None:
        self._bot: Graha = bot
        self.guild_id: int | None = guild_id
        self.channel_id: int | None = channel_id
        self.thread_id: int | None = thread_id
        self.webhook_url: str | None = webhook_url
        self.subscriptions: SubscribedEventsFlags = SubscribedEventsFlags._from_value(subscriptions)
        self.daily_role_id: int | None = daily_role_id
        self.weekly_role_id: int | None = weekly_role_id
        self.fashion_report_role_id: int | None = fashion_report_role_id

    @classmethod
    def from_record(cls, bot: Graha, /, *, record: EventRecord) -> Self:
        return cls(
            bot,
            guild_id=record["guild_id"],
            channel_id=record["channel_id"],
            thread_id=record["thread_id"],
            webhook_url=record["webhook_url"],
            subscriptions=record["subscriptions"],
            daily_role_id=record["daily_role_id"],
            weekly_role_id=record["weekly_role_id"],
            fashion_report_role_id=record["fashion_report_role_id"],
        )

    @property
    def guild(self) -> Guild | None:
        if self.guild_id:
            return self._bot.get_guild(self.guild_id)

    def is_thread(self) -> bool:
        return bool(self.thread_id)

    @property
    def channel(self) -> discord.TextChannel | None:
        if not self.channel_id:
            return None

        if self.guild:
            return self.guild.get_channel(self.channel_id)  # type: ignore
        else:
            return self._bot.get_channel(self.channel_id)  # type: ignore # ? TODO: This is slow.

    @property
    def thread(self) -> discord.Thread | None:
        if not self.channel_id or not self.thread_id:
            return None

        assert self.channel  # guarded above

        return self.channel.get_thread(self.thread_id)

    @property
    def daily_role(self) -> Role | None:
        if self.guild and self.daily_role_id:
            return self.guild.get_role(self.daily_role_id)

    @property
    def weekly_role(self) -> Role | None:
        if self.guild and self.weekly_role_id:
            return self.guild.get_role(self.weekly_role_id)

    @property
    def fashion_report_role(self) -> Role | None:
        if self.guild and self.weekly_role_id:
            return self.guild.get_role(self.weekly_role_id)

    @property
    def webhook(self) -> discord.Webhook | None:
        if self.webhook_url:
            return discord.Webhook.from_url(self.webhook_url, session=self._bot.session, client=self._bot)
