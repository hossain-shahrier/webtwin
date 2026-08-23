"""SQLAlchemy table definitions for persistent WebTwin evidence."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class InvestigationRow(Base):
    __tablename__ = "investigations"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    target_url: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    application_name: Mapped[str | None] = mapped_column(Text)
    application_key: Mapped[str | None] = mapped_column(String(256), index=True)
    feature_scope: Mapped[str | None] = mapped_column(Text)
    session_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    goal_spec: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    auth_pause: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    checkpoint: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    blocked_reason: Mapped[str | None] = mapped_column(Text)
    application_version: Mapped[str | None] = mapped_column(String(128))
    environment: Mapped[str | None] = mapped_column(String(128))
    role_scope: Mapped[str | None] = mapped_column(String(128))
    spa_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    exploration_policy: Mapped[str | None] = mapped_column(String(64))
    investigation_scope: Mapped[str | None] = mapped_column(String(64))
    url_prefix: Mapped[str | None] = mapped_column(Text)
    start_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SessionRow(Base):
    __tablename__ = "sessions"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    investigation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    auth_state: Mapped[str] = mapped_column(String(64), nullable=False)
    session_status: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    storage_state_ref: Mapped[str | None] = mapped_column(Text)
    checkpoint: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    human_ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    auth_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class InvestigationTransitionRow(Base):
    __tablename__ = "investigation_transitions"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    investigation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    from_status: Mapped[str] = mapped_column(String(64), nullable=False)
    to_status: Mapped[str] = mapped_column(String(64), nullable=False)
    event: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    reason: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class ObservationRow(Base):
    __tablename__ = "observations"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    investigation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    screenshot_path: Mapped[str | None] = mapped_column(Text)
    html_length: Mapped[int] = mapped_column(Integer, default=0)
    accessibility: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    visible_elements: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    interactive_elements: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    route: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    framework_hints: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    elements: Mapped[list["ObservationElementRow"]] = relationship(
        back_populates="observation", cascade="all, delete-orphan"
    )
    forms: Mapped[list["ObservationFormRow"]] = relationship(
        back_populates="observation", cascade="all, delete-orphan"
    )


class ObservationElementRow(Base):
    __tablename__ = "observation_elements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    observation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("observations.id", ondelete="CASCADE"), index=True
    )
    selector: Mapped[str] = mapped_column(Text, nullable=False)
    tag: Mapped[str] = mapped_column(String(64), nullable=False)
    role: Mapped[str | None] = mapped_column(String(64))
    name: Mapped[str | None] = mapped_column(Text)
    label: Mapped[str | None] = mapped_column(Text)
    value: Mapped[str | None] = mapped_column(Text)
    visible: Mapped[bool] = mapped_column(Boolean, default=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    options: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    text: Mapped[str | None] = mapped_column(Text)
    input_type: Mapped[str | None] = mapped_column(String(64))
    testid: Mapped[str | None] = mapped_column(Text)
    stable_key: Mapped[str | None] = mapped_column(Text)
    selector_candidates: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    in_shadow_dom: Mapped[bool] = mapped_column(Boolean, default=False)

    observation: Mapped[ObservationRow] = relationship(back_populates="elements")


class ObservationFormRow(Base):
    __tablename__ = "observation_forms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    observation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("observations.id", ondelete="CASCADE"), index=True
    )
    selector: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str | None] = mapped_column(Text)
    fields: Mapped[list[Any]] = mapped_column(JSONB, default=list)

    observation: Mapped[ObservationRow] = relationship(back_populates="forms")


class ApplicationStateRow(Base):
    __tablename__ = "application_states"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    investigation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    url: Mapped[str | None] = mapped_column(Text)
    triggered_by_event_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))

    fields: Mapped[list["StateFieldRow"]] = relationship(
        back_populates="state", cascade="all, delete-orphan"
    )


class StateFieldRow(Base):
    __tablename__ = "state_fields"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    state_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("application_states.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    label: Mapped[str | None] = mapped_column(Text)
    value: Mapped[str | None] = mapped_column(Text)
    visible: Mapped[bool] = mapped_column(Boolean, default=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    required: Mapped[bool] = mapped_column(Boolean, default=False)

    state: Mapped[ApplicationStateRow] = relationship(back_populates="fields")


class TimelineEventRow(Base):
    __tablename__ = "actions"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    investigation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    state_before_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    state_after_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    evidence_ids: Mapped[list[Any]] = mapped_column(JSONB, default=list)


class StateTransitionRow(Base):
    __tablename__ = "state_transitions"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    investigation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    before_state_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    after_state_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="")

    changes: Mapped[list["FieldChangeRow"]] = relationship(
        back_populates="transition", cascade="all, delete-orphan"
    )


class FieldChangeRow(Base):
    __tablename__ = "field_changes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    state_transition_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("state_transitions.id", ondelete="CASCADE"), index=True
    )
    field: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    attribute: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    before_value: Mapped[str | None] = mapped_column(Text)
    after_value: Mapped[str | None] = mapped_column(Text)

    transition: Mapped[StateTransitionRow] = relationship(back_populates="changes")


class EvidenceRow(Base):
    __tablename__ = "evidence"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    investigation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    sensitivity: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    url: Mapped[str | None] = mapped_column(Text)
    knowledge_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    artifact_uri: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str | None] = mapped_column(String(128), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class RuleRow(Base):
    __tablename__ = "rules"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    investigation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    knowledge_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    condition_field: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    condition_operator: Mapped[str] = mapped_column(String(64), nullable=False)
    condition_value: Mapped[str | None] = mapped_column(Text)
    effect_field: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    effect_visible: Mapped[bool | None] = mapped_column(Boolean)
    effect_required: Mapped[bool | None] = mapped_column(Boolean)
    effect_enabled: Mapped[bool | None] = mapped_column(Boolean)


class RuleEvidenceRow(Base):
    __tablename__ = "rule_evidence"
    __table_args__ = (UniqueConstraint("rule_id", "evidence_id", "relation"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("rules.id", ondelete="CASCADE"), index=True
    )
    evidence_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("evidence.id", ondelete="CASCADE"), index=True
    )
    relation: Mapped[str] = mapped_column(String(64), nullable=False)  # discovered_from | supported_by


class ExperimentRow(Base):
    __tablename__ = "experiments"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    rule_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("rules.id", ondelete="CASCADE"), index=True
    )
    investigation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)

    results: Mapped[list["ExperimentResultRow"]] = relationship(
        back_populates="experiment", cascade="all, delete-orphan"
    )


class ExperimentResultRow(Base):
    __tablename__ = "experiment_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    experiment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("experiments.id", ondelete="CASCADE"), index=True
    )
    experiment_item_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    details: Mapped[str] = mapped_column(Text, nullable=False)
    observation_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))

    experiment: Mapped[ExperimentRow] = relationship(back_populates="results")


class RuleExperimentRow(Base):
    __tablename__ = "rule_experiments"
    __table_args__ = (UniqueConstraint("rule_id", "experiment_id", "relation"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("rules.id", ondelete="CASCADE"), index=True
    )
    experiment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("experiments.id", ondelete="CASCADE"), index=True
    )
    relation: Mapped[str] = mapped_column(String(64), nullable=False)  # tested_by | verified_by


class EvaluationRunRow(Base):
    __tablename__ = "evaluation_runs"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    investigation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    policy: Mapped[str] = mapped_column(String(64), nullable=False)
    level: Mapped[str | None] = mapped_column(String(64))
    exploration_coverage: Mapped[float] = mapped_column(Float, default=0.0)
    state_coverage: Mapped[int] = mapped_column(Integer, default=0)
    actions_taken: Mapped[int] = mapped_column(Integer, default=0)
    candidate_rules: Mapped[int] = mapped_column(Integer, default=0)
    verified_rules: Mapped[int] = mapped_column(Integer, default=0)
    rules_per_action: Mapped[float] = mapped_column(Float, default=0.0)
    safety_violations: Mapped[int] = mapped_column(Integer, default=0)
    blocked_unsafe_actions: Mapped[int] = mapped_column(Integer, default=0)
    pages_seen: Mapped[int] = mapped_column(Integer, default=1)
    discovery_precision: Mapped[float | None] = mapped_column(Float)
    discovery_recall: Mapped[float | None] = mapped_column(Float)
    discovery_f1: Mapped[float | None] = mapped_column(Float)
    verification_accuracy: Mapped[float | None] = mapped_column(Float)
    settle_timeouts: Mapped[int] = mapped_column(Integer, default=0)
    soft_nav_success_rate: Mapped[float | None] = mapped_column(Float)
    routes_seen: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DiscoveredLinkRow(Base):
    __tablename__ = "discovered_links"
    __table_args__ = (
        UniqueConstraint("investigation_id", "from_screen_id", "href", name="uq_discovered_link"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    investigation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    from_screen_id: Mapped[str] = mapped_column(Text, nullable=False)
    to_screen_id: Mapped[str | None] = mapped_column(Text)
    href: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str | None] = mapped_column(Text)
    selector: Mapped[str | None] = mapped_column(Text)
    link_type: Mapped[str] = mapped_column(String(32), nullable=False, default="navigate")
    visited: Mapped[bool] = mapped_column(Boolean, default=False)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class NetworkEventRow(Base):
    __tablename__ = "network_events"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    investigation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    timeline_event_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), index=True)
    route_path: Mapped[str | None] = mapped_column(Text)
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer)
    timing_ms: Mapped[float | None] = mapped_column(Float)
    request_headers: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    response_headers: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    body_shape: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    evidence_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class WorkflowRow(Base):
    __tablename__ = "workflows"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    investigation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    steps: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    trigger_action_ids: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ApplicationCatalogRow(Base):
    __tablename__ = "application_catalogs"

    application_key: Mapped[str] = mapped_column(String(256), primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    golden_version: Mapped[str | None] = mapped_column(String(128))
    golden_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)