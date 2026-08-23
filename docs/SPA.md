# WebTwin SPA Mode

SPA mode lets WebTwin investigate client-routed apps without treating every in-app link as a hard `page.goto`.

## Enable

| Mechanism | Example |
|-----------|---------|
| Env | `WEBTWIN_SPA_MODE=1` |
| Investigation flag | `spa_mode: true` on create |
| Environment / scope | `environment` or `feature_scope` / goal scope containing `spa` |

When `spa_mode=false` (default), L1–L9 multipage HTML behavior is unchanged: same-origin `<a href>` → `NAVIGATE` + `goto`.

## Contracts

### `RouteSnapshot`

Persisted on each observation (`observations.route` JSONB):

- `url`, `path`, `search`, `hash`, `title`

### `ElementIdentity`

On interactive elements:

- `stable_key` priority: `data-testid` / `data-qa` / `data-cy` → accessible name → `name` / label → CSS path
- `selector_candidates[]` for verification retries
- `in_shadow_dom` when collected from an open shadow root

### Action kinds

| Type | Behavior |
|------|----------|
| `NAVIGATE` | Hard `page.goto` (first load, cross-origin, explicit reload) |
| `ROUTE` | Soft click / hash change (same-origin SPA links in spa mode) |
| `SCROLL` | Wheel + scroll containers (`[data-scroll-container]`) |

## Settle gate

`browser/observer/settle.py` replaces blind `wait_for_timeout(150)`:

1. `domcontentloaded` (bounded)
2. `networkidle` (best-effort, not infinite)
3. Optional URL / hash match for soft nav
4. MutationObserver quiet period (`WEBTWIN_SETTLE_STABLE_MS`, default 200)

Budget: `WEBTWIN_SETTLE_TIMEOUT_MS` (default 8000). Exceeding budget fails the investigation with an auditable settle reason on the timeline (`settle` events).

## Safety & secrets

- Soft-nav still respects SAFE / CAUTION / DESTRUCTIVE
- Network headers and allowlisted `localStorage` keys are redacted (`WEBTWIN_STORAGE_ALLOWLIST`)
- JWT / token keys never stored in plaintext evidence

## Benchmark

```bash
WEBTWIN_API_URL=http://127.0.0.1:8060 pnpm nx run evaluation:benchmark-spa
```

S1–S7 live under `tests/evaluation/synthetic_spa/`. Gate: `soft_nav_success_rate ≥ 0.95`; L1–L9 remains `evaluation:benchmark` with spa mode off.
