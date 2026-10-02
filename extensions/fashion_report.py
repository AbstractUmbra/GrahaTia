"""
This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import re
from typing import TYPE_CHECKING, NamedTuple

import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.utils import MISSING

from utilities.context import Context as BaseContext, Interaction
from utilities.shared.cache import cache
from utilities.shared.cog import BaseCog
from utilities.shared.time import Weekday, resolve_next_weekday, resolve_previous_weekday

if TYPE_CHECKING:
    from bot import Graha
    from utilities.containers.event_subscription import EventSubConfig
    from utilities.shared._types.xiv.fashionreportxiv import ReportStateResponse

FASHION_REPORT_PATTERN: re.Pattern[str] = re.compile(
    r"Fashion Report - Full Details - For Week of (?P<date>[0-9]{1,2}/[0-9]{1,2}/[0-9]{4}) \(Week (?P<week_num>[0-9]{3})\)",
)
FASHION_REPORT_START: datetime.datetime = datetime.datetime(
    year=2018,
    month=1,
    day=26,
    hour=8,
    minute=0,
    second=0,
    microsecond=0,
    tzinfo=datetime.UTC,
)
API_BASE_URL = "https://fashionreportxiv.com"

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.DEBUG)


def resolve_next_window() -> datetime.datetime:
    dt = datetime.datetime.now(datetime.UTC)

    next_weekday = Weekday.friday if 1 < dt.weekday() <= 4 else Weekday.tuesday
    return resolve_next_weekday(source=dt, target=next_weekday, current_week_included=True)


def weeks_since_start(dt: datetime.datetime, /) -> int:
    td = dt - FASHION_REPORT_START

    seconds = round(td.total_seconds())
    weeks, _ = divmod(seconds, 60 * 60 * 24 * 7)

    return weeks


class Context(BaseContext):
    subscription_config: EventSubConfig


class FashionReportSubmission(NamedTuple):
    title: str
    prose: str
    url: str
    week_num: int
    created_at: datetime.datetime

    @staticmethod
    def is_available() -> bool:
        now = datetime.datetime.now(datetime.UTC)
        wd = now.isoweekday()
        reset_time = datetime.time(hour=8, minute=0, second=0)
        # return True on the following criteria:
        # it is Monday
        # it is Tuesday BEFORE 8am UTC
        # it is Friday AFTER 8am UTC
        # it is Saturday or Sunday
        return wd == 1 or (wd == 2 and now.time() < reset_time) or (wd == 5 and now.time() > reset_time) or wd >= 6

    def _has_new_data(self) -> bool:
        next_window = resolve_next_window()
        since_start = weeks_since_start(next_window)

        return self.week_num == since_start

    def start_period(self) -> datetime.datetime:
        next_ = self._next_event()
        if next_.weekday() == 4:
            return next_
        # it will be 4
        return resolve_next_weekday(target=Weekday.friday, source=next_, current_week_included=True)

    def judging_concludes(self) -> datetime.datetime:
        start = self.start_period()
        return resolve_next_weekday(
            target=Weekday.tuesday, source=start, current_week_included=True, before_time=datetime.time(hour=8)
        )

    def _next_event(self) -> datetime.datetime:
        now = datetime.datetime.now(datetime.UTC)
        wd = now.isoweekday()
        reset_time = datetime.time(hour=8, minute=0, second=0)
        is_available = self.is_available()

        diff = 2 - wd if is_available else 5 - wd

        if (diff == 0 and now.time() < reset_time) or (diff == 5 and now.time() > reset_time):
            days = 0
        else:
            days = diff + 7 if diff <= 0 else diff

        return (now + datetime.timedelta(days=days)).replace(hour=8, minute=0, second=0, microsecond=0)


class FashionReport(BaseCog["Graha"]):
    def __init__(self, bot: Graha) -> None:
        super().__init__(bot)
        self.reset_cache.start()
        self.current_report: FashionReportSubmission = MISSING
        self.report_task: asyncio.Task[None] = asyncio.create_task(self._wait_for_report())
        self._ready: asyncio.Event = asyncio.Event()

    async def cog_load(self) -> None:
        # we don't add this on init since loading this Cog will fail if this method errors,
        # so if the api request doesn't work, we don't start this extension.
        self._ready.set()

    def cog_unload(self) -> None:
        self.report_task.cancel("Unloading FashionReport cog.")
        self.reset_cache.cancel()
        self._ready.clear()

    def reset_state(self) -> bool:
        self.current_report = MISSING
        self.report_task.cancel("Manual cache reset.")

        try:
            self.report_task.exception()
        except (asyncio.CancelledError, asyncio.InvalidStateError):
            LOGGER.warning("[FashionReport] -> {Reset State} :: Task was in error state.")

        self.report_task = asyncio.create_task(self._wait_for_report())
        return self._fetch_report.invalidate(self)

    async def _wait_for_report(self) -> None:
        await self._ready.wait()

        if self.current_report is not MISSING:
            LOGGER.warning("[FashionReport] :: Report already cached, is the cache stale?")
            return

        LOGGER.info("[FashionReport] :: Starting loop to gain report.")

        while True:
            dt = resolve_next_window()
            try:
                submission = await self._fetch_report(dt=dt)
            except ValueError:
                LOGGER.warning("[FashionReport] :: Submission not found, sleeping for 5m.")
                LOGGER.debug("[FashionReport] :: Next window would be %r (week #%s)", dt.isoformat(), weeks_since_start(dt))
                self._fetch_report.invalidate(self)
                await asyncio.sleep(300)
                continue
            else:
                LOGGER.info("[FashionReport] :: Found report, setting attribute.")
                self.current_report = submission
                break

        LOGGER.info(
            "[FashionReport] :: gotten report at %r (report created at %r)",
            datetime.datetime.now(datetime.UTC).isoformat(),
            submission.created_at.isoformat(),
        )

    @cache(ignore_kwargs=True)
    async def _fetch_report(self, *, dt: datetime.datetime) -> FashionReportSubmission:
        week_num = weeks_since_start(dt)
        this_window = resolve_previous_weekday(target=Weekday.tuesday, source=dt, current_week_included=True)

        async with self.bot.session.get(f"{API_BASE_URL}/api/report-state") as resp:
            resp.raise_for_status()
            data: ReportStateResponse = await resp.json()

        response_num = int(data["lastOptions"]["week"])

        if week_num != int(data["lastOptions"]["week"]):
            LOGGER.warning(
                "[FashionReport] -> [API] :: Found a response but for bad week #%s (should be #%s)", response_num, week_num
            )
            raise ValueError("No report found for the current week")

        LOGGER.info("[FashionReport] -> [API] :: Found report for week #%s", week_num)

        return FashionReportSubmission(
            data["lastOptions"]["reportTitle"],
            f"Fashion Report details for the week of {this_window:%m/%d/%Y} (Week {week_num})",
            data["links"]["results"],
            week_num,
            datetime.datetime.fromtimestamp(data["easy80"]["_updatedAt"] / 1000, tz=datetime.UTC),
        )

    def generate_fashion_embed(self) -> discord.Embed:
        # guarded
        submission = self.current_report

        embed = discord.Embed(title=submission.prose, url=submission.url)
        submission_start_string = (
            f"{discord.utils.format_dt(submission.start_period(), 'F')} "
            f"({discord.utils.format_dt(submission.start_period(), 'R')})"
        )
        submission_end_string = (
            f"{discord.utils.format_dt(submission.judging_concludes(), 'F')} "
            f"({discord.utils.format_dt(submission.judging_concludes(), 'R')})"
        )

        embed.description = (
            f"### {submission.title}\n\n"
            f"Judging period starts at {submission_start_string}.\n"
            f"Judging period ends at {submission_end_string}."
        )
        embed.set_footer(text="If the title and image title do not match, it means the new image is not created yet!")

        if submission.is_available() or submission._has_new_data():
            embed.colour = discord.Colour.green()
        else:
            embed.colour = discord.Colour.dark_orange()
            embed.set_footer(text="The above image may be for the previous Friday's Fashion Report!")

        # Discord caching is stupid so now I add the query param of week num to help
        embed.set_image(url=f"{API_BASE_URL}/hint.png?v={submission.week_num}")

        return embed

    @app_commands.command(name="fashion-report")
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.describe(ephemeral="Whether to show the data privately to you, or not.")
    async def fashion_report_app_cmd(self, interaction: Interaction, ephemeral: bool = True) -> None:  # ruff: ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument] # required by dpy
        """Get the latest available Fashion Report information from /u/Gottesstrafe!"""

        if not self.current_report:
            await interaction.response.send_message(
                "Sorry, but I haven't found the post from Kaiyoko/Gottesstrafe yet, try again later?",
                ephemeral=ephemeral,
            )
            return

        embed = self.generate_fashion_embed()
        await interaction.response.send_message(embed=embed, ephemeral=ephemeral)

    @commands.group(name="fashionreport", aliases=["fr", "fashion-report"], invoke_without_command=True)
    async def fashion_report(self, ctx: Context) -> None:
        """Fetch the latest fashion report data from /u/KaiyokoStar or /u/Gottesstrafe."""

        if self.current_report:
            embed = self.generate_fashion_embed()
            send = ctx.send
        else:
            await ctx.send("Sorry, the post for this week isn't up yet, I'll reply when it is!")
            await self.report_task
            embed = self.generate_fashion_embed()
            send = ctx.message.reply

        await send(embeds=[embed])

    @commands.is_owner()
    @fashion_report.command(name="cache", aliases=["cache-reset"], hidden=True)
    async def fr_cache(self, ctx: Context) -> None:
        invalidated = self.reset_state()
        return await ctx.message.add_reaction(ctx.tick(invalidated))

    @tasks.loop(time=datetime.time(hour=8, tzinfo=datetime.UTC))
    async def reset_cache(self) -> None:
        if datetime.datetime.now(datetime.UTC).weekday() != 4:
            LOGGER.warning("[FashionReport] :: Tried to reset cache on non-Friday.")
            return

        LOGGER.warning("[FashionReport] :: Resetting cache and state.")
        self.reset_state()


async def setup(bot: Graha) -> None:
    await bot.add_cog(FashionReport(bot))
