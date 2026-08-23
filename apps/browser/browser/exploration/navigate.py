"""Bounded navigation helpers for live sites (analytics often block full load)."""

from __future__ import annotations

import os

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError


def navigation_timeout_ms() -> int:
    return int(os.environ.get("WEBTWIN_NAV_TIMEOUT_MS", "45000"))


def goto_resilient(page: Page, url: str) -> None:
    """
    Navigate with domcontentloaded (not full load) — real sites rarely reach networkidle/load.
    Falls back once with a longer timeout if the first attempt times out.
    """
    timeout = navigation_timeout_ms()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        return
    except PlaywrightTimeoutError:
        page.goto(url, wait_until="commit", timeout=timeout)
