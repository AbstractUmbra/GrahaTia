from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

import discord

from utilities.shared.cog import BaseCog
from utilities.shared.formats import random_pastel_colour, ts
from utilities.shared.time import Weekday, resolve_next_weekday

if TYPE_CHECKING:
    from bot import Graha

TOURNAMENT_START_DATE: datetime.datetime = datetime.datetime(year=2024, month=12, day=24, hour=8, tzinfo=datetime.UTC)
# this isn't actually the start date, but this is the date we'll start recording from.
# We only need to work out if the current week is fortnightly


class TripleTriad(BaseCog["Graha"]):
    def __init__(self, bot: Graha, /) -> None:
        super().__init__(bot)

    def _resolve_next_tournament_window(self, dt: datetime.datetime | None = None, /) -> datetime.datetime:
        dt = dt or datetime.datetime.now(datetime.UTC)

        then = resolve_next_weekday(
            target=Weekday.tuesday,
            source=dt,
            current_week_included=True,
            before_time=datetime.time(hour=8, tzinfo=datetime.UTC),
        )
        if (then - TOURNAMENT_START_DATE).days % 14 != 0:
            then = resolve_next_weekday(
                target=Weekday.tuesday,
                source=dt + datetime.timedelta(days=7),
                current_week_included=True,
                before_time=datetime.time(hour=8, tzinfo=datetime.UTC),
            )

        return then.replace(hour=8, minute=0, second=0, microsecond=0, tzinfo=datetime.UTC)

    def _in_tournament_week(self, dt: datetime.datetime | None = None, /) -> bool:
        dt = dt or datetime.datetime.now(datetime.UTC)

        td = dt - TOURNAMENT_START_DATE

        return (td.days % 14) < 7

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

    def generate_tournament_embed(self, dt: datetime.datetime | None = None, /) -> discord.Embed:
        dt = dt or self._resolve_next_tournament_window()
        then = dt + datetime.timedelta(days=7)

        embed = discord.Embed(title="Triple Triad Tournament signup time!", colour=random_pastel_colour()).set_thumbnail(
            url="https://media.discordapp.net/attachments/872373121292853248/991352363577250003/unknown.png?width=198&height=262",
        )
        embed.description = f"You can claim your winnings from this tournament at {ts(then):F} (in {ts(then):R})!"

        return embed


async def setup(bot: Graha, /) -> None:
    return await bot.add_cog(TripleTriad(bot))
