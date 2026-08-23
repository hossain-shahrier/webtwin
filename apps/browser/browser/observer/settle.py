"""Async settle gate for SPA / multipage — replaces blind sleep."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError


@dataclass
class SettleResult:
    ok: bool
    reason: str
    elapsed_ms: float
    network_idle: bool = False
    dom_stable: bool = False
    url_matched: bool = False


def settle_after_action(
    page: Page,
    *,
    expect_url_contains: str | None = None,
    timeout_ms: int | None = None,
    stable_ms: int | None = None,
) -> SettleResult:
    """
    Bounded settle: networkidle (best-effort) + optional URL + DOM mutation quiet period.
    Never hangs forever — fail closed with reason.
    """
    started = time.monotonic()
    budget = timeout_ms if timeout_ms is not None else int(os.environ.get("WEBTWIN_SETTLE_TIMEOUT_MS", "8000"))
    quiet = stable_ms if stable_ms is not None else int(os.environ.get("WEBTWIN_SETTLE_STABLE_MS", "200"))
    network_idle = False
    url_matched = expect_url_contains is None
    dom_stable = False

    try:
        page.wait_for_load_state("domcontentloaded", timeout=min(budget, 5000))
    except PlaywrightTimeoutError:
        pass

    remaining = max(100, budget - int((time.monotonic() - started) * 1000))
    try:
        page.wait_for_load_state("networkidle", timeout=remaining)
        network_idle = True
    except PlaywrightTimeoutError:
        network_idle = False

    if expect_url_contains:
        remaining = max(100, budget - int((time.monotonic() - started) * 1000))
        try:
            page.wait_for_url(lambda url: expect_url_contains in url, timeout=remaining)
            url_matched = True
        except (PlaywrightTimeoutError, Exception):
            url_matched = expect_url_contains in (page.url or "")

    remaining = max(50, budget - int((time.monotonic() - started) * 1000))
    try:
        page.evaluate(
            """(quietMs) => new Promise((resolve) => {
                let timer = setTimeout(() => resolve(true), quietMs);
                const observer = new MutationObserver(() => {
                    clearTimeout(timer);
                    timer = setTimeout(() => {
                        observer.disconnect();
                        resolve(true);
                    }, quietMs);
                });
                observer.observe(document.documentElement, {
                    childList: true, subtree: true, attributes: true, characterData: true
                });
            })""",
            quiet,
        )
        dom_stable = True
    except Exception:
        page.wait_for_timeout(min(quiet, remaining))
        dom_stable = True

    elapsed_ms = (time.monotonic() - started) * 1000
    if elapsed_ms > budget + 500:
        return SettleResult(
            ok=False,
            reason=f"settle budget exceeded ({elapsed_ms:.0f}ms > {budget}ms)",
            elapsed_ms=elapsed_ms,
            network_idle=network_idle,
            dom_stable=dom_stable,
            url_matched=url_matched,
        )
    if expect_url_contains and not url_matched:
        return SettleResult(
            ok=False,
            reason=f"url did not contain {expect_url_contains!r} (at {page.url})",
            elapsed_ms=elapsed_ms,
            network_idle=network_idle,
            dom_stable=dom_stable,
            url_matched=False,
        )
    return SettleResult(
        ok=True,
        reason="settled",
        elapsed_ms=elapsed_ms,
        network_idle=network_idle,
        dom_stable=dom_stable,
        url_matched=url_matched,
    )
