"""
This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""

import datetime

DAILY_RESET_TIME: datetime.time = datetime.time(hour=15, tzinfo=datetime.UTC)
DAILY_RESET_REMINDER_TIME: datetime.time = datetime.time(hour=14, tzinfo=datetime.UTC)
WEEKLY_RESET_TIME: datetime.time = datetime.time(hour=8, tzinfo=datetime.UTC)
WEEKLY_RESET_REMINDER_TIME: datetime.time = datetime.time(hour=7, tzinfo=datetime.UTC)

__all__ = (
    "DAILY_RESET_REMINDER_TIME",
    "DAILY_RESET_TIME",
    "WEEKLY_RESET_REMINDER_TIME",
    "WEEKLY_RESET_TIME",
)
