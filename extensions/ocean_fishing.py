from __future__ import annotations

import datetime
import math
from typing import TYPE_CHECKING, ClassVar, TypedDict

import discord
from discord.ext import commands

from utilities.cog import GrahaBaseCog
from utilities.context import Context


if TYPE_CHECKING:
    from bot import Graha


class UpcomingVoyage(TypedDict):
    date: datetime.datetime
    destination: str


class Voyage:
    DESTINATION_MAPPING: ClassVar[dict[str, str]] = {
        "T": "Rothlyt Sound",
        "N": "Northern Strait of Merlthor",
        "B": "Bloodbrine Sea",
        "R": "Rhotano Sea",
    }

    TIME_MAPPING: ClassVar[dict[str, str]] = {
        "D": "Day",
        "N": "Night",
        "S": "Sunset",
    }

    ROUTE_MAPPING: ClassVar[dict[str, list[str]]] = {
        "T": ["The Cieldalaes", "Rhotano Sea", "The Rothlyt Sound"],
        "N": ["The Southern Strait of Merlthor", "Galadion Bay", "The Northern Strait of Merlthor"],
        "B": ["The Cieldalaes", "The Northern Strait of Merlthor", "The Bloodbrine Sea"],
        "R": ["Galadion Bay", "The Southern Strait of Merlthor", "The Rhotano Sea"],
    }

    ROUTE_TIME_MAPPING: ClassVar[dict[str, list[str]]] = {
        "D": ["\U0001F31E \U00002B07\U0000FE0F", "\U0001F31D", "\U0001F31E"],
        "N": ["\U0001F31E", "\U0001F31E \U00002B07\U0000FE0F", "\U0001F31D"],
        "S": ["\U0001F31D", "\U0001F31E", "\U0001F31E \U00002B07\U0000FE0F"],
    }

    __slots__ = (
        "start_time",
        "_dest_time",
    )

    def __init__(self, input_: UpcomingVoyage) -> None:
        self.start_time: datetime.datetime = input_["date"]
        self._dest_time: str = input_["destination"]

    def __repr__(self) -> str:
        return f"<Voyage start_time={self.start_time} destination={self.destination!r} time={self.time!r}>"

    def __str__(self) -> str:
        return self.details

    def registration_opens(self) -> datetime.datetime:
        return self.start_time - datetime.timedelta(minutes=15)

    def has_set_sail(self, dt: datetime.datetime | None = None, /) -> bool:
        dt = dt or datetime.datetime.now(datetime.timezone.utc)
        return self.start_time < dt

    def can_register(self, dt: datetime.datetime | None = None, /) -> bool:
        open = self.registration_opens()
        dt = dt or datetime.datetime.now(datetime.timezone.utc)
        if 0 < (dt - open).total_seconds() <= 900:
            return True

        return False

    def route(self) -> str:
        routes: list[tuple[str, str]] = []

        for route_destination, time in zip(
            self.ROUTE_MAPPING[self._dest_time[0]], self.ROUTE_TIME_MAPPING[self._dest_time[1]]
        ):
            routes.append((route_destination, time))

        return " -> ".join([f"{item[0]} ({item[1]})" for item in routes])

    @property
    def destination(self) -> str:
        return self.DESTINATION_MAPPING[self._dest_time[0]]

    @property
    def time(self) -> str:
        return self.TIME_MAPPING[self._dest_time[1]]

    @property
    def details(self) -> str:
        return f"{self.destination!r} at {self.time.lower()}"

    @property
    def emoji(self) -> str:
        if self.time == "Day":
            return "\U0001F31E"
        elif self.time == "Night":
            return "\U0001F31D"
        else:
            return "\U0001F31E \U00002B07\U0000FE0F"


class OceanFishing(GrahaBaseCog):
    STARTING_EPOCH: ClassVar[datetime.datetime] = datetime.datetime.fromtimestamp(1593302400, tz=datetime.timezone.utc)
    DESTINATION_CYCLE: ClassVar[list[str]] = ["B", "T", "N", "R"]
    TIME_CYCLE: ClassVar[list[str]] = ["S", "S", "S", "S", "N", "N", "N", "N", "D", "D", "D", "D"]

    def __init__(self, bot: Graha, /) -> None:
        super().__init__(bot)
        self.voyage_cache: list[str] = []
        self.cache_voyages()

    def _from_epoch(self, day: int, hour: int) -> datetime.datetime:
        return (
            self.STARTING_EPOCH
            + datetime.timedelta(days=day)
            + datetime.timedelta(seconds=hour * 3600)
            - datetime.timedelta(seconds=32400)
        )

    def cache_voyages(self) -> None:
        dt = datetime.datetime.fromtimestamp(2700, tz=datetime.timezone.utc)
        cache = self._calculate_voyages(dt=dt, count=144)

        self.voyage_cache = [item["destination"] for item in cache]

    def _calculate_voyages(
        self, *, dt: datetime.datetime, count: int, filter_: list[str] | None = None
    ) -> list[UpcomingVoyage]:
        adjusted_date = (dt + datetime.timedelta(hours=9)) - datetime.timedelta(minutes=45)
        day = math.floor((adjusted_date.timestamp() - 1593302400) / 86400)
        hour = adjusted_date.hour

        offset = hour & 1
        hour += 2 if offset else 1

        if hour > 23:
            day += 1
            hour -= 24

        voyage_number = hour >> 1
        destination_index = ((day + voyage_number) % len(self.DESTINATION_CYCLE) + len(self.DESTINATION_CYCLE)) % len(
            self.DESTINATION_CYCLE
        )
        time_index = ((day + voyage_number) % len(self.TIME_CYCLE) + len(self.TIME_CYCLE)) % len(self.TIME_CYCLE)

        upcoming_voyages: list[UpcomingVoyage] = []

        while len(upcoming_voyages) < count:
            current_destination = self.DESTINATION_CYCLE[destination_index] + self.TIME_CYCLE[time_index]
            if not filter_ or (current_destination in filter_):
                upcoming_voyages.append({"date": self._from_epoch(day, hour), "destination": current_destination})

            if hour == 23:
                day += 1
                hour = 1
                destination_index = (destination_index + 2) % len(self.DESTINATION_CYCLE)
                time_index = (time_index + 2) % len(self.TIME_CYCLE)
            else:
                hour += 2
                destination_index = (destination_index + 1) % len(self.DESTINATION_CYCLE)
                time_index = (time_index + 1) % len(self.TIME_CYCLE)

        return upcoming_voyages

    def calculate_voyages(self, *, dt: datetime.datetime, count: int = 144, filter_: list[str] | None) -> list[Voyage]:
        start_index = math.floor((dt - datetime.timedelta(minutes=45)).timestamp() / 7200)
        upcoming_voyages = []

        for idx in range(100000):
            if len(upcoming_voyages) >= count:
                break

            dest_time = self.voyage_cache[(start_index + idx) % 144]

            if (not filter_) or dest_time in filter_:
                upcoming_voyages.append(
                    Voyage(
                        {
                            "date": datetime.datetime.fromtimestamp(
                                (start_index + idx + 1) * 7200, tz=datetime.timezone.utc
                            ),
                            "destination": dest_time,
                        }
                    )
                )

        return upcoming_voyages

    def _generate_ocean_fishing_embed(self, dt: datetime.datetime, /) -> discord.Embed:
        embed = discord.Embed(colour=discord.Colour.random(), title="Ocean Fishing availability")

        current, next_ = self.calculate_voyages(dt=dt, count=2, filter_=None)
        now = datetime.datetime.now(datetime.timezone.utc)

        fmt = f"The current ocean fishing expedition is {current} {current.emoji} with a route of:-\n{current.route()}.\n"
        if current.has_set_sail(now):
            fmt += "The registration window for this has closed and the voyage is underway.\n\n"
        elif current.can_register(now):
            closes = discord.utils.format_dt(current.start_time)
            closes_rel = discord.utils.format_dt(current.start_time, "R")
            fmt += f"The registration window for this voyage is currently open if you wish to join. Registration will close at {closes} ({closes_rel}).\n\n"
        else:
            registration_opens = current.registration_opens()
            registration_opens_formatted = discord.utils.format_dt(registration_opens)
            registration_opens_formatted_rel = discord.utils.format_dt(registration_opens, "R")
            fmt += f"The registration window for this voyage will open at {registration_opens_formatted} ({registration_opens_formatted_rel})."
        embed.add_field(name="Current Route", value=fmt, inline=False)

        fmt = ""
        next_fmt = discord.utils.format_dt(next_.start_time)
        next_fmt_rel = discord.utils.format_dt(next_.start_time, "R")
        fmt += f"Next available ocean fishing expedition to {next_} {next_.emoji} is on the {next_fmt} ({next_fmt_rel}) with a route of:-\n{next_.route()}.\n"
        next_window_fmt = discord.utils.format_dt(next_.registration_opens())
        next_window_fmt_rel = discord.utils.format_dt(next_.registration_opens(), "R")
        fmt += f"Registration opens at {next_window_fmt} ({next_window_fmt_rel})."
        embed.add_field(name="Next Route", value=fmt, inline=False)

        return embed

    @commands.command(name="oceanfishing", aliases=["of", "fishing"])
    async def ocean_fishing_times(self, ctx: Context) -> None:
        """Shows your local time against the current ocean fishing schedule windows."""
        now = datetime.datetime.now(datetime.timezone.utc)

        await ctx.send(embed=self._generate_ocean_fishing_embed(now))


async def setup(bot: Graha) -> None:
    await bot.add_cog(OceanFishing(bot))
