from webtwin_core.models.evidence import Evidence, EvidenceSensitivity, EvidenceType


def test_network_evidence_is_sensitive() -> None:
    evidence = Evidence(
        investigation_id=__import__("uuid").uuid4(),
        type=EvidenceType.NETWORK,
        payload={"url": "https://example.com/api", "status": 200},
    )
    assert evidence.sensitivity == EvidenceSensitivity.SENSITIVE


def test_dom_evidence_is_safe() -> None:
    evidence = Evidence(
        investigation_id=__import__("uuid").uuid4(),
        type=EvidenceType.DOM,
        payload={"html": "<div>hello</div>"},
    )
    assert evidence.sensitivity == EvidenceSensitivity.SAFE
    assert evidence.content_hash is not None
    assert len(evidence.content_hash) == 64
