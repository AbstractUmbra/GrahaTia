"""
This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
import pathlib
import traceback
from collections import Counter, deque
from collections.abc import Callable, Coroutine
from logging.handlers import RotatingFileHandler
from typing import TYPE_CHECKING, Any, Literal, NoReturn, overload

import aiohttp
import asyncpg
import discord
import jishaku
import mystbin
import sentry_sdk
import tomli
from discord import app_commands
from discord.ext import commands
from discord.utils import _ColourFormatter as ColourFormatter, stream_supports_colour
from sentry_sdk.integrations.aiohttp import AioHttpIntegration

from extensions import EXTENSIONS
from utilities.async_config import Config
from utilities.context import Context
from utilities.db import db_init
from utilities.prefix import callable_prefix as _callable_prefix


if TYPE_CHECKING:
    from typing_extensions import Self

    from utilities._types.bot_config import Config as BotConfig

LOGGER = logging.getLogger("root.graha")
jishaku.Flags.HIDE = True
jishaku.Flags.RETAIN = True
jishaku.Flags.NO_UNDERSCORE = True
jishaku.Flags.NO_DM_TRACEBACK = True

_config_path = pathlib.Path("configs/config.toml")
with _config_path.open("rb") as fp:
    CONFIG: BotConfig = tomli.load(fp)  # type: ignore # can't narrow this legally.


class GrahaCommandTree(app_commands.CommandTree):
    client: Graha

    async def on_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        LOGGER.exception("Exception occurred in the CommandTree:\n%s", error)

        e = discord.Embed(title="Command Error", colour=0xA32952)
        e.add_field(name="Command", value=(interaction.command and interaction.command.name) or "No command.")
        e.add_field(name="Author", value=interaction.user, inline=False)
        channel = interaction.channel
        guild = interaction.guild
        location_fmt = f"Channel: {channel.name} ({channel.id})"  # type: ignore
        if guild:
            location_fmt += f"\nGuild: {guild.name} ({guild.id})"
        e.add_field(name="Location", value=location_fmt, inline=True)
        (exc_type, exc, tb) = type(error), error, error.__traceback__
        trace = traceback.format_exception(exc_type, exc, tb)
        clean = "".join(trace)
        e.description = f"```py\n{clean}\n```"
        e.timestamp = datetime.datetime.now(datetime.timezone.utc)
        await self.client.logging_webhook.send(embed=e)
        await self.client.owner.send(embed=e)


class RemoveNoise(logging.Filter):
    def __init__(self) -> None:
        super().__init__(name="discord.state")

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelname == "WARNING" and "referencing an unknown" in record.msg:
            return False
        return True


class LogHandler:
    def __init__(self, *, stream: bool = True) -> None:
        self.log: logging.Logger = logging.getLogger()
        self.max_bytes: int = 32 * 1024 * 1024
        self.logging_path = pathlib.Path("./logs/")
        self.logging_path.mkdir(exist_ok=True)
        self.stream: bool = stream

        # patches
        self.info = self.log.info
        self.warning = self.log.warning
        self.error = self.log.error
        self.exception = self.log.exception
        self.debug = self.log.debug

    async def __aenter__(self) -> Self:
        return self.__enter__()

    def __enter__(self: Self) -> Self:
        logging.getLogger("discord").setLevel(logging.INFO)
        logging.getLogger("discord.http").setLevel(logging.INFO)
        logging.getLogger("hondana.http").setLevel(logging.INFO)
        logging.getLogger("discord.state").addFilter(RemoveNoise())

        self.log.setLevel(logging.INFO)
        handler = RotatingFileHandler(
            filename=self.logging_path / "Graha.log", encoding="utf-8", mode="w", maxBytes=self.max_bytes, backupCount=5
        )
        dt_fmt = "%Y-%m-%d %H:%M:%S"
        fmt = logging.Formatter("[{asctime}] [{levelname:<7}] {name}: {message}", dt_fmt, style="{")
        handler.setFormatter(fmt)
        self.log.addHandler(handler)
        if dsn := CONFIG["logging"].get("sentry_dsn"):
            sentry_sdk.init(dsn=dsn, integrations=[AioHttpIntegration()])

        if self.stream:
            stream_handler = logging.StreamHandler()
            if stream_supports_colour(stream_handler):
                stream_handler.setFormatter(ColourFormatter())
            self.log.addHandler(stream_handler)

        return self

    async def __aexit__(self, *args: Any) -> None:
        return self.__exit__(*args)

    def __exit__(self, *args: Any) -> None:
        handlers = self.log.handlers[:]
        for hdlr in handlers:
            hdlr.close()
            self.log.removeHandler(hdlr)


class Graha(commands.Bot):
    """G'raha Tia, the best catboy."""

    pool: asyncpg.Pool[asyncpg.Record]
    user: discord.ClientUser
    log_handler: LogHandler
    session: aiohttp.ClientSession
    start_time: datetime.datetime
    command_stats: Counter[str]
    socket_stats: Counter[str]
    global_log: logging.Logger
    command_types_used: Counter[bool]
    mb_client: mystbin.Client
    bot_app_info: discord.AppInfo
    _original_help_command: commands.HelpCommand | None  # for help command overriding
    _stats_cog_gateway_handler: logging.Handler

    def __init__(self) -> None:
        super().__init__(
            command_prefix=_callable_prefix,
            tree_cls=GrahaCommandTree,
            intents=discord.Intents.all(),
            allowed_mentions=discord.AllowedMentions.none(),
            activity=discord.Game(name="My default prefix is 'gt ', but mention me to see all of them!"),
        )
        self._prefix_data: Config[list[str]] = Config(pathlib.Path("configs/prefixes.json"))
        self._blacklist_data: Config[list[str]] = Config(pathlib.Path("configs/blacklist.json"))

        # auto spam detection
        self._spam_cooldown_mapping: commands.CooldownMapping = commands.CooldownMapping.from_cooldown(
            10, 12.0, commands.BucketType.user
        )
        self._spammer_count: Counter = Counter()

        # misc logging
        self._previous_websocket_events: deque = deque(maxlen=10)
        self._error_handling_cooldown: commands.CooldownMapping = commands.CooldownMapping.from_cooldown(
            1, 5, commands.BucketType.user
        )
        self.command_stats = Counter()
        self.socket_stats = Counter()
        self.global_log: logging.Logger = LOGGER
        self.start_time: datetime.datetime = datetime.datetime.now(datetime.timezone.utc)

    def bot_check(self, ctx: Context) -> bool:
        if ctx.guild and ctx.guild.id == 149998214810959872:
            return ctx.channel.id in {995124873259135067, 872379715443380295}
        return True

    def run(self) -> NoReturn:
        raise NotImplementedError("Please use `.start()` instead.")

    @property
    def owner(self) -> discord.User:
        return self.bot_app_info.owner

    @property
    def config(self) -> BotConfig:
        return CONFIG

    @discord.utils.cached_property
    def logging_webhook(self) -> discord.Webhook:
        return discord.Webhook.from_url(self.config["logging"]["webhook_url"], session=self.session)

    async def on_socket_response(self, message: Any) -> None:
        """Quick override to log websocket events."""
        self._previous_websocket_events.append(message)

    async def on_ready(self) -> None:
        self.global_log.info("Graha got a ready event at %s", datetime.datetime.now())

    async def on_resume(self) -> None:
        self.global_log.info("Graha got a resume event at %s", datetime.datetime.now())

    async def on_command_error(self, ctx: Context, error: commands.CommandError) -> None:
        await ctx.message.add_reaction("\u274c")
        if ctx.exc_handled is True:  # let's suppress any already handled errors without following the ray id creation.
            return

        assert ctx.command is not None  # type checking - disable assertions
        ret = ""
        if isinstance(error, commands.NoPrivateMessage):
            retry_period = self._error_handling_cooldown.update_rate_limit(ctx.message)
            if retry_period:
                return
            ret += "Sorry, this command is not available in DMs."

        elif isinstance(error, commands.DisabledCommand):
            retry_period = self._error_handling_cooldown.update_rate_limit(ctx.message)
            if retry_period:
                return
            ret += "Sorry, this command has been disabled."

        elif isinstance(error, commands.CommandInvokeError):
            origin_ = error.original
            tb_fmt = traceback.format_exception(type(origin_), origin_, origin_.__traceback__)
            clean = "".join(tb_fmt)

            if not isinstance(origin_, discord.HTTPException):
                LOGGER.exception("in `%s` with ray id: '%s' ::\n%s", ctx.command.name, ctx.ray_id, clean, exc_info=True)

            ret += "There was an error in that command. My developer has been notified."

        else:
            return

        await ctx.send(content=ret)

    def _get_guild_prefixes(
        self,
        guild: discord.abc.Snowflake,
        *,
        local_: Callable[[Graha, discord.Message], list[str]] = _callable_prefix,
        raw: bool = False,
    ) -> list[str]:
        if raw:
            return self._prefix_data.get(guild.id, ["gt "])

        snowflake_proxy = discord.Object(id=0)
        snowflake_proxy.guild = guild  # type: ignore # this is actually valid, the class just has no slots or attr to override.
        return local_(self, snowflake_proxy)  # type: ignore # this is actually valid, the class just has no slots or attr to override.

    async def _set_guild_prefixes(self, guild: discord.abc.Snowflake, prefixes: list[str] | None) -> None:
        if not prefixes:
            await self._prefix_data.put(guild.id, [])
        elif len(prefixes) > 10:
            raise commands.errors.TooManyArguments("Cannot have more than 10 custom prefixes.")
        else:
            await self._prefix_data.put(guild.id, prefixes)

    async def _blacklist_add(self, object_id: int) -> None:
        await self._blacklist_data.put(object_id, True)

    async def _blacklist_remove(self, object_id: int) -> None:
        try:
            await self._blacklist_data.remove(object_id)
        except KeyError:
            pass

    @overload
    def _log_spammer(
        self, ctx: Context, message: discord.Message, retry_after: float, *, autoblock: Literal[True]
    ) -> Coroutine[None, None, discord.WebhookMessage]:
        ...

    @overload
    def _log_spammer(self, ctx: Context, message: discord.Message, retry_after: float, *, autoblock: Literal[False]) -> None:
        ...

    @overload
    def _log_spammer(self, ctx: Context, message: discord.Message, retry_after: float, *, autoblock: bool = ...) -> None:
        ...

    def _log_spammer(
        self, ctx: Context, message: discord.Message, retry_after: float, *, autoblock: bool = False
    ) -> Coroutine[None, None, discord.WebhookMessage] | None:
        guild_name = getattr(ctx.guild, "name", "No Guild (DMs)")
        guild_id = getattr(ctx.guild, "id", None)
        fmt = "User %s (ID %s) in guild %r (ID %s) is spamming. retry_after: %.2fs"
        LOGGER.warning(fmt, message.author, message.author.id, guild_name, guild_id, retry_after)
        if not autoblock:
            return

        embed = discord.Embed(title="Autoblocked Member", colour=0xDDA453)
        embed.add_field(name="User", value=f"{message.author} (ID {message.author.id})", inline=False)
        if guild_id is not None:
            embed.add_field(name="Guild Info", value=f"{guild_name} (ID {guild_id})", inline=False)
        embed.add_field(name="Channel Info", value=f"{message.channel} (ID: {message.channel.id}", inline=False)
        embed.timestamp = datetime.datetime.now(datetime.timezone.utc)

        return self.logging_webhook.send(embed=embed, wait=True)

    async def process_commands(self, message: discord.Message, /) -> None:
        ctx = await self.get_context(message, cls=Context)

        if ctx.command is None:
            return

        if ctx.author.id in self._blacklist_data:
            return

        if ctx.guild is not None and ctx.guild.id in self._blacklist_data:
            return

        bucket = self._spam_cooldown_mapping.get_bucket(message)
        if not bucket:
            return
        current = message.created_at.timestamp()
        retry_after = bucket.update_rate_limit(current)
        if retry_after and message.author.id != self.owner_id:
            self._spammer_count[message.author.id] += 1
            if self._spammer_count[message.author.id] >= 5:
                await self._blacklist_add(message.author.id)
                await self._log_spammer(ctx, message, retry_after, autoblock=True)
                del self._spammer_count[message.author.id]
            else:
                self._log_spammer(ctx, message, retry_after)
            return
        else:
            self._spammer_count.pop(message.author.id, None)

        await self.invoke(ctx)

    async def on_message(self, message: discord.Message, /) -> None:
        if message.author.bot:
            return

        conditional_acces = CONFIG.get("conditional_access")
        if conditional_acces:
            if message.guild and (access := conditional_acces.get(str(message.guild.id))):
                if message.channel.id not in access:
                    return

        await self.process_commands(message)

    async def on_message_edit(self, before: discord.Message, after: discord.Message, /) -> None:
        if after.author.id == self.owner_id:
            if not before.embeds and after.embeds:
                return

            await self.process_commands(after)

    async def on_guild_join(self, guild: discord.Guild, /) -> None:
        """When the bot joins a guild."""
        if guild.id in self._blacklist_data:
            await guild.leave()

    async def start(self) -> None:
        try:
            await super().start(token=self.config["bot"]["token"], reconnect=True)
        finally:
            path = pathlib.Path("logs/prev_events.log")
            with path.open("w+", encoding="utf-8") as f:
                for event in self._previous_websocket_events:
                    try:
                        last_log = json.dumps(event, ensure_ascii=True, indent=2)
                    except Exception:
                        f.write(f"{event}\n")
                    else:
                        f.write(f"{last_log}\n")

    async def setup_hook(self) -> None:
        self.mb_client = mystbin.Client(session=self.session, token=CONFIG["misc"]["mystbin_token"])
        self.start_time: datetime.datetime = datetime.datetime.now(datetime.timezone.utc)
        self.bot_app_info = await self.application_info()
        self.owner_id = self.bot_app_info.owner.id


async def main() -> None:
    async with Graha() as bot, aiohttp.ClientSession() as session, LogHandler() as log_handler, asyncpg.create_pool(
        dsn=CONFIG["database"]["dsn"],
        command_timeout=60,
        max_inactive_connection_lifetime=0,
        init=db_init,
    ) as pool:
        bot.pool = pool
        bot.log_handler = log_handler

        bot.session = session

        await bot.load_extension("jishaku")
        for extension in EXTENSIONS:
            await bot.load_extension(extension.name)
            bot.log_handler.info("Loaded %sextension: %s", "module " if extension.ispkg else "", extension.name)

        await bot.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
