from typing import Literal, TypedDict

__all__: tuple[str, ...] = (
    "Error",
    "PrepareResponse"
)

class Error(TypedDict):
    status: Literal["error"]
    reason: str

class PrepareResponse(TypedDict):
    status: Literal["ok"]
    url: str