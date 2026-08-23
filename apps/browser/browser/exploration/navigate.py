"""Bounded navigation helpers for live sites (analytics often block full load)."""

from __future__ import annotations

import os
from urllib.parse import urlparse

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

_RECOVERABLE_NAV_MARKERS = (
    "ERR_ABORTED",
    "NS_BINDING_ABORTED",
    "interrupted by another navigation",
    "net::ERR_FAILED",  # some CDNs abort the prior request when redirecting
)


def navigation_timeout_ms() -> int:
    return int(os.environ.get("WEBTWIN_NAV_TIMEOUT_MS", "45000"))


def _navigation_recoverable(error: BaseException) -> bool:
    message = str(error)
    return any(marker in message for marker in _RECOVERABLE_NAV_MARKERS)


def _normalize_path(path: str) -> str:
    return (path or "/").rstrip("/") or "/"


def _navigation_reached_target(target: str, current: str) -> bool:
    """True when the browser landed on the target URL or a same-origin usable page."""
    if not current or current == "about:blank":
        return False
    target_parsed = urlparse(target)
    current_parsed = urlparse(current)
    if target_parsed.netloc and target_parsed.netloc != current_parsed.netloc:
        return False
    target_path = _normalize_path(target_parsed.path)
    current_path = _normalize_path(current_parsed.path)
    if target_path == current_path:
        return True
    if current_path.startswith(target_path) or target_path.startswith(current_path):
        return True
    # Auth walls / middleware redirects on the same host (e.g. /login, /signin)
    return bool(target_parsed.netloc == current_parsed.netloc)


def _page_has_content(page: Page) -> bool:
    try:
        return bool(
            page.evaluate(
                "() => Boolean(document.body && document.body.children.length > 0)"
            )
        )
    except Exception:
        return False


def _wait_for_usable_page(page: Page, *, timeout_ms: int) -> None:
    try:
        page.wait_for_load_state("domcontentloaded", timeout=min(10000, timeout_ms))
    except PlaywrightTimeoutError:
        pass


def goto_resilient(page: Page, url: str) -> None:
    """
    Navigate with domcontentloaded (not full load) — real sites rarely reach networkidle/load.

    Enterprise SPAs and auth middleware often abort the initial document request while
    redirecting or re-navigating; treat ERR_ABORTED as success when the page is usable.
    """
    if page.url and page.url.rstrip("/") == url.rstrip("/"):
        return

    timeout = navigation_timeout_ms()
    last_error: BaseException | None = None

    for wait_until in ("domcontentloaded", "commit"):
        try:
            page.goto(url, wait_until=wait_until, timeout=timeout)
            return
        except PlaywrightTimeoutError as error:
            last_error = error
            if wait_until == "commit":
                _wait_for_usable_page(page, timeout_ms=timeout)
                if _navigation_reached_target(url, page.url) or _page_has_content(page):
                    return
                raise
        except Exception as error:
            last_error = error
            if not _navigation_recoverable(error):
                raise
            _wait_for_usable_page(page, timeout_ms=timeout)
            if _navigation_reached_target(url, page.url) or _page_has_content(page):
                return
            if wait_until == "commit":
                break

    if last_error is not None:
        raise RuntimeError(
            f"Navigation to {url!r} failed (last url={page.url!r}): {last_error}"
        ) from last_error
