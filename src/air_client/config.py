"""Start-up defaults for the console.

This console is not hosted anywhere. Developers and QA clone the repo, run it on
their own machine, and point it at whichever AIR deployment they are testing —
usually a remote one. So the thing configuration has to get right is not "what
are the settings" but **"which environment am I about to send this to"**.

Hence *targets*: named bundles of base URLs and keys, declared once in `.env`
and switched from the sidebar at runtime. One is always present — ``local`` —
and it is pre-wired to the ports and development key that air-classifier's own
`.env.example` ships, so a fresh checkout works before anyone edits anything.

Nothing here is authoritative once the app is running: the sidebar owns the live
connection, because changing it without a restart is the entire point.

Spelling in `.env`::

    AIR_CLIENT__TARGET=qa                       # which one is selected at boot

    AIR_CLIENT__TARGETS__QA__LABEL=QA (shared)
    AIR_CLIENT__TARGETS__QA__CLASSIFIER_BASE_URL=https://classifier.qa.example
    AIR_CLIENT__TARGETS__QA__CLASSIFIER_API_KEY=airc_...
    AIR_CLIENT__TARGETS__QA__PLATFORM_BASE_URL=https://platform.qa.example
    AIR_CLIENT__TARGETS__QA__PLATFORM_API_KEY=

The flat ``AIR_CLIENT__CLASSIFIER_BASE_URL`` style still works and is read as an
override of the built-in ``local`` target.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

ENV_PREFIX = "AIR_CLIENT__"
TARGETS_PREFIX = f"{ENV_PREFIX}TARGETS__"

#: The target that always exists, so the console is useful with no `.env` at all.
LOCAL_TARGET_NAME = "local"

# Ports come from the AIR port map in air-infra/README.md, which reserves
# 8080-8089 for services: 8080 air-infra, 8081 air-platform, 8082 air-classifier.
LOCAL_CLASSIFIER_BASE_URL = "http://127.0.0.1:8082"
LOCAL_PLATFORM_BASE_URL = "http://127.0.0.1:8081"

#: The development key air-classifier ships in its own `.env.example`. It is
#: valid only against that repo's development hash salt, and it is a default
#: rather than a bypass on purpose — local runs then exercise the same
#: authenticated path as every remote environment, so a key handling bug
#: surfaces here instead of the first time someone points at QA.
LOCAL_CLASSIFIER_API_KEY = "airc_local_dev_key"

#: Hosts that mean "this machine". Anything else is treated as remote and is
#: flagged as such everywhere the console shows a URL.
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0", "host.docker.internal"})

_TARGET_FIELDS = frozenset(
    {
        "LABEL",
        "CLASSIFIER_BASE_URL",
        "CLASSIFIER_API_KEY",
        "PLATFORM_BASE_URL",
        "PLATFORM_API_KEY",
    }
)


def _load_dotenv() -> None:
    """Fold a sibling `.env` into os.environ without adding a dependency.

    Only `KEY=value` lines are honoured, and existing environment variables
    always win — an explicit export should beat a stale file.
    """
    path = Path(__file__).resolve().parents[2] / ".env"
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def _get(name: str, default: str) -> str:
    value = os.environ.get(f"{ENV_PREFIX}{name}")
    return value.strip() if value and value.strip() else default


def _get_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(f"{ENV_PREFIX}{name}")
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _get_float(name: str, default: float) -> float:
    raw = os.environ.get(f"{ENV_PREFIX}{name}")
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def location_of(base_url: str) -> str:
    """``"local"``, ``"remote"`` or ``"unset"`` for one base URL.

    Drives every "where is this going" indicator in the UI, so it errs towards
    saying *remote*: a URL that cannot be parsed is not this machine.
    """
    if not base_url.strip():
        return "unset"
    host = (urlparse(base_url).hostname or "").lower()
    if not host:
        return "remote"
    if host in LOCAL_HOSTS or host.endswith(".local"):
        return "local"
    return "remote"


@dataclass(frozen=True, slots=True)
class Target:
    """One named environment the console can be pointed at."""

    name: str
    label: str
    classifier_base_url: str
    classifier_api_key: str
    platform_base_url: str
    platform_api_key: str

    @property
    def location(self) -> str:
        """The stronger of the two services' locations — remote wins.

        A target with one remote leg is a remote target for warning purposes,
        even if the other leg is still pointing at localhost.
        """
        legs = {location_of(self.classifier_base_url), location_of(self.platform_base_url)}
        if "remote" in legs:
            return "remote"
        if "local" in legs:
            return "local"
        return "unset"


@dataclass(frozen=True, slots=True)
class Defaults:
    """Seed values for the sidebar."""

    targets: dict[str, Target]
    selected: str
    timeout_seconds: float
    verify_tls: bool
    #: Appearance at start-up: ``auto`` (follow the OS), ``light`` or ``dark``.
    #: Validated by :func:`air_client.theme.resolve_mode`, which owns the modes.
    theme: str

    @property
    def selected_target(self) -> Target:
        return self.targets[self.selected]


def _collect_declared() -> dict[str, dict[str, str]]:
    """Group ``AIR_CLIENT__TARGETS__<NAME>__<FIELD>`` variables by target name."""
    declared: dict[str, dict[str, str]] = {}
    for key, value in os.environ.items():
        if not key.startswith(TARGETS_PREFIX):
            continue
        name, _, field = key[len(TARGETS_PREFIX) :].partition("__")
        if not name or field not in _TARGET_FIELDS:
            continue
        declared.setdefault(name.lower(), {})[field] = value.strip()
    return declared


def _build_local(fields: dict[str, str]) -> Target:
    """The built-in target, with `.env` overrides applied on top.

    Flat keys are honoured here so a `.env` that predates named targets keeps
    working: they are, in effect, edits to ``local``.
    """
    return Target(
        name=LOCAL_TARGET_NAME,
        label=fields.get("LABEL") or "Local — services on this machine",
        classifier_base_url=fields.get("CLASSIFIER_BASE_URL")
        or _get("CLASSIFIER_BASE_URL", LOCAL_CLASSIFIER_BASE_URL),
        classifier_api_key=fields.get("CLASSIFIER_API_KEY")
        or _get("CLASSIFIER_API_KEY", LOCAL_CLASSIFIER_API_KEY),
        platform_base_url=fields.get("PLATFORM_BASE_URL")
        or _get("PLATFORM_BASE_URL", LOCAL_PLATFORM_BASE_URL),
        platform_api_key=fields.get("PLATFORM_API_KEY") or _get("PLATFORM_API_KEY", ""),
    )


def load_defaults() -> Defaults:
    _load_dotenv()
    declared = _collect_declared()

    targets: dict[str, Target] = {
        LOCAL_TARGET_NAME: _build_local(declared.pop(LOCAL_TARGET_NAME, {}))
    }
    for name in sorted(declared):
        fields = declared[name]
        targets[name] = Target(
            name=name,
            label=fields.get("LABEL") or name.upper(),
            classifier_base_url=fields.get("CLASSIFIER_BASE_URL", ""),
            classifier_api_key=fields.get("CLASSIFIER_API_KEY", ""),
            platform_base_url=fields.get("PLATFORM_BASE_URL", ""),
            platform_api_key=fields.get("PLATFORM_API_KEY", ""),
        )

    selected = _get("TARGET", LOCAL_TARGET_NAME).lower()
    if selected not in targets:
        # A typo in AIR_CLIENT__TARGET must not silently connect you to
        # something else; falling back to local is the safe direction.
        selected = LOCAL_TARGET_NAME

    return Defaults(
        targets=targets,
        selected=selected,
        timeout_seconds=_get_float("TIMEOUT_SECONDS", 60.0),
        verify_tls=_get_bool("VERIFY_TLS", True),
        theme=_get("THEME", "auto").lower(),
    )
