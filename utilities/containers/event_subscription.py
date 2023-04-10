"""
This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from discord import Guild, Role
from typing_extensions import Self

from .._types.xiv.record_aliases.subscription import EventRecord
from ..containers.subscription_bitflags import SubscriptionFlags


if TYPE_CHECKING:
    from bot import Graha

__all__ = ("EventSubConfig",)


class EventSubConfig:
    __slots__ = (
        "_bot",
        "guild_id",
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
        subscriptions: int = 0,
        webhook_url: str | None = None,
        daily_role_id: int | None = None,
        weekly_role_id: int | None = None,
        fashion_report_role_id: int | None = None,
    ) -> None:
        self._bot: Graha = bot
        self.guild_id: int | None = guild_id
        self.webhook_url: str | None = webhook_url
        self.subscriptions: SubscriptionFlags = SubscriptionFlags._from_value(subscriptions)
        self.daily_role_id: int | None = daily_role_id
        self.weekly_role_id: int | None = weekly_role_id
        self.fashion_report_role_id: int | None = fashion_report_role_id

    @classmethod
    def from_record(cls, bot: Graha, /, *, record: EventRecord) -> Self:
        return cls(
            bot,
            guild_id=record["guild_id"],
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
