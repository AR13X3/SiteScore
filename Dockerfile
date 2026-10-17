# SiteScore in one container: the FastAPI app serving the built frontend, on the committed
# demo pack (real data, no downloads). This is what the live demo runs on Hugging Face
# Spaces (see .github/workflows/deploy-demo.yml), and it runs anywhere else too:
#
#   docker build -t sitescore . && docker run -p 7860:7860 sitescore
#
# No model key is set, so the AI analyst replays its recorded runs. Pass
# -e OPENROUTER_API_KEY=... to run it live instead.

# --- the frontend --------------------------------------------------------------------
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- the app -------------------------------------------------------------------------
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    SITESCORE_CACHE_DIR=/app/.local \
    SITESCORE_WARM_EVIDENCE=1 \
    PORT=7860

WORKDIR /app
# Dependencies first (from pyproject.toml), so code changes don't reinstall them.
COPY pyproject.toml ./
RUN python -c "import tomllib; open('/tmp/requirements.txt', 'w').write('\n'.join(tomllib.load(open('pyproject.toml', 'rb'))['project']['dependencies']))" \
    && pip install -r /tmp/requirements.txt

# Hugging Face runs Spaces as uid 1000; the app writes its data store under /app/data.
RUN useradd --create-home --uid 1000 app
COPY --chown=app . .
COPY --from=web --chown=app /web/dist ./frontend/dist
USER app

EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s CMD python -c "import urllib.request, os; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/api/health')"
CMD ["sh", "-c", "exec python -m uvicorn sitescore.api.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips '*'"]
