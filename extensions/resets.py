"""
This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""

from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING, ClassVar

import discord
from discord import app_commands

from utilities.containers.cactpot import Datacenter, Region
from utilities.shared.cog import BaseCog
from utilities.shared.time import Weekday, resolve_next_weekday

if TYPE_CHECKING:
    from bot import Graha
    from extensions.triple_triad import TripleTriad
    from utilities.context import Interaction


LOGGER = logging.getLogger(__name__)


class Resets(BaseCog["Graha"], name="Reset Information"):
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

    async def _wait_for_next_cactpot(self, dt: datetime.datetime, /) -> tuple[Region, int]:
        wd = dt.weekday()
        if wd not in (5, 6):
            LOGGER.warning(
                "[Resets] -> {Waiting for Cactpot} :: Called on a non-weekend (at %r). Altering and waiting.",
                str(dt),
            )
            dt = resolve_next_weekday(
                target=Weekday.saturday,
                current_week_included=True,
                before_time=datetime.time(tzinfo=datetime.UTC),
            ).replace(hour=0, minute=0, second=0, microsecond=0)
            wd = dt.weekday()

        # special case sunday for NA
        if dt.weekday() == 6:
            when = resolve_next_weekday(
                target=Weekday.sunday,
                source=dt,
                current_week_included=True,
                before_time=datetime.time(hour=1, minute=45, second=0, microsecond=0, tzinfo=datetime.UTC),
            ).replace(hour=1, minute=45, second=0, microsecond=0)

            LOGGER.info("[Resets] -> {Waiting for Cactpot} :: Next cactpot schedule is NA (at %r).", str(when))
            await discord.utils.sleep_until(when)
            return Region.NA, 16

        # saturday here
        if dt.hour > 1 and dt.hour < 9:
            when = resolve_next_weekday(
                target=Weekday.saturday,
                source=dt,
                current_week_included=True,
                before_time=datetime.time(hour=8, minute=45, second=0, microsecond=0, tzinfo=datetime.UTC),
            ).replace(hour=8, minute=45, second=0, microsecond=0)
            LOGGER.info("[Resets] -> {Waiting for Cactpot} :: Next cactpot schedule is OCE (at %r).", str(when))

            await discord.utils.sleep_until(when)
            return Region.OCE, 128
        if dt.hour > 9 and dt.hour < 12:
            when = resolve_next_weekday(
                target=Weekday.saturday,
                source=dt,
                current_week_included=True,
                before_time=datetime.time(hour=11, minute=45, second=0, microsecond=0, tzinfo=datetime.UTC),
            ).replace(hour=11, minute=45, second=0, microsecond=0)
            LOGGER.info("[Resets] -> {Waiting for Cactpot} :: Next cactpot schedule is JP (at %r).", str(when))

            await discord.utils.sleep_until(when)
            return Region.JP, 64

        when = resolve_next_weekday(
            target=Weekday.saturday,
            source=dt,
            current_week_included=True,
            before_time=datetime.time(hour=18, minute=45, second=0, microsecond=0, tzinfo=datetime.UTC),
        ).replace(hour=18, minute=45, second=0, microsecond=0)
        LOGGER.info("[Resets] -> {Waiting for Cactpot} :: Next cactpot schedule is EU (at %r).", str(when))

        await discord.utils.sleep_until(when)
        return Region.EU, 32

    def _get_cactpot_reset_data(self, region_or_dc: Datacenter | Region, /) -> tuple[datetime.datetime, Region]:
        value = region_or_dc.value if isinstance(region_or_dc, Datacenter) else region_or_dc

        match value:
            case Region.NA:
                time = datetime.time(hour=2, tzinfo=datetime.UTC)
            case Region.EU:
                time = datetime.time(hour=19, tzinfo=datetime.UTC)
            case Region.JP:
                time = datetime.time(hour=12, tzinfo=datetime.UTC)
            case Region.OCE:
                time = datetime.time(hour=9, tzinfo=datetime.UTC)

        wd = Weekday.saturday
        # special case NA since it's technically sunday
        if value is Region.NA:
            wd = Weekday.sunday

        date = resolve_next_weekday(
            source=datetime.datetime.now(datetime.UTC),
            target=wd,
            current_week_included=True,
            before_time=time,
        )
        return datetime.datetime.combine(date.date(), time, tzinfo=datetime.UTC), value

    def _get_cactpot_embed(self, datacenter: Datacenter | Region, /) -> discord.Embed:
        next_, region = self._get_cactpot_reset_data(datacenter)

        next_full_fmt = discord.utils.format_dt(next_, "F")
        next_rel_fmt = discord.utils.format_dt(next_, "R")

        fmt = f"Cashing out is available at {next_full_fmt} ({next_rel_fmt}) for {region.resolved_name()} datacenters!"

        embed = discord.Embed(title=f"[{region.name}] Jumbo Cactpot cashout!", colour=discord.Colour.random())
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
        weeklies_fmt = self.WEEKLIES[:]
        tt: TripleTriad | None = self.bot.get_cog("TripleTriad")  # pyright: ignore[reportAssignmentType] # cog downcasting
        if tt:
            tournament_prose = "TT Tourament entry" if tt._in_tournament_week(next_weekly) else "TT Tournament rewards"
            weeklies_fmt.insert(3, tournament_prose)

        weekly_fmt = f"Resets at {weekly_dt_full} ({weekly_dt_relative})\n\n" + "\n".join(weeklies_fmt)

        embed = discord.Embed(colour=discord.Colour.random())
        embed.set_thumbnail(
            url="https://media.discordapp.net/attachments/872373121292853248/991352363577250003/unknown.png?width=198&height=262",
        )
        embed.title = "Weekly Reset Details!"
        embed.add_field(name="Weekly Reset", value=weekly_fmt, inline=False)
        embed.timestamp = next_weekly

        return embed

    @app_commands.command(name="reset-information")
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.describe(
        daily="Whether to show information on daily resets, or not.",
        weekly="Whether to show information on daily resets, or not.",
        ephemeral="Whether to show the data privately to you, or not.",
    )
    async def resets_summary(
        self,
        interaction: Interaction,
        daily: bool = True,  # noqa: FBT001, FBT002 # required by dpy
        weekly: bool = True,  # noqa: FBT001, FBT002 # required by dpy
        ephemeral: bool = True,  # noqa: FBT001, FBT002 # required by dpy
    ) -> None:
        """Sends a summary of the daily and weekly reset information."""

        if not any([daily, weekly]):
            return await interaction.response.send_message(
                "Well... you need to request at least one of the daily or weekly items.",
                ephemeral=True,
            )

        embeds = []
        if daily:
            embeds.append(self._get_daily_reset_embed())
        if weekly:
            embeds.append(self._get_weekly_reset_embed())

        return await interaction.response.send_message(embeds=embeds, ephemeral=ephemeral)

    @app_commands.command()
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.describe(
        region="Choose a region to show the information for. Will show all regions if no choice is made.",
        ephemeral="Whether to show the data privately to you, or not.",
    )
    async def cactpot(self, interaction: Interaction, region: Region | None = None, ephemeral: bool = True) -> None:  # noqa: FBT001, FBT002 # required by dpy
        """Shows data on when the next Jumbo Cactpot calling is!"""
        regions = [region] if region else Region
        embeds = [self._get_cactpot_embed(reg) for reg in regions]

        return await interaction.response.send_message(embeds=embeds, ephemeral=ephemeral)


async def setup(bot: Graha) -> None:
    await bot.add_cog(Resets(bot))
