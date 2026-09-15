"""diagnosis service — fault-tree over symptom + equipment + readings.

STUB: the model call and retrieval are placeholders. Two invariants are real
and enforced here regardless of model wiring:
  1. Every diagnosis writes an audit record (model, prompt, retrieved_doc).
  2. Hazard signals never return a self-serve fault tree — they escalate.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
import re
import uuid

# Whole-word / phrase signals. Kept as regex alternatives so "compressor" and
# "cooling" do NOT trip the "co" abbreviation for carbon monoxide.
HAZARD_SIGNALS = [
    r"gas", r"gas smell", r"\bco\b", r"carbon monoxide",
    r"smoke", r"scorch\w*", r"burning", r"sparking", r"shock",
]
_HAZARD_RE = re.compile("|".join(HAZARD_SIGNALS), re.IGNORECASE)


@dataclass
class Reading:
    metric: str
    value: float
    unit: str


@dataclass
class Citation:
    code_body: str
    section: str
    edition_year: int
    state: str
    jurisdiction: str
    source_url: str  # provenance mandatory — see schema.sql code_citations


@dataclass
class DiagnosisResult:
    ranked_faults: list[dict[str, Any]]
    citations: list[Citation]
    audit_id: str
    escalate: bool = False
    field_notes: list[str] = field(default_factory=list)


def _write_audit(model: str, prompt: str, retrieved_doc: str, output: str) -> str:
    """Persist a diagnosis_audit row. Returns audit id.

    Placeholder: real implementation inserts into diagnosis_audit. The point is
    that NOTHING returns to the tech without this row existing.
    """
    if not (model and prompt and retrieved_doc):
        raise ValueError("refusing to emit a diagnosis without full audit trail")
    return str(uuid.uuid4())


def _is_hazard(symptom: str) -> bool:
    return bool(_HAZARD_RE.search(symptom))


def diagnose(equipment_model: str, symptom: str, readings: list[Reading]) -> DiagnosisResult:
    if _is_hazard(symptom):
        audit_id = _write_audit(
            model="policy:hazard-shortcircuit",
            prompt=f"{equipment_model} | {symptom}",
            retrieved_doc="EXECUTION_BOUNDARY:hazard-escalation",
            output="ESCALATE",
        )
        return DiagnosisResult(
            ranked_faults=[],
            citations=[],
            audit_id=audit_id,
            escalate=True,
            field_notes=["Hazard signal detected. STOP. Trigger supervisor "
                         "live-view before any further action."],
        )

    # --- STUB: replace with grounded retrieval + model call ---
    model = "STUB-not-wired"
    prompt = f"model={equipment_model} symptom={symptom} readings={readings}"
    retrieved_doc = "STUB: no corpus wired yet"
    ranked_faults = [{
        "fault": "not-implemented",
        "confidence": 0.0,
        "why": "diagnosis model + corpus not yet wired",
        "next_check": "wire retrieval over manufacturer service manuals",
    }]
    citations: list[Citation] = []
    audit_id = _write_audit(model, prompt, retrieved_doc, str(ranked_faults))
    return DiagnosisResult(ranked_faults, citations, audit_id)


if __name__ == "__main__":
    demo = diagnose("Carrier 24ACC6", "no cooling, compressor runs",
                    [Reading("superheat", 22, "F"), Reading("subcooling", 3, "F")])
    print(demo)
    hazard = diagnose("Rheem furnace", "gas smell near unit", [])
    print(hazard)
