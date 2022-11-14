"""
This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""

from typing import TypedDict


__all__ = (
    "WorldsData",
    "DatacenterData",
)


class DatacenterData(TypedDict):
    datacenters: list[dict[str, list[str]]]
    zoneinfo_tz: str


class WorldsData(TypedDict):
    NA: DatacenterData
    EU: DatacenterData
    OCE: DatacenterData
    JP: DatacenterData
