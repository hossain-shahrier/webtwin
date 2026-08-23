from playwright.sync_api import Page
from webtwin_core.models import ElementSnapshot, FormSnapshot, Observation


def capture_observation(page: Page, investigation_id) -> Observation:
    elements: list[ElementSnapshot] = []
    interactive: list[str] = []
    visible: list[str] = []

    for element in page.locator("input, select, textarea, button").all():
        selector = element.evaluate(
            """(el) => {
                if (el.id) return `#${el.id}`;
                if (el.name) return `[name="${el.name}"]`;
                return el.tagName.toLowerCase();
            }"""
        )
        tag = element.evaluate("(el) => el.tagName.toLowerCase()")
        name = element.get_attribute("name")
        label = element.get_attribute("aria-label") or element.get_attribute("placeholder")
        value = element.input_value() if tag in {"input", "select", "textarea"} else None
        is_visible = element.is_visible()
        is_enabled = element.is_enabled()
        is_required = element.evaluate("(el) => !!el.required")
        input_type = element.get_attribute("type") if tag == "input" else None
        text = element.inner_text().strip() if tag == "button" else None
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
        if is_enabled and tag in {"input", "select", "textarea", "button"}:
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

    return Observation(
        investigation_id=investigation_id,
        url=page.url,
        title=page.title(),
        elements=elements,
        forms=forms,
        visible_elements=visible,
        interactive_elements=interactive,
        accessibility={"interactive_count": len(interactive)},
        html_length=len(page.content()),
    )
