from __future__ import annotations

from io import BytesIO
from typing import TYPE_CHECKING, Union
import discord

import yarl
from discord.ext import commands
from utilities.cog import GrahaBaseCog as BaseCog
from utilities.context import Context

if TYPE_CHECKING:
    from typing import ClassVar

    from bot import Graha
    from utilities._types.xiv.character_cards.character_cards import Error, PrepareResponse


class APIError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(f"api returned an error: {reason}")
        self.reason = reason


class CharacterCards(BaseCog):
    URL: ClassVar[yarl.URL] = yarl.URL("https://xiv-character-cards.drakon.cloud/")

    def __init__(self, bot: Graha, /) -> None:
        super().__init__(bot)

    async def get_card(self, *, world: str, name: str) -> str:
        """Fetches a character card from the api, returning the url to the final image.

        Args:
            world (str): The character's world.
            name (str): The character's name, in First, Last format.

        Returns:
            str: The prepared image url.
        """
        async with self.bot.session.get(self.URL / f"prepare/name/{world}/{name}") as r:
            res: Union[Error, PrepareResponse] = await r.json()

        if res["status"] == "error":
            raise APIError(res["reason"])

        # yarl does not support starting from slashes, so i just trim the slash instead.
        return str(self.URL / res["url"][1:])

    @commands.command()
    async def character_card(self, ctx: Context, world: str, *, character: str):
        """
        Generates a character card displaying information about a given character
        Give the name in the format, `First, Last`.
        """
        async with ctx.typing():
            img: str = await self.get_card(world=world, name=character)

            async with self.bot.session.get(img) as res:
                bytes: BytesIO = BytesIO(await res.read())

            await ctx.send(f"Here is the card for {character}!", file=discord.File(fp=bytes, filename=f"{character}-card.png"))


async def setup(bot: Graha):
    await bot.add_cog(CharacterCards(bot))
