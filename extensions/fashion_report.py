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
from utilities.exceptions import NoSubmissionFoundError
from utilities.shared.cache import cache
from utilities.shared.cog import BaseCog
from utilities.shared.reddit import RedditError, RedditHandler
from utilities.shared.time import Weekday, resolve_next_weekday

if TYPE_CHECKING:
    from bot import Graha
    from utilities.containers.event_subscription import EventSubConfig
    from utilities.shared._types.xiv.reddit.fashion_report import TopLevelListingResponse

FASHION_REPORT_PATTERN: re.Pattern[str] = re.compile(
    r"Fashion Report - Full Details - For Week of (?P<date>[0-9]{1,2}/[0-9]{1,2}/[0-9]{4}) \(Week (?P<week_num>[0-9]{3})\)",
)
LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.DEBUG)


class Context(BaseContext):
    subscription_config: EventSubConfig


class FashionReportSubmission(NamedTuple):
    prose: str
    url: str
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

    def next_event(self) -> datetime.datetime:
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
    AuthHandler: RedditHandler
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
        return self._filter_submissions.invalidate(self)

    @staticmethod
    def resolve_next_window() -> datetime.datetime:
        dt = datetime.datetime.now(datetime.UTC)

        next_weekday = Weekday.friday if 1 < dt.weekday() <= 4 else Weekday.tuesday
        return resolve_next_weekday(source=dt, target=next_weekday, current_week_included=True)

    async def _wait_for_report(self) -> None:
        await self._ready.wait()

        if self.current_report is not MISSING:
            LOGGER.warning("[FashionReport] :: Report already cached, is the cache stale?")
            return

        LOGGER.info("[FashionReport] :: Starting loop to gain report.")

        while True:
            dt = self.resolve_next_window()
            try:
                submission = await self._filter_submissions(dt=dt)
            except ValueError:
                LOGGER.warning("[FashionReport] :: Submission not found, sleeping for 5m.")
                LOGGER.debug("[FashionReport] :: Next window would be %r", dt.isoformat())
                self._filter_submissions.invalidate(self)
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

    def weeks_since_start(self, dt: datetime.datetime) -> int:
        td = dt - self.FASHION_REPORT_START

        seconds = round(td.total_seconds())
        weeks, _ = divmod(seconds, 60 * 60 * 24 * 7)

        return weeks

    @cache(ignore_kwargs=True)
    async def _filter_submissions(self, *, dt: datetime.datetime) -> FashionReportSubmission:
        try:
            submissions: TopLevelListingResponse = await self.bot.reddit.get(
                "https://oauth.reddit.com/user/Gottesstrafe/submitted",
            )
        except RedditError as err:
            raise RedditError("[Fashion Report] -> {Submission Filtering} :: Reddit API request failed") from err

        for submission in submissions["data"]["children"]:
            match = FASHION_REPORT_PATTERN.search(submission["data"]["title"])
            if not match:
                LOGGER.debug(
                    "[FashionReport] :: FashionReport author entry found but is not a fashion report: %r",
                    submission["data"]["title"],
                )
                continue

            if self.weeks_since_start(dt) != int(match["week_num"]):
                LOGGER.debug(
                    (
                        "[FashionReport] -> {Submission Filtering} :: Found a submission, "
                        "but doesn't match the expected week (wanted %s but got %s)"
                    ),
                    self.weeks_since_start(dt),
                    match["week_num"],
                )
                continue

            created = datetime.datetime.fromtimestamp(submission["data"]["created_utc"], tz=datetime.UTC)
            if (dt - created) < datetime.timedelta(days=7):
                LOGGER.debug(
                    "[FashionReport] -> {Submission Filtering} :: Found fashion report entry, current: %r",
                    created.isoformat(),
                )
                break
        else:
            raise NoSubmissionFoundError("No submissions matches")

        return FashionReportSubmission(
            f"Fashion Report details for week of {match['date']} (Week {match['week_num']})",
            submission["data"]["url"],
            created,
        )

    def generate_fashion_embed(self) -> discord.Embed:
        # guarded
        submission = self.current_report

        embed = discord.Embed(title=submission.prose, url=submission.url)
        dt_string = (
            f"{discord.utils.format_dt(submission.next_event(), 'F')} "
            f"({discord.utils.format_dt(submission.next_event(), 'R')})"
        )

        if submission.is_available():
            embed.description = f"Judging ends at {dt_string}"
            embed.colour = discord.Colour.green()
        else:
            embed.description = f"Judging becomes available at {dt_string}"
            embed.colour = discord.Colour.dark_orange()
            embed.set_footer(text="The above image is for the previous Friday's Fashion Report!")

        embed.set_image(url=submission.url)

        return embed

    @app_commands.command(name="fashion-report")
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.describe(ephemeral="Whether to show the data privately to you, or not.")
    async def fashion_report_app_cmd(self, interaction: Interaction, ephemeral: bool = True) -> None:  # noqa: FBT001, FBT002 # required by dpy
        """Get the latest available Fashion Report information from /u/Gottesstrafe!"""

        if not self.current_report:
            await interaction.response.send_message(
                "Sorry, but I haven't found the post from Gottesstrafe yet, try again later?",
                ephemeral=ephemeral,
            )
            return

        embed = self.generate_fashion_embed()
        await interaction.response.send_message(embed=embed, ephemeral=ephemeral)

    @commands.group(name="fashionreport", aliases=["fr", "fashion-report"], invoke_without_command=True)
    async def fashion_report(self, ctx: Context) -> None:
        """Fetch the latest fashion report data from /u/Gottesstrafe."""

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
