"""
This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""

from __future__ import annotations

import operator
from functools import reduce
from typing import TYPE_CHECKING, Self

from asyncpg import BitString
from discord.flags import BaseFlags as DpyFlags, fill_with_flags, flag_value

if TYPE_CHECKING:
    from typing import Self

__all__ = (
    "SubscribedEventsFlags",
    "flag_value",
)


@fill_with_flags()
class SubscribedEventsFlags(DpyFlags):
    __slots__ = ()

    def __init__(self, value: int = 0, **kwargs: bool) -> None:
        self.value: int = value

        for key, inner_value in kwargs.items():
            if key not in self.VALID_FLAGS:
                msg = f"{key!r} is not a valid flag name."
                raise TypeError(msg)
            setattr(self, key, inner_value)

    @classmethod
    def all(cls) -> Self:
        value = reduce(operator.or_, cls.VALID_FLAGS.values())
        self = cls.__new__(cls)
        self.value = value
        return self

    @classmethod
    def none(cls) -> Self:
        self = cls.__new__(cls)
        self.value = self.DEFAULT_VALUE
        return self

    def to_bitstring(self) -> BitString:
        return BitString.from_int(self.value, length=64)

    @flag_value
    def daily_resets(self) -> int:
        return 1 << 0

    @flag_value
    def weekly_resets(self) -> int:
        return 1 << 1

    @flag_value
    def fashion_report(self) -> int:
        return 1 << 2

    @flag_value
    def ocean_fishing(self) -> int:
        return 1 << 3

    @flag_value
    def jumbo_cactpot_na(self) -> int:
        return 1 << 4

    @flag_value
    def jumbo_cactpot_eu(self) -> int:
        return 1 << 5

    @flag_value
    def jumbo_cactpot_jp(self) -> int:
        return 1 << 6

    @flag_value
    def jumbo_cactpot_oce(self) -> int:
        return 1 << 7

    @flag_value
    def gate(self) -> int:
        return 1 << 8

    @flag_value
    def open_tournament(self) -> int:
        return 1 << 9

    @flag_value
    def triple_tournament_tournament(self) -> int:
        return 1 << 10

    @flag_value
    def island_sanctuary(self) -> int:
        return 1 << 11
