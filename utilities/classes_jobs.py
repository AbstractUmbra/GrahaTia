from discord.enums import Enum

__all__ = (
    "HealerClass",
    "Healers",
    "MagicalRangedDps",
    "MagicalRangedDpsClass",
    "MeleeDps",
    "MeleeDpsClass",
    "PhysicalRangedDps",
    "PhysicalRangedDpsClass",
    "Roles",
    "TankClass",
    "Tanks",
)


class Roles(Enum):
    flex = 0
    tank = 1
    healer = 2
    melee_dps = 3
    physical_ranged_dps = 4
    magical_ranged_dps = 5


class TankClass(Enum):
    gladiator = 1
    marauder = 2


class Tanks(Enum):
    paladin = 1
    warrior = 2
    dark_knight = 3
    gunbreaker = 4


class HealerClass(Enum):
    conjurer = 1


class Healers(Enum):
    white_mage = 1
    scholar = 2
    astrologian = 3
    sage = 4


class MeleeDpsClass(Enum):
    pugilist = 1
    lancer = 2
    rogue = 3


class MeleeDps(Enum):
    monk = 1
    dragoon = 2
    ninja = 3
    samurai = 4
    reaper = 5
    viper = 6


class PhysicalRangedDpsClass(Enum):
    archer = 1


class PhysicalRangedDps(Enum):
    bard = 1
    machinist = 2
    dancer = 3


class MagicalRangedDpsClass(Enum):
    thaumaturge = 1
    arcanist = 2


class MagicalRangedDps(Enum):
    black_mage = 1
    summoner = 2
    red_mage = 3
    pictomancer = 4
    blu_mage = 5
