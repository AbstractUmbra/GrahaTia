"""
This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from discord.ext import commands

if TYPE_CHECKING:
    from discord import Message

    from bot import Graha


def callable_prefix(bot: Graha, message: Message, /) -> list[str]:
    first_char = message.author.display_name[0]
    lower, upper = first_char.lower(), first_char.upper()

    ret = [lower, upper, "gt "]
    if message.guild is None:
        return commands.when_mentioned_or(*ret)(bot, message)

    guild_prefixes: list[str] | None = bot._prefix_data.get(str(message.guild.id))
    if guild_prefixes is None:
        guild_prefixes = ret
    else:
        guild_prefixes.extend(ret)

    return commands.when_mentioned_or(*guild_prefixes)(bot, message)
