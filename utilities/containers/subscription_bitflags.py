"""
This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""

from __future__ import annotations

from functools import reduce

from discord.flags import BaseFlags, fill_with_flags, flag_value


__all__ = ("SubscriptionFlags",)


@fill_with_flags()
class SubscriptionFlags(BaseFlags):
    __slots__ = ()

    def __init__(self, value: int = 0, **kwargs: bool) -> None:
        self.value: int = value
        for key, value in kwargs.items():
            if key not in self.VALID_FLAGS:
                raise TypeError(f"{key!r} is not a valid flag name.")
            setattr(self, key, value)

    @classmethod
    def all(cls) -> SubscriptionFlags:
        """A factory method that creates a :class:`Intents` with everything enabled."""
        value = reduce(lambda a, b: a | b, cls.VALID_FLAGS.values())
        self = cls.__new__(cls)
        self.value = value
        return self

    @classmethod
    def none(cls) -> SubscriptionFlags:
        """A factory method that creates a :class:`Intents` with everything disabled."""
        self = cls.__new__(cls)
        self.value = self.DEFAULT_VALUE
        return self

    @flag_value
    def daily_reset(self) -> int:
        return 1 << 0

    @flag_value
    def weekly_reset(self) -> int:
        return 1 << 1

    @flag_value
    def fashion_report(self) -> int:
        return 1 << 2
