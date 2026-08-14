# air-client

A Streamlit console for exercising the AIR services by hand during development.
Send a request, read the response, copy the cURL that reproduces it.

Two service surfaces, one per tab:

| Tab           | Service        | State                                                      |
| ------------- | -------------- | ---------------------------------------------------------- |
| **Sentiment** | air-classifier | Built against `air-classifier/docs/openapi.json`             |
| **Chat**      | air-platform   | Request builder — the chat API does not exist yet            |
| **System**    | both           | Health, readiness, capabilities, and a log of recent calls   |

> **air-classifier** was until recently **air-sentiment**. Only the repository
> was renamed: the service still uses the `AIR_SENTIMENT__` settings prefix and
> still serves `/v1/sentiment`, `/v1/feedback` and `/v1/reviews`. Where this
> README spells the old name, it is because the wire or the config still does.

## Quickstart

```bash
make install                                   # .venv + the console
make run                                       # http://127.0.0.1:8501
```

Point the sidebar at a running service. For air-classifier locally:

```bash
cd ../air-classifier
export AIR_SENTIMENT__SECURITY__ALLOW_UNAUTHENTICATED=true   # prefix not yet renamed
make run                                       # http://127.0.0.1:8080
```

Leave the console's **X-API-Key** blank in that mode. Otherwise paste a raw key —
it is sent as `X-API-Key`, the header air-classifier authenticates on.

Copy `.env.example` to `.env` to preset the sidebar instead of retyping it each
session. The sidebar always wins at runtime.

## Sentiment tab

Pick an endpoint and a mode:

- **Sentiment** — `/v1/sentiment`, no domain assumptions.
- **Feedback** — `/v1/feedback`, adds `channel`, `user_segment`, `subject`, and
  returns urgency, actionability and a suggested route.
- **Reviews** — `/v1/reviews`, adds `rating`, `product_id`, `verified_purchase`,
  and returns aspects and rating consistency.

**Single** posts one item; **Batch** posts to `/{endpoint}/batch`, taking either
one text per line or a full JSON items array.

The response pane shows a **Summary** (verdict, which tier decided, the
escalation ladder, safety, usage), the **raw JSON**, the **headers**, and the
**request** as runnable cURL with the API key masked until you ask for it.

### Why options have tick boxes

`Options.model_fields_set` is load-bearing server-side: an API key carrying
`force_pii_redaction` rejects an explicit `redact_pii: false` but silently
accepts the same value arriving as an unspoken default. So each option has an
enable checkbox, and unticked options are **omitted from the payload entirely**
rather than sent at their default value. Ticking `redact_pii` and setting it to
false is a genuinely different request from leaving it alone, and the console
lets you send both.

The same care applies to blank text inputs — every request model sets
`additionalProperties: false`, so empty fields are omitted, never sent as `""`
or `null`.

## Chat tab

**air-platform currently ships only a README.** There is no chat endpoint to
code against, so this tab is a Postman-style request builder rather than a form:
you own the method, path, headers and body; the console owns auth, timing and
rendering. When the contract lands, adopting it means saving a preset — not
rewriting the tab.

- `{{message}}` and `{{session_id}}` in the body template are substituted and
  JSON-escaped at send time, so the composer box drives whichever field the
  eventual contract uses.
- The reply extractor probes the response for the field that plausibly holds the
  assistant's text (`reply`, `choices[0].message.content`, `data.reply`, …),
  renders it as a chat bubble, and tells you which path it used. Add the real
  one to `REPLY_PATHS` in `src/air_client/tabs/chat.py` once it is settled.
- Presets ship for a simple chat shape, an OpenAI-style shape and a RAG shape.
  Save your own with the name box next to **Send**; they last for the session.

## Layout

```
src/air_client/
  app.py                    entry point and tab shell
  config.py                 environment defaults that seed the sidebar
  http.py                   one request in, one Exchange out; cURL rendering
  state.py                  session-scoped storage, so responses survive reruns
  theme.py                  the CSS
  components/
    sidebar.py              connection settings
    response_view.py        the shared response pane
    summary.py              decoding an analysis response
  tabs/
    sentiment.py  chat.py  system.py
```

`make check` runs ruff and mypy (strict).

## Notes

- Responses live in `st.session_state`. Streamlit re-runs the script on every
  interaction, so anything rendered straight after a button press would
  otherwise vanish the moment you tick a checkbox.
- Network failures are rendered, not raised — a refused connection is an
  ordinary result when the service you are testing is also being written.
- Batch: the schema allows 1000 items, but the service's own
  `AIR_SENTIMENT__APP__MAX_BATCH_ITEMS` defaults to 100. The console warns above 100.
