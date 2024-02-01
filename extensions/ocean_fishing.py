from __future__ import annotations

import datetime
import math
from typing import TYPE_CHECKING, ClassVar, NamedTuple

import discord
from discord.enums import Enum
from discord.ext import commands

from utilities.cog import GrahaBaseCog

if TYPE_CHECKING:
    from bot import Graha
    from utilities.context import Context


class Route(Enum):
    indigo = "Indigo"
    ruby = "Ruby"


class Time(Enum):
    day = "D"
    sunset = "S"
    night = "N"


class Stop(Enum):
    galadion_bay = "Galadion Bay"
    the_southern_strait_of_merlthor = "The Southern Strait of Merlthor"
    the_northern_strait_of_merlthor = "The Northern Strait of Merlthor"
    rhotano_sea = "Rhotano Sea"
    the_cieldalaes = "The Cieldalaes"
    the_bloodbrine_sea = "The Bloodbrine Sea"
    the_rothlyt_sound = "The Rothlyt Sound"
    the_sirensong_sea = "The Sirensong Sea"
    kugane = "Kugane"
    the_ruby_sea = "The Ruby Sea"
    the_one_river = "The One River"


class Destination(Enum):
    the_northern_strait_of_merlthor = Stop.the_northern_strait_of_merlthor
    rhotano_sea = Stop.rhotano_sea
    the_bloodbrine_sea = Stop.the_bloodbrine_sea
    the_rothlyt_sound = Stop.the_rothlyt_sound
    the_ruby_sea = Stop.the_ruby_sea
    the_one_river = Stop.the_one_river


DAY: str = "\U00002600\U0000fe0f"
SUNSET: str = "\U0001f305"
NIGHT: str = "\U0001f311"

DESTINATION_CYCLE: dict[Route, list[Destination]] = {
    Route.indigo: [
        Destination.the_bloodbrine_sea,
        Destination.the_rothlyt_sound,
        Destination.the_northern_strait_of_merlthor,
        Destination.rhotano_sea,
    ],
    Route.ruby: [Destination.the_one_river, Destination.the_ruby_sea],
}
DESTINATION_MAPPING: dict[Destination, str] = {
    Destination.the_bloodbrine_sea: "The Bloodbrine Sea",
    Destination.the_rothlyt_sound: "The RothlytSound",
    Destination.the_northern_strait_of_merlthor: "The Northern Strait of Merlthor",
    Destination.rhotano_sea: "Rhotano Sea",
}
STOP_MAPPING: dict[Destination, list[Stop]] = {
    Destination.the_northern_strait_of_merlthor: [
        Stop.the_southern_strait_of_merlthor,
        Stop.galadion_bay,
        Stop.the_northern_strait_of_merlthor,
    ],
    Destination.rhotano_sea: [Stop.galadion_bay, Stop.the_southern_strait_of_merlthor, Stop.rhotano_sea],
    Destination.the_bloodbrine_sea: [Stop.the_cieldalaes, Stop.the_northern_strait_of_merlthor, Stop.the_bloodbrine_sea],
    Destination.the_rothlyt_sound: [Stop.the_cieldalaes, Stop.rhotano_sea, Stop.the_rothlyt_sound],
    Destination.the_ruby_sea: [Stop.the_sirensong_sea, Stop.kugane, Stop.the_ruby_sea],
    Destination.the_one_river: [Stop.the_sirensong_sea, Stop.kugane, Stop.the_one_river],
}

TIME_CYCLE: dict[Route, list[Time]] = {
    Route.indigo: [
        Time.sunset,
        Time.sunset,
        Time.sunset,
        Time.sunset,
        Time.night,
        Time.night,
        Time.night,
        Time.night,
        Time.day,
        Time.day,
        Time.day,
        Time.day,
    ],
    Route.ruby: [Time.day, Time.day, Time.sunset, Time.sunset, Time.night, Time.night],
}
TIME_MAPPING: dict[Time, str] = {
    Time.day: "Day",
    Time.night: "Night",
    Time.sunset: "Sunset",
}

STOP_TIME_MAPPING: dict[Time, list[str]] = {
    Time.day: [SUNSET, NIGHT, DAY],
    Time.night: [DAY, SUNSET, NIGHT],
    Time.sunset: [NIGHT, DAY, SUNSET],
}


class Voyage(NamedTuple):
    start_time: datetime.datetime
    d: Destination
    t: Time

    def __repr__(self) -> str:
        return f"<Voyage start_time={self.start_time} destination={self.destination!r} time={self.time!r}>"

    def __str__(self) -> str:
        return self.details

    @property
    def sets_sail(self) -> datetime.datetime:
        return self.start_time + datetime.timedelta(minutes=15)

    @property
    def destination(self) -> str:
        return DESTINATION_MAPPING[self.d]

    @property
    def time(self) -> str:
        return TIME_MAPPING[self.t]

    @property
    def details(self) -> str:
        return f"{self.destination!r} at {self.time.lower()}"

    def has_set_sail(self, dt: datetime.datetime | None = None, /) -> bool:
        dt = dt or datetime.datetime.now(datetime.UTC)
        return self.sets_sail < dt

    def can_register(self, dt: datetime.datetime | None = None, /) -> bool:
        dt = dt or datetime.datetime.now(datetime.UTC)
        return self.has_set_sail(dt)

    def formatted_start_times(self) -> tuple[str, str]:
        return discord.utils.format_dt(self.start_time), discord.utils.format_dt(self.start_time, "R")

    def formatted_sail_times(self) -> tuple[str, str]:
        return discord.utils.format_dt(self.sets_sail), discord.utils.format_dt(self.sets_sail, "R")

    def stops(self) -> str:
        routes: list[tuple[str, str]] = []

        for stop, time in zip(STOP_MAPPING[self.d], STOP_TIME_MAPPING[self.t]):
            routes.append((stop.value, time))

        return "\n".join([f"{item[1]}: {item[0]}" for item in routes])


class OceanFishing(GrahaBaseCog):
    STARTING_EPOCH: ClassVar[datetime.datetime] = datetime.datetime.fromtimestamp(1593302400, tz=datetime.UTC)

    def __init__(self, bot: Graha, /) -> None:
        super().__init__(bot)
        self.voyage_cache: dict[Route, list[tuple[Destination, Time]]] = {}
        self.cache_voyages(route=Route.indigo)
        self.cache_voyages(route=Route.ruby)

    def _from_epoch(self, day: int, hour: int) -> datetime.datetime:
        return (
            self.STARTING_EPOCH
            + datetime.timedelta(days=day)
            + datetime.timedelta(seconds=hour * 3600)
            - datetime.timedelta(seconds=32400)
        )

    def cache_voyages(self, *, route: Route) -> None:
        dt = datetime.datetime.fromtimestamp(2700, tz=datetime.UTC)
        cache = self._calculate_voyages(route=route, dt=dt, count=144)

        self.voyage_cache[route] = [(item.d, item.t) for item in cache]

    def _calculate_voyages(self, *, route: Route, dt: datetime.datetime, count: int) -> list[Voyage]:
        _destination_cycle = DESTINATION_CYCLE[route]
        _time_cycle = TIME_CYCLE[route]
        adjusted_date = (dt + datetime.timedelta(hours=9)) - datetime.timedelta(minutes=45)
        day = math.floor((adjusted_date.timestamp() - 1593302400) / 86400)
        hour = adjusted_date.hour

        offset = hour & 1
        hour += 2 if offset else 1

        if hour > 23:
            day += 1
            hour -= 24

        voyage_number = hour >> 1
        destination_index = ((day + voyage_number) % len(DESTINATION_CYCLE) + len(DESTINATION_CYCLE)) % len(
            DESTINATION_CYCLE
        )
        time_index = ((day + voyage_number) % len(TIME_CYCLE) + len(TIME_CYCLE)) % len(TIME_CYCLE)

        upcoming_voyages: list[Voyage] = []

        while len(upcoming_voyages) < count:
            _current_destination = _destination_cycle[destination_index]
            _current_time = _time_cycle[time_index]
            upcoming_voyages.append(Voyage(self._from_epoch(day, hour), _current_destination, _current_time))

            if hour == 23:
                day += 1
                hour = 1
                destination_index = (destination_index + 2) % len(DESTINATION_CYCLE)
                time_index = (time_index + 2) % len(TIME_CYCLE)
            else:
                hour += 2
                destination_index = (destination_index + 1) % len(DESTINATION_CYCLE)
                time_index = (time_index + 1) % len(TIME_CYCLE)

        return upcoming_voyages

    def calculate_voyages(self, route: Route, /, *, dt: datetime.datetime, count: int = 144) -> list[Voyage]:
        start_index = math.floor((dt - datetime.timedelta(minutes=45)).timestamp() / 7200)
        upcoming_voyages: list[Voyage] = []

        for idx in range(count):
            dest, time = self.voyage_cache[route][(start_index + idx) % 144]
            upcoming_voyages.append(
                Voyage(datetime.datetime.fromtimestamp((start_index + idx + 1) * 7200, tz=datetime.UTC), dest, time)
            )

        return upcoming_voyages

    def _generate_ocean_fishing_embed(self, dt: datetime.datetime, /, *, route: Route) -> discord.Embed:
        embed = discord.Embed(colour=discord.Colour.random(), title=f"Ocean Fishing availability ({route.value} route)")

        current, next_ = self.calculate_voyages(route, dt=dt, count=2)
        now = datetime.datetime.now(datetime.UTC)

        current_start_time, current_start_time_rel = current.formatted_start_times()
        current_sail_time, current_sail_time_rel = current.formatted_sail_times()
        next_start_time, next_start_time_rel = next_.formatted_start_times()
        next_sail_time, next_sail_time_rel = next_.formatted_sail_times()

        current_fmt = current.stops() + "\n\n"
        if current.has_set_sail(now):
            current_fmt += "The registration window for this has closed and the voyage is underway.\n\n"
        elif current.can_register(now):
            current_fmt += (
                "The registration window for this voyage is currently open if you wish to join. Registration will close at"
                f" {current_sail_time} ({current_sail_time_rel}).\n\n"
            )
        else:
            current_fmt += (
                "The registration window for this voyage will open at" f" {current_start_time} ({current_start_time_rel})."
            )
        embed.add_field(name="Current Route", value=current_fmt, inline=False)

        next_fmt = f"Sets sail at {next_sail_time} ({next_sail_time_rel}) with a route of:-\n{next_.stops()}\n\n"
        next_fmt += f"Registration opens at {next_start_time} ({next_start_time_rel})."
        embed.add_field(name="Next Route", value=next_fmt, inline=False)

        embed.set_footer(text="The route is named after the final stop.")

        return embed

    def _generate_both_embeds(self, dt: datetime.datetime, /) -> list[discord.Embed]:
        return [
            self._generate_ocean_fishing_embed(dt, route=Route.indigo),
            self._generate_ocean_fishing_embed(dt, route=Route.ruby),
        ]

    @commands.command(name="oceanfishing", aliases=["of", "fishing"])
    async def ocean_fishing_times(self, ctx: Context) -> None:
        """Shows your local time against the current ocean fishing schedule windows."""
        now = datetime.datetime.now(datetime.UTC)

        await ctx.send(
            content="You can view Lulu's helpful tools on Ocean Fishing data [here](https://ffxiv.pf-n.co/ocean-fishing)!",
            embeds=self._generate_both_embeds(now),
        )


async def setup(bot: Graha) -> None:
    await bot.add_cog(OceanFishing(bot))
