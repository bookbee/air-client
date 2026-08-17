# syntax=docker/dockerfile:1.7
#
# The console in a container, for people who would rather not install Python
# 3.12 to run a test tool. It changes one thing that matters: `localhost` now
# means *this container*, not your machine. The compose file points the `local`
# target at `host.docker.internal` for exactly that reason — see docker-compose.yml.

ARG PYTHON_IMAGE=python:3.12-slim
ARG VENV=/opt/venv


# ── Builder ───────────────────────────────────────────────────────────────────
FROM ${PYTHON_IMAGE} AS builder

ARG VENV
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore \
    PYTHONDONTWRITEBYTECODE=1

RUN python -m venv "${VENV}"
ENV PATH="${VENV}/bin:${PATH}"

WORKDIR /build

# Dependencies resolve from pyproject alone. A stub package satisfies hatchling
# so this layer — the expensive one — survives every source edit.
COPY pyproject.toml README.md ./
RUN mkdir -p src/air_client && touch src/air_client/__init__.py
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && pip install .

COPY src ./src
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-deps --force-reinstall .


# ── Runtime ───────────────────────────────────────────────────────────────────
FROM ${PYTHON_IMAGE} AS runtime

ARG VENV

LABEL org.opencontainers.image.title="air-client" \
      org.opencontainers.image.description="Streamlit console for exercising the AIR services" \
      org.opencontainers.image.source="https://github.com/bookbee/air-client" \
      org.opencontainers.image.licenses="Proprietary"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="${VENV}/bin:${PATH}"

RUN groupadd --system --gid 1001 air && \
    useradd --system --uid 1001 --gid air --home-dir /app --shell /usr/sbin/nologin air && \
    install -d -o air -g air /app

COPY --from=builder ${VENV} ${VENV}

WORKDIR /app
# The palette and both theme variants live here; without it the console falls
# back to Streamlit's stock light theme and the dark mode looks half-applied.
COPY --chown=air:air .streamlit ./.streamlit

USER air

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=2).read()"]

# 0.0.0.0 so the port publish reaches it; the console is bound to loopback on
# the host side in docker-compose.yml, since it is a local tool either way.
ENTRYPOINT ["streamlit", "run", "/opt/venv/lib/python3.12/site-packages/air_client/app.py", \
            "--server.address", "0.0.0.0", "--server.port", "8501", \
            "--server.headless", "true"]
