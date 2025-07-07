from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

import discord

from utilities.shared.cog import BaseCog
from utilities.shared.formats import random_pastel_colour
from utilities.shared.time import Weekday, resolve_next_weekday

if TYPE_CHECKING:
    from bot import Graha

OC_INVITE: str = "https://discord.gg/overseascasuals"
OC_BOT_CHANNEL: str = "https://canary.discord.com/channels/1034534280757522442/1034985297391407126"


class IslandSanctuary(BaseCog["Graha"]):
    @staticmethod
    def next_reset(*, source: datetime.datetime | None = None) -> datetime.datetime:
        return resolve_next_weekday(
            target=Weekday.tuesday, source=source, current_week_included=True, before_time=datetime.time(hour=8)
        )

    def generate_embed(self, *, when: datetime.datetime | None = None) -> discord.Embed:
        when = when or (datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=15))
        embed = discord.Embed(title="Island Sanctuary workshop has reset!", url=OC_INVITE, colour=random_pastel_colour())
        embed.set_image(url="https://static.abstractumbra.dev/images/sanctuary.png")
        embed.description = (
            "The link in this embed is a Discord invite to the Overseas Casuals server.\n"
            "They optimize and automate reporting on which island workshop crafting schedule will maximize your profile! "
            "Check them out and after finding your way around, check out the "
            f"[#bot-spam]({OC_BOT_CHANNEL}) channel and use their bot to get your weekly plannings!"
        )
        embed.timestamp = self.next_reset(source=when)
        embed.set_footer(text="Not affiliated with OC in any way, just a fan!")

        return embed


async def setup(bot: Graha, /) -> None:
    await bot.add_cog(IslandSanctuary(bot))
