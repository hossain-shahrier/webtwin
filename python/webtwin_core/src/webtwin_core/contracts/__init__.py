"""Executable Contract Pack — verified rules → runnable Playwright pytest."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from webtwin_core.models import BusinessRule
from webtwin_core.negative_space import AbsenceAssertion, derive_absences_from_rules
from webtwin_core.privacy import redact_mapping


class ContractFile(BaseModel):
    path: str
    content: str
    language: str = "python"


class ContractPack(BaseModel):
    investigation_id: str
    target_url: str
    files: list[ContractFile] = Field(default_factory=list)
    rule_count: int = 0
    absence_count: int = 0
    guidance: list[str] = Field(default_factory=list)


def _py_str(value: object) -> str:
    return repr(str(value) if value is not None else "")


def _selector(rule: BusinessRule, which: str) -> str:
    if which == "condition":
        return rule.condition_selector or f'[name="{rule.condition.field}"]'
    return rule.effect_selector or f'[name="{rule.effect.field}"]'


def _generate_pytest(
    *,
    investigation_id: str,
    target_url: str,
    rules: list[BusinessRule],
    absences: list[AbsenceAssertion],
) -> str:
    lines = [
        '"""Auto-generated WebTwin behavioral contracts.',
        "Do not invent assertions — regenerate from Clone Spec / verified rules.",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "import pytest",
        "from playwright.sync_api import Page, expect",
        "",
        f'TARGET_URL = {_py_str(target_url)}',
        f'INVESTIGATION_ID = {_py_str(investigation_id)}',
        "",
        "",
        "@pytest.fixture(scope='function')",
        "def page_ready(page: Page) -> Page:",
        "    page.goto(TARGET_URL)",
        "    page.wait_for_load_state('domcontentloaded')",
        "    return page",
        "",
        "",
        "def _fill(page: Page, selector: str, value: str) -> None:",
        "    locator = page.locator(selector)",
        "    if value == '__click__':",
        "        locator.first.click()",
        "        return",
        "    tag = locator.first.evaluate('(el) => el.tagName.toLowerCase()')",
        "    if tag == 'select':",
        "        locator.first.select_option(value)",
        "    else:",
        "        locator.first.fill(value)",
        "",
    ]

    for index, rule in enumerate(rules):
        if rule.status.value != "verified":
            continue
        setup = redact_mapping(rule.setup_fields)
        fn = f"test_contract_{index:03d}_{_safe(rule.condition.field)}_{_safe(rule.effect.field)}"
        lines.append(f"def {fn}(page_ready: Page) -> None:")
        lines.append(f'    """{rule.name}"""')
        lines.append("    page = page_ready")
        for key, value in setup.items():
            lines.append(f'    _fill(page, \'[name="{key}"]\', {_py_str(value)})')
        cond_sel = _selector(rule, "condition")
        if rule.condition.operator == "clicked":
            lines.append(f"    _fill(page, {_py_str(cond_sel)}, '__click__')")
        else:
            lines.append(
                f"    _fill(page, {_py_str(cond_sel)}, {_py_str(rule.condition.value)})"
            )
        effect_sel = _selector(rule, "effect")
        if rule.effect.visible is True:
            lines.append(f"    expect(page.locator({_py_str(effect_sel)}).first).to_be_visible()")
        elif rule.effect.visible is False:
            lines.append(
                f"    expect(page.locator({_py_str(effect_sel)})).to_have_count(0)"
            )
        if rule.effect.required is True:
            lines.append(
                f"    assert page.locator({_py_str(effect_sel)}).first.get_attribute('required') is not None"
            )
        lines.append("")

    for index, absence in enumerate(absences):
        fn = f"test_absence_{index:03d}_{_safe(absence.condition_field)}_{_safe(absence.effect_field)}"
        lines.append(f"def {fn}(page_ready: Page) -> None:")
        lines.append(f'    """assert_never {absence.effect_field} when {absence.condition_field}"""')
        lines.append("    page = page_ready")
        for key, value in (absence.setup_fields or {}).items():
            lines.append(f'    _fill(page, \'[name="{key}"]\', {_py_str(value)})')
        lines.append(
            f'    _fill(page, \'[name="{absence.condition_field}"]\', '
            f"{_py_str(absence.condition_value)})"
        )
        lines.append(
            f'    expect(page.locator(\'[name="{absence.effect_field}"]\')).to_have_count(0)'
        )
        lines.append("")

    if not any(rule.status.value == "verified" for rule in rules) and not absences:
        lines.extend(
            [
                "def test_no_contracts_yet(page_ready: Page) -> None:",
                "    pytest.skip('No verified rules or absences to contract')",
                "",
            ]
        )
    return "\n".join(lines)


def _safe(text: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in text)[:40]


def build_contract_pack(
    investigation_id: UUID,
    target_url: str,
    rules: list[BusinessRule],
    *,
    absences: list[AbsenceAssertion] | None = None,
) -> ContractPack:
    derived = absences if absences is not None else derive_absences_from_rules(rules)
    verified = [rule for rule in rules if rule.status.value == "verified"]
    content = _generate_pytest(
        investigation_id=str(investigation_id),
        target_url=target_url,
        rules=verified,
        absences=derived,
    )
    return ContractPack(
        investigation_id=str(investigation_id),
        target_url=target_url,
        files=[
            ContractFile(
                path="tests/webtwin_contracts/test_behavioral_contracts.py",
                content=content,
            ),
            ContractFile(
                path="tests/webtwin_contracts/README.md",
                content=(
                    "# WebTwin behavioral contracts\n\n"
                    "Generated from verified rules + negative-space absences.\n\n"
                    "```bash\npytest tests/webtwin_contracts -q\n```\n"
                ),
                language="markdown",
            ),
        ],
        rule_count=len(verified),
        absence_count=len(derived),
        guidance=[
            "Run contracts in CI against the clone under test.",
            "Regenerate after each golden pin; do not hand-edit assertions.",
            "Failures mean behavioral drift — investigate with Drift Twin.",
        ],
    )
