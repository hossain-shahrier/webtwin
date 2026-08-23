"""Fill dashboard-submitted auth form values into the live Playwright page."""

from __future__ import annotations

from playwright.sync_api import Page
from playwright.sync_api import Error as PlaywrightError

from browser.observer.settle import settle_after_action


def _try_fill(page: Page, selectors: list[str], value: str) -> bool:
    for selector in selectors:
        if not selector:
            continue
        try:
            locator = page.locator(selector)
            if locator.count() == 0:
                continue
            target = locator.first
            if not target.is_visible():
                continue
            tag = target.evaluate("(el) => el.tagName.toLowerCase()")
            input_type = (target.get_attribute("type") or "").lower()
            if tag == "select":
                try:
                    target.select_option(value)
                except PlaywrightError:
                    target.select_option(label=value)
            elif input_type in {"checkbox", "radio"}:
                if value.lower() in {"1", "true", "yes", "on"}:
                    target.check()
                else:
                    target.uncheck()
            else:
                target.fill(value, force=True)
            return True
        except PlaywrightError:
            continue
    return False


def _try_click_submit(page: Page, submit_label: str | None) -> bool:
    candidates = [
        'button[type="submit"]',
        'input[type="submit"]',
        'button:has-text("Sign in")',
        'button:has-text("Log in")',
        'button:has-text("Login")',
        'button:has-text("Register")',
        'button:has-text("Create account")',
        'button:has-text("Continue")',
    ]
    if submit_label:
        candidates.insert(0, f'button:has-text("{submit_label}")')
    for selector in candidates:
        try:
            locator = page.locator(selector)
            if locator.count() == 0:
                continue
            target = locator.first
            if target.is_visible():
                target.click(timeout=5000)
                settle_after_action(page)
                return True
        except PlaywrightError:
            continue
    return False


def apply_auth_form_fill(page: Page, form: dict | None, values: dict[str, str]) -> tuple[bool, str]:
    """Fill observed auth fields then click submit. Returns (ok, details)."""
    if not values:
        return False, "no values provided"
    fields = list((form or {}).get("fields") or [])
    filled = 0
    for field in fields:
        key = field.get("key")
        if not key or key not in values:
            continue
        selectors = [field.get("selector") or ""] + list(field.get("selector_candidates") or [])
        name = field.get("name")
        if name:
            selectors.extend(
                [
                    f'input[name="{name}"]',
                    f'select[name="{name}"]',
                    f'textarea[name="{name}"]',
                ]
            )
        if _try_fill(page, selectors, str(values[key])):
            filled += 1

    if filled == 0:
        return False, "could not fill any fields (selectors missing or not visible)"

    settle_after_action(page)
    clicked = _try_click_submit(page, (form or {}).get("submit_label"))
    details = f"filled {filled} field(s)" + ("; submitted" if clicked else "; submit button not found")
    return True, details
