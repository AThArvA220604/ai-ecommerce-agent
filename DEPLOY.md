# Deployment Guide

This project can be deployed three ways, listed easiest to most production-like.

**Honest upfront:** the code has not been run end-to-end. The architecture
is sound, syntax checks pass, and the shapes match, but a real first run
will surface something. If you hit an error, paste the traceback — it's
almost certainly a one-line fix.

---

## Prerequisites

| Tool        | Version | Required for                      |
|-------------|---------|-----------------------------------|
| Python      | 3.11+   | Local backend (Option A)          |
| Node.js     | 20+     | Local frontend (Option A)         |
| Docker      | 24+     | Options B and C                   |
| OpenAI key  | any     | LLM mode (system runs without it) |

---

## Option A — Local Dev (fastest, for development)

Two terminal windows.

### Terminal 1: backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Copy env template; system runs in rule-mode without edits
cp ../.env.example .env
# To enable LLM mode: edit .env, set USE_LLM=true and OPENAI_API_KEY=sk-...

uvicorn main:app --reload --port 8000
```

Verify:
```bash
curl http://localhost:8000/api/health
# Expected: {"status":"healthy", "service":"ai-ecommerce-agent", "ai":{...}}
```

### Terminal 2: frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The header badge should say **Rule Engine** if
no OpenAI key is set, or **AI Engine** with the model name if it is.

### Troubleshooting

- **ImportError on startup**: Python version too old. Needs 3.11+ for
  union types like `int | None`.
- **"No module named 'openai'"**: run `pip install -r requirements.txt`
  from inside the venv.
- **Frontend shows "Offline Demo"**: backend isn't running on port 8000.
  Check terminal 1. Click the refresh icon next to the badge to retry.
- **Backend starts but dashboard is empty**: DB didn't seed. Check for
  `backend/ecommerce.db` file. Delete it and restart to re-seed.

---

## Option B — Docker Compose (recommended for reviewers)

Single command after setting up `.env`.

```bash
# From repo root
cp .env.example .env
# Edit .env if you want LLM mode; otherwise leave as-is

docker compose up --build
```

Frontend at http://localhost:5173, backend at http://localhost:8000.

The compose file:
- Builds both images from their respective Dockerfiles
- Uses a named volume `db-data` so the SQLite file survives restarts
- Health-checks the backend via Python's stdlib (the `python:3.12-slim`
  base image doesn't ship `curl`)
- Starts the frontend only after the backend passes its health check

### Stopping

```bash
docker compose down             # stop containers, keep data volume
docker compose down -v          # stop AND wipe the database
```

### Switching between rule/LLM mode

Edit `.env`:
```bash
USE_LLM=true
OPENAI_API_KEY=sk-your-key-here
```

Then:
```bash
docker compose up -d            # picks up new env vars without rebuild
```

No container rebuild needed — the env is read fresh at process start
via `pydantic-settings`.

### Troubleshooting

- **Frontend container exits immediately**: the multi-stage nginx build
  needs the Vite build to succeed. Check `docker compose logs frontend`.
  Most common cause: a syntax error in `App.jsx` that `npm run build`
  catches but `npm run dev` tolerates.
- **Backend keeps restarting**: `docker compose logs backend`. If it's
  a migration error, `docker compose down -v` wipes the volume and
  re-seeds fresh.
- **"Bind for 0.0.0.0:8000 failed"**: something else is using that port.
  Either kill it, or edit `docker-compose.yml` to map `8001:8000`.

---

## Option C — Cloud Deployment

The system is two containers + one volume. Any container platform runs it.
I'll describe three realistic paths. **All three skip the "production-
grade" items deliberately not built yet** (real Postgres, secrets manager,
TLS, rate limiting). Those are called out at the end.

### C1 — Single VM (DigitalOcean droplet, EC2, Hetzner, etc.)

The honest, boring, cheap path. Works for a portfolio project or a small
internal tool.

```bash
# On a fresh Ubuntu 22.04 VM with Docker installed
git clone <your-repo>
cd ai-ecommerce-agent
cp .env.example .env
nano .env                       # set USE_LLM, OPENAI_API_KEY
docker compose up -d --build
```

Then point a domain at the VM and put Caddy in front for TLS:

```caddyfile
# /etc/caddy/Caddyfile
your-domain.com {
    reverse_proxy /api/* localhost:8000
    reverse_proxy /* localhost:5173
}
```

Monthly cost: ~$6–12 on the smallest droplet. Sufficient for the load
profile this app is designed for (single-digit concurrent users).

### C2 — Fly.io (closest-to-Heroku experience)

Fly natively runs Docker images with persistent volumes, which maps
cleanly to this app's shape.

```bash
fly launch --no-deploy          # generates fly.toml, pick region
fly volume create db_data --size 1
fly secrets set OPENAI_API_KEY=sk-... USE_LLM=true
fly deploy
```

You'll need to adapt `fly.toml` to mount the volume at `/data` and
expose only the backend (the frontend can be deployed separately as
static assets to Cloudflare Pages or Netlify — cheaper and faster than
running an nginx container).

**Caveat:** Fly deploys each service separately. Split the compose
setup into two apps and configure the frontend's `VITE_API_URL` to
point at the backend's public URL at build time.

### C3 — Render / Railway

Both platforms have native support for docker-compose repos. The
cold-start latency on free tiers (~30s) will trigger the frontend's
"Backend offline" banner until the container wakes. Not ideal for
demos — pay for a "keep alive" tier or deploy to option C1.

### What's NOT production-ready even after deployment

Be honest about this in your README if it's a portfolio project:

1. **SQLite in a single volume.** Works for one worker, one container.
   Real production needs Postgres, and the code is structured to swap
   to it (asyncpg, SQLAlchemy), but that wiring isn't done.

2. **No authentication.** Anyone with the URL can process orders.
   Add an `API_KEY` env var checked by a FastAPI dependency before
   putting this on a public URL.

3. **No rate limiting.** A user with an API key could burn your
   OpenAI quota. `slowapi` is the fix; it's not installed.

4. **Circuit breaker is per-process.** With multiple workers, each has
   its own failure count. For a single-container deploy, fine. For a
   replicated deploy, move the breaker state to Redis.

5. **No backups.** The `db-data` volume is single-instance. Add a
   cron job that dumps the SQLite file to S3 nightly, or move to
   managed Postgres.

6. **No observability.** Logs go to stdout, which is fine if your
   platform captures them. No metrics, no tracing, no alerts on the
   error rate. Acceptable for a demo; mandatory for production.

If you're deploying this for a job application rather than actual
production use, the single VM path is enough. If you're deploying for
real users, budget two days to add items 1–5 above before pointing
real traffic at it.

---

## Verifying the Deployment

Whichever path you chose, run this checklist:

```bash
# 1. Health endpoint returns 200
curl -sf https://your-url/api/health | head

# 2. Dashboard loads (either path)
curl -sI https://your-url/ | head -1
# Expected: HTTP/1.1 200 OK or HTTP/2 200

# 3. An order can be processed (manually from the dashboard)
#    Then verify it persisted:
curl -s https://your-url/api/orders | head

# 4. The engine badge in the header matches your .env
#    Rule Engine if USE_LLM=false or no API key
#    AI Engine + model name if USE_LLM=true and key is valid
```

If any of those fail, the problem is almost certainly:
- An env var not being read by the container (check `docker compose config`)
- A port not being exposed by your platform
- A volume not mounted at `/data`

Open a shell into the running container and check `env | grep -E 'USE_LLM|OPENAI'`
and `ls -la /data/` to narrow it down.
