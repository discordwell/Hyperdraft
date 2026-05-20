# Claude credential setup and refresh

The container hosts a `claude` CLI used by three feature paths:

- **Ultra-agent subprocess** (Phase 2) — spawned per ultra match by `scripts/launch_ultra_agent.sh`.
- **Auto-repair** (Phase 3) — `src/server/auto_repair.py` invokes `claude -p` when the engine throws.
- **On-demand training** (Phase 4) — `/api/admin/train` runs `claude -p '/ultra-loop …'`.

All three read auth from `~/.claude/.credentials.json` inside the container. That file lives on the `hyperdraft-claude-home` named volume so it persists across image rebuilds; only the initial setup (and any token refresh) requires action.

## One-time setup

1. On your local Mac:

   ```bash
   claude setup-token
   ```

   This walks through the browser flow and writes a long-lived token to `~/.claude/.credentials.json`.

2. Get the running container's name:

   ```bash
   ssh ovh2 'docker ps --filter "name=hyperdraft" --format "{{.Names}}"'
   # → hyperdraft-hyperdraft-1
   ```

3. Copy the credentials file into the container's claude-home volume:

   ```bash
   scp ~/.claude/.credentials.json ovh2:/tmp/claude-creds.json
   ssh ovh2 'docker cp /tmp/claude-creds.json hyperdraft-hyperdraft-1:/root/.claude/.credentials.json && rm /tmp/claude-creds.json'
   ```

4. Verify the container can authenticate:

   ```bash
   ssh ovh2 'docker exec hyperdraft-hyperdraft-1 claude /status'
   ```

   Expect a status line that doesn't include `Not logged in`.

The volume `hyperdraft-claude-home` survives `docker compose down`, image rebuilds, and (with `restart: unless-stopped`) host reboots. Re-run steps 1-4 only when the token expires or you rotate it.

## Token expiry symptoms

If the token expires:

- Ultra-agent subprocess logs in `storage/ultra-agent/<MATCH_ID>__<AI_ID>.log` will end with an auth error and the AI seat sits idle.
- Auto-repair sessions in `storage/repair/<session>/` will write `STATUS: ERR auth` and bail without producing a patch.

Refresh procedure:

1. On your local Mac: `claude setup-token` (overwrites `~/.claude/.credentials.json`).
2. Re-run steps 2-4 above.

No container restart is required — the CLI re-reads the credentials file per invocation.

## Why not bake credentials into the image?

The credentials are a long-lived bearer token. Baking them into the image would:

- Ship them in `docker save` exports and any image-layer caches.
- Couple the image to a single workspace, breaking reuse.
- Force a rebuild on every token refresh.

The named-volume approach keeps the image generic and decouples auth refresh from deploys.
