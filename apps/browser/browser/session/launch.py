"""Chromium launch tuned for long-running crawls (including visible / non-headless workers)."""

from __future__ import annotations

import os

from playwright.sync_api import Browser, Playwright


def launch_chromium(playwright: Playwright, *, headless: bool) -> Browser:
    """
    Launch Chromium with background-tab throttling disabled.

    Minimized or occluded windows otherwise throttle timers and network, which
    causes Playwright click/evaluate timeouts during live crawls.
    """
    args = [
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
    ]
    if not headless:
        args.append("--disable-features=CalculateNativeWinOcclusion")
    channel = os.environ.get("WEBTWIN_CHROMIUM_CHANNEL")
    launch_kwargs: dict = {"headless": headless, "args": args}
    if channel:
        launch_kwargs["channel"] = channel
    return playwright.chromium.launch(**launch_kwargs)


def action_timeout_ms(*, headless: bool | None = None) -> int:
    if "WEBTWIN_ACTION_TIMEOUT_MS" in os.environ:
        return int(os.environ["WEBTWIN_ACTION_TIMEOUT_MS"])
    if headless is False:
        return 30000
    return 10000
