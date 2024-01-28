"""
This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""

from __future__ import annotations

import datetime
import zoneinfo
from typing import TYPE_CHECKING, ClassVar

import discord
from discord.ext import commands

from utilities.cog import GrahaBaseCog as BaseCog
from utilities.containers.cactpot import Datacenter, Region
from utilities.shared.time import Weekday, resolve_next_weekday

if TYPE_CHECKING:
    from bot import Graha
    from utilities.context import Context


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

    def _get_next_datacenter_cactpot_data(self, dt: datetime.datetime | None = None) -> tuple[Region, int]:
        # assuming we're calling this on a saturday and also the tz will be los angeles (PST)
        now = dt or datetime.datetime.now(zoneinfo.ZoneInfo("America/Los_Angeles"))

        if now.hour > 11 and now.hour < 18:
            return Region.NA, 16
        elif now.hour > 4 and now.hour < 11:
            return Region.EU, 32
        elif now.hour > 1 and now.hour < 4:
            return Region.JP, 64
        else:
            return Region.OCE, 128

    def _get_cactpot_reset_data(self, region_or_dc: Datacenter | Region, /) -> tuple[datetime.datetime, Region]:
        date = resolve_next_weekday(target=Weekday.saturday, current_week_included=True)

        tz = zoneinfo.ZoneInfo("America/Los_Angeles")

        value = region_or_dc.value if isinstance(region_or_dc, Datacenter) else region_or_dc

        match value:
            case Region.NA:
                time = datetime.time(hour=18, tzinfo=tz)
            case Region.EU:
                time = datetime.time(hour=11, tzinfo=tz)
            case Region.JP:
                time = datetime.time(hour=4, tzinfo=tz)
            case Region.OCE:
                time = datetime.time(hour=1, tzinfo=tz)

        return datetime.datetime.combine(date.date(), time, tzinfo=tz), value

    def _get_cactpot_embed(self, datacenter: Datacenter | Region, /) -> discord.Embed:
        next_, region = self._get_cactpot_reset_data(datacenter)

        next_full_fmt = discord.utils.format_dt(next_, "F")
        next_rel_fmt = discord.utils.format_dt(next_, "R")

        fmt = f"Cashing out is available at {next_full_fmt} ({next_rel_fmt}) for {region.resolved_name()} datacenters!"

        embed = discord.Embed(title="Jumbo Cactpot cashout!", colour=discord.Colour.random())
        embed.set_thumbnail(
            url="https://media.discordapp.net/attachments/872373121292853248/991352363577250003/unknown.png?width=198&height=262",
        )
        embed.description = fmt

        return embed

    def _get_daily_reset_time(self) -> datetime.datetime:
        now = datetime.datetime.now(datetime.UTC)
        next_reset = now + datetime.timedelta(days=1) if now.hour >= 15 else now

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
        time_ = datetime.time(hour=8, minute=0, second=0, microsecond=0)
        next_ = resolve_next_weekday(
            target=Weekday.tuesday,
            current_week_included=True,
            before_time=time_,
        )

        return datetime.datetime.combine(next_, time_, tzinfo=datetime.UTC)

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
