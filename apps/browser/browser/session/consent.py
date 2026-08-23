"""Dismiss common cookie / consent overlays so exploration can click real UI."""

from __future__ import annotations

from playwright.sync_api import Page


_CONSENT_SELECTORS = (
    "#onetrust-accept-btn-handler",
    "#didomi-notice-agree-button",
    "button#accept-cookie",
    '[data-testid="cookie-accept"]',
    'button:has-text("Accept all")',
    'button:has-text("Accept All")',
    'button:has-text("Accept cookies")',
    'button:has-text("I agree")',
    'button:has-text("Agree")',
    'button:has-text("Accept")',
    'button:has-text("Accetta tutti")',
    'button:has-text("Accetta")',
)


def dismiss_consent_banners(page: Page, *, timeout_ms: int = 2500) -> bool:
    """Best-effort consent dismiss. Returns True if a control was clicked."""
    for selector in _CONSENT_SELECTORS:
        try:
            locator = page.locator(selector)
            if locator.count() == 0:
                continue
            target = locator.first
            if not target.is_visible(timeout=timeout_ms):
                continue
            target.click(timeout=timeout_ms)
            page.wait_for_timeout(300)
            return True
        except Exception:
            continue
    return False
