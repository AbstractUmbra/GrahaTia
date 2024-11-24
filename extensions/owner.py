"""
This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""

from __future__ import annotations

import asyncio
import io
import pathlib
import re
import subprocess  # accepted
import time
import traceback
from typing import TYPE_CHECKING, Literal

import discord
from discord.ext import commands
from discord.ext.commands import Greedy  # noqa: TC002

from utilities import formats
from utilities.shared.cog import BaseCog

if TYPE_CHECKING:
    from asyncpg import Record

    from bot import Graha
    from utilities.context import Context, GuildContext

SANE_EXTENSION_REGEX = re.compile(r"(?P<prefix>extensions(?:\.|\\|\/))?(?P<extension>\w+)")


class ModuleConverter(commands.Converter[str]):
    async def convert(self, ctx: Context, argument: str, /) -> str:
        match = SANE_EXTENSION_REGEX.search(argument)

        if not match:
            raise commands.ExtensionNotFound(argument)

        if not match["prefix"]:
            argument = "extensions/" + match["extension"]

        extension_path = pathlib.Path(argument)
        if not extension_path.is_dir():
            extension_path = extension_path.with_suffix(".py")

        if not extension_path.exists():
            raise commands.ExtensionNotFound(argument)

        return ".".join(extension_path.parts).removesuffix(".py")


class Admin(BaseCog["Graha"]):
    """Admin-only commands that make the bot dynamic."""

    def cleanup_code(self, content: str) -> str:
        """Automatically removes code blocks from the code."""
        if content.startswith("```") and content.endswith("```"):
            return "\n".join(content.split("\n")[1:-1])

        # remove `foo`
        return content.strip("` \n")

    async def cog_check(self, ctx: Context) -> bool:
        return await self.bot.is_owner(ctx.author)

    @commands.command()
    @commands.guild_only()
    async def leave(self, ctx: GuildContext) -> None:
        """Leaves the current guild."""
        await ctx.guild.leave()

    @commands.command()
    async def load(self, ctx: Context, *, module: str = commands.param(converter=ModuleConverter)) -> None:
        """Loads a module."""
        try:
            await self.bot.load_extension(module)
        except commands.ExtensionError as err:
            await ctx.send(f"{err.__class__.__name__}: {err}")
        else:
            await ctx.message.add_reaction(ctx.tick(True))  # noqa: FBT003 # quick shortcut

    @commands.command()
    async def unload(self, ctx: Context, *, module: str = commands.param(converter=ModuleConverter)) -> None:
        """Unloads a module."""
        try:
            await self.bot.unload_extension(module)
        except commands.ExtensionError as err:
            await ctx.send(f"{err.__class__.__name__}: {err}")
        else:
            await ctx.message.add_reaction(ctx.tick(True))  # noqa: FBT003 # quick shortcut

    @commands.group(name="reload", invoke_without_command=True)
    async def _reload(self, ctx: Context, *, module: str = commands.param(converter=ModuleConverter)) -> None:
        """Reloads a module."""
        try:
            await self.bot.reload_extension(module)
        except commands.ExtensionNotLoaded:
            return await self.bot.load_extension(module)
        except commands.ExtensionError as err:
            await ctx.send(f"{err.__class__.__name__}: {err}")
            await ctx.message.add_reaction(ctx.tick(False))  # noqa: FBT003 # quick shortcut
            return None

        await ctx.message.add_reaction(ctx.tick(True))  # noqa: FBT003 # quick shortcut

        return None

    async def _git_pull(self) -> list[str]:
        process = await asyncio.create_subprocess_shell("git pull", stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        result = await process.communicate()

        return [output.decode() for output in result]

    @_reload.command(name="all")
    async def _reload_all(self, ctx: Context) -> None:
        """Reloads all loaded extensions whilst optionally pulling from git."""

        sorted_exts = sorted(self.bot.extensions)

        results: list[tuple[bool, str]] = []

        for ext in sorted_exts:
            try:
                await self.bot.reload_extension(ext)
            except commands.ExtensionError:
                results.append((False, ext))
            else:
                results.append((True, ext))

        failed_exts = [ext for failed, ext in results if failed is False]
        if failed_exts:
            await ctx.message.add_reaction(ctx.tick(False))  # noqa: FBT003 # quick shortcut
            ret = "\n".join(failed_exts)
            await ctx.send(f"These extensions failed to be reloaded:\n\n{ret}")
        else:
            await ctx.message.add_reaction(ctx.tick(True))  # noqa: FBT003 # quick shortcut

    @commands.group(invoke_without_command=True)
    async def sql(self, ctx: Context, *, query: str) -> None:
        """Run some SQL."""
        query = self.cleanup_code(query)

        strategy = ctx.db.execute if query.count(";") > 1 else ctx.db.fetch

        try:
            start = time.perf_counter()
            results = await strategy(query)
            dati = (time.perf_counter() - start) * 1000.0
        except (ValueError, TypeError):
            await ctx.send(f"```py\n{traceback.format_exc()}\n```")
            return

        rows = len(results)
        if isinstance(results, str) or rows == 0:
            await ctx.send(f"`{dati:.2f}ms: {results}`")
            return

        headers = list(results[0].keys())
        table = formats.TabularData()
        table.set_columns(headers)
        table.add_rows(list(r.values()) for r in results)
        render = table.render()

        fmt = f"```\n{render}\n```\n*Returned {formats.plural(rows):row} in {dati:.2f}ms*"
        if len(fmt) > 2000:
            filep = io.BytesIO(fmt.encode("utf-8"))
            await ctx.send("Too many results...", files=[discord.File(filep, "results.txt")])
        else:
            await ctx.send(fmt)

    @sql.command(name="table")
    async def sql_table(self, ctx: Context, *, table_name: str) -> None:
        """Runs a query describing the table schema."""
        query = """SELECT column_name, data_type, column_default, is_nullable
                   FROM INFORMATION_SCHEMA.COLUMNS
                   WHERE table_name = $1
                """

        results: list[Record] = await ctx.db.fetch(query, table_name)

        headers = list(results[0].keys())
        table = formats.TabularData()
        table.set_columns(headers)
        table.add_rows(list(r.values()) for r in results)
        render = table.render()

        fmt = f"```\n{render}\n```"
        if len(fmt) > 2000:
            filep = io.BytesIO(fmt.encode("utf-8"))
            await ctx.send("Too many results...", files=[discord.File(filep, "results.txt")])
        else:
            await ctx.send(fmt)

    @commands.command()
    @commands.guild_only()
    async def sync(
        self,
        ctx: GuildContext,
        guilds: Greedy[discord.Object],
        spec: Literal["~", "*", "^"] | None = None,
    ) -> None:
        """
        Pass guild ids or pass a sync specification:-

        `~` -> Current guild.
        `*` -> Copies global to current guild.
        `^` -> Clears all guild commands.
        """
        if not guilds:
            if spec == "~":
                fmt = await ctx.bot.tree.sync(guild=ctx.guild)
            elif spec == "*":
                ctx.bot.tree.copy_global_to(guild=ctx.guild)
                fmt = await ctx.bot.tree.sync(guild=ctx.guild)
            elif spec == "^":
                ctx.bot.tree.clear_commands(guild=ctx.guild)
                await ctx.bot.tree.sync(guild=ctx.guild)
                fmt = []
            else:
                fmt = await ctx.bot.tree.sync()

            await ctx.send(
                f"Synced {formats.plural(len(fmt)):command} {'globally' if spec is None else 'to the current guild.'}",
            )
            return

        ret = 0
        for guild in guilds:
            try:
                await ctx.bot.tree.sync(guild=guild)
            except discord.HTTPException:
                pass
            else:
                ret += 1

        await ctx.send(f"Synced the tree to {formats.plural(ret):guild}.")


async def setup(bot: Graha) -> None:
    """Cog entrypoint."""
    await bot.add_cog(Admin(bot))
