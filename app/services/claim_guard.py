from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping


class ClaimGuardError(ValueError):
    pass


ALLOWED_CLAIM_TYPES = {"metric_assertion", "status_assertion", "scenario_statement"}
FORBIDDEN_METRICS = {
    "medical_risk_probability",
    "mortality_probability",
    "illness_probability",
    "population_exposed",
    "people_exposed",
}


@dataclass(frozen=True, slots=True)
class GuardDecision:
    approved: bool
    decision: str
    reason_code: str
    reason: str
    evidence_key: str | None = None
    classification: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "approved": self.approved,
            "decision": self.decision,
            "reason_code": self.reason_code,
            "reason": self.reason,
            "evidence_key": self.evidence_key,
            "classification": self.classification,
        }


def _ledger_index(packet: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    ledger = packet.get("evidence_ledger")
    if not isinstance(ledger, list):
        raise ClaimGuardError("Explainability packet has no evidence ledger.")
    index: dict[str, Mapping[str, Any]] = {}
    for item in ledger:
        if not isinstance(item, Mapping):
            raise ClaimGuardError("Evidence ledger entries must be objects.")
        key = item.get("key")
        if not isinstance(key, str) or not key or key in index:
            raise ClaimGuardError("Evidence ledger keys must be unique non-empty strings.")
        index[key] = item
    return index


def _same_value(expected: Any, claimed: Any, tolerance: float = 1e-6) -> bool:
    if expected is None or claimed is None:
        return expected is claimed
    if isinstance(expected, bool) or isinstance(claimed, bool):
        return expected == claimed
    if isinstance(expected, (int, float)) and isinstance(claimed, (int, float)):
        e = float(expected)
        c = float(claimed)
        return math.isfinite(e) and math.isfinite(c) and abs(e - c) <= tolerance
    return expected == claimed


def evaluate_structured_claim(packet: Mapping[str, Any], claim: Mapping[str, Any]) -> GuardDecision:
    claim_type = claim.get("claim_type")
    if claim_type not in ALLOWED_CLAIM_TYPES:
        return GuardDecision(
            False,
            "reject",
            "unsupported_claim_type",
            "Only grounded metric, status, and scenario statements are allowed at Day 7.",
        )

    if claim_type == "scenario_statement":
        statement = claim.get("statement")
        expected = packet.get("scenario_statement")
        if isinstance(statement, str) and statement.strip() == expected:
            return GuardDecision(True, "approve", "scenario_exact_match", "Scenario statement matches the verified packet scope.")
        return GuardDecision(False, "reject", "scenario_scope_mismatch", "Scenario statement does not match the verified scenario-replay scope.")

    metric_key = claim.get("metric_key")
    if not isinstance(metric_key, str) or not metric_key:
        return GuardDecision(False, "reject", "missing_metric_key", "A metric/status claim requires a metric_key.")
    if metric_key in FORBIDDEN_METRICS:
        return GuardDecision(False, "reject", "forbidden_metric", "HeatShield does not support this metric as evidence.", metric_key)

    ledger = _ledger_index(packet)
    entry = ledger.get(metric_key)
    if entry is None:
        return GuardDecision(False, "reject", "unsupported_metric", "Metric is not present in the verified evidence ledger.", metric_key)
    classification = entry.get("classification") if isinstance(entry.get("classification"), str) else None

    if claim_type == "status_assertion":
        claimed_status = claim.get("status")
        if claimed_status == classification:
            return GuardDecision(
                True,
                "approve",
                "status_grounded",
                "Claimed evidence status matches the verified ledger classification.",
                metric_key,
                classification,
            )
        return GuardDecision(
            False,
            "reject",
            "status_mismatch",
            "Claimed evidence status does not match the verified ledger classification.",
            metric_key,
            classification,
        )

    if classification in {"unknown", "withheld"}:
        return GuardDecision(
            False,
            "reject",
            "value_unavailable",
            "A numeric/factual value cannot be asserted for evidence that is unknown or withheld.",
            metric_key,
            classification,
        )
    if classification not in {"observed", "derived"}:
        return GuardDecision(False, "reject", "invalid_classification", "Evidence classification is not claimable.", metric_key, classification)

    claimed_value = claim.get("claimed_value")
    expected = entry.get("value")
    if not _same_value(expected, claimed_value):
        return GuardDecision(
            False,
            "reject",
            "value_mismatch",
            f"Claimed value does not match verified evidence value {expected!r}.",
            metric_key,
            classification,
        )
    return GuardDecision(
        True,
        "approve",
        "metric_grounded",
        "Claim exactly matches an observed/derived value in the verified evidence ledger.",
        metric_key,
        classification,
    )


_PERCENT_RISK = re.compile(r"\b\d+(?:\.\d+)?\s*%\s*(?:health|medical|clinical|illness|mortality)?\s*risk\b", re.I)
_CURRENT_HEAT = re.compile(r"\b(?:current|currently|right now|live)\b.{0,35}\b(?:heat|temperature|heat index|hotspot)\b", re.I)
_PEOPLE_EXPOSURE = re.compile(r"\b(?:people|persons|population|students|patients|workers)\s+(?:are\s+)?exposed\b", re.I)
_MEDICAL_PROBABILITY = re.compile(r"\b(?:medical|clinical|illness|mortality)\s+(?:risk|probability|chance)\b", re.I)
_SAFETY_CERTAINTY = re.compile(r"\b(?:safe|unsafe|will get sick|will not get sick|guaranteed)\b", re.I)


def screen_natural_language(text: str) -> GuardDecision:
    if not isinstance(text, str) or not text.strip():
        return GuardDecision(False, "reject", "empty_text", "Candidate text is empty.")
    normalized = " ".join(text.split())
    checks = (
        (_PERCENT_RISK, "medical_probability_claim", "Percentage health/medical risk is not produced by HeatShield."),
        (_CURRENT_HEAT, "historical_as_current", "Day 4.4/Day 7 hazard evidence is historical scenario evidence, not current heat."),
        (_PEOPLE_EXPOSURE, "mapped_objects_as_people", "Mapped context objects do not establish actual people or occupancy exposed."),
        (_MEDICAL_PROBABILITY, "medical_probability_claim", "Medical/clinical probability claims are outside the evidence model."),
        (_SAFETY_CERTAINTY, "unsupported_safety_certainty", "HeatShield planning evidence cannot certify individual safety or illness outcomes."),
    )
    for pattern, code, reason in checks:
        if pattern.search(normalized):
            return GuardDecision(False, "reject", code, reason)
    return GuardDecision(
        False,
        "requires_structured_grounding",
        "natural_language_not_self_authorizing",
        "Natural-language text is never approved directly. Convert each factual statement into structured claims and ground them against the evidence ledger first.",
    )


def evaluate_claims(packet: Mapping[str, Any], claims: Iterable[Mapping[str, Any]]) -> tuple[GuardDecision, ...]:
    return tuple(evaluate_structured_claim(packet, claim) for claim in claims)
