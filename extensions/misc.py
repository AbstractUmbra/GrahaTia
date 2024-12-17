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
from discord import app_commands
from discord.ext import commands

from utilities.shared.cog import BaseCog
from utilities.shared.formats import to_codeblock
from utilities.shared.time import ordinal

if TYPE_CHECKING:
    from bot import Graha
    from utilities.context import Interaction

TZ_NAME_MAPPING = {
    "UTC": "Europe (Chaos/Light)",
    "America/Los_Angeles": "NA (Aether/Primal/Crystal)",
    "Asia/Tokyo": "Japan (Gaia/Mana/Elemental/Meteor)",
    "Australia/Sydney": "Australia (Materia)",
}


class Misc(BaseCog["Graha"]):
    def _clean_dt(self, dt: datetime.datetime) -> str:
        ord_ = ordinal(dt.day)
        return dt.strftime(f"%H:%M on %A, {ord_} of %B %Y")

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

            embed.set_footer(
                text="You can also use the first letter of your display name followed by a space.",
                icon_url=message.author.display_avatar,
            )

            await message.reply(embed=embed, mention_author=False)

    @app_commands.command(name="invite")
    async def invite_graha(self, interaction: Interaction) -> None:
        """Invite G'raha Tia to your server or as an installation!"""
        assert interaction.client.user

        required_permissions = discord.Permissions(
            send_messages=True,
            read_messages=True,
            read_message_history=True,
            embed_links=True,
            manage_webhooks=True,
        )
        perms_link = discord.utils.oauth_url(interaction.client.user.id, permissions=required_permissions)
        clean_link = discord.utils.oauth_url(interaction.client.user.id)
        installation_link = discord.utils.oauth_url(interaction.client.user.id, scopes=["applications.commands"])

        fmt = (
            f"Hello, thank you for wanting to invite me.\nI like being upfront about things so [this link]({perms_link})"
            f" will invite me with the mandatory permissions I need for full features.\n[This link]({clean_link}) will"
            " invite me with no permissions and you can update and assign permissions/roles as necessary.\n\n"
            f"[This link]({installation_link}) should also allow you to invite me as an installed application, "
            "so you can use most of my commands anywhere!"
        )

        now = datetime.datetime.now(datetime.UTC)
        embed = discord.Embed(colour=discord.Colour.random(), description=fmt, timestamp=now)
        embed.set_author(name=interaction.client.user.name, icon_url=interaction.client.user.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="server-times")
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.describe(ephemeral="Whether to show the data privately to you, or not.")
    async def server_times(self, interaction: Interaction, ephemeral: bool = True) -> None:  # noqa: FBT001, FBT002 # required by dpy
        """Shows your local time against the datacenter server times."""
        await interaction.response.defer(ephemeral=ephemeral)

        utc = datetime.datetime.now(datetime.UTC)

        clean_utc = discord.utils.format_dt(utc, "F")
        fmt = f"The time now is {clean_utc}, the server times are:-\n\n"

        embed = discord.Embed(colour=discord.Colour.teal())
        embed.description = fmt

        for tz, name in TZ_NAME_MAPPING.items():
            local = utc.astimezone(zoneinfo.ZoneInfo(tz))
            embed.add_field(name=name, value=self._clean_dt(local), inline=False)

        await interaction.followup.send(embed=embed, ephemeral=ephemeral)


async def setup(bot: Graha) -> None:
    await bot.add_cog(Misc(bot))
