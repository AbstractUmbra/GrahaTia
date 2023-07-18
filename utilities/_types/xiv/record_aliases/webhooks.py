from typing import TypedDict


__all__ = ("WebhooksRecord",)


class WebhooksRecord(TypedDict):
    guild_id: int
    webhook_id: int | None
    webhook_url: str | None
    webhook_token: str | None
