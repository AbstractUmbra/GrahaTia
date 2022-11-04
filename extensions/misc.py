"""
This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""

from __future__ import annotations

import datetime
import re
import zoneinfo
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from bot import Graha
from utilities.cog import GrahaBaseCog as BaseCog
from utilities.context import Context
from utilities.formats import to_codeblock
from utilities.time import ordinal


if TYPE_CHECKING:
    from bot import Graha

TZ_NAME_MAPPING = {
    "UTC": "Europe (Chaos/Light)",
    "America/Los_Angeles": "NA (Aether/Primal/Crystal)",
    "Asia/Tokyo": "Japan (Gaia/Mana/Elemental/Meteor)",
    "Australia/Sydney": "Australia (Materia)",
}


class Misc(BaseCog):
    def _clean_dt(self, dt: datetime.datetime) -> str:
        ord_ = ordinal(dt.day)
        fmt = dt.strftime(f"%H:%M on %A, {ord_} of %B %Y")

        return fmt

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message, /) -> None:
        if re.fullmatch(rf"<@!?{self.bot.user.id}>", message.content):
            embed = discord.Embed(colour=discord.Colour.random())

            guild = message.guild or discord.Object(id=0)
            prefixes = self.bot._get_guild_prefixes(guild=guild, raw=True)

            fmt = "Hey there, my prefixes in this server are:-\n\n"
            fmt += f"{self.bot.user.mention} \n"
            fmt += to_codeblock("\n".join(prefixes), language="", escape_md=False)
            embed.description = fmt

            embed.set_footer(text=f"{message.author} :: ({message.author.id})", icon_url=message.author.display_avatar)

            await message.reply(embed=embed, mention_author=False)

    @commands.command(name="invite")
    async def invite_graha(self, ctx: Context) -> None:
        assert ctx.bot.user

        required_permissions = discord.Permissions(
            send_messages=True,
            read_messages=True,
            read_message_history=True,
            embed_links=True,
            manage_webhooks=True,
        )
        perms_link = discord.utils.oauth_url(ctx.bot.user.id, permissions=required_permissions)
        clean_link = discord.utils.oauth_url(ctx.bot.user.id)

        fmt = (
            "Hello, thank you for wanting to invite me.\n"
            f"I like being upfront about things so [this link]({perms_link})"
            " will invite me with the mandatory permissions I need for full features.\n"
            f"[This link]({clean_link}) will invite me with no permissions and you can update and assign permissions/roles as necessary."
        )

        now = datetime.datetime.now(datetime.timezone.utc)
        embed = discord.Embed(colour=discord.Colour.random(), description=fmt, timestamp=now)
        embed.set_author(name=ctx.bot.user.name, icon_url=ctx.bot.user.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(name="servertime", aliases=["st", "ST"])
    async def server_times(self, ctx: Context) -> None:
        """Shows your local time against the datacenter server times."""
        utc = datetime.datetime.now(datetime.timezone.utc)

        clean_utc = discord.utils.format_dt(utc, "F")
        fmt = f"The time now is {clean_utc}, the server times are:-\n\n"

        embed = discord.Embed(colour=discord.Colour.teal())
        embed.description = fmt

        for tz, name in TZ_NAME_MAPPING.items():
            _local = utc.astimezone(zoneinfo.ZoneInfo(tz))
            embed.add_field(name=name, value=self._clean_dt(_local), inline=False)

        await ctx.send(embed=embed)


async def setup(bot: Graha) -> None:
    await bot.add_cog(Misc(bot))
