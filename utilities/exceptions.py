"""
This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sentry_sdk.types import Event, Hint

__all__ = ("NoSubmissionFound",)


def sentry_before_send(event: "Event", hint: "Hint") -> "Event | None":
    if "exc_info" in hint:
        _, exc_value, _ = hint["exc_type"]
        if isinstance(exc_value, NoSubmissionFound):
            return None

        return event

    return None


class NoSubmissionFound(ValueError):
    """A generic error for when no submissions are found for the fashion report on reddit."""
