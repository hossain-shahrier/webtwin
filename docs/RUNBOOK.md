# WebTwin Runbook

## Environment contract

| Variable | Default | Purpose |
|----------|---------|---------|
| `DATABASE_URL` | `postgresql+psycopg://webtwin:webtwin@127.0.0.1:5432/webtwin` | Postgres |
| `WEBTWIN_STORE` | `memory` (tests) / `postgres` (dev) | Store backend |
| `WEBTWIN_API_URL` | `http://127.0.0.1:8060` | Browser / eval → API |
| `NEXT_PUBLIC_API_URL` | `http://127.0.0.1:8060` | Dashboard → API |
| `PORT` | `8060` | API listen port |
| `WEBTWIN_KG_ENABLED` | `false` | Neo4j sync |
| `NEO4J_URI` | `bolt://127.0.0.1:7687` | Knowledge graph |
| `WEBTWIN_LLM_PROVIDER` | unset / `heuristic` | AI planner (`openai`/`anthropic`/`heuristic`) |
| `WEBTWIN_LLM_API_KEY` | unset | Optional remote LLM key |
| `WEBTWIN_APP_VERSION` | `synthetic-1` | Version metadata on investigations |
| `WEBTWIN_ENVIRONMENT` | `eval` | Environment label |
| `WEBTWIN_ROLE_SCOPE` | unset | Role tag for multi-session knowledge |
| `WEBTWIN_SPA_MODE` | unset / `0` | Soft nav + SPA observation (`1` enables) |
| `WEBTWIN_SETTLE_TIMEOUT_MS` | `8000` | Async settle budget after actions |
| `WEBTWIN_SETTLE_STABLE_MS` | `200` | DOM quiet period for settle |
| `WEBTWIN_STORAGE_ALLOWLIST` | `theme,locale,...` | SPA localStorage keys to capture (redacted) |

## Local (recommended)

```bash
docker compose -f infrastructure/docker/docker-compose.yml up -d postgres
pnpm nx run api:migrate
pnpm nx run api:dev:postgres
NEXT_PUBLIC_API_URL=http://127.0.0.1:8060 pnpm nx serve web
WEBTWIN_API_URL=http://127.0.0.1:8060 pnpm nx run evaluation:benchmark
WEBTWIN_API_URL=http://127.0.0.1:8060 pnpm nx run evaluation:benchmark-spa
WEBTWIN_API_URL=http://127.0.0.1:8060 WEBTWIN_EXPLORATION_POLICIES=random,first_unexplored,information_gain,llm pnpm nx run evaluation:compare-policies
```

Browser stays on the host (Playwright):

```bash
WEBTWIN_API_URL=http://127.0.0.1:8060 pnpm nx run browser:investigate
# Or poll dashboard-created jobs:
WEBTWIN_API_URL=http://127.0.0.1:8060 pnpm nx run browser:worker
```

## Optional Knowledge Graph

```bash
docker compose -f infrastructure/docker/docker-compose.yml --profile kg up -d neo4j
uv sync --directory apps/api --group kg
WEBTWIN_KG_ENABLED=1 pnpm nx run api:sync-kg
```

Q&A (evidence-grounded): `POST /investigations/{id}/questions` with `{ "question": "Why does End Date appear?" }`.

## Optional remote LLM planner

```bash
export WEBTWIN_LLM_PROVIDER=openai   # or anthropic | heuristic
export WEBTWIN_LLM_API_KEY=...
# Ablation still includes llm policy via heuristic when no key is set
WEBTWIN_EXPLORATION_POLICIES=random,first_unexplored,information_gain,llm \
  pnpm nx run evaluation:compare-policies
```

## SPA mode

See [SPA.md](./SPA.md) and staging [SPA_PILOT.md](./SPA_PILOT.md). Default remains multipage HTML (`spa_mode=false`).

```bash
pnpm nx run webtwin-core:test
pnpm nx run api:test
pnpm nx run evaluation:explore
```
