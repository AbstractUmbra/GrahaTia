"""
This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, ClassVar

import discord
from discord.ext import commands

from utilities.cog import GrahaBaseCog as BaseCog
from utilities.context import Context


if TYPE_CHECKING:
    from bot import Graha


class Resets(BaseCog, name="Reset Information"):
    DAILIES: ClassVar[list[str]] = [
        "Beast Tribe",
        "Duty Roulettes",
        "Hunt Marks",
        "Mini Cactpot",
        "Levequests",
    ]
    WEEKLIES: ClassVar[list[str]] = [
        "Custom Delivery",
        "Doman Enclave",
        "Wondrous Tails",
        "Hunt Marks",
        "Raid Lockouts",
        "Challenge Log",
        "Masked Carnivale",
        "Squadron Priority Missions",
        "Currency Limits",
    ]

    def __init__(self, bot: Graha) -> None:
        super().__init__(bot)

    def _get_daily_reset_time(self) -> datetime.datetime:
        now = datetime.datetime.now(datetime.timezone.utc)
        if now.hour >= 15:
            next_reset = now + datetime.timedelta(days=1)
        else:
            next_reset = now

        return next_reset.replace(hour=15, minute=0, second=0, microsecond=0)

    def _get_daily_reset_embed(self) -> discord.Embed:
        next_daily = self._get_daily_reset_time()

        daily_dt_full = discord.utils.format_dt(next_daily, "F")
        daily_dt_relative = discord.utils.format_dt(next_daily, "R")
        daily_fmt = f"Resets at {daily_dt_full} ({daily_dt_relative})\n\n" + "\n".join(self.DAILIES)

        embed = discord.Embed(colour=discord.Colour.random())
        embed.set_thumbnail(
            url="https://media.discordapp.net/attachments/872373121292853248/991352363577250003/unknown.png?width=198&height=262",
        )
        embed.title = "Daily Reset Details!"
        embed.add_field(name="Daily Reset", value=daily_fmt, inline=False)
        embed.timestamp = next_daily

        return embed

    def _get_weekly_reset_time(self) -> datetime.datetime:
        now = datetime.datetime.now(datetime.timezone.utc).date()
        diff = 1 - now.weekday()
        days = diff + 7 if diff <= 0 else diff

        if days == 0:  # today is Tuesday
            days = 7

        next_reset = now + datetime.timedelta(days=days)  # 1 is Tuesday

        return datetime.datetime.combine(
            next_reset, datetime.time(hour=8, minute=0, second=0, microsecond=0), tzinfo=datetime.timezone.utc
        )

    def _get_weekly_reset_embed(self) -> discord.Embed:
        next_weekly = self._get_weekly_reset_time()

        weekly_dt_full = discord.utils.format_dt(next_weekly, "F")
        weekly_dt_relative = discord.utils.format_dt(next_weekly, "R")
        weekly_fmt = f"Resets at {weekly_dt_full} ({weekly_dt_relative})\n\n" + "\n".join(self.WEEKLIES)

        embed = discord.Embed(colour=discord.Colour.random())
        embed.set_thumbnail(
            url="https://media.discordapp.net/attachments/872373121292853248/991352363577250003/unknown.png?width=198&height=262",
        )
        embed.title = "Weekly Reset Details!"
        embed.add_field(name="Weekly Reset", value=weekly_fmt, inline=False)
        embed.timestamp = next_weekly

        return embed

    @commands.command(name="reset", aliases=["resets", "r"])
    async def resets_summary(self, ctx: Context) -> None:
        """Sends a reset information summary!"""

        daily = self._get_daily_reset_embed()
        weekly = self._get_weekly_reset_embed()

        await ctx.send(embeds=[daily, weekly])


async def setup(bot: Graha) -> None:
    await bot.add_cog(Resets(bot))
