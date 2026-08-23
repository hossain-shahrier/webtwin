from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from webtwin_core.models.spa import ElementIdentity, RouteSnapshot


class ElementSnapshot(BaseModel):
    selector: str
    tag: str
    role: str | None = None
    name: str | None = None
    label: str | None = None
    value: str | None = None
    visible: bool = True
    enabled: bool = True
    required: bool = False
    options: list[str] = Field(default_factory=list)
    text: str | None = None
    input_type: str | None = None
    testid: str | None = None
    stable_key: str | None = None
    identity: ElementIdentity | None = None
    selector_candidates: list[str] = Field(default_factory=list)
    in_shadow_dom: bool = False


class FormSnapshot(BaseModel):
    selector: str
    name: str | None = None
    fields: list[ElementSnapshot] = Field(default_factory=list)


class Observation(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    investigation_id: UUID
    captured_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    url: str
    title: str
    elements: list[ElementSnapshot] = Field(default_factory=list)
    forms: list[FormSnapshot] = Field(default_factory=list)
    visible_elements: list[str] = Field(default_factory=list)
    interactive_elements: list[str] = Field(default_factory=list)
    accessibility: dict[str, Any] = Field(default_factory=dict)
    screenshot_path: str | None = None
    html_length: int = 0
    route: RouteSnapshot | None = None
    framework_hints: dict[str, Any] = Field(default_factory=dict)

    def to_application_state(self, sequence: int) -> "ApplicationState":
        from webtwin_core.models.state import ApplicationState, FieldState

        fields: list[FieldState] = []
        for element in self.elements:
            fields.append(
                FieldState(
                    name=element.stable_key or element.name or element.selector,
                    label=element.label,
                    value=element.value,
                    visible=element.visible,
                    enabled=element.enabled,
                    required=element.required,
                )
            )

        return ApplicationState(
            investigation_id=self.investigation_id,
            sequence=sequence,
            captured_at=self.captured_at,
            url=self.url,
            fields=fields,
        )
