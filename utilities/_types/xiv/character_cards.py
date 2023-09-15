from typing import Literal, TypedDict

__all__ = (
    "Error",
    "PrepareResponse",
)


class Error(TypedDict):
    status: Literal["error"]
    reason: str


class PrepareResponse(TypedDict):
    status: Literal["ok"]
    url: str
