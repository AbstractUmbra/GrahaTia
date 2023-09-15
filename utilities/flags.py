from __future__ import annotations

from functools import reduce
from typing import TYPE_CHECKING

from discord.flags import BaseFlags, fill_with_flags, flag_value

if TYPE_CHECKING:
    from typing_extensions import Self

__all__ = ("SubscribedEventsFlags",)


@fill_with_flags()
class SubscribedEventsFlags(BaseFlags):
    __slots__ = ()

    def __init__(self, value: int = 0, **kwargs: bool) -> None:
        self.value: int = value
        for key, value in kwargs.items():
            if key not in self.VALID_FLAGS:
                raise TypeError(f"{key!r} is not a valid flag name.")
            setattr(self, key, value)

    @classmethod
    def all(cls: type[Self]) -> Self:
        value = reduce(lambda a, b: a | b, cls.VALID_FLAGS.values())
        self = cls.__new__(cls)
        self.value = value
        return self

    @classmethod
    def none(cls: type[Self]) -> Self:
        self = cls.__new__(cls)
        self.value = self.DEFAULT_VALUE
        return self

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
    def jumbo_cactpot(self) -> int:
        return 1 << 4
