# hyperdraft-lfs — giftless on Fly.io, backed by Cloudflare R2

A tiny Git LFS server. Stores objects in Cloudflare R2 (free tier covers our usage); runs as a single Fly.io machine (free tier). Anonymous reads (so `git clone` of the public Hyperdraft repo "just works" for everyone); JWT-gated writes (only you can push new LFS objects).

## Architecture

```
git-lfs client
    │ POST /objects/batch
    ▼
giftless (this app, on Fly.io)
    │ S3 SignURL
    ▼
Cloudflare R2 bucket   ◀──── git-lfs uploads/downloads bytes directly here
```

Giftless never sees the PNG bytes — it just signs URLs. So the server can stay tiny indefinitely.

## One-time setup

### 1. Cloudflare R2

In the dashboard:

1. Sidebar → R2 → "Enable" (requires CC on file even for free tier)
2. Create bucket: `hyperdraft-lfs` (location hint: WNAM if you're west coast)
3. "Manage R2 API Tokens" → Create API token
   - Permission: Object Read & Write
   - Specify bucket: `hyperdraft-lfs`
   - TTL: forever (or rotate later)
4. Note the **Account ID** (top of R2 page), the **Access Key ID**, and the **Secret Access Key**

### 2. Fly.io

```bash
# Already installed flyctl. Create account and log in:
fly auth signup       # opens browser
# or: fly auth login if you already have an account
```

### 3. Local config

```bash
cd infra/giftless
cp .env.example .env
# Edit .env — fill in R2 values from step 1.
# Generate the JWT secret:
openssl rand -base64 48 | tr -d '\n' | pbcopy   # macOS — secret now on clipboard
# Paste into .env as GIFTLESS_JWT_SECRET.
```

### 4. Deploy

```bash
fly apps create hyperdraft-lfs        # one-time, creates the Fly app
./scripts/set-secrets.sh              # push R2 + JWT secret to Fly
./scripts/deploy.sh                   # build image, ship to Fly
```

After deploy, sanity-check:

```bash
curl -i https://hyperdraft-lfs.fly.dev/
# expect HTTP 200
```

### 5. Issue yourself a write token

```bash
./scripts/issue-token.sh --install discordwell/Hyperdraft
# installs a 2-hour JWT into your git credential helper.
# git push will now authenticate to LFS automatically.
```

Re-run `issue-token.sh --install` whenever your token expires (every 2h). Or extend `max_lifetime` in `giftless.yaml` if you'd rather have a long-lived token.

## How the Hyperdraft repo uses this

The Hyperdraft repo has a `.lfsconfig`:

```
[lfs]
  url = https://hyperdraft-lfs.fly.dev/discordwell/Hyperdraft.git/info/lfs
```

And tracks PNG paths via `.gitattributes`:

```
assets/card_art/** filter=lfs diff=lfs merge=lfs -text
frontend/public/scp-art/** filter=lfs diff=lfs merge=lfs -text
```

The migration that moved historical art into LFS is documented at `docs/safety/lfs_migration_runbook.md` (in the Hyperdraft repo).

## Operations

### Local smoke test before deploying

```bash
./scripts/local-test.sh
# runs giftless in Docker against your .env
# then in another terminal: curl -i http://localhost:8000/
```

### Check production logs

```bash
fly logs -a hyperdraft-lfs
```

### View Fly secrets (names only — values are encrypted)

```bash
fly secrets list -a hyperdraft-lfs
```

### Rotate the R2 access key

1. Cloudflare dashboard → R2 → Manage API Tokens → roll the key
2. Update `.env` locally with new values
3. `./scripts/set-secrets.sh` (this triggers a Fly redeploy of the machine)

### Rotate the JWT secret

```bash
openssl rand -base64 48 | tr -d '\n'
# update .env, then:
./scripts/set-secrets.sh
# invalidates all outstanding tokens — re-issue with issue-token.sh
```

### Bucket inspection (without going to dashboard)

```bash
rclone config            # one-time: add an "r2" remote with your creds
rclone ls r2:hyperdraft-lfs
rclone size r2:hyperdraft-lfs
```

## Costs (as of 2026)

| Resource | Tier we use | Headroom |
|---|---|---|
| Cloudflare R2 storage | Free up to 10GB | We use ~2.7GB |
| Cloudflare R2 Class A ops (writes) | Free up to 1M/mo | We do ~5K on initial migration, ~10/mo after |
| Cloudflare R2 Class B ops (reads) | Free up to 10M/mo | A clone = one Class B per file (~4400 PNGs) |
| Cloudflare R2 egress | Free | — |
| Fly.io VM (shared-cpu-1x, 256MB) | Free up to 3 small machines | We use 1 |

Total: **$0/month** unless we blow past the free tier. To estimate: each fresh clone reads ~4400 objects, so we'd need ~2,272 clones/month to exhaust the Class B free tier.

## Why giftless, why not X

- **Compared to GitHub LFS** ($5/mo): same UX, but we keep the money and own the auth.
- **Compared to `lfs-test-server`** (Go): giftless is Python, more configurable auth, actively maintained for production use.
- **Compared to running our own S3 backend**: R2 has zero egress fees. AWS S3 would cost ~$25/mo just for egress on a few hundred clones.
- **Compared to `git-annex`** / **DVC**: those require additional tooling on the client. LFS is built into git.

## Failure modes and what to do

| Symptom | Likely cause | Fix |
|---|---|---|
| `git clone` hangs on smudge | Fly machine cold-starting (5s) or down | Wait, or `fly status -a hyperdraft-lfs` |
| `LFS: 403 Forbidden` on push | JWT expired or missing | `./scripts/issue-token.sh --install ...` |
| `LFS: 500 Internal Server Error` | R2 creds bad, or bucket missing | `fly logs -a hyperdraft-lfs` |
| Cloners get tiny pointer files instead of PNGs | Their local `git-lfs` isn't installed | They need `git lfs install` once |
| `fly deploy` fails with "app not found" | `fly apps create hyperdraft-lfs` not run yet | Run it |
