# Hyperdraft top-level Makefile.
#
# Most day-to-day work happens via deploy.sh and pytest directly; targets
# here capture the rarely-used one-shots that benefit from being a named
# command rather than tribal knowledge.

SSH_HOST ?= ovh2
REMOTE_DIR ?= /opt/hyperdraft

.PHONY: help seed-art seed-art-local docker-build docker-up docker-down docker-logs

help:
	@echo "Hyperdraft targets:"
	@echo "  seed-art        Pull card art + scp-art onto the production host via Git LFS."
	@echo "                  Idempotent. Run after first deploy or when art changes."
	@echo "  seed-art-local  Same as seed-art but for the local checkout."
	@echo "  docker-build    Build the production image locally (no push)."
	@echo "  docker-up       Start the local docker-compose stack."
	@echo "  docker-down     Stop the local docker-compose stack."
	@echo "  docker-logs     Tail the local container logs."

# Hydrate art on the production host via Git LFS (cheap, R2-backed).
# The docker-compose bind mounts depend on these directories existing.
seed-art:
	@echo ">> Seeding art on ${SSH_HOST}:${REMOTE_DIR} via Git LFS..."
	ssh ${SSH_HOST} "cd ${REMOTE_DIR} && \
	  (command -v git-lfs >/dev/null || (echo 'install git-lfs first: sudo apt-get install -y git-lfs' && exit 1)) && \
	  git lfs install --local && \
	  git lfs pull --include='assets/card_art/**,frontend/public/scp-art/**'"
	@echo ">> Art seed complete."

seed-art-local:
	@echo ">> Seeding art locally via Git LFS..."
	git lfs install --local
	git lfs pull --include='assets/card_art/**,frontend/public/scp-art/**'
	@echo ">> Local art seed complete."

docker-build:
	docker compose -f docker-compose.prod.yml -p hyperdraft build

docker-up:
	docker compose -f docker-compose.prod.yml -p hyperdraft up -d --build

docker-down:
	docker compose -f docker-compose.prod.yml -p hyperdraft down

docker-logs:
	docker compose -f docker-compose.prod.yml -p hyperdraft logs --tail=200 -f hyperdraft
