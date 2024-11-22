from discord.enums import Enum

__all__ = (
    "Datacenter",
    "Region",
)


class Region(Enum):
    EU = 1
    NA = 2
    JP = 3
    OCE = 4

    def resolved_name(self) -> str:
        return str(self.name)


class Datacenter(Enum):
    chaos = Region.EU
    light = Region.EU
    aether = Region.NA
    primal = Region.NA
    crystal = Region.NA
    dynamis = Region.NA
    elemental = Region.JP
    gaia = Region.JP
    mana = Region.JP
    meteor = Region.JP
    materia = Region.OCE
