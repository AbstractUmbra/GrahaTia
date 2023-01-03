"""
This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict


if TYPE_CHECKING:
    from typing_extensions import NotRequired


__all__ = ("Config",)


class BotConfig(TypedDict):
    token: str


class DatabaseConfig(TypedDict):
    dsn: str


class LoggingConfig(TypedDict):
    webhook_url: str
    sentry_dsn: NotRequired[str]


class MiscConfig(TypedDict):
    mystbin_token: str


class Config(TypedDict):
    bot: BotConfig
    database: DatabaseConfig
    logging: LoggingConfig
    misc: MiscConfig
    conditional_access: NotRequired[dict[str, list[int]]]
