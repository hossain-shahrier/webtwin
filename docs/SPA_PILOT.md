# SPA Staging Pilot Playbook

Enterprise proof beyond synthetic fixtures. Postgres remains system of record; LLM never upgrades `RuleStatus`.

## Preconditions

1. Staging SPA URL with stable `data-testid` (or `data-qa` / `data-cy`) on interactive controls
2. Soft routes are same-origin hash or History API links (no full document reload for in-app nav)
3. API on Postgres: `pnpm nx run api:dev:postgres`
4. Worker: `WEBTWIN_SPA_MODE=1 WEBTWIN_API_URL=http://127.0.0.1:8060 pnpm nx run browser:worker`

## Recommended create payload

```json
{
  "goal": "Discover business logic on staging SPA",
  "target_url": "https://staging.example.com/app",
  "spa_mode": true,
  "environment": "staging-spa",
  "feature_scope": "spa-pilot",
  "application_version": "staging"
}
```

## Settle & storage knobs

| Variable | Suggested staging value |
|----------|-------------------------|
| `WEBTWIN_SPA_MODE` | `1` |
| `WEBTWIN_SETTLE_TIMEOUT_MS` | `10000`–`15000` |
| `WEBTWIN_SETTLE_STABLE_MS` | `250`–`400` |
| `WEBTWIN_STORAGE_ALLOWLIST` | `theme,locale,ui.prefs` (never tokens) |
| `WEBTWIN_MAX_ACTIONS` | `30`–`50` |

## Auth

- Prefer Playwright `storage_state` cookies after HITL login (dashboard resume)
- SPA login walls: password field, URL auth hints, or SSO button (`data-testid="sso-login"`)
- Do not paste JWTs into evidence or logs

## Success metric

On a staging SPA after restart-safe Postgres persistence:

- ≥ **3 verified rules** with ≥1 evidence link each
- Network-backed validation rules include `NETWORK` evidence with `route_path` / timeline correlation when fetches occur
- Settle failures and soft-nav outcomes visible on investigation timeline / metrics (`settle_timeouts`, `soft_nav_success_rate`, `routes_seen`)

## Dashboard signals

Investigation detail shows:

- `spa_mode` flag
- Current route from latest observation (when present)
- Settle / soft-nav metrics from latest evaluation run

## Safety

- No blind `window.location` injection
- CAUTION / DESTRUCTIVE still blocked from automation
- Fail closed on settle budget exceeded
