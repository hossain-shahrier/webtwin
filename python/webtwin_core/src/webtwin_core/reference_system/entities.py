"""Infer domain entities from observed fields, forms, and screen titles."""

from __future__ import annotations

import re
from collections import Counter
from typing import Iterable

from pydantic import BaseModel, Field

# token → canonical entity (business-domain vocabulary for ATS / enterprise apps)
_ENTITY_LEXICON: dict[str, str] = {
    # identity / person
    "applicant": "Applicant",
    "candidate": "Applicant",
    "student": "Applicant",
    "person": "Person",
    "user": "User",
    "profile": "Profile",
    "first_name": "Person",
    "lastname": "Person",
    "last_name": "Person",
    "firstname": "Person",
    "surname": "Person",
    "fullname": "Person",
    "date_of_birth": "Person",
    "dob": "Person",
    "gender": "Person",
    "nationality": "Person",
    "citizenship": "Person",
    # contact
    "email": "Contact",
    "phone": "Contact",
    "mobile": "Contact",
    "telephone": "Contact",
    "fax": "Contact",
    # address / location
    "address": "Address",
    "street": "Address",
    "city": "Address",
    "province": "Address",
    "state": "Address",
    "region": "Address",
    "zip": "Address",
    "zipcode": "Address",
    "postal": "Address",
    "country": "Address",
    "nation": "Address",
    "estero": "Address",
    "comune": "Address",
    "cap": "Address",
    # application / enrollment
    "application": "Application",
    "apply": "Application",
    "enrollment": "Application",
    "enrolment": "Application",
    "admission": "Application",
    "program": "Application",
    "programme": "Application",
    "course": "Application",
    "degree": "Application",
    "faculty": "Application",
    # employment
    "employment": "Employment",
    "employer": "Employment",
    "job": "Employment",
    "position": "Employment",
    "salary": "Employment",
    "contract": "Employment",
    "end_date": "Employment",
    "start_date": "Employment",
    "hire": "Employment",
    "recruiter": "Employment",
    # education
    "education": "Education",
    "school": "Education",
    "university": "Education",
    "diploma": "Education",
    "gpa": "Education",
    "transcript": "Education",
    # documents
    "document": "Document",
    "attachment": "Document",
    "upload": "Document",
    "file": "Document",
    "cv": "Document",
    "resume": "Document",
    "passport": "Document",
    "id_card": "Document",
    # auth
    "password": "Authentication",
    "username": "Authentication",
    "login": "Authentication",
    "signin": "Authentication",
    "otp": "Authentication",
    "mfa": "Authentication",
    "spid": "Authentication",
    # payment
    "payment": "Payment",
    "billing": "Payment",
    "invoice": "Payment",
    "card": "Payment",
    "iban": "Payment",
    # org
    "company": "Organization",
    "organization": "Organization",
    "organisation": "Organization",
    "department": "Organization",
    "team": "Organization",
}


class EntityFieldRef(BaseModel):
    field: str
    label: str | None = None
    screen_id: str | None = None


class DomainEntity(BaseModel):
    name: str
    confidence: float = 0.5
    field_count: int = 0
    screen_ids: list[str] = Field(default_factory=list)
    fields: list[EntityFieldRef] = Field(default_factory=list)
    rule_names: list[str] = Field(default_factory=list)


def _normalize_token(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _tokens_from_text(text: str) -> list[str]:
    normalized = _normalize_token(text)
    if not normalized:
        return []
    parts = [part for part in normalized.split("_") if part]
    tokens = [normalized, *parts]
    # also keep bigrams for compound names like first_name
    for index in range(len(parts) - 1):
        tokens.append(f"{parts[index]}_{parts[index + 1]}")
    return tokens


def match_entity_from_route(path: str | None) -> str | None:
    """Prefer admin route segments over generic lexicon tokens (e.g. job-seeker ≠ Employment)."""
    if not path:
        return None
    normalized = path.lower().replace("-", "_")
    route_patterns: list[tuple[str, str]] = [
        ("job_seeker", "JobSeeker"),
        ("company_management", "Company"),
        ("/company/", "Company"),
        ("agency_management", "Agency"),
        ("user_management", "SystemUser"),
        ("task_management", "Task"),
        ("holiday_management", "Holiday"),
        ("prompt_template", "PromptTemplate"),
        ("application_management", "Application"),
        ("job_management", "Job"),
        ("role_permission", "RolePermission"),
        ("qmate", "QMate"),
        ("second_screening", "SecondScreening"),
        ("hearing_form", "HearingForm"),
        ("reports", "Report"),
    ]
    for pattern, entity in route_patterns:
        if pattern in normalized:
            return entity
    return None


def match_entity_name(*texts: str | None, route_path: str | None = None) -> str | None:
    """Return the highest-priority entity name matched from route path or free text."""
    route_entity = match_entity_from_route(route_path)
    if route_entity:
        return route_entity

    scores: Counter[str] = Counter()
    for text in texts:
        if not text:
            continue
        for token in _tokens_from_text(text):
            entity = _ENTITY_LEXICON.get(token)
            if entity:
                scores[entity] += 1
    if not scores:
        return None
    return scores.most_common(1)[0][0]


def infer_entities_from_fields(
    fields: Iterable[tuple[str, str | None, str | None]],
    *,
    screen_id: str | None = None,
) -> dict[str, list[EntityFieldRef]]:
    """
    fields: iterable of (name, label, form_name).
    Returns entity_name → field refs.
    """
    grouped: dict[str, list[EntityFieldRef]] = {}
    for name, label, form_name in fields:
        entity = match_entity_name(name, label, form_name)
        if not entity:
            continue
        grouped.setdefault(entity, []).append(
            EntityFieldRef(field=name, label=label, screen_id=screen_id)
        )
    return grouped


def merge_entity_maps(
    maps: list[dict[str, list[EntityFieldRef]]],
) -> list[DomainEntity]:
    by_name: dict[str, list[EntityFieldRef]] = {}
    for mapping in maps:
        for name, refs in mapping.items():
            by_name.setdefault(name, []).extend(refs)

    entities: list[DomainEntity] = []
    for name, refs in by_name.items():
        # dedupe by field name (same form repeated across edit screens)
        seen: set[str] = set()
        unique: list[EntityFieldRef] = []
        for ref in refs:
            if ref.field in seen:
                continue
            seen.add(ref.field)
            unique.append(ref)
        screens = sorted({ref.screen_id for ref in unique if ref.screen_id})
        # confidence scales with field diversity
        confidence = min(0.95, 0.35 + 0.08 * len(unique))
        entities.append(
            DomainEntity(
                name=name,
                confidence=confidence,
                field_count=len(unique),
                screen_ids=screens,
                fields=unique[:40],
            )
        )
    entities.sort(key=lambda item: (-item.field_count, item.name))
    return entities


def attach_rules_to_entities(
    entities: list[DomainEntity],
    rule_names_by_field: dict[str, list[str]],
) -> list[DomainEntity]:
    for entity in entities:
        names: list[str] = []
        for ref in entity.fields:
            names.extend(rule_names_by_field.get(ref.field.lower(), []))
            if ref.label:
                names.extend(rule_names_by_field.get(ref.label.lower(), []))
        # also match entity name tokens in rule titles
        entity_l = entity.name.lower()
        for field, rule_names in rule_names_by_field.items():
            if entity_l in field or any(entity_l in name.lower() for name in rule_names):
                names.extend(rule_names)
        entity.rule_names = sorted(set(names))[:20]
    return entities


def entity_relevant_blob(entity_names: Iterable[str]) -> set[str]:
    """Tokens that mark an action as relevant to known entities."""
    tokens: set[str] = set()
    reverse: dict[str, list[str]] = {}
    for token, entity in _ENTITY_LEXICON.items():
        reverse.setdefault(entity, []).append(token)
    for name in entity_names:
        tokens.add(name.lower())
        for token in reverse.get(name, []):
            tokens.add(token)
    return tokens
