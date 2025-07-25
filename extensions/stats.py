"""
This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""

from __future__ import annotations

import asyncio
import datetime
import gc
import io
import itertools
import logging
import operator
import pathlib
import re
import secrets
import sys
import textwrap
import traceback
from collections import Counter, defaultdict
from importlib.metadata import version as metadata_version
from typing import TYPE_CHECKING, Annotated, Any, TypedDict

import asyncpg
import discord
import psutil
import pygit2
from discord.ext import commands, menus, tasks

from utilities import formats, time
from utilities.context import Context, GuildContext
from utilities.shared.cog import BaseCog
from utilities.shared.formats import to_codeblock
from utilities.shared.paginator import FieldPageSource, RoboPages

if TYPE_CHECKING:
    from bot import Graha

log = logging.getLogger(__name__)

LOGGING_CHANNEL = 1037306036698230814


class DataBatchEntry(TypedDict):
    guild: int | None
    channel: int
    author: int
    used: str
    prefix: str
    command: str
    failed: bool
    app_command: bool


class LoggingHandler(logging.Handler):
    def __init__(self, cog: Stats) -> None:
        self.cog: Stats = cog
        super().__init__(logging.INFO)

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: PLR6301 # override
        return record.name == "discord.gateway"

    def emit(self, record: logging.LogRecord) -> None:
        self.cog.add_record(record)


_INVITE_REGEX = re.compile(r"(?:https?:\/\/)?discord(?:\.gg|\.com|app\.com\/invite)?\/[A-Za-z0-9]+")


def censor_invite(obj: Any, *, _regex: re.Pattern[str] = _INVITE_REGEX) -> str:
    return _regex.sub("[censored-invite]", str(obj))


def hex_value(arg: str) -> int:
    return int(arg, base=16)


def object_at(addr: int) -> Any | None:
    for o in gc.get_objects():
        if id(o) == addr:
            return o
    return None


class Stats(BaseCog["Graha"]):  # noqa: PLR0904
    """Bot usage statistics."""

    def __init__(self, bot: Graha) -> None:
        super().__init__(bot)
        self.process: psutil.Process = psutil.Process()
        self._batch_lock = asyncio.Lock()
        self._data_batch: list[DataBatchEntry] = []
        self.bulk_insert_loop.add_exception_type(asyncpg.PostgresConnectionError)
        self.bulk_insert_loop.start()
        self._logging_queue = asyncio.Queue()
        self.logging_worker.start()

    @property
    def display_emoji(self) -> discord.PartialEmoji:
        return discord.PartialEmoji(name="\N{BAR CHART}")

    async def bulk_insert(self) -> None:
        query = """INSERT INTO commands (guild_id, channel_id, author_id, used, prefix, command, failed, app_command)
                   SELECT x.guild, x.channel, x.author, x.used, x.prefix, x.command, x.failed, x.app_command
                   FROM jsonb_to_recordset($1::jsonb) AS
                   x(
                        guild BIGINT,
                        channel BIGINT,
                        author BIGINT,
                        used TIMESTAMP,
                        prefix TEXT,
                        command TEXT,
                        failed BOOLEAN,
                        app_command BOOLEAN
                    )
                """

        if self._data_batch:
            await self.bot.pool.execute(query, self._data_batch)
            total = len(self._data_batch)
            if total > 1:
                log.info("Registered %s commands to the database.", total)
            self._data_batch.clear()

    def cog_unload(self) -> None:
        self.bulk_insert_loop.stop()
        self.logging_worker.cancel()

    async def cog_check(self, ctx: Context) -> bool:  # noqa: PLR6301 # override
        return await ctx.bot.is_owner(ctx.author)

    @tasks.loop(seconds=10.0)
    async def bulk_insert_loop(self) -> None:
        async with self._batch_lock:
            await self.bulk_insert()

    @tasks.loop(seconds=0.0)
    async def logging_worker(self) -> None:
        record = await self._logging_queue.get()
        await self.send_log_record(record)

    async def register_command(self, ctx: Context) -> None:
        if ctx.command is None:
            return

        command = ctx.command.qualified_name
        is_app_command = ctx.interaction is not None
        self.bot.command_stats[command] += 1
        self.bot.command_types_used[is_app_command] += 1
        message = ctx.message
        destination = None
        if ctx.guild is None:
            destination = "Private Message"
            guild_id = None
        else:
            destination = f"#{message.channel} ({message.guild})"
            guild_id = ctx.guild.id

        if ctx.interaction and ctx.interaction.command:
            content = f"/{ctx.interaction.command.qualified_name}"
        else:
            content = message.content

        log.info("%s: %s in %s: %s", message.created_at, message.author, destination, content)
        async with self._batch_lock:
            self._data_batch.append(
                {
                    "guild": guild_id,
                    "channel": ctx.channel.id,
                    "author": ctx.author.id,
                    "used": message.created_at.isoformat(),
                    "prefix": ctx.prefix,  # pyright: ignore[reportArgumentType] # it's never None here
                    "command": command,
                    "failed": ctx.command_failed,
                    "app_command": is_app_command,
                },
            )

    @commands.Cog.listener()
    async def on_command_completion(self, ctx: Context) -> None:
        await self.register_command(ctx)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction) -> None:
        command = interaction.command
        # Check if a command is found and it's not a hybrid command
        # Hybrid commands are already counted via on_command_completion
        if (
            command is not None
            and interaction.type is discord.InteractionType.application_command
            and not command.__class__.__name__.startswith("Hybrid")  # Kind of awful, but it'll do
        ):
            # This is technically bad, but since we only access Command.qualified_name and it's
            # available on all types of commands then it's fine
            ctx = await self.bot.get_context(interaction, cls=Context)
            ctx.command_failed = interaction.command_failed or ctx.command_failed
            await self.register_command(ctx)

    @commands.Cog.listener()
    async def on_socket_event_type(self, event_type: str) -> None:
        self.bot.socket_stats[event_type] += 1

    @discord.utils.cached_property
    def webhook(self) -> discord.Webhook:
        return self.bot.logging_webhook

    @commands.command(hidden=True)
    @commands.is_owner()
    async def commandstats(self, ctx: Context, limit: int = 12) -> None:
        """Shows command stats.

        Use a negative number for bottom instead of top.
        This is only for the current session.
        """
        counter = self.bot.command_stats
        total = sum(counter.values())
        slash_commands = self.bot.command_types_used[True]

        delta = discord.utils.utcnow() - self.bot.start_time
        minutes = delta.total_seconds() / 60
        cpm = total / minutes

        if limit > 0:
            common = counter.most_common(limit)
            title = f"Top {limit} Commands"
        else:
            common = counter.most_common()[limit:]
            title = f"Bottom {limit} Commands"

        source = FieldPageSource(common, inline=True, clear_description=False)
        source.embed.title = title
        source.embed.description = f"{total} total commands used ({slash_commands} slash command uses) ({cpm:.2f}/minute)"

        pages = RoboPages(source, ctx=ctx, compact=True)
        await pages.start()

    @commands.command(hidden=True)
    async def socketstats(self, ctx: Context) -> None:
        delta = discord.utils.utcnow() - self.bot.start_time
        minutes = delta.total_seconds() / 60
        total = sum(self.bot.socket_stats.values())
        cpm = total / minutes
        await ctx.send(f"{total} socket events observed ({cpm:.2f}/minute):\n{self.bot.socket_stats}")

    def get_bot_uptime(self, *, brief: bool = False) -> str:
        return time.human_timedelta(self.bot.start_time, accuracy=None, brief=brief, suffix=False)

    @commands.command()
    async def uptime(self, ctx: Context) -> None:
        """Tells you how long the bot has been up for."""
        await ctx.send(f"Uptime: **{self.get_bot_uptime()}**")

    @staticmethod
    def format_commit(commit: pygit2.Commit) -> str:
        short, _, _ = commit.message.partition("\n")
        short_sha2 = str(commit.id)[0:6]
        commit_tz = datetime.timezone(datetime.timedelta(minutes=commit.commit_time_offset))
        commit_time = datetime.datetime.fromtimestamp(commit.commit_time).astimezone(commit_tz)

        # [`hash`](url) message (offset)
        offset = discord.utils.format_dt(commit_time.astimezone(datetime.UTC), "R")
        return f"[`{short_sha2}`](https://github.com/AbstractUmbra/Graha/commit/{commit.id}) {short} ({offset})"

    def get_last_commits(self, count: int = 3) -> str:
        repo = pygit2.Repository(".git")  # pyright: ignore[reportPrivateImportUsage] module not exported by upstream
        commits = list(itertools.islice(repo.walk(repo.head.target, pygit2.enums.SortMode.TOPOLOGICAL), count))
        return "\n".join(self.format_commit(c) for c in commits)

    @commands.command()
    async def about(self, ctx: Context) -> None:
        """Tells you information about the bot itself."""

        revision = self.get_last_commits()
        embed = discord.Embed(description="Latest Changes:\n" + revision)
        embed.title = "Official Bot Server Invite"
        embed.url = "https://discord.gg/aYGYJxwqe5"
        embed.colour = discord.Colour.blurple()

        embed.set_author(name=str(self.bot.owner), icon_url=self.bot.owner.display_avatar.url)

        # statistics
        total_members = 0
        total_unique = len(self.bot.users)

        text = 0
        voice = 0
        guilds = 0
        for guild in self.bot.guilds:
            guilds += 1
            if guild.unavailable:
                continue

            total_members += guild.member_count or 0
            for channel in guild.channels:
                if isinstance(channel, discord.TextChannel):
                    text += 1
                elif isinstance(channel, discord.VoiceChannel):
                    voice += 1

        embed.add_field(name="Members", value=f"{total_members} total\n{total_unique} unique")
        embed.add_field(name="Channels", value=f"{text + voice} total\n{text} text\n{voice} voice")

        cpu_count = psutil.cpu_count()
        assert cpu_count

        memory_usage = self.process.memory_full_info().uss / 1024**2
        cpu_usage = self.process.cpu_percent() / cpu_count
        embed.add_field(name="Process", value=f"{memory_usage:.2f} MiB\n{cpu_usage:.2f}% CPU")

        version = metadata_version("discord.py")
        embed.add_field(name="Guilds", value=guilds)
        embed.add_field(name="Commands Run", value=sum(self.bot.command_stats.values()))
        embed.add_field(name="Uptime", value=self.get_bot_uptime(brief=True))
        embed.set_footer(text=f"Made with discord.py v{version}", icon_url="http://i.imgur.com/5BFecvA.png")
        embed.timestamp = discord.utils.utcnow()
        await ctx.send(embeds=[embed])

    def censor_object(self, obj: str | discord.abc.Snowflake) -> str:
        if not isinstance(obj, str) and obj.id in self.bot.blacklist_data:
            return "[censored]"
        return censor_invite(obj)

    @staticmethod
    async def show_guild_stats(ctx: Context) -> None:
        assert ctx.guild

        lookup = (
            "\N{FIRST PLACE MEDAL}",
            "\N{SECOND PLACE MEDAL}",
            "\N{THIRD PLACE MEDAL}",
            "\N{SPORTS MEDAL}",
            "\N{SPORTS MEDAL}",
        )

        embed = discord.Embed(title="Server Command Stats", colour=discord.Colour.blurple())

        # total command uses
        query = "SELECT COUNT(*), MIN(used) FROM commands WHERE guild_id=$1;"
        count: tuple[int, datetime.datetime] = await ctx.db.fetchrow(query, ctx.guild.id)  # pyright: ignore[reportAssignmentType] # stub shenanigans

        embed.description = f"{count[0]} commands used."
        timestamp = count[1].replace(tzinfo=datetime.UTC) if count[1] else discord.utils.utcnow()

        embed.set_footer(text="Tracking command usage since").timestamp = timestamp

        query = """SELECT command,
                          COUNT(*) as "uses"
                   FROM commands
                   WHERE guild_id=$1
                   GROUP BY command
                   ORDER BY "uses" DESC
                   LIMIT 5;
                """

        records = await ctx.db.fetch(query, ctx.guild.id)

        value = (
            "\n".join(f"{lookup[index]}: {command} ({uses} uses)" for (index, (command, uses)) in enumerate(records))
            or "No Commands"
        )

        embed.add_field(name="Top Commands", value=value, inline=True)

        query = """SELECT command,
                          COUNT(*) as "uses"
                   FROM commands
                   WHERE guild_id=$1
                   AND used > (CURRENT_TIMESTAMP - INTERVAL '1 day')
                   GROUP BY command
                   ORDER BY "uses" DESC
                   LIMIT 5;
                """

        records = await ctx.db.fetch(query, ctx.guild.id)

        value = (
            "\n".join(f"{lookup[index]}: {command} ({uses} uses)" for (index, (command, uses)) in enumerate(records))
            or "No Commands."
        )
        embed.add_field(name="Top Commands Today", value=value, inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)

        query = """SELECT author_id,
                          COUNT(*) AS "uses"
                   FROM commands
                   WHERE guild_id=$1
                   GROUP BY author_id
                   ORDER BY "uses" DESC
                   LIMIT 5;
                """

        records = await ctx.db.fetch(query, ctx.guild.id)

        value = (
            "\n".join(
                f"{lookup[index]}: <@!{author_id}> ({uses} bot uses)" for (index, (author_id, uses)) in enumerate(records)
            )
            or "No bot users."
        )

        embed.add_field(name="Top Command Users", value=value, inline=True)

        query = """SELECT author_id,
                          COUNT(*) AS "uses"
                   FROM commands
                   WHERE guild_id=$1
                   AND used > (CURRENT_TIMESTAMP - INTERVAL '1 day')
                   GROUP BY author_id
                   ORDER BY "uses" DESC
                   LIMIT 5;
                """

        records = await ctx.db.fetch(query, ctx.guild.id)

        value = (
            "\n".join(
                f"{lookup[index]}: <@!{author_id}> ({uses} bot uses)" for (index, (author_id, uses)) in enumerate(records)
            )
            or "No command users."
        )

        embed.add_field(name="Top Command Users Today", value=value, inline=True)
        await ctx.send(embeds=[embed])

    @staticmethod
    async def show_member_stats(ctx: GuildContext, member: discord.Member) -> None:
        lookup = (
            "\N{FIRST PLACE MEDAL}",
            "\N{SECOND PLACE MEDAL}",
            "\N{THIRD PLACE MEDAL}",
            "\N{SPORTS MEDAL}",
            "\N{SPORTS MEDAL}",
        )

        embed = discord.Embed(title="Command Stats", colour=member.colour)
        embed.set_author(name=str(member), icon_url=member.display_avatar.url)

        # total command uses
        query = "SELECT COUNT(*), MIN(used) FROM commands WHERE guild_id=$1 AND author_id=$2;"
        count: tuple[int, datetime.datetime] = await ctx.db.fetchrow(query, ctx.guild.id, member.id)  # pyright: ignore[reportAssignmentType] # stub shenanigans

        embed.description = f"{count[0]} commands used."
        timestamp = count[1].replace(tzinfo=datetime.UTC) if count[1] else discord.utils.utcnow()

        embed.set_footer(text="First command used").timestamp = timestamp

        query = """SELECT command,
                          COUNT(*) as "uses"
                   FROM commands
                   WHERE guild_id=$1 AND author_id=$2
                   GROUP BY command
                   ORDER BY "uses" DESC
                   LIMIT 5;
                """

        records = await ctx.db.fetch(query, ctx.guild.id, member.id)

        value = (
            "\n".join(f"{lookup[index]}: {command} ({uses} uses)" for (index, (command, uses)) in enumerate(records))
            or "No Commands"
        )

        embed.add_field(name="Most Used Commands", value=value, inline=False)

        query = """SELECT command,
                          COUNT(*) as "uses"
                   FROM commands
                   WHERE guild_id=$1
                   AND author_id=$2
                   AND used > (CURRENT_TIMESTAMP - INTERVAL '1 day')
                   GROUP BY command
                   ORDER BY "uses" DESC
                   LIMIT 5;
                """

        records = await ctx.db.fetch(query, ctx.guild.id, member.id)

        value = (
            "\n".join(f"{lookup[index]}: {command} ({uses} uses)" for (index, (command, uses)) in enumerate(records))
            or "No Commands"
        )

        embed.add_field(name="Most Used Commands Today", value=value, inline=False)
        await ctx.send(embeds=[embed])

    @commands.group(invoke_without_command=True)
    @commands.guild_only()
    @commands.cooldown(1, 30.0, type=commands.BucketType.member)
    async def stats(self, ctx: GuildContext, *, member: discord.Member | None = None) -> None:
        """Tells you command usage stats for the server or a member."""
        async with ctx.typing():
            if member is None:
                await self.show_guild_stats(ctx)
            else:
                await self.show_member_stats(ctx, member)

    @stats.command(name="global")
    @commands.is_owner()
    async def stats_global(self, ctx: Context) -> None:
        """Global all time command statistics."""

        query = "SELECT COUNT(*) FROM commands;"
        total: tuple[int] = await ctx.db.fetchrow(query)  # pyright: ignore[reportAssignmentType] # stub shenanigans

        e = discord.Embed(title="Command Stats", colour=discord.Colour.blurple())
        e.description = f"{total[0]} commands used."

        lookup = (
            "\N{FIRST PLACE MEDAL}",
            "\N{SECOND PLACE MEDAL}",
            "\N{THIRD PLACE MEDAL}",
            "\N{SPORTS MEDAL}",
            "\N{SPORTS MEDAL}",
        )

        query = """SELECT command, COUNT(*) AS "uses"
                   FROM commands
                   GROUP BY command
                   ORDER BY "uses" DESC
                   LIMIT 5;
                """

        records = await ctx.db.fetch(query)
        value = "\n".join(f"{lookup[index]}: {command} ({uses} uses)" for (index, (command, uses)) in enumerate(records))
        e.add_field(name="Top Commands", value=value, inline=False)

        query = """SELECT guild_id, COUNT(*) AS "uses"
                   FROM commands
                   GROUP BY guild_id
                   ORDER BY "uses" DESC
                   LIMIT 5;
                """

        records = await ctx.db.fetch(query)
        value = []
        for index, (guild_id, uses) in enumerate(records):
            if guild_id is None:
                guild = "Private Message"
            else:
                guild = self.censor_object(self.bot.get_guild(guild_id) or f"<Unknown {guild_id}>")

            emoji = lookup[index]
            value.append(f"{emoji}: {guild} ({uses} uses)")

        e.add_field(name="Top Guilds", value="\n".join(value), inline=False)

        query = """SELECT author_id, COUNT(*) AS "uses"
                   FROM commands
                   GROUP BY author_id
                   ORDER BY "uses" DESC
                   LIMIT 5;
                """

        records = await ctx.db.fetch(query)
        value = []
        for index, (author_id, uses) in enumerate(records):
            user = self.censor_object(self.bot.get_user(author_id) or f"<Unknown {author_id}>")
            emoji = lookup[index]
            value.append(f"{emoji}: {user} ({uses} uses)")

        e.add_field(name="Top Users", value="\n".join(value), inline=False)
        await ctx.send(embeds=[e])

    @stats.command(name="today")
    @commands.is_owner()
    async def stats_today(self, ctx: Context) -> None:
        """Global command statistics for the day."""

        query = "SELECT failed, COUNT(*) FROM commands WHERE used > (CURRENT_TIMESTAMP - INTERVAL '1 day') GROUP BY failed;"
        total = await ctx.db.fetch(query)
        failed = 0
        success = 0
        question = 0
        for state, count in total:
            if state is False:
                success += count
            elif state is True:
                failed += count
            else:
                question += count

        e = discord.Embed(title="Last 24 Hour Command Stats", colour=discord.Colour.blurple())
        e.description = (
            f"{failed + success + question} commands used today. ({success} succeeded, {failed} failed, {question} unknown)"
        )

        lookup = (
            "\N{FIRST PLACE MEDAL}",
            "\N{SECOND PLACE MEDAL}",
            "\N{THIRD PLACE MEDAL}",
            "\N{SPORTS MEDAL}",
            "\N{SPORTS MEDAL}",
        )

        query = """SELECT command, COUNT(*) AS "uses"
                   FROM commands
                   WHERE used > (CURRENT_TIMESTAMP - INTERVAL '1 day')
                   GROUP BY command
                   ORDER BY "uses" DESC
                   LIMIT 5;
                """

        records = await ctx.db.fetch(query)
        value = "\n".join(f"{lookup[index]}: {command} ({uses} uses)" for (index, (command, uses)) in enumerate(records))
        e.add_field(name="Top Commands", value=value, inline=False)

        query = """SELECT guild_id, COUNT(*) AS "uses"
                   FROM commands
                   WHERE used > (CURRENT_TIMESTAMP - INTERVAL '1 day')
                   GROUP BY guild_id
                   ORDER BY "uses" DESC
                   LIMIT 5;
                """

        records = await ctx.db.fetch(query)
        value = []
        for index, (guild_id, uses) in enumerate(records):
            if guild_id is None:
                guild = "Private Message"
            else:
                guild = self.censor_object(self.bot.get_guild(guild_id) or f"<Unknown {guild_id}>")
            emoji = lookup[index]
            value.append(f"{emoji}: {guild} ({uses} uses)")

        e.add_field(name="Top Guilds", value="\n".join(value), inline=False)

        query = """SELECT author_id, COUNT(*) AS "uses"
                   FROM commands
                   WHERE used > (CURRENT_TIMESTAMP - INTERVAL '1 day')
                   GROUP BY author_id
                   ORDER BY "uses" DESC
                   LIMIT 5;
                """

        records = await ctx.db.fetch(query)
        value = []
        for index, (author_id, uses) in enumerate(records):
            user = self.censor_object(self.bot.get_user(author_id) or f"<Unknown {author_id}>")
            emoji = lookup[index]
            value.append(f"{emoji}: {user} ({uses} uses)")

        e.add_field(name="Top Users", value="\n".join(value), inline=False)
        await ctx.send(embeds=[e])

    async def send_guild_stats(self, e: discord.Embed, guild: discord.Guild) -> None:
        e.add_field(name="Name", value=guild.name)
        e.add_field(name="ID", value=guild.id)
        e.add_field(name="Shard ID", value=guild.shard_id or "N/A")
        e.add_field(name="Owner", value=f"{guild.owner} (ID: {guild.owner_id})")

        bots = sum(m.bot for m in guild.members)
        total = guild.member_count or 1
        e.add_field(name="Members", value=str(total))
        e.add_field(name="Bots", value=f"{bots} ({bots / total:.2%})")

        if guild.icon:
            e.set_thumbnail(url=guild.icon.url)

        if guild.me:
            e.timestamp = guild.me.joined_at

        await self.webhook.send(embed=e)

    @stats_today.before_invoke
    @stats_global.before_invoke
    async def before_stats_invoke(self, ctx: Context) -> None:  # noqa: PLR6301 # required for callbacks
        await ctx.typing()

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        e = discord.Embed(colour=0x53DDA4, title="New Guild")  # green colour
        await self.send_guild_stats(e, guild)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        e = discord.Embed(colour=0xDD5F53, title="Left Guild")  # red colour
        await self.send_guild_stats(e, guild)

    @commands.Cog.listener()
    async def on_command_error(self, ctx: Context, error: Exception) -> None:
        await self.register_command(ctx)
        if not isinstance(error, (commands.CommandInvokeError, commands.ConversionError)):
            return

        error = error.original
        if isinstance(error, (discord.Forbidden, discord.NotFound, menus.MenuError)):
            return

        embed = discord.Embed(title="Command Error", colour=discord.Colour.red())
        error = getattr(error, "original", error)
        tb_fmt = traceback.format_exception(type(error), error, error.__traceback__)
        clean = "".join(tb_fmt)

        embed.description = to_codeblock(clean, language="py", escape_md=False)
        embed.add_field(name="Name", value=ctx.command.qualified_name)
        embed.add_field(name="Author", value=f"{ctx.author} ({ctx.author.id})")
        fmt = f"Channel: {ctx.channel} (ID: {ctx.channel.id})"
        if ctx.guild:
            fmt += f"\nGuild: {ctx.guild} (ID: {ctx.guild.id})"
        embed.add_field(name="Location", value=fmt, inline=False)
        embed.add_field(name="Content", value=textwrap.shorten(ctx.message.content, width=512))
        embed.timestamp = datetime.datetime.now(datetime.UTC)
        embed.set_footer(text=f"Ray ID: {ctx.ray_id}")

        await self.webhook.send(embed=embed, wait=False)

    def add_record(self, record: logging.LogRecord) -> None:
        self._logging_queue.put_nowait(record)

    async def send_log_record(self, record: logging.LogRecord) -> None:
        attributes = {"INFO": "\N{INFORMATION SOURCE}\U0000fe0f", "WARNING": "\N{WARNING SIGN}"}

        emoji = attributes.get(record.levelname, "\N{CROSS MARK}")
        dt = datetime.datetime.fromtimestamp(record.created, datetime.UTC)

        if "heartbeat blocked" in record.message:
            message = formats.to_codeblock(record.message, language="py", escape_md=False)
        else:
            message = record.message

        msg = textwrap.shorten(f"{emoji} {discord.utils.format_dt(dt, 'F')}\n{message}", width=1990)
        if record.name == "discord.gateway":
            username = "Gateway"
            avatar_url = "https://i.imgur.com/4PnCKB3.png"
        else:
            username = f"{record.name} Logger"
            avatar_url = discord.utils.MISSING

        await self.webhook.send(msg, username=username, avatar_url=avatar_url)

    @commands.command(hidden=True)
    @commands.is_owner()
    async def bothealth(self, ctx: Context) -> None:  # noqa: PLR0914, PLR0915 # large function call
        """Various bot health monitoring tools."""

        # This uses a lot of private methods because there is no
        # clean way of doing this otherwise.

        HEALTHY = discord.Colour(value=0x43B581)  # noqa: N806
        UNHEALTHY = discord.Colour(value=0xF04947)  # noqa: N806
        WARNING = discord.Colour(value=0xF09E47)  # noqa: N806

        total_warnings = 0

        embed = discord.Embed(title="Bot Health Report", colour=HEALTHY)

        # Check the connection pool health.
        pool = self.bot.pool
        total_waiting = len(pool._queue._getters)  # noqa: SLF001
        current_generation = pool._generation  # noqa: SLF001

        description = [
            f"Total `Pool.acquire` Waiters: {total_waiting}",
            f"Current Pool Generation: {current_generation}",
            f"Connections In Use: {len(pool._holders) - pool._queue.qsize()}",  # noqa: SLF001
        ]

        questionable_connections = 0
        connection_value = []
        for index, holder in enumerate(pool._holders, start=1):  # noqa: SLF001
            generation = holder._generation  # noqa: SLF001
            in_use = holder._in_use is not None  # noqa: SLF001
            is_closed = holder._con is None or holder._con.is_closed()  # noqa: SLF001
            display = f"gen={holder._generation} in_use={in_use} closed={is_closed}"  # noqa: SLF001
            questionable_connections += any((in_use, generation != current_generation))
            connection_value.append(f"<Holder i={index} {display}>")

        joined_value = "\n".join(connection_value)
        embed.add_field(name="Connections", value=f"```py\n{joined_value}\n```", inline=False)

        spam_control = self.bot.spam_cooldown_mapping
        being_spammed = [str(key) for key, value in spam_control._cache.items() if value._tokens == 0]  # noqa: SLF001

        description.extend((
            f"Current Spammers: {', '.join(being_spammed) if being_spammed else 'None'}",
            f"Questionable Connections: {questionable_connections}",
        ))

        total_warnings += questionable_connections
        if being_spammed:
            embed.colour = WARNING
            total_warnings += 1

        all_tasks = asyncio.all_tasks(loop=self.bot.loop)
        event_tasks = [t for t in all_tasks if "Client._run_event" in repr(t) and not t.done()]

        cogs_directory = pathlib.Path(__file__).parent
        tasks_directory = pathlib.Path("discord") / "ext" / "tasks" / "__init__.py"
        inner_tasks = [t for t in all_tasks if str(cogs_directory) in repr(t) or str(tasks_directory) in repr(t)]

        bad_inner_tasks = ", ".join(hex(id(t)) for t in inner_tasks if t.done() and t._exception is not None)  # noqa: SLF001
        total_warnings += bool(bad_inner_tasks)
        embed.add_field(name="Inner Tasks", value=f"Total: {len(inner_tasks)}\nFailed: {bad_inner_tasks or 'None'}")
        embed.add_field(name="Events Waiting", value=f"Total: {len(event_tasks)}", inline=False)

        command_waiters = len(self._data_batch)
        is_locked = self._batch_lock.locked()
        description.append(f"Commands Waiting: {command_waiters}, Batch Locked: {is_locked}")

        cpu_count = psutil.cpu_count()
        assert cpu_count

        memory_usage = self.process.memory_full_info().uss / 1024**2
        cpu_usage = self.process.cpu_percent() / cpu_count
        embed.add_field(name="Process", value=f"{memory_usage:.2f} MiB\n{cpu_usage:.2f}% CPU", inline=False)

        global_rate_limit = not self.bot.http._global_over.is_set()  # noqa: SLF001
        description.append(f"Global Rate Limit: {global_rate_limit}")

        if command_waiters >= 8:
            total_warnings += 1
            embed.colour = WARNING

        if global_rate_limit or total_warnings >= 9:
            embed.colour = UNHEALTHY

        embed.set_footer(text=f"{total_warnings} warning(s)")
        embed.description = "\n".join(description)
        await ctx.send(embeds=[embed])

    @commands.command(hidden=True, aliases=["cancel_task"])
    @commands.is_owner()
    async def debug_task(self, ctx: Context, memory_id: Annotated[int, hex_value]) -> None:  # noqa: PLR6301 # required
        """Debug a task by a memory location."""
        task = object_at(memory_id)
        if task is None or not isinstance(task, asyncio.Task):
            await ctx.send(f"Could not find Task object at {hex(memory_id)}.")
            return

        if ctx.invoked_with == "cancel_task":
            task.cancel()
            await ctx.send(f"Cancelled task object {task!r}.")
            return

        paginator = commands.Paginator(prefix="```py")
        fp = io.StringIO()
        frames = len(task.get_stack())
        paginator.add_line(f"# Total Frames: {frames}")
        task.print_stack(file=fp)

        for line in fp.getvalue().splitlines():
            paginator.add_line(line)

        for page in paginator.pages:
            await ctx.send(page)

    @staticmethod
    async def tabulate_query(ctx: Context, query: str, *args: Any) -> None:
        records = await ctx.db.fetch(query, *args)

        if len(records) == 0:
            await ctx.send("No results found.")
            return

        headers = list(records[0].keys())
        table = formats.TabularData()
        table.set_columns(headers)
        table.add_rows(list(r.values()) for r in records)
        render = table.render()

        fmt = f"```\n{render}\n```"
        if len(fmt) > 2000:
            fp = io.BytesIO(fmt.encode("utf-8"))
            await ctx.send("Too many results...", files=[discord.File(fp, "results.txt")])
        else:
            await ctx.send(fmt)

    @commands.group(hidden=True, invoke_without_command=True)
    @commands.is_owner()
    async def command_history(self, ctx: Context) -> None:
        """Command history."""
        query = """SELECT
                        CASE failed
                            WHEN TRUE THEN command || ' [!]'
                            ELSE command
                        END AS "command",
                        to_char(used, 'Mon DD HH12:MI:SS AM') AS "invoked",
                        author_id,
                        guild_id
                   FROM commands
                   ORDER BY used DESC
                   LIMIT 15;
                """
        await self.tabulate_query(ctx, query)

    @command_history.command(name="for")
    @commands.is_owner()
    async def command_history_for(self, ctx: Context, days: Annotated[int, int | None] = 7, *, command: str) -> None:
        """Command history for a command."""

        query = """SELECT *, t.success + t.failed AS "total"
                   FROM (
                       SELECT guild_id,
                              SUM(CASE WHEN failed THEN 0 ELSE 1 END) AS "success",
                              SUM(CASE WHEN failed THEN 1 ELSE 0 END) AS "failed"
                       FROM commands
                       WHERE command=$1
                       AND used > (CURRENT_TIMESTAMP - $2::interval)
                       GROUP BY guild_id
                   ) AS t
                   ORDER BY "total" DESC
                   LIMIT 30;
                """

        await self.tabulate_query(ctx, query, command, datetime.timedelta(days=days))

    @command_history.command(name="guild", aliases=["server"])
    @commands.is_owner()
    async def command_history_guild(self, ctx: Context, guild_id: int) -> None:
        """Command history for a guild."""

        query = """SELECT
                        CASE failed
                            WHEN TRUE THEN command || ' [!]'
                            ELSE command
                        END AS "command",
                        channel_id,
                        author_id,
                        used
                   FROM commands
                   WHERE guild_id=$1
                   ORDER BY used DESC
                   LIMIT 15;
                """
        await self.tabulate_query(ctx, query, guild_id)

    @command_history.command(name="user", aliases=["member"])
    @commands.is_owner()
    async def command_history_user(self, ctx: Context, user_id: int) -> None:
        """Command history for a user."""

        query = """SELECT
                        CASE failed
                            WHEN TRUE THEN command || ' [!]'
                            ELSE command
                        END AS "command",
                        guild_id,
                        used
                   FROM commands
                   WHERE author_id=$1
                   ORDER BY used DESC
                   LIMIT 20;
                """
        await self.tabulate_query(ctx, query, user_id)

    @command_history.command(name="log")
    @commands.is_owner()
    async def command_history_log(self, ctx: Context, days: int = 7) -> None:
        """Command history log for the last N days."""

        query = """SELECT command, COUNT(*)
                   FROM commands
                   WHERE used > (CURRENT_TIMESTAMP - $1::interval)
                   GROUP BY command
                   ORDER BY 2 DESC
                """

        all_commands = {c.qualified_name: 0 for c in self.bot.walk_commands()}

        records = await ctx.db.fetch(query, datetime.timedelta(days=days))
        for name, uses in records:
            if name in all_commands:
                all_commands[name] = uses

        as_data = sorted(all_commands.items(), key=operator.itemgetter(1), reverse=True)
        table = formats.TabularData()
        table.set_columns(["Command", "Uses"])
        table.add_rows(tup for tup in as_data)
        render = table.render()

        embed = discord.Embed(title="Summary", colour=discord.Colour.green())
        embed.set_footer(text="Since").timestamp = discord.utils.utcnow() - datetime.timedelta(days=days)

        top_ten = "\n".join(f"{command}: {uses}" for command, uses in records[:10])
        bottom_ten = "\n".join(f"{command}: {uses}" for command, uses in records[-10:])
        embed.add_field(name="Top 10", value=top_ten)
        embed.add_field(name="Bottom 10", value=bottom_ten)

        unused = ", ".join(name for name, uses in as_data if uses == 0)
        if len(unused) > 1024:
            unused = "Way too many..."

        embed.add_field(name="Unused", value=unused, inline=False)

        await ctx.send(embeds=[embed], files=[discord.File(io.BytesIO(render.encode()), filename="full_results.txt")])

    @command_history.command(name="cog")
    @commands.is_owner()
    async def command_history_cog(self, ctx: Context, days: int = 7, *, cog_name: str | None = None) -> None:
        """Command history for a cog or grouped by a cog."""

        interval = datetime.timedelta(days=days)
        if cog_name is not None:
            cog = self.bot.get_cog(cog_name)
            if cog is None:
                await ctx.send(f"Unknown cog: {cog_name}")
                return None

            query = """SELECT *, t.success + t.failed AS "total"
                       FROM (
                           SELECT command,
                                  SUM(CASE WHEN failed THEN 0 ELSE 1 END) AS "success",
                                  SUM(CASE WHEN failed THEN 1 ELSE 0 END) AS "failed"
                           FROM commands
                           WHERE command = any($1::text[])
                           AND used > (CURRENT_TIMESTAMP - $2::interval)
                           GROUP BY command
                       ) AS t
                       ORDER BY "total" DESC
                       LIMIT 30;
                    """
            return await self.tabulate_query(ctx, query, [c.qualified_name for c in cog.walk_commands()], interval)

        # A more manual query with a manual grouper.
        query = """SELECT *, t.success + t.failed AS "total"
                   FROM (
                       SELECT command,
                              SUM(CASE WHEN failed THEN 0 ELSE 1 END) AS "success",
                              SUM(CASE WHEN failed THEN 1 ELSE 0 END) AS "failed"
                       FROM commands
                       WHERE used > (CURRENT_TIMESTAMP - $1::interval)
                       GROUP BY command
                   ) AS t;
                """

        class Count:
            __slots__ = ("failed", "success", "total")

            def __init__(self) -> None:
                self.success = 0
                self.failed = 0
                self.total = 0

            def add(self, record: dict[str, int]) -> None:
                self.success += record["success"]
                self.failed += record["failed"]
                self.total += record["total"]

        data = defaultdict(Count)
        records = await ctx.db.fetch(query, interval)
        for record in records:
            command = self.bot.get_command(record["command"])
            if command is None or command.cog is None:
                data["No Cog"].add(record)
            else:
                data[command.cog.qualified_name].add(record)

        table = formats.TabularData()
        table.set_columns(["Cog", "Success", "Failed", "Total"])
        data = sorted(
            [(cog, e.success, e.failed, e.total) for cog, e in data.items()],
            key=operator.itemgetter(-1),
            reverse=True,
        )

        table.add_rows(data)
        render = table.render()
        await ctx.send(f"```\n{render}\n```")
        return None


old_on_error = commands.Bot.on_error


async def on_error(self: Graha, event: str, *args: Any, **_: Any) -> None:
    (exception_type, exception, tb) = sys.exc_info()
    ray_id = secrets.token_hex(16)

    embed = discord.Embed(title="Event Error", colour=discord.Colour.brand_red())
    embed.add_field(name="Event", value=event)
    clean = "".join(traceback.format_exception(exception_type, exception, tb))
    embed.description = formats.to_codeblock(clean, escape_md=False)
    embed.set_footer(text=f"Ray ID: {ray_id}")
    embed.timestamp = datetime.datetime.now(datetime.UTC)

    fmt = ["```py"]
    for index, arg in enumerate(args):
        fmt.append(f"[{index}]: {arg!r}")
    fmt.append("```")
    embed.add_field(name="Arguments", value="\n".join(fmt), inline=False)

    await self.logging_webhook.send(embed=embed, wait=False)


async def setup(bot: Graha) -> None:
    if not hasattr(bot, "command_stats"):
        bot.command_stats = Counter()

    if not hasattr(bot, "socket_stats"):
        bot.socket_stats = Counter()

    if not hasattr(bot, "command_types_used"):
        bot.command_types_used = Counter()

    cog = Stats(bot)
    await bot.add_cog(cog)
    bot._stats_cog_gateway_handler = handler = LoggingHandler(cog)  # noqa: SLF001
    logging.getLogger().addHandler(handler)
    commands.Bot.on_error = on_error  # pyright: ignore[reportAttributeAccessIssue] # monkeypatching


async def teardown(bot: Graha) -> None:  # noqa: RUF029 # expected by the extension handler
    commands.Bot.on_error = old_on_error
    logging.getLogger().removeHandler(bot._stats_cog_gateway_handler)  # noqa: SLF001
    del bot._stats_cog_gateway_handler  # noqa: SLF001
