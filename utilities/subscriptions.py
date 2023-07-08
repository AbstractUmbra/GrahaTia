"""
This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from discord import TextChannel

from utilities.flags import SubscribedEventsFlags


if TYPE_CHECKING:
    from bot import Graha

__all__ = ("EventSubConfig",)


class EventSubConfig:
    valid: bool
    channel: TextChannel | None

    __slots__ = (
        "_bot",
        "guild_id",
        "channel_id",
        "subscription_flags",
        "valid",
        "channel",
    )

    def __init__(self, bot: Graha, guild_id: int, channel_id: int, subscription_value: int) -> None:
        self._bot: Graha = bot
        self.guild_id: int = guild_id
        self.channel_id: int = channel_id
        self.subscription_flags: SubscribedEventsFlags = SubscribedEventsFlags(subscription_value)
        self.channel: TextChannel | None = None
        self.resolve()

    def resolve(self) -> None:
        guild = self._bot.get_guild(self.guild_id)
        if not guild:
            self.valid = False
            return

        channel = guild.get_channel(self.channel_id)
        if not channel or not isinstance(channel, TextChannel):
            self.valid = False
            return

        self.channel = channel
        self.valid = True
