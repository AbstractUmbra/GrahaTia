from typing import TypedDict

__all__ = ("WebhooksRecord",)


class WebhooksRecord(TypedDict):
    guild_id: int
    webhook_id: int
    webhook_url: str
    webhook_token: str
