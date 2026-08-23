from playwright.sync_api import Page
from webtwin_core.models import ElementSnapshot, FormSnapshot, Observation

from browser.observer.screenshot import capture_screenshot


def _accessibility_tree(page: Page) -> dict:
    try:
        snapshot = page.accessibility.snapshot()
        if not snapshot:
            return {"interactive_count": 0}
        nodes = []

        def walk(node: dict, depth: int = 0) -> None:
            if depth > 4 or len(nodes) > 80:
                return
            nodes.append(
                {
                    "role": node.get("role"),
                    "name": node.get("name"),
                    "value": node.get("value"),
                }
            )
            for child in node.get("children") or []:
                walk(child, depth + 1)

        walk(snapshot)
        return {"interactive_count": len(nodes), "nodes": nodes}
    except Exception:
        return {"interactive_count": 0}


def capture_observation(page: Page, investigation_id, *, with_screenshot: bool = True) -> Observation:
    elements: list[ElementSnapshot] = []
    interactive: list[str] = []
    visible: list[str] = []

    locator = page.locator(
        'input, select, textarea, button, a[href], [role="alert"], .error, [id*="error"], [id*="validation"]'
    )
    for element in locator.all():
        selector = element.evaluate(
            """(el) => {
                if (el.id) return `#${el.id}`;
                if (el.name) return `[name="${el.name}"]`;
                if (el.tagName.toLowerCase() === 'a' && el.getAttribute('href')) {
                  return `a[href="${el.getAttribute('href')}"]`;
                }
                return el.tagName.toLowerCase();
            }"""
        )
        tag = element.evaluate("(el) => el.tagName.toLowerCase()")
        name = element.get_attribute("name") or element.get_attribute("id")
        label = element.get_attribute("aria-label") or element.get_attribute("placeholder")
        href = element.get_attribute("href") if tag == "a" else None
        value = element.input_value() if tag in {"input", "select", "textarea"} else href
        is_visible = element.is_visible()
        is_enabled = element.is_enabled() if tag in {"input", "select", "textarea", "button", "a"} else True
        is_required = (
            element.evaluate("(el) => !!el.required") if tag in {"input", "select", "textarea"} else False
        )
        input_type = element.get_attribute("type") if tag == "input" else None
        text = element.inner_text().strip() if tag in {"button", "a", "div", "span", "p"} else None
        options: list[str] = []
        if tag == "select":
            options = element.evaluate(
                """(el) => Array.from(el.options).map((opt) => opt.value || opt.textContent.trim())"""
            )

        snapshot = ElementSnapshot(
            selector=selector,
            tag=tag,
            name=name,
            label=label,
            value=value,
            visible=is_visible,
            enabled=is_enabled,
            required=is_required,
            options=options,
            text=text,
            input_type=input_type,
        )
        elements.append(snapshot)
        if is_visible:
            visible.append(selector)
        if is_enabled and tag in {"input", "select", "textarea", "button", "a"}:
            interactive.append(selector)

    forms: list[FormSnapshot] = []
    for form in page.locator("form").all():
        form_selector = form.evaluate(
            """(el) => el.id ? `#${el.id}` : (el.name ? `form[name="${el.name}"]` : 'form')"""
        )
        form_name = form.get_attribute("name")
        field_snapshots = [
            element for element in elements if element.selector.startswith(form_selector)
        ]
        forms.append(FormSnapshot(selector=form_selector, name=form_name, fields=field_snapshots))

    screenshot_path = None
    if with_screenshot:
        try:
            screenshot_path = capture_screenshot(page, investigation_id)
        except Exception:
            screenshot_path = None

    accessibility = _accessibility_tree(page)
    accessibility["interactive_count"] = max(
        accessibility.get("interactive_count", 0), len(interactive)
    )

    return Observation(
        investigation_id=investigation_id,
        url=page.url,
        title=page.title(),
        elements=elements,
        forms=forms,
        visible_elements=visible,
        interactive_elements=interactive,
        accessibility=accessibility,
        screenshot_path=screenshot_path,
        html_length=len(page.content()),
    )
