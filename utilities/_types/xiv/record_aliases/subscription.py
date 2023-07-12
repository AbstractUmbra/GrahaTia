"""
This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""

from typing import TypedDict


__all__ = ("EventRecord",)


class EventRecord(TypedDict):
    """
    This is actually an asyncpg Record.
    """

    guild_id: int
    channel_id: int | None
    thread_id: int | None
    webhook_url: str
    subscriptions: int
    daily_role_id: int | None
    weekly_role_id: int | None
    fashion_report_role_id: int | None
