from __future__ import annotations

import pathlib
from collections import defaultdict
from io import BytesIO
from typing import TYPE_CHECKING

import discord
import yarl
from discord import app_commands
from discord.app_commands.commands import _populate_choices

from utilities import fuzzy
from utilities.cog import GrahaBaseCog as BaseCog
from utilities.shared.formats import from_json

if TYPE_CHECKING:
    from typing import ClassVar

    from bot import Graha
    from utilities.shared._types.xiv.character_cards import Error, PrepareResponse
    from utilities.shared._types.xiv.worlds import WorldsData

_worlds_path = pathlib.Path("configs/worlds.json")
if not _worlds_path.exists():
    raise RuntimeError("Worlds data is not present.")

with _worlds_path.open("r") as fp:
    WORLDS_DATA: WorldsData = from_json(fp.read())


class APIError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(f"api returned an error: {reason}")
        self.reason = reason


class CharacterCards(BaseCog):
    URL: ClassVar[yarl.URL] = yarl.URL("https://xiv-character-cards.drakon.cloud/")
    worlds: dict[str, list[str]]
    datacenters: list[app_commands.Choice[str]]
    all_worlds: list[app_commands.Choice[str]]

    def __init__(self, bot: Graha, /) -> None:
        super().__init__(bot)
        self._cache_data()
        _populate_choices(self.character_card._params, {"datacenter": self.datacenters})

    def _cache_data(self) -> None:
        datacenters: list[app_commands.Choice[str]] = []
        all_worlds: list[app_commands.Choice[str]] = []
        worlds: dict[str, list[str]] = defaultdict(list)
        for key, value in WORLDS_DATA.items():
            for dc_data in value["datacenters"]:  # type: ignore # typing grievance with TypedDict.items()
                for dc, worlds_ in dc_data.items():
                    datacenters.append(app_commands.Choice(name=f"[{key}] {dc}", value=dc))
                    for world in worlds_:
                        all_worlds.append(app_commands.Choice(name=f"[{key} {dc}] {world}", value=world))
                        worlds[dc].append(world)

        self.worlds = dict(worlds)
        self.datacenters = datacenters
        self.all_worlds = all_worlds

    def _resolve_world_to_dc(self, world: str, /) -> str | None:
        for key, value in self.worlds.items():
            if world in value:
                return key

    def _resolve_dc_to_region(self, datacenter: str, /) -> str | None:
        for key, value in WORLDS_DATA.items():
            for dc in value["datacenters"]:  # type: ignore # typing grievance with TypedDict.items()
                if datacenter in dc:
                    return key

    async def get_card(self, *, world: str, name: str) -> str:
        """Fetches a character card from the api, returning the url to the final image.

        Parameters
        -----------
        world :class:`str`: The character's world.
        name :class`str`: The character's name.

        Returns
        ---------
        :class:`str`:  The prepared image url.
        """
        async with self.bot.session.get(self.URL / f"prepare/name/{world}/{name}") as r:
            res: Error | PrepareResponse = await r.json()

        if res["status"] == "error":
            raise APIError(res["reason"])

        # yarl does not support starting from slashes, so i just trim the slash instead.
        return str(self.URL / res["url"][1:])

    @app_commands.command()
    @app_commands.describe(datacenter="The datacenter the character exists in.", world="Your character's home world.")
    async def character_card(self, interaction: discord.Interaction, datacenter: str, world: str, character: str) -> None:
        """
        Generates a character card displaying information about a given character.
        """
        await interaction.response.defer(thinking=True)
        try:
            img: str = await self.get_card(world=world, name=character)
        except APIError:
            return await interaction.followup.send(
                embed=discord.Embed(description="An error occurred with the api, this is likely due to an invalid name.")
            )

        async with self.bot.session.get(img) as resp:
            data = await resp.read()
            buffer: BytesIO = BytesIO(data)
        await interaction.followup.send(
            f"Here is the card for {character}!", file=discord.File(fp=buffer, filename=f"{character}-card.png")
        )

    # @character_card.autocomplete("datacenter")
    async def datacenter_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        if not current:
            return self.datacenters[:25]

        matches = fuzzy.extract(current, choices=[choice.name for choice in self.datacenters], limit=5, score_cutoff=20)

        ret: list[app_commands.Choice[str]] = []
        for item, _ in matches:
            _x = discord.utils.get(self.datacenters, name=item)
            if _x:
                ret.append(_x)

        return ret[:25]

    @character_card.autocomplete("world")
    async def world_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        namespace = interaction.namespace

        dc_key: str = namespace.datacenter

        worlds = self.worlds[dc_key]

        if not current:
            return [app_commands.Choice(name=world, value=world) for world in worlds]

        matches = fuzzy.extract(current, choices=worlds, limit=5, score_cutoff=20)

        ret: list[app_commands.Choice[str]] = []
        for item, _ in matches:
            _x = discord.utils.get(self.all_worlds, name=item)
            if _x:
                ret.append(_x)

        return ret[:25]


async def setup(bot: Graha) -> None:
    await bot.add_cog(CharacterCards(bot))
