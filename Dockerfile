# syntax=docker/dockerfile:1.7
#
# Hyperdraft production image.
#
# Stage 1 builds the React frontend (vite -> /build/frontend/dist).
# Stage 2 is the python runtime that serves both the API and the built SPA,
# plus the `claude` CLI used by the in-container ultra-agent / auto-repair /
# training features (Phase 2-4 of the Hosted Claude Code rollout).
#
# Card art and SCP art are intentionally NOT baked into the image; they are
# bind-mounted at runtime from the host (see docker-compose.prod.yml).

# === Stage 1: build the React frontend ===
FROM node:20-slim AS frontend-builder
WORKDIR /build/frontend

# Copy package files first for better layer caching across source-only edits.
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


# === Stage 2: python runtime ===
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# System deps:
#   - curl, ca-certificates, gnupg, git: utilities, plus git for the auto-repair baseline snapshot
#   - nodejs (Node 20 via NodeSource): host for the npm-installed claude CLI
#   - @anthropic-ai/claude-code: the CLI invoked by scripts/launch_ultra_agent.sh,
#     auto_repair.py (Phase 3), and the /api/admin/train endpoint (Phase 4)
# Pinned for reproducible builds AND to defeat Docker layer-caching: editing
# this version (or passing --build-arg CLAUDE_CODE_VERSION=...) busts the cache
# so `npm install` actually re-runs and the in-container claude CLI updates.
# An unpinned install stays frozen at whatever version was first cached.
# Must be >= 2.1.154 for Opus 4.8 support.
ARG CLAUDE_CODE_VERSION=2.1.154
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        git \
        gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g @anthropic-ai/claude-code@${CLAUDE_CODE_VERSION} \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps — copy requirements first for layer caching across source-only edits.
COPY requirements-server.txt ./
RUN pip install --no-cache-dir -r requirements-server.txt

# Copy source. .dockerignore filters out card art, scp-art, .git, .claude,
# node_modules, art-runs, data/raw, etc. — see that file for the full list.
COPY . .

# Replace any host-built frontend/dist with the stage-1 fresh build.
COPY --from=frontend-builder /build/frontend/dist ./frontend/dist

# Storage subdirs used by the in-container claude features (Phase 2-4).
RUN mkdir -p storage/ultra-agent storage/repair storage/training storage/logs

# Baseline git snapshot. Phase 3's auto_repair diffs Claude's in-container
# edits against this commit to extract a patch for human review. .dockerignore
# already excluded the host's .git, so this is a clean snapshot of the image.
RUN git init -q \
    && git config user.email "auto-repair@hyperdraft.local" \
    && git config user.name "auto-repair baseline" \
    && git add -A \
    && git commit -q -m "image baseline"

EXPOSE 8030

# Shell form so Phase 3 can prepend a patch-apply step. ``exec`` lets SIGTERM
# reach uvicorn instead of being trapped by the shell.
CMD ["sh", "-c", "exec uvicorn src.server.main:socket_app --host 0.0.0.0 --port 8030"]
