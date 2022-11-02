"""
This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from discord.ext.commands import Cog


if TYPE_CHECKING:
    from bot import Graha

__all__ = ("GrahaBaseCog",)


class GrahaBaseCog(Cog):
    __slots__ = ("bot",)

    def __init__(self, bot: Graha, /) -> None:
        self.bot: Graha = bot

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}>"
