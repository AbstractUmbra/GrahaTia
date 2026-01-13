from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, ClassVar, Literal

import discord
from discord import app_commands
from discord.enums import Enum

from utilities.shared.cog import BaseCog
from utilities.shared.formats import ts

if TYPE_CHECKING:
    from bot import Graha
    from utilities.context import Interaction

type GateSpawnMinute = Literal[0, 20, 40]


class LeapOfFaith(Enum):
    nym = 0
    belah_dia = 1
    sylphstep = 2

    def clean(self) -> str:
        lof_name = self.name.replace("_", "'").title()
        return f"Leap of Faith [{lof_name}]"

    @property
    def url(self) -> str:
        return "https://ffxiv.consolegameswiki.com/wiki/Leap_of_Faith"


class AirForceOne(Enum):
    the_gold_saucer = 0
    cieldalaes = 1

    def clean(self) -> str:
        afo_name = self.name.replace("_", "'").title()
        return f"Air Force One [{afo_name}]"

    @property
    def url(self) -> str:
        return "https://ffxiv.consolegameswiki.com/wiki/Air_Force_One"


class GATE(Enum):
    cliffhanger = "https://ffxiv.consolegameswiki.com/wiki/Cliffhanger"
    air_force_one = AirForceOne
    leap_of_faith = LeapOfFaith
    any_way_the_wind_blows = "https://ffxiv.consolegameswiki.com/wiki/Any_Way_the_Wind_Blows"
    the_slice_is_right = "https://ffxiv.consolegameswiki.com/wiki/The_Slice_Is_Right"

    def clean(self) -> str:
        return self.name.replace("_", " ").title()


class GATEs(BaseCog["Graha"]):
    GATES: ClassVar[dict[GateSpawnMinute, list[GATE]]] = {
        0: [GATE.cliffhanger, GATE.air_force_one, GATE.leap_of_faith],
        20: [GATE.any_way_the_wind_blows, GATE.the_slice_is_right, GATE.air_force_one],
        40: [GATE.the_slice_is_right, GATE.air_force_one, GATE.leap_of_faith],
    }

    def resolve_next_gate(self, dt: datetime.datetime | None = None) -> tuple[datetime.datetime, list[GATE]]:
        resolved = (dt or datetime.datetime.now(datetime.UTC)).replace(second=0, microsecond=0)

        if 0 <= resolved.minute < 20:
            min_ = 20
        elif 20 <= resolved.minute < 40:
            min_ = 40
        elif resolved.minute >= 40:
            return (resolved + datetime.timedelta(hours=1)).replace(minute=0), self.GATES[0]
        else:
            min_ = 0

        return resolved.replace(minute=min_), self.GATES[min_]

    @staticmethod
    def resolve_leap_of_faith(minute: GateSpawnMinute) -> LeapOfFaith:
        if minute == 0:
            return LeapOfFaith.nym
        if minute == 20:
            return LeapOfFaith.belah_dia
        return LeapOfFaith.sylphstep

    @staticmethod
    def resolve_air_force_one(minute: GateSpawnMinute) -> AirForceOne:
        if minute == 20:
            return AirForceOne.the_gold_saucer
        return AirForceOne.cieldalaes

    def generate_gate_embed(self, when: datetime.datetime | None = None) -> discord.Embed:
        when, gates = self.resolve_next_gate(when)

        embed = discord.Embed(title="GATEs coming up!", colour=discord.Colour.random(), timestamp=when)

        fmt = f"A random GATE from the below 3 opens up {ts(when):R}!\n\n"
        for gate in gates:
            if gate is GATE.leap_of_faith:
                leap_of_faith = self.resolve_leap_of_faith(when.minute)  # pyright: ignore[reportArgumentType] # resolved in earlier call
                fmt += f"[{leap_of_faith.clean()}]({leap_of_faith.url})\n"
                continue
            if gate is GATE.air_force_one:
                air_force_one = self.resolve_air_force_one(when.minute)  # pyright: ignore[reportArgumentType] # resolved in earlier call
                fmt += f"[{air_force_one.clean()}]({air_force_one.url})\n"
                continue
            fmt += f"[{gate.clean()}]({gate.value})" + "\n"

        embed.description = fmt

        return embed

    @app_commands.command(name="next-gate")
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.describe(ephemeral="Whether to show the data privately to you, or not.")
    async def gate(self, interaction: Interaction, ephemeral: bool = True) -> None:  # noqa: FBT001, FBT002 # required by dpy
        """Shows data on the next possible selection for the GATE in the Golden Saucer."""
        now = datetime.datetime.now(datetime.UTC)

        await interaction.response.send_message(embed=self.generate_gate_embed(now), ephemeral=ephemeral)


async def setup(bot: Graha) -> None:
    await bot.add_cog(GATEs(bot))
