from __future__ import annotations

import re

from webtwin_core.exploration.actions import ActionType, ExploratoryAction, SafetyClass

DESTRUCTIVE_PATTERNS = (
    r"\bdelete\b",
    r"\bremove\b",
    r"\bdestroy\b",
    r"\bpayment\b",
    r"\bpay\b",
    r"\bpublish\b",
    r"\birreversible\b",
    r"\bsubmit application\b",
    r"\bdelete account\b",
    r"\bdelete record\b",
)

CAUTION_PATTERNS = (
    r"\bsave\b",
    r"\bsubmit\b",
    r"\bupload\b",
    r"\bsend\b",
    r"\bconfirm\b",
)


def classify_action_safety(action: ExploratoryAction) -> SafetyClass:
    haystack = " ".join(
        part for part in (action.target, action.label, action.selector, *action.values) if part
    ).lower()

    for pattern in DESTRUCTIVE_PATTERNS:
        if re.search(pattern, haystack):
            return SafetyClass.DESTRUCTIVE
    if action.type == ActionType.CLICK:
        for pattern in CAUTION_PATTERNS:
            if re.search(pattern, haystack):
                return SafetyClass.CAUTION
    if action.type == ActionType.INPUT and action.metadata.get("input_type") == "file":
        return SafetyClass.CAUTION
    return SafetyClass.SAFE


def apply_safety(action: ExploratoryAction) -> ExploratoryAction:
    return action.model_copy(update={"safety": classify_action_safety(action)})


def filter_automatable(
    actions: list[ExploratoryAction],
    *,
    allow_caution: bool = False,
) -> list[ExploratoryAction]:
    allowed = {SafetyClass.SAFE}
    if allow_caution:
        allowed.add(SafetyClass.CAUTION)
    classified = [apply_safety(action) for action in actions]
    return [action for action in classified if action.safety in allowed]


def requires_human_approval(action: ExploratoryAction) -> bool:
    return apply_safety(action).safety in {SafetyClass.CAUTION, SafetyClass.DESTRUCTIVE}
