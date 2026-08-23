from webtwin_core.models import Evidence, TimelineEvent


class TimelineRecorder:
    def __init__(self) -> None:
        self.events: list[TimelineEvent] = []

    def record(self, event: TimelineEvent) -> TimelineEvent:
        self.events.append(event)
        print(f"[timeline] {event.occurred_at.isoformat()} {event.type}: {event.description}")
        return event


class EvidenceRecorder:
    def __init__(self) -> None:
        self.items: list[Evidence] = []

    def record(self, evidence: Evidence) -> Evidence:
        self.items.append(evidence)
        return evidence
