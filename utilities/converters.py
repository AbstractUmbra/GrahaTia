"""
This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""

from __future__ import annotations

import datetime
import zoneinfo
from typing import TYPE_CHECKING, Literal, TypedDict

import discord
from discord import app_commands
from discord.ext import commands

from utilities.context import Context


if TYPE_CHECKING:
    from typing_extensions import NotRequired


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


class DatetimeConverter(commands.Converter[datetime.datetime]):
    @staticmethod
    async def get_timezone(ctx: Context) -> zoneinfo.ZoneInfo | None:
        if ctx.guild is None:
            tz = zoneinfo.ZoneInfo("UTC")
        else:
            row: str | None = await ctx.bot.pool.fetchval(
                "SELECT tz FROM tz_store WHERE user_id = $1 and $2 = ANY(guild_ids);", ctx.author.id, ctx.guild.id
            )
            if row:
                tz = zoneinfo.ZoneInfo(row)
            else:
                tz = zoneinfo.ZoneInfo("UTC")

        return tz

    @classmethod
    async def parse(
        cls,
        argument: str,
        /,
        *,
        ctx: Context,
        timezone: datetime.tzinfo | None = datetime.timezone.utc,
        now: datetime.datetime | None = None,
    ) -> list[tuple[datetime.datetime, int, int]]:
        now = now or datetime.datetime.now(datetime.timezone.utc)

        times: list[tuple[datetime.datetime, int, int]] = []

        async with ctx.bot.session.post(
            "http://127.0.0.1:7731/parse",
            data={
                "locale": "en_US",
                "text": argument,
                "dims": '["time", "duration"]',
                "tz": str(timezone),
            },
        ) as response:
            data: list[DucklingResponse] = await response.json()

            for time in data:
                if time["dim"] == "time" and "value" in time["value"]:
                    times.append(
                        (
                            datetime.datetime.fromisoformat(time["value"]["value"]),
                            time["start"],
                            time["end"],
                        )
                    )
                elif time["dim"] == "duration":
                    times.append(
                        (
                            datetime.datetime.now(datetime.timezone.utc)
                            + datetime.timedelta(seconds=time["value"]["normalized"]["value"]),
                            time["start"],
                            time["end"],
                        )
                    )

        return times

    @classmethod
    async def convert(cls, ctx: Context, argument: str) -> datetime.datetime:

        timezone = await cls.get_timezone(ctx)
        now = ctx.message.created_at.astimezone(tz=timezone)

        parsed_times = await cls.parse(argument, ctx=ctx, timezone=timezone, now=now)

        if len(parsed_times) == 0:
            raise commands.BadArgument("Could not parse time.")
        elif len(parsed_times) > 1:
            ...  # TODO: Raise on too many?

        return parsed_times[0][0]


class WhenAndWhatConverter(commands.Converter[tuple[datetime.datetime, str]]):
    @classmethod
    async def convert(cls, ctx: Context, argument: str) -> tuple[datetime.datetime, str]:
        timezone = await DatetimeConverter.get_timezone(ctx)
        now = ctx.message.created_at.astimezone(tz=timezone)

        # Strip some common stuff
        for prefix in ("me to ", "me in ", "me at ", "me that "):
            if argument.startswith(prefix):
                argument = argument[len(prefix) :]
                break

        for suffix in ("from now",):
            if argument.endswith(suffix):
                argument = argument[: -len(suffix)]

        argument = argument.strip()

        # Determine the date argument
        parsed_times = await DatetimeConverter.parse(argument, ctx=ctx, timezone=timezone, now=now)

        if len(parsed_times) == 0:
            raise commands.BadArgument("Could not parse time.")
        elif len(parsed_times) > 1:
            ...  # TODO: Raise on too many?

        when, begin, end = parsed_times[0]

        if begin != 0 and end != len(argument):
            raise commands.BadArgument("Could not distinguish time from argument.")

        if begin == 0:
            what = argument[end + 1 :].lstrip(" ,.!:;")
        else:
            what = argument[:begin].strip()

        for prefix in ("to ",):
            if what.startswith(prefix):
                what = what[len(prefix) :]

        return (when, what or "…")


class WhenAndWhatTransformer(app_commands.Transformer):
    @staticmethod
    async def get_timezone(interaction: discord.Interaction) -> zoneinfo.ZoneInfo | None:
        if interaction.guild is None:
            tz = zoneinfo.ZoneInfo("UTC")
        else:
            row: str | None = await interaction.client.pool.fetchval(  # type: ignore
                "SELECT tz FROM tz_store WHERE user_id = $1 and $2 = ANY(guild_ids);",
                interaction.user.id,
                interaction.guild.id,
            )
            if row:
                tz = zoneinfo.ZoneInfo(row)
            else:
                tz = zoneinfo.ZoneInfo("UTC")

        return tz

    @classmethod
    async def parse(
        cls,
        argument: str,
        /,
        *,
        interaction: discord.Interaction,
        timezone: datetime.tzinfo | None = datetime.timezone.utc,
        now: datetime.datetime | None = None,
    ) -> list[tuple[datetime.datetime, int, int]]:
        now = now or datetime.datetime.now(datetime.timezone.utc)

        times: list[tuple[datetime.datetime, int, int]] = []

        async with interaction.client.session.post(  # type: ignore
            "http://127.0.0.1:7731/parse",
            data={
                "locale": "en_US",
                "text": argument,
                "dims": '["time", "duration"]',
                "tz": str(timezone),
            },
        ) as response:
            data: list[DucklingResponse] = await response.json()

            for time in data:
                if time["dim"] == "time" and "value" in time["value"]:
                    times.append(
                        (
                            datetime.datetime.fromisoformat(time["value"]["value"]),
                            time["start"],
                            time["end"],
                        )
                    )
                elif time["dim"] == "duration":
                    times.append(
                        (
                            datetime.datetime.now(datetime.timezone.utc)
                            + datetime.timedelta(seconds=time["value"]["normalized"]["value"]),
                            time["start"],
                            time["end"],
                        )
                    )

        return times

    @classmethod
    async def transform(cls, interaction: discord.Interaction, value: str) -> datetime.datetime:
        timezone = await cls.get_timezone(interaction)
        now = interaction.created_at.astimezone(tz=timezone)

        # Strip some common stuff
        for prefix in ("me to ", "me in ", "me at ", "me that "):
            if value.startswith(prefix):
                value = value[len(prefix) :]
                break

        for suffix in ("from now",):
            if value.endswith(suffix):
                value = value[: -len(suffix)]

        value = value.strip()

        parsed_times = await cls.parse(value, interaction=interaction, timezone=timezone, now=now)

        if len(parsed_times) == 0:
            raise commands.BadArgument("Could not parse time.")
        elif len(parsed_times) > 1:
            ...  # TODO: Raise on too many?

        when, begin, end = parsed_times[0]

        if begin != 0 and end != len(value):
            raise ValueError("Could not distinguish time from argument.")

        if begin == 0:
            what = value[end + 1 :].lstrip(" ,.!:;")
        else:
            what = value[:begin].strip()

        for prefix in ("to ",):
            if what.startswith(prefix):
                what = what[len(prefix) :]

        return when
