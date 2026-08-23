# Apply@polito findings — WebTwin authenticated portal probe

**Target:** [Apply@polito](https://didattica.polito.it/pls/portal30/sviluppo.pkg_apply.app?t=0)  
**Probed:** 2026-08-23  
**Mode:** WebTwin browser observer + auth detector (no credentials used in automated probe)

---

## Executive answer

| Question | Answer |
|----------|--------|
| Can WebTwin open the URL? | **Yes** — redirects to the login wall |
| Can it fetch **logged-in** structure from your everyday Chrome/Safari login automatically? | **No** — Playwright does **not** read your browser’s cookie DB |
| Can it reuse a login **you complete for WebTwin**? | **Yes** — via Playwright `storage_state` (HITL capture) |
| Can it automate SPID / password login? | **No** (by design) — human-in-the-loop only |

Your local login in Chrome is in a different browser profile. WebTwin runs its own Chromium unless you explicitly export a Playwright session file after logging in inside that Chromium window.

---

## What the unauthenticated probe found

Automated open of the apply URL redirected to:

`https://didattica.polito.it/pls/portal30/sviluppo.pkg_apply.login?msg=82&t=0`

| Signal | Value |
|--------|--------|
| Title | Apply@polito |
| Framework hints | Not React / Next / Vue (classic portal / Oracle PL/SQL style) |
| Observed interactive elements | ~24 |
| Password field | **Visible** (`#p_id_af_password` / `p_af_password`) |
| Username | Placeholder **Username** |
| SPID | Present (“Entra con SPID”, IdP list, `spid_idp`, links to spid.gov.it) |
| Auth pause | `login_required` (correct) |
| Safe automatable actions (pre-login) | Very few (e.g. lost-password link, username input) — **login / Accedi / SPID are blocked from automation** |

Screenshot artifact (local): `~/.webtwin/artifacts/<id>/observation.png`

This matches the public login surface described on the Apply portal (username/password + SPID providers).

---

## How authenticated capture works in WebTwin

```text
1. Headed Chromium opens Apply@polito
2. You log in (SPID or username/password) in that window
3. WebTwin saves storage_state JSON (cookies + localStorage allowlist)
4. Later headless runs load that file via WEBTWIN_STORAGE_STATE
5. Observation → exploration → evidence continues behind the login wall
```

### Step A — Capture session (one-time / when session expires)

```bash
uv run --directory apps/browser python scripts/capture_storage_state.py \
  --url 'https://didattica.polito.it/pls/portal30/sviluppo.pkg_apply.app?t=0' \
  --out ~/.webtwin/apply_polito_storage.json
```

Log in in the window that opens, then press Enter in the terminal.

### Step B — Investigate with that session

```bash
WEBTWIN_STORAGE_STATE=~/.webtwin/apply_polito_storage.json \
WEBTWIN_TARGET_URL='https://didattica.polito.it/pls/portal30/sviluppo.pkg_apply.app?t=0' \
WEBTWIN_MAX_ACTIONS=15 \
WEBTWIN_API_URL=http://127.0.0.1:8060 \
WEBTWIN_HEADLESS=true \
pnpm nx run browser:investigate
```

Or create an investigation in the dashboard and run the worker after capturing state into that investigation’s session file under `~/.webtwin/sessions/<investigation-id>.json`.

**Never commit** `apply_polito_storage.json` — it holds session cookies.

---

## Gaps found and fixes applied

| Gap | Fix |
|-----|-----|
| SPID not treated as SSO | `SessionManager.sso_button_visible` now matches SPID / “Entra con SPID” |
| Auth URL hints miss `spid` / `apply.login` | Added to `AUTH_HINTS` |
| No way to inject an exported login | `WEBTWIN_STORAGE_STATE` bootstrap in `SessionStore` |
| No guided HITL export | `apps/browser/scripts/capture_storage_state.py` |

Still **out of scope** (enterprise policy):

- Reading Chrome/Safari cookie databases
- Automating SPID IdP flows or storing passwords
- Bypassing “Sessione scaduta” without a fresh HITL login

---

## Expected results after a successful session capture

Once `storage_state` is valid and the apply app loads authenticated:

1. **RouteSnapshot** for portal paths under `/pls/portal30/...`
2. **Element inventory** of forms/fields behind login (stable_key / name / selectors)
3. **Network evidence** for XHR/form posts (headers redacted)
4. **Screenshots** of observed pages
5. **Candidate rules** only if the UI exposes conditional logic (visibility/required/validation) — a static brochure-like dashboard may yield few or zero rules (same as public polito.it)

If the session is expired, expect redirect back to `pkg_apply.login` and `auth_required` pause again.

---

## Comparison: public polito.it vs Apply@polito

| | [polito.it/en](https://www.polito.it/en) | Apply@polito |
|--|------------------------------------------|--------------|
| Auth | Public | Login / SPID wall |
| WebTwin unauthenticated | Full multipage explore | Stops at login (correct) |
| Verified business rules | Unlikely (content site) | Possible only **after** HITL session + form-heavy flows |
| Session reuse | N/A | `WEBTWIN_STORAGE_STATE` required |

---

## Safety notes

- Soft-nav / exploration still respects SAFE / CAUTION / DESTRUCTIVE (Accedi / SPID not auto-clicked as business actions).
- Network and storage capture redact secrets; do not paste JWTs into tickets or evidence.
- Prefer short-lived investigation sessions; delete `~/.webtwin/apply_polito_storage.json` when done.
