import datetime

DAILY_RESET_TIME: datetime.time = datetime.time(hour=15, tzinfo=datetime.UTC)
DAILY_RESET_REMINDER_TIME: datetime.time = datetime.time(hour=14, tzinfo=datetime.UTC)
WEEKLY_RESET_TIME: datetime.time = datetime.time(hour=8, tzinfo=datetime.UTC)
WEEKLY_RESET_REMINDER_TIME: datetime.time = datetime.time(hour=7, tzinfo=datetime.UTC)

__all__ = (
    "DAILY_RESET_REMINDER_TIME",
    "DAILY_RESET_TIME",
    "WEEKLY_RESET_REMINDER_TIME",
    "WEEKLY_RESET_TIME",
)
