from enum import StrEnum


class KnowledgeKind(StrEnum):
    OBSERVED = "observed"
    INFERRED = "inferred"
    DOCUMENTED = "documented"
    UNKNOWN = "unknown"
