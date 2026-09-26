# Multi-stage build: build the React UI, then run the FastAPI server that
# serves both the API and the built static UI.

# ---- Stage 1: build the web UI ----
FROM node:20-slim AS web-build
WORKDIR /web
COPY web/package*.json ./
RUN npm install
COPY web/ ./
RUN npm run build

# ---- Stage 2: python runtime ----
FROM python:3.12-slim AS runtime
WORKDIR /app

# System deps kept minimal; git enables the git_* tools.
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# Install the Python package.
COPY pyproject.toml ./
COPY agentos ./agentos
COPY server ./server
RUN python -m pip install --no-cache-dir -e .

# Bring in the built web UI so the server can serve it at "/".
COPY --from=web-build /web/dist ./web/dist

EXPOSE 8000

# Configure at runtime via env (FREELLM_BASE_URL, FREELLM_API_KEY, AGENTOS_MODEL,
# AGENTOS_AUTH_TOKEN, AGENTOS_ALLOWED_ORIGINS, ...).
CMD ["python", "-m", "uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8000"]
