"""
This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at http://mozilla.org/MPL/2.0/.

This file was sourced from [RoboDanny](https://github.com/Rapptz/RoboDanny).
"""

from __future__ import annotations

import datetime
import secrets
from functools import cached_property
from typing import TYPE_CHECKING, Any, Protocol, TypeVar

import discord
from discord.ext import commands
from discord.utils import MISSING

from .shared.paste import create_paste
from .shared.ui import BaseView, ConfirmationView

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence
    from types import TracebackType

    from aiohttp import ClientSession
    from asyncpg import Connection
    from typing_extensions import TypeVar  # noqa: TC004

    from bot import Graha

    CogT_co = TypeVar("CogT_co", bound=commands.Cog, covariant=True, default=commands.Cog)
else:
    CogT_co = TypeVar("CogT_co", bound=commands.Cog, covariant=True)


__all__ = (
    "Context",
    "GuildContext",
)

T = TypeVar("T")
Interaction = discord.Interaction["Graha"]


# For typing purposes, `Context.db` returns a Protocol type
# that allows us to properly type the return values via narrowing
# Right now, asyncpg is untyped so this is better than the current status quo
# To actually receive the regular Pool type `Context.pool` can be used instead.


class ConnectionContextManager(Protocol):
    async def __aenter__(self) -> Connection: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...


class DatabaseProtocol(Protocol):
    async def execute(self, query: str, *args: Any, timeout: float | None = None) -> str: ...

    async def fetch(self, query: str, *args: Any, timeout: float | None = None) -> list[Any]: ...

    async def fetchrow(self, query: str, *args: Any, timeout: float | None = None) -> Any | None: ...

    async def fetchval(self, query: str, *args: Any, timeout: float | None = None) -> Any | None: ...

    async def executemany(self, query: str, args: Iterable[Sequence[Any]], *, timeout: float | None = None) -> None: ...

    async def close(self) -> None: ...

    def acquire(self, *, timeout: float | None = None) -> ConnectionContextManager: ...

    def release(self, connection: Connection) -> None: ...


class DisambiguatorView[T](BaseView):
    message: discord.Message
    selected: T

    def __init__(self, ctx: Context, data: list[T], entry: Callable[[T], Any]) -> None:
        super().__init__()
        self.ctx: Context = ctx
        self.data: list[T] = data

        options = []
        for i, x in enumerate(data):
            opt = entry(x)
            if not isinstance(opt, discord.SelectOption):
                opt = discord.SelectOption(label=str(opt))
            opt.value = str(i)
            options.append(opt)

        select = discord.ui.Select["DisambiguatorView"](options=options)

        select.callback = self.on_select_submit
        self.select = select
        self.add_item(select)

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("This select menu is not meant for you, sorry.", ephemeral=True)
            return False
        return True

    async def on_select_submit(self, interaction: Interaction) -> None:
        index = int(self.select.values[0])
        self.selected = self.data[index]
        await interaction.response.defer()
        if not self.message.flags.ephemeral:
            await self.message.delete()

        self.stop()


class Context[CogT_co: commands.Cog](commands.Context["Graha"]):
    channel: discord.TextChannel | discord.VoiceChannel | discord.Thread | discord.DMChannel
    bot: Graha
    command: commands.Command[Any, ..., Any]
    cog: CogT_co

    __slots__ = ("pool",)

    def __init__(self, **kwargs) -> None:  # noqa: ANN003
        super().__init__(**kwargs)
        self.pool = self.bot.pool
        self.exc_handled: bool = False

    def __repr__(self) -> str:
        return "<Context>"

    @property
    def session(self) -> ClientSession:
        return self.bot.session

    @property
    def db(self) -> DatabaseProtocol:
        return self.pool  # pyright: ignore[reportReturnType] # override for protocol

    @cached_property
    def ray_id(self) -> str:
        return secrets.token_hex(16)

    @discord.utils.cached_property
    def replied_reference(self) -> discord.MessageReference | None:
        ref = self.message.reference
        if ref and isinstance(ref.resolved, discord.Message):
            return ref.resolved.to_reference()

        return None

    @discord.utils.cached_property
    def replied_message(self) -> discord.Message | None:
        ref = self.message.reference
        if ref and isinstance(ref.resolved, discord.Message):
            return ref.resolved

        return None

    async def disambiguate(self, matches: list[T], entry: Callable[[T], Any], *, ephemeral: bool = False) -> T:
        if len(matches) == 0:
            raise ValueError("No results found.")

        if len(matches) == 1:
            return matches[0]

        if len(matches) > 25:
            raise ValueError("Too many results... sorry.")

        view = DisambiguatorView[T](self, matches, entry)
        message = await self.send(
            "There are too many matches... Which one did you mean?",
            view=view,
            ephemeral=ephemeral,
            wait=True,
        )
        assert message
        view.message = message

        await view.wait()
        return view.selected

    async def prompt(
        self,
        message: str,
        *,
        timeout: float = 60.0,
        delete_after: bool = True,
        author_id: int | None = None,
    ) -> bool | None:
        """An interactive reaction confirmation dialog.
        Parameters
        -----------
        message: str
            The message to show along with the prompt.
        timeout: float
            How long to wait before returning.
        delete_after: bool
            Whether to delete the confirmation message after we're done.
        author_id: int | None
            The member who should respond to the prompt. Defaults to the author of the
            Context's message.
        Returns
        --------
        bool | None
            ``True`` if explicit confirm,
            ``False`` if explicit deny,
            ``None`` if deny due to timeout
        """

        author_id = author_id or self.author.id
        view = ConfirmationView(
            timeout=timeout,
            delete_after=delete_after,
            author_id=author_id,
        )
        view.message = await self.send(message, view=view, ephemeral=delete_after)
        await view.wait()
        return view.value

    def tick(self, opt: bool | None, label: str | None = None) -> str:  # noqa: FBT001 # quick hack shortcut
        lookup = {
            True: "<:TickYes:735498312861351937>",
            False: "<:CrossNo:735498453181923377>",
            None: "<:QuestionMaybe:738038828928860269>",
        }
        emoji = lookup.get(opt, "❌")
        if label is not None:
            return f"{emoji}: {label}"
        return emoji

    async def send(
        self,
        content: str | None = None,
        *,
        tts: bool = False,
        embeds: Sequence[discord.Embed] | None = None,
        files: Sequence[discord.File] | None = None,
        stickers: Sequence[discord.GuildSticker | discord.StickerItem] | None = None,
        delete_after: float | None = None,
        nonce: str | int | None = None,
        allowed_mentions: discord.AllowedMentions | None = None,
        reference: discord.Message | discord.MessageReference | discord.PartialMessage | None = None,
        mention_author: bool | None = None,
        view: discord.ui.View | None = None,
        suppress_embeds: bool = False,
        ephemeral: bool = False,
        silent: bool = False,
        poll: discord.Poll | None = MISSING,
        paste: bool = False,
        wait: bool = False,
    ) -> discord.Message | None:
        content = str(content) if content is not None else None
        if (paste and content) or (content and len(content) >= 2000):
            password = secrets.token_urlsafe(10)
            paste_url = await create_paste(
                content=content,
                password=password,
                expiry=(datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=2)),
                mb_client=self.bot.mb_client,
            )
            content = (
                "Sorry, the output was too large but I posted it to mystb.in for you here:"
                f" {paste_url}.\nThe password is: `{password}`."
            )

        # this is a cluster fuck
        # one day we'll be able to match *args and **kwargs of a super method
        sent = await super().send(
            content=content,
            tts=tts,
            embeds=embeds,  # pyright: ignore[reportArgumentType] # see above
            files=files,  # pyright: ignore[reportArgumentType] # see above
            stickers=stickers,  # pyright: ignore[reportArgumentType] # see above
            delete_after=delete_after,  # pyright: ignore[reportArgumentType] # see above
            nonce=nonce,  # pyright: ignore[reportArgumentType] # see above
            allowed_mentions=allowed_mentions,  # pyright: ignore[reportArgumentType] # see above
            reference=reference,  # pyright: ignore[reportArgumentType] # see above
            mention_author=mention_author,  # pyright: ignore[reportArgumentType] # see above
            view=view,  # pyright: ignore[reportArgumentType] # see above
            suppress_embeds=suppress_embeds,
            ephemeral=ephemeral,
            silent=silent,
            poll=poll,  # pyright: ignore[reportArgumentType] # see above
        )

        if wait is True:
            return sent

        return None


class GuildContext(Context):
    author: discord.Member
    guild: discord.Guild
    channel: discord.VoiceChannel | discord.TextChannel | discord.Thread
    me: discord.Member
    prefix: str
