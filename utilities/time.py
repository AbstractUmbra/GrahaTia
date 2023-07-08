"""
This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""

from __future__ import annotations

import datetime

from dateutil.relativedelta import relativedelta
from discord.utils import format_dt

from .formats import human_join, plural


def human_timedelta(
    dt: datetime.datetime,
    *,
    source: datetime.datetime | None = None,
    accuracy: int | None = 3,
    brief: bool = False,
    suffix: bool = True,
) -> str:
    now = source or (datetime.datetime.now(datetime.timezone.utc))
    # Microsecond free zone
    now = now.replace(microsecond=0)
    dt = dt.replace(microsecond=0)

    # This implementation uses relativedelta instead of the much more obvious
    # divmod approach with seconds because the seconds approach is not entirely
    # accurate once you go over 1 week in terms of accuracy since you have to
    # hardcode a month as 30 or 31 days.
    # A query like "11 months" can be interpreted as "!1 months and 6 days"
    if dt > now:
        delta = relativedelta(dt, now)
        str_suffix = ""
    else:
        delta = relativedelta(now, dt)
        str_suffix = " ago" if suffix else ""

    attrs: list[tuple[str, str]] = [
        ("year", "y"),
        ("month", "mo"),
        ("day", "d"),
        ("hour", "h"),
        ("minute", "m"),
        ("second", "s"),
    ]

    output = []
    for attr, brief_attr in attrs:
        elem = getattr(delta, attr + "s")
        if not elem:
            continue

        if attr == "day":
            weeks = delta.weeks
            if weeks:
                elem -= weeks * 7
                if not brief:
                    output.append(format(plural(weeks), "week"))
                else:
                    output.append(f"{weeks}w")

        if elem <= 0:
            continue

        if brief:
            output.append(f"{elem}{brief_attr}")
        else:
            output.append(format(plural(elem), attr))

    if accuracy is not None:
        output = output[:accuracy]

    if len(output) == 0:
        return "now"
    else:
        if not brief:
            return human_join(output, final="and") + str_suffix
        else:
            return " ".join(output) + str_suffix


def hf_time(dt: datetime.datetime) -> str:
    date_modif = ordinal(dt.day)
    return dt.strftime(f"%A {date_modif} of %B %Y @ %H:%M %Z (%z)")


def ordinal(number: int) -> str:
    return f"{number}{'tsnrhtdd'[(number//10%10!=1)*(number%10<4)*number%10::4]}"


def format_relative(dt: datetime.datetime) -> str:
    return format_dt(dt, "R")
