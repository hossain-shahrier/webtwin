from enum import StrEnum


class RuleStatus(StrEnum):
    DISCOVERED = "discovered"
    CANDIDATE = "candidate"
    UNDER_VERIFICATION = "under_verification"
    VERIFIED = "verified"
    CONTRADICTED = "contradicted"
