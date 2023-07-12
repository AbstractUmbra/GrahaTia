"""
This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""

from typing import TYPE_CHECKING, Literal, TypedDict


if TYPE_CHECKING:
    from typing_extensions import NotRequired


__all__ = ("DucklingResponse",)


class DucklingNormalised(TypedDict):
    unit: Literal["second"]
    value: int


class DucklingResponseValue(TypedDict):
    normalized: DucklingNormalised
    type: Literal["value"]
    unit: str
    value: NotRequired[str]
    minute: NotRequired[int]
    hour: NotRequired[int]
    second: NotRequired[int]
    day: NotRequired[int]
    week: NotRequired[int]
    hour: NotRequired[int]


class DucklingResponse(TypedDict):
    body: str
    dim: Literal["duration", "time"]
    end: int
    start: int
    latent: bool
    value: DucklingResponseValue
