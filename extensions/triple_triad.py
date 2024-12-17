from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

import discord

from utilities.shared.cog import BaseCog
from utilities.shared.formats import random_pastel_colour, ts

if TYPE_CHECKING:
    from bot import Graha


class TripleTriad(BaseCog["Graha"]):
    def __init__(self, bot: Graha, /) -> None:
        super().__init__(bot)

    def _resolve_next_open_tournament_window(self, dt: datetime.datetime | None = None, /) -> datetime.datetime:
        dt = dt or datetime.datetime.now(datetime.UTC)

        hour = dt.hour
        hours = 2 if hour % 2 == 1 else 1

        return (dt + datetime.timedelta(hours=hours)).replace(minute=0, second=0, microsecond=0)

    def generate_open_tournament_embed(self, dt: datetime.datetime | None = None, /) -> discord.Embed:
        dt = dt or self._resolve_next_open_tournament_window()

        embed = discord.Embed(title="Open Tournament signup time!", colour=random_pastel_colour()).set_thumbnail(
            url="https://media.discordapp.net/attachments/872373121292853248/991352363577250003/unknown.png?width=198&height=262",
        )
        embed.description = f"The next start time for the Open Tournament will be {ts(dt):F} ({ts(dt):R})"

        return embed


async def setup(bot: Graha, /) -> None:
    return await bot.add_cog(TripleTriad(bot))
