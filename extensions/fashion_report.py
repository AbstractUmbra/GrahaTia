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

import bs4
import discord
from discord.ext import commands, tasks
from discord.utils import MISSING
from jishaku.functools import executor_function

from utilities.context import Context as BaseContext
from utilities.shared.cache import cache
from utilities.shared.cog import BaseCog
from utilities.shared.formats import plural
from utilities.shared.time import Weekday, resolve_next_weekday

if TYPE_CHECKING:
    from collections.abc import Mapping

    from bot import Graha
    from utilities.containers.event_subscription import EventSubConfig

FASHION_REPORT_PATTERN: re.Pattern[str] = re.compile(
    r"Fashion Report - Full Details - For Week of (?P<date>[0-9]{1,2}/[0-9]{1,2}/[0-9]{4}) \(Week (?P<week_num>[0-9]{3})\)"
)
LOGGER = logging.getLogger(__name__)

MIMIC_HEADERS: Mapping[str, str] = {
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.5",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
}


class Context(BaseContext):
    subscription_config: EventSubConfig


class KaiyokoSubmission(NamedTuple):
    prose: str
    reset: str
    dt: datetime.datetime
    post_url: str
    image_url: str
    colour: discord.Colour


class KaiyokoHTML(NamedTuple):
    match: re.Match[str]
    child: bs4.PageElement
    post_url: str
    image_url: str


class FashionReport(BaseCog["Graha"]):
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
        self.current_report: KaiyokoSubmission = MISSING
        self._report_task: asyncio.Task[None] = asyncio.create_task(self._wait_for_report())

    def cog_unload(self) -> None:
        self._report_task.cancel("Unloading FashionReport cog.")
        self.reset_cache.cancel()

    def _reset_state(self, *, dt: datetime.datetime | None = None) -> bool:
        self.current_report = MISSING
        self._report_task.cancel("Manual cache reset.")

        try:
            self._report_task.exception()
        except (asyncio.CancelledError, asyncio.InvalidStateError):
            LOGGER.warning("[FashionReport] -> {Reset State} :: Task was in error state.")
            pass

        dt = dt or self._resolve_next_window(dt)
        self._report_task = asyncio.create_task(self._wait_for_report(dt=dt))
        return self._filter_submissions.invalidate(self)

    def _resolve_next_window(self, dt: datetime.datetime | None = None) -> datetime.datetime:
        dt = dt or datetime.datetime.now(datetime.UTC)

        next_weekday = Weekday.friday if 1 < dt.weekday() <= 4 else Weekday.tuesday
        return resolve_next_weekday(
            source=dt,
            target=next_weekday,
            current_week_included=True,
            # before_time=datetime.time(hour=8, tzinfo=datetime.UTC),
        )

    async def _wait_for_report(self, *, dt: datetime.datetime | None = None) -> None:
        dt = dt or datetime.datetime.now(datetime.UTC)
        if self.current_report is not MISSING:
            LOGGER.warning("[FashionReport] :: Report already cached, is the cache stale?")
            return

        LOGGER.info("[FashionReport] :: Starting loop to gain report.")

        tries = 0
        while True:
            tries += 1
            try:
                submission = await self._filter_submissions(dt=dt)
            except ValueError:
                to_sleep = 60 * tries
                LOGGER.warning("[FashionReport] :: Submission not found, sleeping for %s", to_sleep)
                await asyncio.sleep(to_sleep)
                continue
            else:
                LOGGER.info("[FashionReport] :: Found report, setting attribute.")
                self.current_report = submission
                break

        LOGGER.info("[FashionReport] :: gotten report at %s", datetime.datetime.now(datetime.UTC))

    def weeks_since_start(self, dt: datetime.datetime) -> int:
        td = dt - self.FASHION_REPORT_START

        seconds = round(td.total_seconds())
        weeks, _ = divmod(seconds, 60 * 60 * 24 * 7)

        return weeks

    def humanify_delta(self, *, td: datetime.timedelta, format_: str, with_seconds: bool = False) -> str:
        seconds = round(td.total_seconds())

        days, seconds = divmod(seconds, 60 * 60 * 24)
        hours, seconds = divmod(seconds, 60 * 60)
        minutes, seconds = divmod(seconds, 60)

        fmt = f"{format_} in "
        if days:
            fmt += f"{plural(days):day}, "

        if with_seconds:
            fmt += f"{plural(hours):hour}, {plural(minutes):minute} and {plural(seconds):second}."
        else:
            fmt += f"{plural(hours):hour} and {plural(minutes):minute}."

        return fmt

    @executor_function
    def _scrape_kaiyoko_page(self, page_html: str, *, dt: datetime.datetime) -> KaiyokoHTML:
        soup = bs4.BeautifulSoup(page_html, "lxml")

        posts = soup.find("div", id="posts")
        if not posts or not isinstance(posts, bs4.Tag):
            raise ValueError("Seems the HTML is malformed.")

        children = posts.find_all("div", {"class": "post"})
        if not children:
            raise ValueError("Seems the inner HTML is malformed?")

        for child in children:
            child: bs4.PageElement
            title = child.find_next("h2", {"class": "post_title"})
            if title and isinstance(title, bs4.Tag):
                post_a_tag, *_ = title.select("a:not(.post_flair)")
                post_title = post_a_tag.text
                post_url = post_a_tag.attrs["href"]
                match = FASHION_REPORT_PATTERN.search(post_title)
                if not match:
                    continue

                if self.weeks_since_start(dt) != int(match["week_num"]):
                    continue

                media_content_tag = child.find_next("div", {"class": "post_media_content"})
                assert isinstance(media_content_tag, bs4.Tag)
                media_content_image_tag = media_content_tag.find_next("image")
                assert isinstance(media_content_image_tag, bs4.Tag)
                image_url = media_content_image_tag.attrs["href"]

                return KaiyokoHTML(match, child, f"https://reddit.com{post_url}", f"https://libreddit.bus-hit.me{image_url}")

        raise ValueError("Can't find any posts for Fashion Report.")  # should be unreachable

    async def get_kaiyoko_submissions(self) -> str:
        async with self.bot.session.get(
            "https://libreddit.bus-hit.me/user/kaiyoko/submitted", headers=MIMIC_HEADERS
        ) as resp:
            return await resp.text()

    @cache(ignore_kwargs=True)
    async def _filter_submissions(self, *, dt: datetime.datetime) -> KaiyokoSubmission:
        html = await self.get_kaiyoko_submissions()
        node = await self._scrape_kaiyoko_page(html, dt=dt)

        header = node.child.find_next("p", {"class": "post_header"})
        assert isinstance(header, bs4.Tag)
        span = header.find_next("span", {"class": "created"})
        assert isinstance(span, bs4.Tag)
        dt_fmt = span.attrs["title"]

        created = datetime.datetime.strptime(dt_fmt, "%b %d %Y, %H:%M:%S UTC").replace(tzinfo=datetime.UTC)

        if (dt - created) > datetime.timedelta(days=7):
            raise ValueError("Invalid HTML node found.")

        wd = dt.isoweekday()
        reset_time = datetime.time(hour=8, minute=0, second=0)
        is_available = (wd == 5 and dt.time() > reset_time) or wd == 1 or wd >= 6 or (wd == 2 and dt.time() < reset_time)

        if is_available:
            diff = 2 - wd  # next tuesday
            fmt = "Judging ends"
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
        reset_str = (
            self.humanify_delta(td=(upcoming_event - dt), format_=fmt)
            + f"\n{discord.utils.format_dt(upcoming_event, 'F')} ({discord.utils.format_dt(upcoming_event, 'R')})"
        )

        return KaiyokoSubmission(
            f"Fashion Report details for week of {node.match['date']} (Week {node.match['week_num']})",
            reset_str,
            upcoming_event,
            node.post_url,
            node.image_url,
            colour,
        )

        raise ValueError("Unable to fetch the reddit post details.")

    def generate_fashion_embed(self) -> discord.Embed:
        # guarded
        submission = self.current_report

        embed = discord.Embed(title=submission.prose, url=submission.post_url, colour=submission.colour)
        embed.description = submission.reset
        embed.set_image(url=submission.image_url)

        return embed

    @commands.group(name="fashionreport", aliases=["fr", "fashion-report"], invoke_without_command=True)
    async def fashion_report(self, ctx: Context) -> None:
        """Fetch the latest fashion report data from /u/Kaiyoko."""

        if self.current_report:
            embed = self.generate_fashion_embed()
            send = ctx.send
        else:
            await ctx.send("Sorry, the post for this week isn't up yet, I'll reply when it is!")
            await self._report_task
            embed = self.generate_fashion_embed()
            send = ctx.message.reply

        await send(embed=embed)

    @commands.is_owner()
    @fashion_report.command(name="cache", aliases=["cache-reset"], hidden=True)
    async def fr_cache(self, ctx: Context) -> None:
        invalidated = self._reset_state()
        return await ctx.message.add_reaction(ctx.tick(invalidated))

    @tasks.loop(time=datetime.time(hour=8, tzinfo=datetime.UTC))
    async def reset_cache(self) -> None:
        if datetime.datetime.now(datetime.UTC).weekday() != 4:
            LOGGER.warning("[FashionReport] :: Tried to reset cache on non-Friday.")
            return

        LOGGER.warning("[FashionReport] :: Resetting cache and state.")
        self._reset_state()


async def setup(bot: Graha) -> None:
    await bot.add_cog(FashionReport(bot))
