# Air-Platform — Team Demo Deck (Outline v3)

**Audience:** Developers, QA, DevOps
**Purpose:** Weekly recurring demo. Slides 1–18 are the stable "spine"; Slide 19 is swapped each week.
**Depth:** High-level architecture + low-level tech stack per module. `air-classifier` and `air-llm` are covered at handover depth — enough for an engineer to own them without you.

> `[CONFIRM]` marks an assumption made that hasn't been checked against real
> code or is a genuine product-scope decision, not a technical fact — correct
> or replace before presenting. Most of the original `[CONFIRM]` markers on
> the module slides (6–14) have since been resolved by reading each repo's
> actual source directly; the remaining few are product-scope calls (Slide 3)
> or depend on a design that doesn't fully exist yet (Slide 5's production
> request path — air-platform doesn't call air-classifier or air-llm for real
> synthesis today, see Slide 14).
>
> **Maintenance:** this file is maintained by air-client going forward, kept
> in sync with each repo's own `docs/overview.md` (air-client's version:
> `air-client/docs/overview.md`) as those get written for the other
> projects. Slide content is only as current as its last verification pass —
> check each slide's "as of this deck's last update" language rather than
> assuming it's live.

---

## Slide 1 — Title
- Air-Platform: Conversational Layer for Commerce
- Presenter, date, "Weekly Engineering Demo"
- One-line positioning: *AI gateway in front of existing REST commerce APIs, powered by the existing data platform.*

## Slide 2 — Agenda & How to Read This Deck
- Where we are: 4 modules in progress, 1 to be started
- Status legend: `In Progress` / `To Be Done` / `Design Only`
- Flag up front: `air-classifier` and `air-llm` are ready, and this deck doubles as their handover
- `air-client` is functionally complete for the three services live today
  (classifier, platform, llm) and actively iterating — not a handover slide
  yet, changes are ongoing. Full detail lives in
  [`docs/overview.md`](overview.md) in that repo; Slide 12 here is the
  presentation-deck summary of it, kept in sync by hand.
- Note that this deck is the running weekly artifact

## Slide 3 — Why Air-Platform
- Problem: commerce capability exists as REST APIs; no natural-language surface
- Two consumer groups:
  - **Customers** — order status, return policy, recommendations, search, add-to-cart
  - **Business team** — sales trends, anomalies, inventory forecasting
- Scope decision: **customer/commerce side first**, business analytics as a later extension
- Non-goals for v1 `[CONFIRM]` — e.g. no voice, no multilingual, no autonomous checkout

## Slide 4 — Module Map (the "air-*" family)
Single visual, five boxes with ownership + status — **every role/status cell
below was corrected from the original draft against the real code**; see
each module's own slide for the evidence.

| Module | Role | Status |
|---|---|---|
| `air-client` | **Not** the customer-facing entry surface — an internal Streamlit console developers/QA use to exercise `air-classifier`, `air-platform` and `air-llm` by hand. See the correction on Slide 5. | In progress — solid for today's 3 services, iterating |
| `air-classifier` | Text classification: sentiment, tone, urgency, escalation routing, review analysis — not a customer-intent router. See Slide 6. | Ready |
| `air-llm` | The platform's one model gateway — unified chat/embeddings API, provider routing/failover, cost, cache. No tool-calling, no intent handling. See Slide 9. | Ready |
| `air-infra` | Local-dev-only: a shared Redis/Postgres/Mongo stack plus a credential broker. Not deploy/CI/CD/observability infra, and never runs in prod, by its own design. See Slide 13. | Active, scope-complete for its (narrow, local-only) purpose |
| `air-platform` | Orchestration + policy layer. Foundational layer (auth, streaming, session lifecycle, propose→confirm) is real and tested; synthesis and downstream calls are stubbed pending Phase 2. See Slide 14. | In progress — Phases 0–1 of 7 shipped |

A real customer-facing entry surface — if the product still needs one — is a
separate, not-yet-scoped component. It is not what `air-client` turned out to
be; don't conflate the two on this slide or the next.

**This isn't the whole family.** air-infra's own README maintains the
canonical port registry for every AIR service, and it already reserves ports
for four more not shown here — `air-tools`, `air-action`, `air-recommender`,
`air-rag` — each marked "Not yet built." Worth a beat if the room asks "is
that everything?"

## Slide 5 — High-Level Architecture (one flow, one diagram)
**Correction, read before presenting:** the request-path line below was drafted
assuming `air-client` would be the customer-facing entry point that live
customer traffic flows through. That is not what got built. The `air-client`
that exists today is a standalone developer console that calls each of the
three services directly and independently, for testing — it forwards nothing
and sits in no production path. Either drop `air-client` from this diagram
entirely, or draw it as a separate box on the side that talks to each service
independently (see Slide 12). If a real customer-facing entry point is still
needed, it's a distinct, unbuilt component — name it separately, don't reuse
`air-client`'s name for it.

End-to-end request path (production, once built — excludes `air-client`):
auth/session → `air-classifier` → `air-platform` (orchestrator) → `air-llm` → tool/API calls → existing commerce REST APIs + data platform → response assembly
- Show both ingress routes: **public internet** and **VPN**
- Mark synchronous vs. streaming paths — partially known: air-platform
  streams turn *lifecycle* events over SSE today (not token-level model
  output — see Slide 14), and air-llm does not stream at all yet (Slide 9).
  What a fully-wired production path looks like end-to-end is still
  `[CONFIRM]`, since air-platform doesn't call air-classifier or air-llm for
  real synthesis yet.

---

# air-classifier — handover block (Slides 6–8)

**Correction, read before presenting:** Slides 6–8 were drafted around an
"intent + routing decision layer for commerce" concept — a pre-LLM gate that
decides which flow a customer utterance goes into. That is not what got
built, and the intent taxonomy below (order status, returns, cart actions...)
does not exist anywhere in the real service; it was invented for this
outline. What actually exists is a **general-purpose text classification
service** — sentiment, tone, urgency, escalation routing, review/aspect
analysis — reachable by any caller, not a gate air-platform's own pipeline
passes utterances through before anything else happens. Rewritten below from
the real source, verified directly against the code, not the plan.

## Slide 6 — air-classifier: The Contract
*What it promises to callers. Read this slide and you can integrate against it.*
- **Job:** given one piece of text — a review, a support message, feedback,
  anything — return its sentiment, how urgent it is, who should own it, and
  whether a person needs to look at it. Climbs a 4-tier cost-aware ladder,
  spending more only when a cheaper rung isn't confident enough.
- **One endpoint:** `POST /v1/classify` (+ `/v1/classify/batch`) — this used
  to be three separate routes (`/v1/sentiment`, `/v1/feedback`,
  `/v1/reviews`); they were consolidated into one shape because a caller
  choosing between three response contracts on one service was always the
  same confusion three endpoints were.
- **Input:** `text` (required) plus everything any of the three old routes
  used to accept, all optional now: `channel`/`user_segment`/`subject`
  (feedback-shaped), `rating`/`product_id`/`verified_purchase`/`title`
  (review-shaped).
- **Output, always present:** sentiment (label, polarity, confidence,
  rationale), urgency, routing (queue + priority), `requires_human`,
  actionability, emotions.
- **Output, only when the ladder reaches an LLM tier:** tone, topics,
  `intent` — the real intent vocabulary is post-hoc, read off text that
  already exists (`complaint`, `refund_request`, `order_tracking`,
  `cancellation`, `praise`, …), not a pre-classification router.
- **Output, only when the caller supplies a `rating`:** `rating_consistency`
  — does the prose agree with the stars.
- **Guarantee it does *not* make:** never calls commerce or any other API,
  never mutates anything — a pure read.
- **Budget, not SLA:** `options.latency_budget_ms` (default 8000ms) and
  `options.max_cost_usd` (default $0.05) bound how far the ladder climbs; the
  only 5xx is "every enabled tier failed or abstained."

## Slide 7 — air-classifier: Inside the Box
*Implementation walkthrough — this is the slide you talk over with the code open.*
- **The real ladder, cheapest first, climbs only when confidence requires it:**
  1. `t0_rules` — deterministic lexicon/regex shortcuts. <1ms, ~$0. Clear
     cases, extreme star ratings.
  2. `t1_classifier` — a quantised zero-shot NLI encoder + lexicon ensemble.
     80–200ms, ~$0. Clear polarity, conventional phrasing, English-tuned.
  3. `t2_local_llm` — a local model, schema-constrained output, model choice
     is air-llm's own config. 200ms–2s, ~$0. Mixed sentiment, mild sarcasm.
  4. `t3_cloud_llm` — a metered cloud model, arbitrated up to a stronger one
     when the fast model is itself unconfident — vendor and model both
     air-llm's choice, not this repo's. 0.8–3s, real $ per call. Genuine
     ambiguity, subtle irony, multilingual edges.
- **As of this deck's last update, every model call — Tiers 2 *and* 3 —
  routes through air-llm exclusively.** This changed recently: this
  service used to hold its own Anthropic/OpenAI/Gemini/Ollama SDK adapters
  behind an *optional* air-infra gateway toggle; that whole layer (five
  provider files, a registry, a circuit breaker per vendor) was deleted and
  replaced with one `AirLlmProvider`. air-classifier now holds **no
  provider SDKs and no provider credentials of its own** — only an air-llm
  service token. See Slide 13 for the air-infra→air-llm extraction this
  completes.
- **Code layout:** `api/v1/` (routes), `pipeline/` (orchestrator, escalation
  policy, `tiers/`), `providers/` (now just `air_llm_provider.py` + versioned
  prompt files), `preprocess/` (PII redaction, language detection,
  normalisation), `security/` (API keys, rate limits), `resilience/`
  (circuit breaker, bulkhead, retry).
- **Stack:** Python/FastAPI, pydantic, orjson; zero provider SDKs — air-llm
  is a hard dependency for Tiers 2 and 3 both (without it reachable, the
  ladder stands down to `t1_classifier`).
- **Config, not code:** every tier's confidence/margin floor and timeout,
  and which air-llm routing alias each rung asks for, live in `Settings`.
- **Failure behaviour:** a failed tier never raises to the caller — the best
  usable lower-tier verdict returns with `degraded: true`.
- **Resolved since this session's hardening review:** the metered cloud tier
  (`t3_cloud_llm`) was found missing its concurrency bulkhead at
  construction time — unbounded concurrent cloud calls were possible where
  every other guarded tier self-constructs a default. **Confirmed fixed**:
  it now self-constructs one exactly like `t2_local_llm` does.

## Slide 8 — air-classifier: Own It
*Extend, test, operate — the takeover slide.*
- **Tune a tier:** thresholds live in `Settings` (`confidence_floor`,
  `margin_floor`, `timeout_ms` per rung) — a config edit, not a code change.
- **Change the rubric:** `providers/prompts/system.md` (cloud) and
  `system_compact.md` (local) are versioned files, not inline strings — a
  worked-examples-heavy rubric with an explicit confidence-calibration
  section, because the escalation policy reads that confidence number
  directly to decide whether to climb.
- **Test assets you inherit:** 33 test files across unit / integration /
  contract layers (every tier, every provider, security, resilience, the
  orchestrator, the prompts). **No CI pipeline exists yet** — `make check`
  runs lint + typecheck + test and is labelled "everything CI runs" in the
  Makefile, but there is no `.github/workflows` or equivalent wired up to
  actually run it automatically.
- **QA hooks:** every response carries `decided_by` and an
  `escalation_trace` — which rung answered and why it did or didn't climb
  past each one below it, so a misclassification is reproducible without
  guessing which tier was even consulted.
- **Ops hooks:** structured JSON logs, an internal-network-only Prometheus
  `/metrics`, per-tier decision/escalation counters, per-provider cost
  tracking.
- **Handover checklist:** `docs/00-plan.md`/`01-hld.md`/`02-lld.md` are all
  **"Draft for review"** — not finalised. 6 commits total in the repo as of
  this deck's last update — young, fast-moving; treat any slide here as
  perishable.

---

# air-llm — handover block (Slides 9–11)

**Correction, read before presenting:** Slides 9–11 were drafted around an
"intent-driven generation layer with a tool loop" concept — the caller hands
it a resolved intent and permitted tools, it runs a tool-calling loop and
validates the output. That is not what got built. What exists is a **model
gateway**: one unified inference API in front of several providers, with
routing/failover, cost accounting and caching — it does not know what an
"intent" is, has no tool-loop or tool registry, and does no output validation
beyond schema-constrained structured output when the caller asks for it.
Rewritten below from the real source, verified directly against the code.

## Slide 9 — air-llm: The Contract
*The one abstraction every other module talks to for generation.*
- **Job:** isolate every caller from provider-specific SDKs, rate limits, and
  API shapes — one contract in front of Ollama, Anthropic, OpenAI, Gemini,
  and any OpenAI-wire-compatible self-hosted backend (vLLM/TGI are the real
  UAT/prod candidates for that slot; llama.cpp/LM Studio for local).
- **One endpoint, two tasks:** `POST /v1/inference` — a `task` field
  (`chat` | `embeddings`) picks between them, not two routes.
- **Input:** `model` (alias, `provider:model`, or a bare name), `messages`
  (chat) or `input` (embeddings), `max_tokens`, `temperature`, `json_schema`
  + `schema_name` for structured output, `cache_prefix`.
- **Output:** `id`, `task`, `model`, `provider`, `content` or `embeddings`,
  `usage` (tokens in/out, cache read/write), `cost_usd`, `cached`, `refusal`,
  `finish_reason`.
- **Guarantee it does *not* make:** no intent handling, no tool loop, no
  output validation beyond structured-output schema conformance — a caller
  that needs any of that builds it on top.
- **Explicitly not shipped yet, by its own docs, not a hidden gap:** adaptive
  routing (routing is a static, DevOps-owned alias→chain config in
  `deploy/routing.yaml`, per release) and a circuit breaker (failover today
  is a per-attempt deadline plus walking the configured chain on error or
  timeout — no failure-history state, no half-open probe).
- **This is now confirmed the platform's *only* model gateway.** The
  provider/routing/cost/cache code was ported near-verbatim from air-infra,
  which has since had that entire module deleted (Slide 13) — air-llm isn't
  "a" gateway alongside another one, it's the one that's left. Reached
  directly by every consumer, in every environment; air-classifier already
  cut over (Slide 7) and holds no provider SDKs of its own anymore.

## Slide 10 — air-llm: Inside the Box
*Implementation walkthrough — talk over this with the code open.*
- **Code layout:** `api/v1/` (`inference.py`, `admin.py`, `system.py`),
  `gateway/` (`router.py` — the chain-walking failover logic, `cache.py`,
  `cost.py`, `providers/` — one adapter per vendor plus
  `self_hosted_provider.py`), `policy/` (`engine.py` for RBAC, `ratelimit.py`
  for a token-bucket limiter), `security/apikeys.py`, `observability/`
  (logging, metrics).
- **Auth:** single `X-API-Key` resolved to a `Principal(service, token_id)`
  via a flat in-memory token map
  (`AIR_LLM_SECURITY__SERVICE_TOKENS=token:service,...`) — the same
  header/shape air-classifier and air-platform already use. air-client's own
  dev token is already provisioned there.
- **RBAC + rate limiting:** `PolicyEngine.decide(principal, resource,
  action)`, gated by a YAML policy doc (`deploy/policy/policy.local.yaml`)
  with a per-caller rate limit — e.g. air-client's key is scoped to `chat`
  only, not `embeddings`, in the shipped local policy.
- **Failure behaviour:** a per-attempt deadline, then the router walks the
  configured provider chain on error or timeout. That's the whole failover
  story today — no adaptive routing, no circuit breaker (both named
  follow-ons in its own `docs/02-lld.md` §10, not oversights).
- **Stack:** Python/FastAPI; a provider SDK per vendor; Ollama needs none.

## Slide 11 — air-llm: Own It
*Extend, test, operate — the takeover slide.*
- **Add a provider:** implement the adapter interface under
  `gateway/providers/`, register it, add it to a chain in
  `deploy/routing.yaml`.
- **Adjust routing or pricing:** `deploy/routing.yaml` /
  `deploy/pricing.yaml` — DevOps-owned YAML, not code; a missing file falls
  back to built-in tables, so a bare checkout still runs.
- **Test assets you inherit:** 10 test files (system, readiness, policy,
  gateway, gateway-config, the inference endpoint, cache, and one
  provider-specific suite for Gemini). **No CI pipeline exists yet** — no
  `.github/workflows` or equivalent.
- **QA hooks:** `/v1/capabilities` reports which providers are actually
  reachable right now; a failed call's `provider`/`model` fields in the
  response (or the RFC 9457 problem body on failure) say exactly which leg
  of the chain answered or refused.
- **Handover checklist:** `docs/00-plan.md`/`01-hld.md`/`02-lld.md` all
  **"Draft for review."** 3 commits total as of this deck's last update —
  genuinely new. The API contract itself (the 5 routes, the schemas, the
  auth header) reads as settled even though internals (a real circuit
  breaker, adaptive routing, a Redis-backed cache/rate-limiter — currently
  in-process only) are explicitly still on the roadmap per its own docs.

---

## Slide 12 — air-client (deep dive)
*Status: in progress, actively iterating. Full detail: `air-client/docs/overview.md`
— this slide is a condensed, hand-kept-in-sync summary of it, not the source
of truth. When the two disagree, `overview.md` wins.*

- **What it actually is:** a single internal surface — a Streamlit console,
  one Python process per developer, no shared server, no customer traffic.
  Not a widget, not mobile, not embedded anywhere.
- **Job:** point at any environment (local / QA / staging), send a real
  request to `air-classifier`, `air-platform`, or `air-llm` through a form
  that matches that service's actual schema, see the decoded response and
  the raw JSON, reproduce it as a runnable `curl` command.
- **Session/state model:** Streamlit's own per-process `st.session_state` —
  last response per tab, call log, target selection. Ephemeral; gone when the
  process stops. No conversation history is "owned" by air-client itself —
  air-platform's `session_id` round-trips through the console but the console
  is not the system of record for it.
- **Auth:** no customer/e-commerce session handoff — that concept doesn't
  apply here. Each service gets its own `X-API-Key`, held per configured
  environment (`.env` + sidebar), sent exactly as any real caller would send
  it. air-platform's two channels (customer/business) are two distinct keys
  the console holds side by side, since the channel comes from the key, not
  a header.
- **Transport:** plain HTTPS request/response via `httpx`, synchronous only.
  No SSE, no WebSocket — a known gap: air-platform exposes an SSE streaming
  variant of its turn API that this console does not yet call.
- **Error / degraded-mode UX:** every failure mode renders as a state in the
  UI (unreachable, unauthenticated, `degraded: true`, a 4xx/5xx problem body)
  — never a raised exception, never a blank screen. The console is meant to
  stay usable while the thing it's pointed at is half-broken.
- **Covers 3 of the module map's services today** — classifier, platform,
  llm. `air-infra` has no client-console coverage yet.

## Slide 13 — air-infra (deep dive)
**Correction, read before presenting:** "Deploy, CI/CD, secrets,
observability" — the Slide 4 framing — overstates it. air-infra is **not** a
deploy/CI/CD/observability platform and was never meant to become one; its
own docs say so directly: *"This project is explicitly not a production
service... the process itself never runs in prod."* What it actually is: a
**local-dev-only control plane** — a shared docker-compose stack (Redis,
Postgres+pgbouncer, Mongo) plus a small FastAPI broker that hands out scoped,
policy-checked credentials to those stores, so every AIR service resolves
against the same local instances instead of standing up its own.

- **The gateway story — a clean, completed handoff, not an open question:**
  air-infra briefly held a real, tested multi-provider LLM gateway (routing,
  failover, cost accounting, caching, Anthropic/OpenAI/Ollama adapters). It
  was **fully extracted to air-llm and deleted from this repo**, the same
  day air-classifier cut over to calling air-llm directly (Slide 7). No
  gateway code remains here. air-infra's own docs, in its own voice: *"Model
  inference used to live here too; it has been fully extracted to air-llm,
  which *is* meant to run in every environment, including production."*
- **Runtime:** docker-compose only — no K8s, no ECS, no cloud IaC anywhere
  in the repo. A fixed external Docker network (`air-net`) is how sibling
  services resolve `redis`/`postgres`/`pgbouncer`/`mongo`/`air-infra` by
  name; air-infra must be started first, or dependents fail immediately
  rather than degrading.
- **Environments: `local` only, by design.** The config schema has a
  `local`/`staging`/`prod` selector, but the docs are explicit this is
  theoretical — "in practice this image only ever boots as `local`." No
  staging/prod target, no SLA, no on-call: a stated non-goal, not a gap.
- **Secrets:** a pluggable backend, three implementations of very different
  maturity — `EnvSecretBackend` (the only one actually used), a `File`
  backend (implemented but unwired here), and a `Vault` backend that is a
  literal `NotImplementedError` stub. Issued credentials never expire — no
  lease/rotation — flagged in air-infra's own docs as *"acceptable for a
  local dev credential; not a pattern to copy into anything that does run
  in prod."*
- **Observability:** real structured logging (`structlog`) and Prometheus
  metrics (`/metrics`, three counters); **no tracing at all** — no
  OpenTelemetry anywhere in the repo. An optional Compose profile brings up
  a shared Prometheus + Grafana that every AIR service can register a
  scrape target with (today: air-infra and air-classifier only).
- **CI/CD: none.** No `.github/workflows`, no pipeline of any kind — same
  gap as every other air-* service surveyed for this deck. `make check`
  (ruff + mypy strict + pytest) is a local, developer-run gate only.
- **Consumers today, per its own policy file:** air-classifier (redis
  read/write), air-platform (redis/postgres/mongo read/write), air-client
  (redis read-only). **air-platform's own docs are stale here** — they still
  describe air-infra as "Model Gateway :8080, already built," which no
  longer matches either repo's actual code (see Slide 14).
- **The port map is bigger than this deck's 5 modules.** air-infra's own
  README maintains the canonical port registry for the whole family — it
  already reserves ports for `air-tools`, `air-action`, `air-recommender`
  and `air-rag`, all marked "Not yet built." Worth a beat on Slide 4 or
  Slide 18 if the room asks "is that everything?"

## Slide 14 — air-platform (status, not design-only)
**Correction, read before presenting:** "To be done / design-only / open
design questions to close before build starts" is stale. There is a running,
tested FastAPI service today — verified directly, not from its docs alone.
It just isn't generating real answers yet, and says so honestly in its own
code rather than faking it.

- **Status:** Phases 0–1 of a 7-phase plan shipped; Phase 2 in progress right
  now (an air-llm client was mid-build, uncommitted, as of this deck's last
  update). Not a handover slide like classifier/llm — no owner transition
  planned yet, and Slide 18 correctly doesn't list one.
- **Real and tested today (126 passing tests):**
  - Both entry routes fully wired — `POST /v1/chat` (customer) and
    `POST /v1/query` (business) — each pinned to its channel by an auth
    dependency, not a runtime branch. A customer key cannot reach
    `/v1/query`, structurally, not by convention.
  - Real auth/RBAC: salted-SHA256 API key store, constant-time comparison,
    per-key scopes and cost/rate ceilings, channel fixed on the key record
    and never read from a header — the same pattern air-classifier uses.
  - Real SSE streaming of the turn's *lifecycle* events (`turn.start`,
    `stage`, `route`, `proposal`, `answer`, `usage`, `turn.end`), content-
    negotiated against the same engine the non-streaming path uses. **Not**
    token-level model streaming — `ANSWER_DELTA` is reserved, unemitted in
    v1, since air-llm itself doesn't stream token-by-token yet either.
  - A real propose→confirm **state machine**: a proposal is stored
    server-side with a TTL; only a structured `confirm.proposal_id/approve`
    on the *next* turn can act on it. Replying "yes" in prose does nothing —
    deliberately, closing a prompt-injection-shaped hole before it opens.
- **Deliberately stubbed, and labelled as such in the code — never silently
  faked:**
  - All 9 pipeline stages run every turn
    (`guardrails_in → context → cache → classify → plan → gather →
    synthesise → guardrails_out → persist`), but only `plan` (a hardcoded
    `/propose` trigger-phrase check) and `persist` (real bounded session
    history) do anything. The rest report `skipped` with a reason.
  - `synthesise` is a literal echo — no model is called anywhere yet.
  - Confirming a proposal returns "Executed *(echo engine — nothing actually
    changed)*" — a labelled placeholder for air-action, which doesn't exist
    yet as a service or a client.
  - air-classifier has **no client in this repo at all** (config block
    exists, disabled by default). air-llm has a client, but it implements
    only a health probe so far — no chat call yet.
- **No CI pipeline** (no `.github/workflows`) — consistent with every air-*
  service surveyed for this deck so far.
- **A candid detail worth repeating to the room:** the plan/HLD docs predate
  air-llm being split out of air-infra and still describe that outdated
  architecture; the README says fixing that is itself deferred to Phase 2.
  Trust the README's status line over the HLD/LLD for "what's true today" —
  and prefer this slide, kept current by air-client, over either.

## Slide 15 — Cross-Cutting Concerns
- AuthN/AuthZ per audience (customer vs. business team)
- Data boundaries: what may be read into context, what may never be written
- Rate limiting, abuse handling, audit logging
- Public vs. VPN exposure differences

## Slide 16 — QA & Test Strategy *(QA-focused)*
- Test pyramid for a non-deterministic system
- Classifier accuracy gates; golden-set evals for generated responses
- Contract tests against the commerce REST APIs; mocked provider in CI
- What "flaky" means here and how we bound it
- Bug triage across module boundaries — classifier, prompt, tool, or integration

## Slide 17 — Ops & Runbook *(DevOps-focused)*
- Dashboards and the 4–5 alerts that matter
- Failure modes: provider outage, timeout storm, cost spike, tool-call loop
- Kill switch / degraded mode → fall back to existing non-AI flows
- Deploy + rollback procedure, prompt changes as deployable artifacts

## Slide 18 — Roadmap, Milestones & Asks
- Timeline across the five modules
- Dependencies and current blockers
- Ownership transition: named owner for `air-classifier` and for `air-llm`, review buddy, transition date
- Explicit asks from the room: reviewers, test data, environments
- **Cross-cutting finding worth its own beat:** none of the five modules —
  classifier, llm, infra, platform, client — has a CI pipeline. Every one
  has a local `make check` (lint + typecheck + test) that nobody has to run,
  and only the developer's own discipline stands between a broken `main` and
  everyone finding out. Worth an explicit ask to the room rather than a
  quiet gap on four separate slides.

## Slide 19 — This Week's Demo *(swap each week)*
- What shipped this week
- Live demo checkpoint
- Next week's target
- (Reusable template slide — keeps the deck incremental)

---

## Gaps I need from you before building

Nearly everything below was open when this outline was first drafted and has
since been resolved by reading each repo's actual source directly, not by
asking. Kept as a record of what was unknown then and where the answer lives
now, rather than deleted — useful for anyone wondering how much of this deck
is verified vs. asserted.

**air-classifier (handover block, Slides 6–8) — all answered, see Slide 6–8:**
1. ~~Which stages are actually implemented?~~ **Answered:** all 4 tiers are real; see Slide 7.
2. ~~Exact input/output schema?~~ **Answered:** see Slide 6.
3. ~~Library/model behind classification?~~ **Answered:** a quantised zero-shot NLI encoder + lexicon ensemble (`t1_classifier`); Tiers 2–3 are air-llm's own model choice now, not this repo's — see Slide 7's correction.
4. ~~Confidence threshold values?~~ **Answered:** per-tier `confidence_floor`/`margin_floor` in `Settings` — config, not a fixed number worth quoting here since it's tunable per deployment.
5. ~~Labelled dataset, accuracy gate in CI?~~ **Partially answered:** no accuracy-gate/golden-set concept exists in this service's actual design — it's a rules+model ladder with per-tier confidence floors, not a trained-classifier-with-eval-set shape. No CI exists regardless (Slide 8).
6. ~~Is the Slide 6 intent list correct?~~ **No — it was wrong.** Replaced; see Slide 6's correction note.

**air-llm (handover block, Slides 9–11) — all answered, see Slide 9–11:**
7. ~~Exact input/output schema?~~ **Answered:** see Slide 9.
8. ~~Provider abstraction real or single-provider?~~ **Answered:** real, 5 adapters (Ollama, Anthropic, OpenAI, Gemini, self-hosted-OpenAI-wire) — see Slide 10.
9. ~~Prompt storage/versioning?~~ **N/A** — air-llm doesn't own prompts; it's a model-call gateway, not a prompt registry (see Slide 9's correction — this question assumed the wrong shape of service).
10. ~~Tool registry?~~ **N/A**, same reason — no tool-calling concept exists here.
11. ~~Eval harness / golden set / CI?~~ **Answered:** none of the three exist. No CI anywhere in the family — see Slide 18.
12. ~~Streaming end-to-end or buffered?~~ **Answered:** buffered only; no streaming at all yet (Slide 9).

**Everything else:**
13. ~~**air-client** — which surface(s), and what transport?~~ **Answered:**
    one internal Streamlit console, synchronous HTTPS only, no SSE/WebSocket.
    See Slide 12 and `air-client/docs/overview.md`.
14. ~~**air-infra** — runtime platform, CI/CD tool, observability stack?~~
    **Answered:** docker-compose only (no K8s/cloud), no CI/CD of any kind,
    structured logs + Prometheus (no tracing). See Slide 13 — and note
    air-infra is *not* a CI/CD/observability platform itself, despite the
    original Slide 4 framing.
15. ~~**Status per module** — one-line "where it stands"?~~ **Answered for
    all five** — see the corrected Slide 4 table.
16. Any **branding constraint** — company template, colours, logo? **Still
    open** — a design/business decision, not something any repo's code can
    answer.
