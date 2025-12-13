"""Evidence-first models for segment-based validation.

These models define what counts as "evidence" for a requirement evaluation,
and allow the backend/UI to show why a requirement is marked passed/failed/not_checked.

They are intentionally lightweight and optional: many pipelines do not yet provide
bounding boxes or entity IDs, so most fields are optional.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class EvidenceType(str, Enum):
    """Coarse taxonomy of evidence sources."""

    DIMENSION = "dimension"  # extracted dimension value+unit (e.g., 90 cm)
    TEXT = "text"  # OCR / annotation snippet
    STRUCTURAL_ELEMENT = "structural_element"  # door/window/wall object from extraction
    DERIVED = "derived"  # derived/aggregated inference from multiple pieces
    MISSING = "missing"  # negative evidence: we looked and couldn't find required info


class EvidenceBoundingBox(BaseModel):
    """Bounding box coordinates.

    Note: segment analyzers currently return different bbox formats across flows.
    Keep this generic and optional.
    """

    model_config = ConfigDict(populate_by_name=True)

    x: float = Field(..., ge=0, le=100)
    y: float = Field(..., ge=0, le=100)
    width: float = Field(..., ge=0, le=100)
    height: float = Field(..., ge=0, le=100)


class EvidenceItem(BaseModel):
    """A single evidence item supporting an evaluation."""

    model_config = ConfigDict(populate_by_name=True)

    evidence_type: EvidenceType

    # Optional numeric measurement
    value: Optional[float] = None
    unit: Optional[str] = None

    # Optional text / snippet used
    text: Optional[str] = None

    # Context
    element: Optional[str] = None  # e.g., "door", "wall", "room height"
    location: Optional[str] = None  # free-form (as extracted)

    # Anchors
    bounding_box: Optional[EvidenceBoundingBox] = None

    # Any other raw fields from the extractor
    raw: Optional[Dict[str, Any]] = None


class RequirementEvaluationStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    NOT_CHECKED = "not_checked"


class RequirementEvaluation(BaseModel):
    """Evidence-first status for a single official requirement (e.g., "2.1")."""

    model_config = ConfigDict(populate_by_name=True)

    requirement_id: str = Field(..., description="Official requirement id (e.g., '2.1')")
    status: RequirementEvaluationStatus

    # If NOT_CHECKED, provide a stable reason string for UI.
    reason_not_checked: Optional[str] = None

    # Evidence supporting pass/fail, or evidence describing what was missing.
    evidence: List[EvidenceItem] = Field(default_factory=list)

    # Optional human-facing notes
    notes_he: Optional[str] = None
