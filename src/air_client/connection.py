"""What the console is pointed at, right now.

One value object, resolved by the sidebar and handed to every tab. It carries
more than the transport strictly needs — the service's name, the target it came
from — because the console's most important job is telling you *where* a request
is about to go, and that answer has to travel with the request.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from air_client.config import location_of


@dataclass(frozen=True, slots=True)
class Connection:
    """Everything needed to talk to one service, and to label it on screen."""

    service: str
    target: str
    target_label: str
    base_url: str
    api_key: str
    timeout: float
    verify: bool
    #: air-platform's channel, when the service has them. It belongs to the key
    #: rather than the request, so it is a property of the connection — not
    #: something a tab can pass as a header.
    channel: str = ""

    @property
    def location(self) -> str:
        """``"local"``, ``"remote"`` or ``"unset"``."""
        return location_of(self.base_url)

    @property
    def is_remote(self) -> bool:
        return self.location == "remote"

    @property
    def authenticated(self) -> bool:
        return bool(self.api_key.strip())

    @property
    def label(self) -> str:
        """Service name, qualified by channel when there is one."""
        return f"{self.service} · {self.channel}" if self.channel else self.service

    @property
    def host(self) -> str:
        """Host and port, for indicators too narrow to carry the whole URL."""
        parsed = urlparse(self.base_url)
        return parsed.netloc or self.base_url or "—"
