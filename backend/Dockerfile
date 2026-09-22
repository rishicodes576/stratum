FROM python:3.13-slim AS build
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
WORKDIR /build
COPY requirements.lock ./
RUN python -m venv /opt/venv && /opt/venv/bin/pip install --require-hashes -r requirements.lock

FROM python:3.13-slim AS runtime
ENV PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --create-home app
WORKDIR /app
COPY --from=build /opt/venv /opt/venv
COPY --chown=app:app app ./app
COPY --chown=app:app migrations ./migrations
COPY --chown=app:app alembic.ini ./
USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/live', timeout=3)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
