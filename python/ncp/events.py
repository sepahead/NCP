"""Events: what an owner, a client, or a server did, for logs and metrics.

Pass an observer to `Owner`, `Client`, or a server. Without one, the SDK reports only the errors
that an operator must see, such as an exception of the application, through the logger "ncp".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

LOGGER = logging.getLogger("ncp")


@dataclass(frozen=True, slots=True)
class Event:
    """One event.

    `kind` is one of: "opened", "open_rejected", "admitted", "repeated", "rejected",
    "expired", "shutdown", "bad_frame", "application_error", "session_end" (owner side);
    "sent", "resent", "verdict", "ignored" (client side); "connection_refused",
    "server_error" (servers).
    """

    kind: str
    role: str
    session: str | None = None
    seq: int | None = None
    op: str | None = None
    outcome: str | None = None
    code: str | None = None
    detail: str | None = None
    error: BaseException | None = None


class Observer(Protocol):
    def event(self, event: Event) -> None: ...


class LogObserver:
    """Write every event to a logger: errors at ERROR, the rest at DEBUG."""

    def __init__(self, logger: logging.Logger = LOGGER) -> None:
        self.logger = logger

    def event(self, event: Event) -> None:
        if event.kind in ("application_error", "server_error"):
            self.logger.error(
                "%s %s: session %s seq %s op %s: %s",
                event.role,
                event.kind,
                event.session,
                event.seq,
                event.op,
                event.detail or event.error,
                exc_info=event.error,
            )
        elif self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug(
                "%s %s: session %s seq %s op %s outcome %s code %s %s",
                event.role,
                event.kind,
                event.session,
                event.seq,
                event.op,
                event.outcome,
                event.code,
                event.detail or "",
            )


class _Default:
    """Reports application and server errors only, so that a failure never passes silently."""

    def event(self, event: Event) -> None:
        if event.kind in ("application_error", "server_error"):
            LogObserver().event(event)


DEFAULT: Any = _Default()
