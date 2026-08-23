"""Deep SPA-aware DOM snapshot with stable identity and open shadow piercing."""

from __future__ import annotations

from urllib.parse import urlparse

from playwright.sync_api import Page
from webtwin_core.models import ElementSnapshot, FormSnapshot, Observation
from webtwin_core.models.spa import ElementIdentity, RouteSnapshot

from browser.observer.screenshot import capture_screenshot

_COLLECT_JS = """() => {
  const MAX = 200;
  const out = [];
  const seen = new Set();

  function testidOf(el) {
    return el.getAttribute('data-testid')
      || el.getAttribute('data-qa')
      || el.getAttribute('data-cy')
      || null;
  }

  function labelOf(el) {
    if (el.getAttribute('aria-label')) return el.getAttribute('aria-label');
    if (el.id) {
      const lab = document.querySelector(`label[for="${el.id}"]`);
      if (lab) return (lab.textContent || '').trim();
    }
    return el.getAttribute('placeholder') || null;
  }

  function cssPath(el) {
    if (el.id) return `#${CSS.escape(el.id)}`;
    const testid = testidOf(el);
    if (testid) return `[data-testid="${testid}"]`;
    if (el.getAttribute('name')) return `[name="${el.getAttribute('name')}"]`;
    const tag = el.tagName.toLowerCase();
    if (tag === 'a' && el.getAttribute('href')) return `a[href="${el.getAttribute('href')}"]`;
    return tag;
  }

  function push(el, inShadow) {
    if (out.length >= MAX) return;
    const tag = el.tagName.toLowerCase();
    const testid = testidOf(el);
    const interactive = ['input','select','textarea','button','a'].includes(tag)
      || el.getAttribute('role') === 'alert'
      || (el.className && String(el.className).includes('error'))
      || !!testid;
    if (!interactive && !(el.id && (String(el.id).includes('error') || String(el.id).includes('validation')))) {
      return;
    }
    const sel = cssPath(el);
    const key = (inShadow ? 'shadow:' : '') + sel + ':' + (el.getAttribute('name') || '') + ':' + tag;
    if (seen.has(key)) return;
    seen.add(key);
    let value = null;
    try {
      if (['input','select','textarea'].includes(tag)) value = el.value;
      else if (tag === 'a') value = el.getAttribute('href');
    } catch (e) {}
    let options = [];
    if (tag === 'select') {
      options = Array.from(el.options || []).map(o => o.value || (o.textContent || '').trim());
    }
    const name = el.getAttribute('name') || el.id || null;
    const role = el.getAttribute('role') || null;
    const label = labelOf(el);
    const candidates = [];
    if (testid) candidates.push(`[data-testid="${testid}"]`);
    if (el.id) candidates.push(`#${CSS.escape(el.id)}`);
    if (el.getAttribute('name')) candidates.push(`[name="${el.getAttribute('name')}"]`);
    if (role && label) candidates.push(`[role="${role}"][aria-label="${label}"]`);
    candidates.push(sel);
    const stable = testid || name || (label ? label.toLowerCase().replace(/\\s+/g, '_').slice(0, 48) : sel);
    out.push({
      selector: sel,
      tag,
      role,
      name,
      label,
      value,
      visible: !!(el.offsetParent !== null || el.getClientRects().length),
      enabled: !el.disabled,
      required: !!el.required,
      options,
      text: (tag === 'button' || tag === 'a' || tag === 'div') ? (el.innerText || '').trim().slice(0, 120) : null,
      input_type: tag === 'input' ? el.getAttribute('type') : null,
      testid,
      stable_key: stable,
      selector_candidates: Array.from(new Set(candidates)),
      in_shadow_dom: !!inShadow,
    });
  }

  function walk(root, inShadow) {
    const nodes = root.querySelectorAll(
      'input, select, textarea, button, a[href], [role="alert"], .error, [id*="error"], [id*="validation"], [data-testid], [data-qa], [data-cy]'
    );
    nodes.forEach(el => push(el, inShadow));
    root.querySelectorAll('*').forEach(el => {
      if (el.shadowRoot) walk(el.shadowRoot, true);
    });
  }

  walk(document, false);
  ['#root', '[data-portal]', '[data-radix-portal]', '.MuiModal-root', '[role="dialog"]'].forEach(sel => {
    document.querySelectorAll(sel).forEach(node => walk(node, false));
  });
  return out;
}"""


def _route_snapshot(page: Page) -> RouteSnapshot:
    parsed = urlparse(page.url)
    return RouteSnapshot(
        url=page.url,
        path=parsed.path or "/",
        search=parsed.query and f"?{parsed.query}" or "",
        hash=parsed.fragment and f"#{parsed.fragment}" or "",
        title=page.title(),
    )


def _accessibility_tree(page: Page) -> dict:
    try:
        snapshot = page.accessibility.snapshot()
    except Exception:
        return {"interactive_count": 0}
    if not snapshot:
        return {"interactive_count": 0}
    nodes = []

    def walk(node: dict, depth: int = 0) -> None:
        if depth > 4 or len(nodes) > 80:
            return
        nodes.append({"role": node.get("role"), "name": node.get("name"), "value": node.get("value")})
        for child in node.get("children") or []:
            walk(child, depth + 1)

    walk(snapshot)
    validation_messages = [
        node.get("name") or node.get("value")
        for node in nodes
        if node.get("role") in {"alert", "status"} and (node.get("name") or node.get("value"))
    ]
    return {
        "interactive_count": len(nodes),
        "nodes": nodes,
        "validation_messages": validation_messages[:20],
    }


def _framework_hints(page: Page) -> dict:
    try:
        return page.evaluate(
            """() => ({
              react: !!(window.React || document.querySelector('[data-reactroot], #root')),
              next: !!(window.next || document.querySelector('#__next')),
              vue: !!window.__VUE__,
            })"""
        )
    except Exception:
        return {}


def capture_observation(page: Page, investigation_id, *, with_screenshot: bool = True) -> Observation:
    raw_elements = page.evaluate(_COLLECT_JS)
    elements: list[ElementSnapshot] = []
    visible: list[str] = []
    interactive: list[str] = []

    for raw in raw_elements or []:
        identity = ElementIdentity(
            stable_key=raw.get("stable_key") or raw.get("selector"),
            role=raw.get("role"),
            name=raw.get("name"),
            testid=raw.get("testid"),
            selector_candidates=list(raw.get("selector_candidates") or []),
            confidence=0.95 if raw.get("testid") else 0.7,
        )
        snapshot = ElementSnapshot(
            selector=raw["selector"],
            tag=raw["tag"],
            role=raw.get("role"),
            name=raw.get("name"),
            label=raw.get("label"),
            value=raw.get("value"),
            visible=bool(raw.get("visible", True)),
            enabled=bool(raw.get("enabled", True)),
            required=bool(raw.get("required", False)),
            options=list(raw.get("options") or []),
            text=raw.get("text"),
            input_type=raw.get("input_type"),
            testid=raw.get("testid"),
            stable_key=raw.get("stable_key"),
            identity=identity,
            selector_candidates=list(raw.get("selector_candidates") or []),
            in_shadow_dom=bool(raw.get("in_shadow_dom", False)),
        )
        elements.append(snapshot)
        if snapshot.visible:
            visible.append(snapshot.selector)
        if snapshot.enabled and snapshot.tag in {"input", "select", "textarea", "button", "a"}:
            interactive.append(snapshot.selector)

    forms: list[FormSnapshot] = []
    for form in page.locator("form").all():
        form_selector = form.evaluate(
            """(el) => el.id ? `#${el.id}` : (el.name ? `form[name="${el.name}"]` : 'form')"""
        )
        forms.append(
            FormSnapshot(
                selector=form_selector,
                name=form.get_attribute("name"),
                fields=[e for e in elements if True][:20],
            )
        )

    screenshot_path = None
    if with_screenshot:
        try:
            screenshot_path = capture_screenshot(page, investigation_id)
        except Exception:
            screenshot_path = None

    accessibility = _accessibility_tree(page)
    accessibility["interactive_count"] = max(accessibility.get("interactive_count", 0), len(interactive))
    route = _route_snapshot(page)

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
        route=route,
        framework_hints=_framework_hints(page),
    )
