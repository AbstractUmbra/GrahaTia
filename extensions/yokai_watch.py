from __future__ import annotations

import pathlib
from collections import defaultdict
from typing import TYPE_CHECKING, Literal

import discord
from discord import Enum, app_commands
from discord.app_commands.commands import _populate_choices  # we do some cheating
from discord.enums import try_enum
from discord.ext import commands

from utilities.shared.formats import from_json, random_pastel_colour

if TYPE_CHECKING:
    from bot import Graha
    from utilities.context import Interaction
    from utilities.shared._types.xiv.yokai import Yokai as YokaiType, YokaiConfig

CONFIG_PATH = pathlib.Path("./configs/yokai.json")


ALLOWED_LOCATIONS: Literal[
    "Stormblood",
    "Heavensward",
    "Central Shroud",
    "Central Thanalan",
    "East Shroud",
    "Eastern Thanalan",
    "Lower La Noscea",
    "Middle La Noscea",
    "North Shroud",
    "Outer La Noscea",
    "South Shroud",
    "Southern Thanalan",
    "Upper La Noscea",
    "Western La Noscea",
    "Western Thanalan",
]


class Yokai(Enum):
    Jibanyan = 1
    Komasan = 2
    USApyon = 3
    Whisper = 4
    Shogunyan = 5
    Hovernyan = 6
    Komajiro = 7
    Noko = 8
    Venoct = 9
    Kyubi = 10
    Robonyan_F__type = 11
    Blizzaria = 12
    Manjimutt = 13
    Lord_Enma = 14
    Lord_Ananta = 15
    Zazel = 16
    Damona = 17

    def clean_name(self) -> str:
        return self.name.replace("__", "-").replace("_", " ")


class YokaiWatch(commands.GroupCog, name="yokai-watch"):
    def __init__(self, bot: Graha, /, *, config: YokaiConfig) -> None:
        self.bot: Graha = bot
        self.config: YokaiConfig = config
        self._weapon_choices = self._populate_weapons()
        self._area_to_yokai = self._populate_areas()
        self._yokai_choices = self._populate_yokai()
        _populate_choices(self.yokai_info._params, {"yokai": self._yokai_choices})
        _populate_choices(self.yokai_weapon_info._params, {"weapon": self._weapon_choices})

    def _populate_areas(self) -> defaultdict[str, list[Yokai]]:
        ret = defaultdict[str, list[Yokai]](list)
        # {"Western Thanalan": [Kyubi, Venoct], ...}

        for data in self.config["yokai"].values():
            for area in data["areas"]:
                ret[area.title()].append(try_enum(Yokai, data["id"]))

        return ret

    def _populate_weapons(self) -> list[app_commands.Choice[int]]:
        return [
            app_commands.Choice(name=f"[{y['weapon']['job']}] {y['weapon']['name']}", value=y["id"])
            for y in self.config["yokai"].values()
        ]

    def _populate_yokai(self) -> list[app_commands.Choice[str]]:
        yokai = [Yokai[n] for n in self.config["yokai"]]
        return [app_commands.Choice(name=n.clean_name(), value=n.clean_name()) for n in yokai]

    def _resolve_id_to_entry(self, yokai_id: int) -> YokaiType:
        for yokai in self.config["yokai"].values():
            if yokai["id"] == yokai_id:
                return yokai

        msg = f"Yo-kai with the ID of {yokai_id} cannot be found."
        raise ValueError(msg)

    @app_commands.command(name="yokai-info")
    async def yokai_info(self, interaction: Interaction, yokai: str) -> None:
        """Get information about a specific Yo-kai minion!"""
        entry = self.config["yokai"][yokai]

        embed = discord.Embed(title=yokai.title(), colour=random_pastel_colour(), url=entry["url"])
        embed.description = (
            f"The areas this Yo-kai allows you to farm medals in are as follows:-\n\n{'\n'.join(entry['areas'])}"
        )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="weapon-info")
    @app_commands.describe(weapon="The weapon to fetch information about.")
    async def yokai_weapon_info(self, interaction: Interaction, weapon: int) -> None:
        """Get info about a specific Yo-kai weapon!"""
        entry = self._resolve_id_to_entry(weapon)
        weapon_entry = entry["weapon"]

        embed = discord.Embed(title=weapon_entry["name"].title(), url=weapon_entry["url"], colour=random_pastel_colour())
        embed.description = f"This weapon was created for the {weapon_entry['job']} job."

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="area-info")
    @app_commands.describe(area="The area to select information about.")
    async def location_info_command(
        self,
        interaction: Interaction,
        area: Literal[
            "Stormblood",
            "Heavensward",
            "Central Shroud",
            "Central Thanalan",
            "East Shroud",
            "Eastern Thanalan",
            "Lower La Noscea",
            "Middle La Noscea",
            "North Shroud",
            "Outer La Noscea",
            "South Shroud",
            "Southern Thanalan",
            "Upper La Noscea",
            "Western La Noscea",
            "Western Thanalan",
        ],
    ) -> None:
        """Get information about Yokai farming areas specifically."""
        await interaction.response.defer()

        try:
            yokai = self._area_to_yokai[area]
        except KeyError:
            return await interaction.followup.send("Sorry, something has broken but my developer knows!")

        embed = discord.Embed(title=area, colour=random_pastel_colour())
        embed.description = (
            f"Yo-kai minions that can gain medals in this area:-\n\n{'\n'.join([y.name.replace('_', ' ') for y in yokai])}"
        )

        return await interaction.followup.send(embed=embed)

    @app_commands.command(name="info")
    async def info_command(self, interaction: Interaction) -> None:
        """Overall information about the Yo-kai Watch event!"""
        fmt = (
            "The Yo-kai Watch! event is a limited time event within Final Fantasy:tm: "
            "XIV where you can collect the Yo-kai minions, "
            "with the optional goal of then gaining Yo-kai weapons and mounts!"
        )

        embed = discord.Embed(
            title="Yo-kai Watch event!",
            url=self.config["event"],
            description=fmt,
            colour=random_pastel_colour(),
        ).set_image(url=self.config["infographic"])

        await interaction.response.send_message(embed=embed)


async def setup(bot: Graha) -> None:
    if not CONFIG_PATH.exists():
        return

    config: YokaiConfig = from_json(CONFIG_PATH.read_text())
    await bot.add_cog(YokaiWatch(bot, config=config))
