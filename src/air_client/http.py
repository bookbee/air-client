"""The transport layer: one request in, one fully-described exchange out.

Everything the UI renders — status pill, timings, raw body, reproducible cURL —
comes from a single :class:`Exchange`, so the response pane never has to know
which tab produced it. Network failures are captured as an ``Exchange`` with an
``error`` rather than raised: a refused connection is an ordinary, expected
result when you are testing a service you are also in the middle of writing.

:func:`send_stream` extends the same shape to SSE: air-platform's turn engine is
content-negotiated (``Accept: text/event-stream`` streams, anything else gets one
JSON body — docs/01-hld.md §5), and until now this console only ever exercised
the second path. A streamed :class:`Exchange` carries its parsed frames in
``events`` rather than ``response_json`` — there is no single body — with
``response_text`` holding the raw frames for the raw-body view.
"""

from __future__ import annotations

import json
import shlex
import time
import uuid
from collections.abc import Iterable, Iterator
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
    #: True for an exchange made with :func:`send_stream`. ``response_json`` is
    #: always ``None`` on one of these — there is no single body — and the
    #: decoded frames live in ``events`` instead, in arrival order.
    is_stream: bool = False
    events: list[dict[str, Any]] = field(default_factory=list)

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


def _iter_sse_frames(lines: Iterable[str]) -> Iterator[tuple[str, dict[str, Any]]]:
    """Decode ``event:``/``data:`` frames per the SSE minimum: blocks separated
    by a blank line, multiple ``data:`` lines in one block joined by ``\\n``. A
    bare ``:`` line (air-platform's heartbeat, docs/02-lld.md §4) is ignored —
    it carries no data and the spec requires clients to skip it.

    The frame's ``event:`` name is a fallback only. air-platform's own
    contract guarantees the payload's own ``event`` field always agrees with
    it (``api/sse.py``'s ``format_event`` takes the name from the model, not
    from its caller), so the payload is authoritative whenever it disagrees or
    the line was dropped by an intermediary.
    """

    def _flush(event_name: str, data_lines: list[str]) -> tuple[str, dict[str, Any]] | None:
        if not data_lines:
            return None
        try:
            payload = json.loads("\n".join(data_lines))
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        return str(payload.get("event") or event_name or "message"), payload

    event_name = ""
    data_lines: list[str] = []
    for line in lines:
        if line == "":
            frame = _flush(event_name, data_lines)
            if frame is not None:
                yield frame
            event_name, data_lines = "", []
        elif line.startswith(":"):
            continue
        elif line.startswith("event:"):
            event_name = line.removeprefix("event:").strip()
        elif line.startswith("data:"):
            data_lines.append(line.removeprefix("data:").strip())
    frame = _flush(event_name, data_lines)
    if frame is not None:
        yield frame


def send_stream(
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    json_body: Any | None = None,
    timeout: float = 60.0,
    verify: bool = True,
) -> Exchange:
    """Perform the call as a real SSE request and describe it as an Exchange.

    Collected rather than rendered live: a Streamlit widget callback can stash
    state for the script's next run but cannot reliably draw incremental UI
    from inside itself (the same reason ``_send_turn`` already stashes into
    ``session_state`` instead of rendering directly), so this exercises the
    real wire mechanics — the ``Accept`` header, one long-lived ``httpx``
    stream, ``event:``/``data:`` framing — and hands back the full, ordered
    event list once the connection closes, rather than a token-by-token
    render as they arrive.

    ``headers["Accept"]`` is overridden here rather than left to the caller:
    the whole point of this function is the streamed path, and a caller that
    forgot to ask for it would silently get a hung connection instead of a
    stream, since a plain JSON `Accept` sent to a streaming-capable server
    still returns one complete body — just slower to show anything.
    """
    stream_headers = dict(headers)
    stream_headers["Accept"] = "text/event-stream"

    exchange = Exchange(
        method=method.upper(),
        url=url,
        request_headers=stream_headers,
        request_body=json_body,
        is_stream=True,
    )

    started = time.perf_counter()
    raw_frames: list[str] = []
    try:
        with (
            httpx.Client(timeout=timeout, verify=verify, follow_redirects=True) as client,
            client.stream(
                method.upper(),
                url,
                headers=stream_headers,
                json=json_body if json_body is not None else None,
            ) as response,
        ):
            exchange.status_code = response.status_code
            exchange.reason = response.reason_phrase
            exchange.response_headers = dict(response.headers)
            for name, payload in _iter_sse_frames(response.iter_lines()):
                raw_frames.append(f"event: {name}\ndata: {json.dumps(payload)}\n")
                exchange.events.append(payload)
    except httpx.TimeoutException:
        exchange.elapsed_ms = (time.perf_counter() - started) * 1000
        exchange.error = f"Timed out after {timeout:.0f}s while streaming."
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
    exchange.response_text = "\n".join(raw_frames)
    return exchange


def to_curl(exchange: Exchange, *, reveal_secrets: bool = False) -> str:
    """Render the exchange as a runnable cURL command.

    Secrets are masked by default so the snippet can be pasted into a ticket;
    tick "reveal" first when you want one that actually runs.
    """
    parts = [f"curl -X {exchange.method}"]
    if exchange.is_stream:
        # Disables curl's own output buffering, so frames print as they arrive
        # instead of all at once at the end — the same buffering hazard
        # air-platform's own `X-Accel-Buffering: no` header guards against.
        parts.append("-N")
    parts.append(shlex.quote(exchange.url))
    for name, value in display_headers(exchange.request_headers, reveal=reveal_secrets).items():
        parts.append(f"-H {shlex.quote(f'{name}: {value}')}")
    if exchange.request_body is not None:
        body = json.dumps(exchange.request_body, indent=2, ensure_ascii=False)
        parts.append(f"-d {shlex.quote(body)}")
    return " \\\n  ".join(parts)
