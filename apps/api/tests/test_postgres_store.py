"""PostgreSQL persistence smoke tests (requires local Postgres)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select

from api.db.engine import create_db_engine, create_session_factory, init_db, ping_db
from api.db.schema import FieldChangeRow, RuleEvidenceRow, RuleExperimentRow
from api.store.postgres import PostgresStore
from webtwin_core.models import (
    ApplicationState,
    BusinessRule,
    ElementSnapshot,
    Evidence,
    EvidenceType,
    FieldChange,
    FieldState,
    Investigation,
    Observation,
    RuleCondition,
    RuleEffect,
    StateDiff,
)
from webtwin_core.models.rule_status import RuleStatus
from webtwin_core.verification.engine import VerificationExperimentResult, VerificationRun


def _postgres_available() -> bool:
    try:
        engine = create_db_engine()
        ping_db(engine)
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _postgres_available(), reason="PostgreSQL not available")


@pytest.fixture()
def pg_store() -> PostgresStore:
    engine = create_db_engine()
    init_db(engine)
    store = PostgresStore(create_session_factory(engine))
    store.clear()
    yield store
    store.clear()


def test_investigation_round_trip(pg_store: PostgresStore) -> None:
    investigation = Investigation(goal="persist me", target_url="https://example.com")
    pg_store.investigations[investigation.id] = investigation

    loaded = pg_store.investigations[investigation.id]
    assert loaded.goal == "persist me"
    assert loaded.target_url == "https://example.com"


def test_state_transition_field_changes_are_queryable(pg_store: PostgresStore) -> None:
    investigation = Investigation(goal="diff", target_url="https://example.com")
    pg_store.investigations[investigation.id] = investigation

    before = ApplicationState(
        investigation_id=investigation.id,
        sequence=1,
        fields=[FieldState(name="condition", value="yes", visible=True)],
    )
    after = ApplicationState(
        investigation_id=investigation.id,
        sequence=2,
        fields=[FieldState(name="condition", value="no", visible=True)],
    )
    pg_store.states[before.id] = before
    pg_store.states[after.id] = after

    diff = StateDiff(
        investigation_id=investigation.id,
        before_state_id=before.id,
        after_state_id=after.id,
        changes=[FieldChange(field="condition", attribute="value", before="yes", after="no")],
        summary="condition.value: 'yes' -> 'no'",
    )
    pg_store.diffs[diff.id] = diff

    with pg_store._session_factory() as session:
        rows = list(
            session.scalars(select(FieldChangeRow).where(FieldChangeRow.state_transition_id == diff.id))
        )
        assert len(rows) == 1
        assert rows[0].field == "condition"
        assert rows[0].attribute == "value"
        assert rows[0].before_value == "yes"
        assert rows[0].after_value == "no"


def test_rule_provenance_links(pg_store: PostgresStore) -> None:
    investigation = Investigation(goal="provenance", target_url="https://example.com")
    pg_store.investigations[investigation.id] = investigation

    evidence = Evidence(
        investigation_id=investigation.id,
        type=EvidenceType.DOM,
        payload={"summary": "observed visibility change"},
    )
    pg_store.evidence[evidence.id] = evidence

    rule = BusinessRule(
        investigation_id=investigation.id,
        name="condition affects reason",
        condition=RuleCondition(field="condition", operator="equals", value="no"),
        effect=RuleEffect(field="reason", visible=True),
        evidence_ids=[evidence.id],
        confidence=0.6,
    )
    pg_store.rules[rule.id] = rule

    run = VerificationRun(
        rule_id=rule.id,
        investigation_id=investigation.id,
        status=RuleStatus.VERIFIED,
        confidence=0.95,
        results=[
            VerificationExperimentResult(
                experiment_id=uuid4(),
                passed=True,
                details="matched",
            )
        ],
    )
    pg_store.verification_runs[run.id] = run
    rule.verification_run_ids.append(run.id)
    rule.status = RuleStatus.VERIFIED
    rule.confidence = 0.95
    pg_store.rules[rule.id] = rule

    loaded = pg_store.rules[rule.id]
    assert evidence.id in loaded.evidence_ids
    assert run.id in loaded.verification_run_ids

    with pg_store._session_factory() as session:
        evidence_links = list(
            session.scalars(select(RuleEvidenceRow).where(RuleEvidenceRow.rule_id == rule.id))
        )
        experiment_links = list(
            session.scalars(select(RuleExperimentRow).where(RuleExperimentRow.rule_id == rule.id))
        )
        assert len(evidence_links) == 1
        assert evidence_links[0].relation == "supported_by"
        assert any(link.relation == "verified_by" for link in experiment_links)


def test_evidence_content_hash_persisted(pg_store: PostgresStore) -> None:
    investigation = Investigation(goal="hash", target_url="https://example.com")
    pg_store.investigations[investigation.id] = investigation
    evidence = Evidence(
        investigation_id=investigation.id,
        type=EvidenceType.DOM,
        payload={"html": "<div>x</div>"},
    )
    assert evidence.content_hash is not None
    pg_store.evidence[evidence.id] = evidence
    loaded = pg_store.evidence[evidence.id]
    assert loaded.content_hash == evidence.content_hash


def test_observation_elements_persisted(pg_store: PostgresStore) -> None:
    investigation = Investigation(goal="obs", target_url="https://example.com")
    pg_store.investigations[investigation.id] = investigation
    observation = Observation(
        investigation_id=investigation.id,
        url="https://example.com/form",
        title="Form",
        elements=[
            ElementSnapshot(
                selector="#condition",
                tag="select",
                name="condition",
                value="yes",
                visible=True,
            )
        ],
    )
    pg_store.observations[observation.id] = observation
    loaded = pg_store.observations[observation.id]
    assert len(loaded.elements) == 1
    assert loaded.elements[0].name == "condition"
