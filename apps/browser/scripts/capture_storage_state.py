#!/usr/bin/env python3
"""Headed HITL capture of Playwright storage_state for authenticated portals.

Usage:
  uv run --directory apps/browser python scripts/capture_storage_state.py \\
    --url 'https://didattica.polito.it/pls/portal30/sviluppo.pkg_apply.app?t=0' \\
    --out ~/.webtwin/apply_polito_storage.json

Then investigate with:
  WEBTWIN_STORAGE_STATE=~/.webtwin/apply_polito_storage.json \\
  WEBTWIN_TARGET_URL='https://didattica.polito.it/pls/portal30/sviluppo.pkg_apply.app?t=0' \\
  WEBTWIN_HEADLESS=true pnpm nx run browser:investigate

Never commit the storage JSON (cookies / session tokens).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright

from browser.exploration.navigate import goto_resilient
from browser.session.consent import dismiss_consent_banners


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture Playwright storage_state after human login")
    parser.add_argument("--url", required=True, help="Portal URL to open")
    parser.add_argument(
        "--out",
        default=str(Path.home() / ".webtwin" / "storage_state.json"),
        help="Output storage_state JSON path",
    )
    args = parser.parse_args()
    out = Path(args.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        goto_resilient(page, args.url)
        dismiss_consent_banners(page)
        print("\n[WebTwin] Complete login in the opened browser window (SPID or username/password).")
        print("[WebTwin] When the authenticated Apply@polito page is visible, return here and press Enter.\n")
        input("[WebTwin] Press Enter to save storage_state… ")
        context.storage_state(path=str(out))
        print(f"[WebTwin] Saved storage_state → {out}")
        print("[WebTwin] Re-run investigate with WEBTWIN_STORAGE_STATE pointing at this file.")
        context.close()
        browser.close()


if __name__ == "__main__":
    main()
