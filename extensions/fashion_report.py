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
from typing import TYPE_CHECKING, ClassVar, NamedTuple

import discord
from discord.ext import commands, tasks

from utilities.cog import GrahaBaseCog as BaseCog
from utilities.context import Context as BaseContext
from utilities.shared.cache import cache
from utilities.shared.formats import plural

if TYPE_CHECKING:
    from bot import Graha
    from utilities.containers.event_subscription import EventSubConfig
    from utilities.shared._types.xiv.reddit.kaiyoko import TopLevelListingResponse

FASHION_REPORT_PATTERN: re.Pattern[str] = re.compile(
    r"Fashion Report - Full Details - For Week of (?P<date>[0-9]{1,2}/[0-9]{1,2}/[0-9]{4}) \(Week (?P<week_num>[0-9]{3})\)"
)
LOGGER = logging.getLogger(__name__)


class Context(BaseContext):
    subscription_config: EventSubConfig


class KaiyokoSubmission(NamedTuple):
    prose: str
    reset: str
    dt: datetime.datetime
    url: str
    colour: discord.Colour


class FashionReport(BaseCog):
    FASHION_REPORT_START: ClassVar[datetime.datetime] = datetime.datetime(
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
        self.report_fut: asyncio.Future[KaiyokoSubmission] = asyncio.Future()
        self._report_task: asyncio.Task[None] = asyncio.create_task(self._wait_for_report())

    async def _wait_for_report(self, *, dt: datetime.datetime | None = None) -> None:
        dt = dt or datetime.datetime.now(datetime.UTC)
        if self.report_fut.done():
            return

        LOGGER.info("[FashionReport] :: Starting loop to gain report.")

        while True:
            try:
                submission = await self._filter_submissions(dt=dt)
            except ValueError:
                await asyncio.sleep(60 * 10)
                continue
            else:
                LOGGER.info("[FashionReport] :: Found report, setting future.")
                self.report_fut.set_result(submission)
                break

    def weeks_since_start(self, dt: datetime.datetime) -> int:
        td = dt - self.FASHION_REPORT_START

        seconds = round(td.total_seconds())
        weeks, _ = divmod(seconds, 60 * 60 * 24 * 7)

        return weeks

    def humanify_delta(self, *, td: datetime.timedelta, format_: str) -> str:
        seconds = round(td.total_seconds())

        days, seconds = divmod(seconds, 60 * 60 * 24)
        hours, seconds = divmod(seconds, 60 * 60)
        minutes, seconds = divmod(seconds, 60)

        fmt = f"{format_} in "
        if days:
            fmt += f"{plural(days):day}, "

        fmt += f"{plural(hours):hour}, {plural(minutes):minute} and {plural(seconds):second}."

        return fmt

    async def get_kaiyoko_submissions(self) -> TopLevelListingResponse:
        headers = {"User-Agent": "Graha Discord Bot (by /u/AbstractUmbra)"}
        async with self.bot.session.get("https://old.reddit.com/user/kaiyoko/submitted.json", headers=headers) as resp:
            data: TopLevelListingResponse = await resp.json()

        return data

    @cache(ignore_kwargs=True)
    async def _filter_submissions(self, *, dt: datetime.datetime) -> KaiyokoSubmission:
        submissions = await self.get_kaiyoko_submissions()

        for submission in submissions["data"]["children"]:
            if match := FASHION_REPORT_PATTERN.search(submission["data"]["title"]):
                if self.weeks_since_start(dt) != int(match["week_num"]):
                    continue

                created = datetime.datetime.fromtimestamp(submission["data"]["created_utc"], tz=datetime.UTC)
                if (dt - created) > datetime.timedelta(days=7):
                    continue

                wd = dt.isoweekday()
                reset_time = datetime.time(hour=8, minute=0, second=0)
                is_available = (
                    (wd == 5 and dt.time() > reset_time) or wd == 1 or wd >= 6 or (wd == 2 and dt.time() < reset_time)
                )

                if is_available:
                    diff = 2 - wd  # next tuesday
                    fmt = "No longer submissible"
                    colour = discord.Colour.green()
                else:
                    diff = 5 - wd  # next friday
                    fmt = "Judging becomes available"
                    colour = discord.Colour.dark_orange()

                if (diff == 0 and dt.time() < reset_time) or (diff == 5 and dt.time() > reset_time):
                    days = 0
                else:
                    days = diff + 7 if diff <= 0 else diff

                upcoming_event = (dt + datetime.timedelta(days=days)).replace(hour=8, minute=0, second=0, microsecond=0)
                reset_str = self.humanify_delta(td=(upcoming_event - dt), format_=fmt)

                return KaiyokoSubmission(
                    f"Fashion Report details for week of {match['date']} (Week {match['week_num']})",
                    reset_str,
                    upcoming_event,
                    submission["data"]["url"],
                    colour,
                )

        raise ValueError("Unable to fetch the reddit post details.")

    async def generate_fashion_embed(self, *, dt: datetime.datetime | None = None) -> discord.Embed:
        dt = dt or datetime.datetime.now(datetime.UTC)

        submission: KaiyokoSubmission = await self.report_fut

        embed = discord.Embed(title=submission.prose, url=submission.url, colour=submission.colour)
        full_timestmap = discord.utils.format_dt(submission.dt, "F")
        relative_timestmap = discord.utils.format_dt(submission.dt, "R")
        embed.description = f"{submission.reset}\nThis switches at {full_timestmap} ({relative_timestmap})."
        embed.set_image(url=submission.url)

        return embed

    @commands.is_owner()
    @commands.command(hidden=True)
    async def fr_cache(self, ctx: Context) -> None:
        invalidated = self._filter_submissions.invalidate(self)
        return await ctx.message.add_reaction(ctx.tick(invalidated))

    @commands.command(name="fashionreport", aliases=["fr", "fashion-report"])
    async def fashion_report(self, ctx: Context) -> None:
        """Fetch the latest fashion report data from /u/Kaiyoko."""
        embed = await self.generate_fashion_embed()

        await ctx.send(embed=embed)

    @tasks.loop(time=datetime.time(hour=15, tzinfo=datetime.UTC))
    async def reset_cache(self) -> None:
        LOGGER.warning("[FashionReport] :: Resetting cache and state.")
        self._filter_submissions.invalidate(self)
        self.report_fut = asyncio.Future()


async def setup(bot: Graha) -> None:
    await bot.add_cog(FashionReport(bot))
