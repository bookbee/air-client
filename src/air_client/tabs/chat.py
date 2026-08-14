"""The air-platform chat tab.

air-platform is a README today — there is no chat API to code against yet. So
this tab is a request builder rather than a form: you own the method, path,
headers and body, and the console owns the plumbing, the timing and the
rendering. When the contract lands, adopting it means saving a preset, not
rewriting this file.

Two things make it feel like a chat client rather than a raw HTTP poker:

* ``{{message}}`` and ``{{session_id}}`` placeholders in the body template are
  substituted (and JSON-escaped) at send time, so the composer box drives
  whatever field the eventual contract happens to use.
* The reply extractor probes the response for the field that plausibly holds
  the assistant's text, and tells you which path it used, so the transcript
  works before anyone has agreed on a schema.
"""

from __future__ import annotations

import json
from typing import Any

import streamlit as st

from air_client.components import response_view
from air_client.components.sidebar import Connection
from air_client.http import build_headers, join_url, send
from air_client.state import current, remember
from air_client.theme import note, section

METHODS = ["POST", "GET", "PUT", "PATCH", "DELETE"]

# Candidate paths to the assistant's text, most specific first. Tried in order
# against the response body; the first hit wins and is reported to the user.
REPLY_PATHS: tuple[tuple[str, ...], ...] = (
    ("choices", "0", "message", "content"),
    ("choices", "0", "delta", "content"),
    ("choices", "0", "text"),
    ("message", "content"),
    ("data", "reply"),
    ("data", "message"),
    ("reply",),
    ("answer",),
    ("response",),
    ("output_text",),
    ("output",),
    ("content",),
    ("text",),
    ("message",),
)

BUILTIN_PRESETS: dict[str, dict[str, Any]] = {
    "Simple chat": {
        "method": "POST",
        "path": "/v1/chat",
        "body": '{\n  "message": "{{message}}",\n  "session_id": "{{session_id}}"\n}',
    },
    "OpenAI-style completions": {
        "method": "POST",
        "path": "/v1/chat/completions",
        "body": (
            "{\n"
            '  "model": "air-default",\n'
            '  "messages": [\n'
            '    {"role": "user", "content": "{{message}}"}\n'
            "  ],\n"
            '  "temperature": 0.7\n'
            "}"
        ),
    },
    "Chat + RAG": {
        "method": "POST",
        "path": "/v1/chat",
        "body": (
            "{\n"
            '  "message": "{{message}}",\n'
            '  "session_id": "{{session_id}}",\n'
            '  "rag": {"enabled": true, "top_k": 5}\n'
            "}"
        ),
    },
    "Health probe": {"method": "GET", "path": "/v1/health", "body": ""},
}

DEFAULT_PRESET = "Simple chat"


def _escaped(value: str) -> str:
    """JSON-escape ``value`` for splicing inside a JSON string literal."""
    return json.dumps(value)[1:-1]


def _substitute(template: str, *, message: str, session_id: str) -> str:
    return template.replace("{{message}}", _escaped(message)).replace(
        "{{session_id}}", _escaped(session_id)
    )


def _extract_reply(payload: Any) -> tuple[str | None, str | None]:
    """Find the assistant's text in an unknown response shape.

    Returns ``(text, dotted_path)``; ``(None, None)`` when nothing looks like a
    reply, which is itself useful feedback while a contract is being designed.
    """
    for path in REPLY_PATHS:
        cursor: Any = payload
        for key in path:
            if isinstance(cursor, dict) and key in cursor:
                cursor = cursor[key]
            elif isinstance(cursor, list) and key.isdigit() and int(key) < len(cursor):
                cursor = cursor[int(key)]
            else:
                cursor = None
                break
        if isinstance(cursor, str) and cursor.strip():
            return cursor, ".".join(path)
    return None, None


def _transcript() -> list[dict[str, str]]:
    turns: list[dict[str, str]] = st.session_state.setdefault("chat-transcript", [])
    return turns


def _presets() -> dict[str, dict[str, Any]]:
    saved = st.session_state.setdefault("chat-presets", {})
    return {**BUILTIN_PRESETS, **saved}


def _apply_preset(name: str) -> None:
    preset = _presets().get(name)
    if preset is None:
        return
    st.session_state["chat-method"] = preset["method"]
    st.session_state["chat-path"] = preset["path"]
    st.session_state["chat-body"] = preset["body"]


def _endpoint_row(connection: Connection) -> tuple[str, str]:
    cols = st.columns([1, 3, 1.4, 0.8])
    method = cols[0].selectbox("Method", METHODS, key="chat-method", label_visibility="collapsed")
    path = cols[1].text_input(
        "Path", key="chat-path", label_visibility="collapsed", placeholder="/v1/chat"
    )

    preset_names = list(_presets())
    chosen = cols[2].selectbox(
        "Preset", preset_names, key="chat-preset", label_visibility="collapsed"
    )
    cols[3].button("Load", key="chat-load", width="stretch", on_click=_apply_preset, args=(chosen,))

    st.caption(f"{method} {join_url(connection.base_url, path)}")
    return method, path


def _headers_editor() -> dict[str, str]:
    with st.expander("Headers"):
        note(
            "`Content-Type`, `Accept`, `X-Request-ID` and the sidebar's `X-API-Key` are "
            "added automatically. Rows here are merged on top and win ties."
        )
        rows = st.data_editor(
            st.session_state.setdefault(
                "chat-headers-rows", [{"enabled": True, "header": "", "value": ""}]
            ),
            num_rows="dynamic",
            width="stretch",
            key="chat-headers-editor",
            column_config={
                "enabled": st.column_config.CheckboxColumn("send", default=True),
                "header": st.column_config.TextColumn("header", width="medium"),
                "value": st.column_config.TextColumn("value", width="large"),
            },
        )

    extra: dict[str, str] = {}
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict) or not row.get("enabled"):
                continue
            name = str(row.get("header") or "").strip()
            value = str(row.get("value") or "").strip()
            if name and value:
                extra[name] = value
    return extra


def _save_preset(method: str, path: str, body: str) -> None:
    name = st.session_state.get("chat-preset-name", "").strip()
    if not name:
        return
    saved = st.session_state.setdefault("chat-presets", {})
    saved[name] = {"method": method, "path": path, "body": body}
    st.session_state["chat-preset-name"] = ""


def _chat_summary(payload: Any) -> None:
    """The chat-bubble view: whichever field turned out to hold the reply."""
    reply, path = _extract_reply(payload)
    if reply is None:
        st.info(
            "No field in this response looked like an assistant reply. The raw body is "
            "on the **Response** tab — once air-platform settles on a field name, add it "
            "to `REPLY_PATHS` in `tabs/chat.py`."
        )
        return

    st.caption(f"Reply read from `{path}`")
    with st.chat_message("assistant"):
        st.markdown(reply)

    if isinstance(payload, dict):
        interesting = {
            key: payload[key]
            for key in (
                "session_id",
                "conversation_id",
                "usage",
                "model",
                "citations",
                "sources",
                "tool_calls",
                "finish_reason",
            )
            if key in payload
        }
        if interesting:
            with st.expander("Other fields in the reply"):
                st.json(interesting)


def render(connection: Connection) -> None:
    """Draw the whole chat tab."""
    st.markdown(
        "Exercise the conversational endpoint on **air-platform**. You drive the "
        "method, path, headers and body; the console handles auth, timing and rendering."
    )
    st.info(
        "air-platform currently ships only a README — no chat service exists yet. This tab "
        "is deliberately contract-agnostic so it works the day the endpoint appears. "
        "The presets are plausible starting shapes, not an agreed API.",
        icon=":material/info:",
    )

    if "chat-body" not in st.session_state:
        _apply_preset(DEFAULT_PRESET)

    method, path = _endpoint_row(connection)
    extra_headers = _headers_editor()

    section("Compose")
    cols = st.columns([3, 1])
    message = cols[0].text_area(
        "message  ·  substituted into {{message}}",
        key="chat-message",
        height=90,
        placeholder="Ask the assistant something…",
    )
    session_id = cols[1].text_input(
        "session_id  ·  {{session_id}}", key="chat-session", value="dev-session-1"
    )

    body_template = st.text_area(
        "Request body  ·  JSON, with {{message}} and {{session_id}} placeholders",
        key="chat-body",
        height=190,
    )

    errors: list[str] = []
    body: Any | None = None
    rendered = _substitute(body_template, message=message, session_id=session_id)

    if method in {"POST", "PUT", "PATCH"} and rendered.strip():
        try:
            body = json.loads(rendered)
        except json.JSONDecodeError as exc:
            errors.append(
                f"Request body is not valid JSON after substitution: {exc.msg} "
                f"(line {exc.lineno}, column {exc.colno})."
            )
    if not path.strip():
        errors.append("Path is required.")

    with st.expander("Body as it will be sent"):
        st.code(
            json.dumps(body, indent=2, ensure_ascii=False) if body is not None else "(no body)",
            language="json",
        )

    controls = st.columns([1, 1, 1.4, 1])
    clicked = controls[0].button(
        "Send", type="primary", key="chat-send", width="stretch", disabled=bool(errors)
    )
    controls[1].button(
        "Clear transcript",
        key="chat-clear",
        width="stretch",
        on_click=lambda: st.session_state.update({"chat-transcript": []}),
    )
    controls[2].text_input(
        "Preset name",
        key="chat-preset-name",
        label_visibility="collapsed",
        placeholder="Save current as…",
    )
    controls[3].button(
        "Save",
        key="chat-save",
        width="stretch",
        on_click=_save_preset,
        args=(method, path, body_template),
    )

    for problem in errors:
        st.warning(problem)

    if clicked:
        with st.spinner("Calling air-platform…"):
            exchange = send(
                method,
                join_url(connection.base_url, path),
                headers=build_headers(connection.api_key, extra_headers),
                json_body=body,
                timeout=connection.timeout,
                verify=connection.verify,
            )
        remember("chat", exchange)

        if exchange.ok:
            reply, _ = _extract_reply(exchange.response_json)
            transcript = _transcript()
            if message.strip():
                transcript.append({"role": "user", "content": message})
            if reply:
                transcript.append({"role": "assistant", "content": reply})

    stored = current("chat")
    if stored is not None:
        section("Response")
        response_view.render(stored, key="chat", summary=_chat_summary)

    transcript = _transcript()
    if transcript:
        section("Transcript")
        st.caption(
            "Accumulated across sends in this session. It is a local view only — the "
            "console does not replay history to the service unless your body template does."
        )
        for turn in transcript:
            with st.chat_message(turn["role"]):
                st.markdown(turn["content"])
