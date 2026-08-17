"""The transport layer: one request in, one fully-described exchange out.

Everything the UI renders — status pill, timings, raw body, reproducible cURL —
comes from a single :class:`Exchange`, so the response pane never has to know
which tab produced it. Network failures are captured as an ``Exchange`` with an
``error`` rather than raised: a refused connection is an ordinary, expected
result when you are testing a service you are also in the middle of writing.
"""

from __future__ import annotations

import json
import shlex
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx

# Header names whose values are masked in the UI and in generated cURL unless
# the operator explicitly asks to reveal them.
SECRET_HEADERS = frozenset({"x-api-key", "authorization", "cookie", "proxy-authorization"})

MASK = "••••••••"


@dataclass(slots=True)
class Exchange:
    """A single request/response round trip, including the failures."""

    method: str
    url: str
    request_headers: dict[str, str]
    request_body: Any | None
    status_code: int | None = None
    reason: str = ""
    response_headers: dict[str, str] = field(default_factory=dict)
    response_json: Any | None = None
    response_text: str = ""
    elapsed_ms: float = 0.0
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.status_code is not None and self.status_code < 400

    @property
    def request_id(self) -> str | None:
        """Prefer the body's request_id; fall back to the X-Request-ID header."""
        if isinstance(self.response_json, dict):
            value = self.response_json.get("request_id")
            if isinstance(value, str) and value:
                return value
        for name, value in self.response_headers.items():
            if name.lower() == "x-request-id" and value:
                return value
        return None

    @property
    def server_latency_ms(self) -> float | None:
        """Service-reported latency, which excludes the network hop we added."""
        if isinstance(self.response_json, dict):
            value = self.response_json.get("latency_ms")
            if isinstance(value, int | float):
                return float(value)
        return None


def display_headers(headers: dict[str, str], *, reveal: bool = False) -> dict[str, str]:
    """Copy of ``headers`` with secrets masked, for anything shown on screen."""
    if reveal:
        return dict(headers)
    return {
        name: (MASK if name.lower() in SECRET_HEADERS and value else value)
        for name, value in headers.items()
    }


def build_headers(api_key: str, extra: dict[str, str] | None = None) -> dict[str, str]:
    """The standard header set: JSON in, JSON out, plus a correlation id.

    ``X-API-Key`` is the header the AIR services authenticate on. A blank key
    omits it rather than sending an empty one, so the failure is the service's
    own "no key presented" 401 — which is the thing you wanted to see — instead
    of a header that looks present and is not.
    """
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if api_key.strip():
        headers["X-API-Key"] = api_key.strip()
    headers["X-Request-ID"] = f"cli_{uuid.uuid4().hex[:20]}"
    if extra:
        headers.update({k: v for k, v in extra.items() if k.strip() and v.strip()})
    return headers


def join_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def send(
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    json_body: Any | None = None,
    timeout: float = 60.0,
    verify: bool = True,
) -> Exchange:
    """Perform the call and describe it, whatever happened."""
    exchange = Exchange(
        method=method.upper(),
        url=url,
        request_headers=dict(headers),
        request_body=json_body,
    )

    started = time.perf_counter()
    try:
        with httpx.Client(timeout=timeout, verify=verify, follow_redirects=True) as client:
            response = client.request(
                method.upper(),
                url,
                headers=headers,
                json=json_body if json_body is not None else None,
            )
    except httpx.TimeoutException:
        exchange.elapsed_ms = (time.perf_counter() - started) * 1000
        exchange.error = (
            f"Timed out after {timeout:.0f}s. The ladder may still be escalating — "
            "raise the timeout in the sidebar, or cap options.max_tier."
        )
        return exchange
    except httpx.ConnectError:
        exchange.elapsed_ms = (time.perf_counter() - started) * 1000
        exchange.error = (
            f"Could not connect to {url}. Is the service running, and is the "
            "base URL in the sidebar right?"
        )
        return exchange
    except httpx.HTTPError as exc:
        exchange.elapsed_ms = (time.perf_counter() - started) * 1000
        exchange.error = f"{type(exc).__name__}: {exc}"
        return exchange

    exchange.elapsed_ms = (time.perf_counter() - started) * 1000
    exchange.status_code = response.status_code
    exchange.reason = response.reason_phrase
    exchange.response_headers = dict(response.headers)
    exchange.response_text = response.text
    try:
        exchange.response_json = response.json()
    except (json.JSONDecodeError, ValueError):
        exchange.response_json = None
    return exchange


def to_curl(exchange: Exchange, *, reveal_secrets: bool = False) -> str:
    """Render the exchange as a runnable cURL command.

    Secrets are masked by default so the snippet can be pasted into a ticket;
    tick "reveal" first when you want one that actually runs.
    """
    parts = [f"curl -X {exchange.method}", shlex.quote(exchange.url)]
    for name, value in display_headers(exchange.request_headers, reveal=reveal_secrets).items():
        parts.append(f"-H {shlex.quote(f'{name}: {value}')}")
    if exchange.request_body is not None:
        body = json.dumps(exchange.request_body, indent=2, ensure_ascii=False)
        parts.append(f"-d {shlex.quote(body)}")
    return " \\\n  ".join(parts)
