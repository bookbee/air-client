# air-client

A Streamlit console for exercising the AIR services by hand. Send a request,
read the response, copy the cURL that reproduces it.

**This is not a hosted service.** Developers and QA clone the repo, run it on
their own machine, and point it at whichever deployment is under test — usually
a remote one. Everything below follows from that: the console never guesses
where it is connecting, and it never lets you forget.

Four tabs, one per surface:

| Tab | Service | What it does |
| --- | --- | --- |
| **Classifier** | air-classifier | `/v1/classify`, single and batch, plus tier probes |
| **Platform** | air-platform | Both channels: `/v1/chat` and `/v1/query` |
| **LLM** | air-llm | `/v1/inference` — chat and embeddings, one endpoint |
| **System** | all three | Health, readiness, capabilities, and a log of every call |

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

### Currency

Every AIR service bills and reports cost in USD — that is what every provider
actually charges in. Wherever the console shows a cost figure, it also shows
an approximate ₹ conversion next to it (`$0.00042 · ~₹0.04`), purely for
convenience. There is no live FX feed: the rate is a fixed default, adjustable
for the session in the sidebar's **Request behaviour** panel, or preset with
`AIR_CLIENT__USD_TO_INR_RATE` in `.env`.

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
AIR_CLIENT__TARGETS__QA__LLM_BASE_URL=https://llm.qa.example.internal
AIR_CLIENT__TARGETS__QA__LLM_API_KEY=
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
climbs only when the rung below is not confident enough.

One endpoint now, not three: `POST /v1/classify` absorbed what used to be
`/v1/sentiment`, `/v1/feedback` and `/v1/reviews` into a single request shape.
`channel`/`user_segment`/`subject` (feedback-shaped) and
`rating`/`rating_scale_max`/`product_id`/`verified_purchase`/`title`
(review-shaped) are both always-available optional fields now, not
route-gated ones — the tab shows them behind one "Optional context" expander.
**Single** posts one item; **Batch** posts to `/v1/classify/batch`, taking
either one text per line or a full JSON items array.

A **Tier probes** expander above the form pins `options.min_tier`/`max_tier`
to a named rung and fills in one of the confident sample texts below, sourced
straight from this repo's own `docs` — a pinned tier that cannot serve
returns `503` rather than quietly falling back, so a working response really
did come from the rung named on the button.

The response pane shows a **Summary** — a dense, dashboard-style read-out of
the verdict, routing, tone/topics/intent, rating consistency (when a rating
was supplied), aspects, emotions, the escalation ladder with the model that
answered each rung, safety and usage/cost (in USD, with an approximate ₹
figure alongside it — see [Currency](#currency) below) — the **raw JSON**,
the **headers**, and the **request** as runnable cURL with the API key
masked until you ask for it.

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

## Platform tab

air-platform runs one pipeline behind two entry points, differing only by
profile — guardrails, output contract, audit sink, quota bucket, tool allow-list:

| Route | Channel | Body field | Adds |
| --- | --- | --- | --- |
| `POST /v1/chat` | customer | `message` | public conversational traffic |
| `POST /v1/query` | business | `query` | `output_schema` for structured output |

**The channel comes from the API key, not from a header.** A caller that could
name its own channel could select the weaker guardrail profile, so air-platform
refuses to read it from the request and enforces the pairing: the customer key on
`/v1/query` is a 403, and so is the business key on `/v1/chat`. The console
therefore holds **one key per channel** and sends the one belonging to the route
you picked — the Send button names the channel it is about to use.

Both development keys are preloaded, so both routes work on a fresh clone:

```bash
AIR_CLIENT__TARGETS__LOCAL__PLATFORM_CUSTOMER_API_KEY=airp_local_customer_key
AIR_CLIENT__TARGETS__LOCAL__PLATFORM_BUSINESS_API_KEY=airp_local_business_key
```

The older single `PLATFORM_API_KEY` is still read, as the customer key.

The response pane decodes a `TurnResult`: the answer as a chat bubble, then a
dashboard summary (status, grounded, refusal, routes, session), any structured
output, the citations, the nine pipeline stages with their latencies, and
usage including cost. A turn that warrants a write returns a **proposal** and
changes nothing — the panel offers **Confirm & execute** and **Decline**
buttons that send a second turn on the same session carrying `confirm`, per
`docs/02-lld.md` §8. Neither development key grants `allow_actions`, so both
403 against a local checkout, which is the correct outcome; they are there
for a remote key that actually carries the scope.

`session_id` is returned by the first turn and fed back into the box, so the next
turn continues the same conversation instead of silently starting a new one.

## LLM tab

air-llm is the AIR platform's central LLM gateway — one unified inference API
in front of Ollama, Anthropic, OpenAI and Gemini, with provider
routing/failover, cost accounting and response caching. It has no UI or test
harness of its own, so this tab is the only place most developers will see a
raw response from it before wiring a real integration.

One endpoint, `POST /v1/inference`, does both tasks it supports — a `task`
radio picks between them, not a route:

| Task | Sends | Notes |
| --- | --- | --- |
| **chat** | `messages` (one required message, or a hand-built JSON array under "Advanced") | Stateless per call — no `session_id`, unlike air-platform |
| **embeddings** | `input`, one string per line | Returns one vector per input string |

Every other field — `model`, `max_tokens`, `temperature`, `json_schema` +
`schema_name`, `cache_prefix` — sits at the request's top level, not under an
`options` sub-object the way air-classifier's and air-platform's do, since
`InferenceRequest` has no such wrapper.

The response pane shows a dashboard summary (task, provider, model, cached,
refusal, finish_reason), the answer as a chat bubble or the embedding count
and dimensionality, and usage/cost. A **Check my policy** button below the
form calls `GET /v1/admin/policy` and shows the raw response — what your key
is actually scoped to, useful when a call 403s and you want to know why.

## System tab

Liveness, readiness and the tier/provider inventory for all three services,
against the currently selected target.

The platform panel has a **channel** switch, because `/v1/capabilities` answers
per channel — guardrails, routes and quotas are profile-specific, so the answer
depends on which key asked.

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
  currency.py               USD -> INR display for cost figures, not a live rate
  dashboard.py              the dense data-grid every response summary is built from
  http.py                   one request in, one Exchange out; cURL rendering
  state.py                  session-scoped storage, so responses survive reruns
  theme.py                  the CSS — fonts, palettes, and dashboard.py's grid styling
  components/
    sidebar.py              target switcher and connection settings
    target_bar.py           the "where is this going" strip and health probe
    response_view.py        the shared response pane
    summary.py              decoding a /v1/classify response
  tables.py                 columns Arrow can type; mixed ones render as text
  tabs/
    classifier.py  platform.py  llm.py  system.py
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
