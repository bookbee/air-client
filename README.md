# air-client

A Streamlit console for exercising the AIR services by hand. Send a request,
read the response, copy the cURL that reproduces it.

**This is not a hosted service.** Developers and QA clone the repo, run it on
their own machine, and point it at whichever deployment is under test — usually
a remote one. Everything below follows from that: the console never guesses
where it is connecting, and it never lets you forget.

Three tabs, one per surface:

| Tab            | Service        | What it does                                             |
| -------------- | -------------- | -------------------------------------------------------- |
| **Classifier** | air-classifier | All three classification routes, single and batch        |
| **Chat**       | air-platform   | Request builder — the chat API does not exist yet        |
| **System**     | both           | Health, readiness, capabilities, and a log of every call |

## Quickstart

```bash
make install     # .venv + the console
make env         # .env from .env.example, if absent
make run         # http://127.0.0.1:8501
```

### Two ways to run it

`make` is the front door for every AIR repo; here it opens onto two runtimes.
Both run the same app with the same settings — everything that shapes behaviour
lives in `.streamlit/config.toml` and `.env`, which both read.

| | Needs | Use it when |
| --- | --- | --- |
| `make up` | Docker | **Using** the console. Nothing to install, works on Windows |
| `make run` | Python 3.12 | **Editing** the console. Auto-reloads on save, `start`/`stop`/`status`, `THEME=` |

The one real difference: in Docker, `local` means the Docker host rather than
the container — and the target bar says so on screen.

`make` itself needs no install on macOS (it ships with the Xcode command line
tools, which `git` already pulls in) or on most Linux distributions. It does not
exist on Windows, and the local targets also use `lsof` and `nohup` — so on
Windows, use `docker compose up -d` directly.

`make run` serves in your terminal — **Ctrl+C stops it**. To run it in the
background instead, and to control it from any terminal:

```bash
make start        # background, logs to .run/console.log
make status       # is it serving, on what port, as what pid
make restart      # after changing .env or .streamlit/config.toml
make stop
make logs         # tail the background log
```

`stop` kills whatever is *listening* on `PORT`, so it works whoever started it —
you, a script, or a terminal you have since closed. It never touches processes
merely *connected* to that port, which includes the browser tab you have the
console open in.

Editing a `.py` file does not need any of this: `runOnSave` is on in
`.streamlit/config.toml`, so a save re-runs the script in place — under
`streamlit run` just as much as under `make run` (`make run RELOAD=false`
overrides it once). A restart is only needed for things read once at start-up:
`.env`, `.streamlit/config.toml` itself, and the `THEME` flag.

### In a container

```bash
make up          # build and run; http://127.0.0.1:8501
make logs
make down
```

Unlike the other AIR repos, this one does not join air-infra's `air-net` and
does not need air-infra running: a console whose job is to reach a remote QA
environment must not depend on a local stack being up. It reaches locally-run
services through the ports they publish on the host.

Inside a container `localhost` is the *container*, so compose re-points the
`local` target at `host.docker.internal` — "local" keeps meaning the services on
your machine. On Docker Desktop this reaches them even when they are bound to
`127.0.0.1` (verified against air-classifier on `:8082`); on Linux, start the
service with `HOST=0.0.0.0` so the container can see it.

The port publishes to loopback only — the console holds API keys, so it is a
tool on your machine, not a service for the network. `.env` is never baked into
the image; compose passes it at runtime.

That starts on the **local** target. To have something to talk to:

```bash
cd ../air-classifier
make install && make env
make run                                       # http://127.0.0.1:8082
```

`local` comes preloaded with air-classifier's development API key
(`airc_local_dev_key`), so the first request works without configuration. The
key is a *default*, not a bypass: local runs authenticate exactly the way QA and
production do, so a key handling bug shows up on your laptop rather than the
first time you point at a shared environment.

## Knowing where you are connected

Wrong-environment mistakes are the expensive ones — a fixture posted at staging,
a local pass mistaken for a QA pass. So the destination is stated everywhere,
unprompted:

- A **target bar** under the title names the selected environment and, for each
  service, its URL, whether it is `LOCAL` or `REMOTE`, and whether a key is set.
  Remote targets colour the whole bar amber.
- **Check both** in that bar probes `/v1/health` on each service and reports
  reachable / unreachable, with latency and the time of the check.
- Every tab repeats the destination in a line of its own, and each **Send**
  button prints the exact URL it will hit next to it.
- The **System** tab's call log records the full URL of everything sent this
  session, and downloads as JSON to attach to a defect report.

### Appearance

Light and dark are both first-class — these screens get stared at for hours.
The sidebar's **Appearance** control offers:

| Mode | What it does |
| ----- | ------------------------------------------------------------------------- |
| **Auto** (default) | Follows your operating system, Streamlit's own widget chrome included. Nothing is overridden, so nothing can disagree. |
| **Light** / **Dark** | Overrides for this session — page, sidebar, header, fields, code and the dataframe grid repaint immediately. |

Streamlit fixes its own theme when a session starts and offers no runtime hook
to change it, so an explicit Light/Dark repaints the console's surfaces while
its alert boxes stay on whatever was resolved at start-up. The sidebar says so
when it detects the mismatch. To pin both from launch:

```bash
make run THEME=dark            # or THEME=light
```

`AIR_CLIENT__THEME=auto|light|dark` in `.env` sets the start-up mode for a team.

### Targets

A target is a named bundle of base URLs and keys. Declare one per deployment in
`.env` and switch between them from the sidebar:

```bash
AIR_CLIENT__TARGET=qa                          # selected at start-up

AIR_CLIENT__TARGETS__QA__LABEL=QA
AIR_CLIENT__TARGETS__QA__CLASSIFIER_BASE_URL=https://classifier.qa.example.internal
AIR_CLIENT__TARGETS__QA__CLASSIFIER_API_KEY=airc_…
AIR_CLIENT__TARGETS__QA__PLATFORM_BASE_URL=https://platform.qa.example.internal
AIR_CLIENT__TARGETS__QA__PLATFORM_API_KEY=
```

`local` always exists, whether or not `.env` does. Switching targets rewrites
the sidebar fields; editing them by hand afterwards is fine and is flagged as
`edited`, with one click to reset. Nothing is written back to disk — sidebar
edits last for the browser session, `.env` is the durable copy. See
[`.env.example`](.env.example) for every key.

## Classifier tab

air-classifier answers one question — what is this text saying, and how sure are
we — through a four-rung escalation ladder: `t0_rules` → `t1_classifier` →
`t2_local_llm` → `t3_cloud_llm`. Every request enters at the cheapest rung and
climbs only when the rung below is not confident enough. The three routes are
that same ladder, specialised:

| Route           | Purpose                                                  | Adds to the request                                             | Adds to the response                          |
| --------------- | -------------------------------------------------------- | --------------------------------------------------------------- | --------------------------------------------- |
| `/v1/sentiment` | The base verdict, no assumptions about the text's origin | —                                                               | —                                             |
| `/v1/feedback`  | Triage inbound product and support feedback              | `channel`, `user_segment`, `subject`                            | `urgency`, `actionability`, `suggested_route` |
| `/v1/reviews`   | Read marketplace reviews per aspect, prose against stars | `rating`, `rating_scale_max`, `product_id`, `verified_purchase` | `aspects`, `rating_consistency`               |

All three are shown side by side in the tab, with the selected one lit, so the
difference stays visible while you work. **Single** posts one item; **Batch**
posts to `/{route}/batch`, taking either one text per line or a full JSON items
array.

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

## System tab

Liveness, readiness and the tier inventory for both services, against the
currently selected target.

`/v1/capabilities` is the one to reach for first. It reports the version, the
batch ceiling and the tier inventory *of the environment you are testing* —
without a running Ollama the ladder stops at `t1_classifier`, and a rung that is
enabled but unavailable explains most surprises. A QA result only means
something next to the capabilities that produced it.

Below the probes, every call made this session, newest first, with its full URL,
status, round-trip time and request id — downloadable as JSON.

## Layout

```text
Dockerfile                  optional containerised run; see `make up`
docker-compose.yml          re-points `local` at the Docker host
src/air_client/
  app.py                    entry point and tab shell
  config.py                 targets and defaults read from .env
  connection.py             the resolved destination, handed to every tab
  http.py                   one request in, one Exchange out; cURL rendering
  state.py                  session-scoped storage, so responses survive reruns
  theme.py                  the CSS
  components/
    sidebar.py              target switcher and connection settings
    target_bar.py           the "where is this going" strip and health probe
    response_view.py        the shared response pane
    summary.py              decoding an analysis response
  tabs/
    classifier.py  chat.py  system.py
```

`make check` runs ruff and mypy (strict).

## Notes

- The layout is fluid rather than a fixed column: request bodies, traces and
  batch tables are wide, and a testing session is mostly spent comparing what
  was sent against what came back.
- Responses live in `st.session_state`. Streamlit re-runs the script on every
  interaction, so anything rendered straight after a button press would
  otherwise vanish the moment you tick a checkbox.
- Network failures are rendered, not raised — a refused connection is an
  ordinary result when the service you are testing is also being written.
- Batch: the schema allows 1000 items, but a deployment's own ceiling defaults
  to 100. The console warns above 100; **Capabilities** reports the real limit
  for the target you are on.
