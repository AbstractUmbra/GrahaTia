from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

import discord

from utilities.shared.cog import BaseCog
from utilities.shared.time import Weekday, resolve_next_weekday

if TYPE_CHECKING:
    from bot import Graha


class IslandSanctuary(BaseCog["Graha"]):
    def next_reset(self, *, source: datetime.datetime | None = None) -> datetime.datetime:
        return resolve_next_weekday(
            target=Weekday.monday, source=source, current_week_included=True, before_time=datetime.time(hour=8)
        )

    def generate_embed(self, *, when: datetime.datetime | None = None) -> discord.Embed:
        embed = discord.Embed(title="Island Sanctuary workshop has reset!")
        embed.set_image(url="https://static.abstractumbra.dev/images/sanctuary.png")
        embed.timestamp = self.next_reset(source=when)

        return embed


async def setup(bot: Graha, /) -> None:
    await bot.add_cog(IslandSanctuary(bot))
