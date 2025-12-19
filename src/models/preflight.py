"""Models for submission preflight (completeness) checks."""

from __future__ import annotations

from enum import Enum
from typing import List, Optional, Dict, Any, Literal

from pydantic import BaseModel, Field


class PreflightStatus(str, Enum):
    """Status of a single preflight check."""

    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    NOT_APPLICABLE = "not_applicable"
    ERROR = "error"


class PreflightCheckResult(BaseModel):
    """Result for a single preflight check."""

    check_id: str = Field(..., description="Check identifier (e.g., PF-01)")
    title: str = Field(..., description="Short Hebrew title")
    explanation: Optional[str] = Field(
        default=None,
        description=(
            "Short Hebrew explanation of what this check is verifying (shown in UI when the user clicks)."
        ),
    )
    source_pages: List[int] = Field(default_factory=list, description="Relevant PDF page numbers")
    status: PreflightStatus = Field(..., description="Pass/fail/warn")
    details: str = Field(..., description="User-facing details in Hebrew")
    evidence_segment_ids: List[str] = Field(default_factory=list, description="Segment IDs that support this check")
    debug: Optional[Dict[str, Any]] = Field(default=None, description="Optional debug payload")


class SubmissionPreflightRequest(BaseModel):
    """Request to run submission preflight checks for a decomposition."""

    decomposition_id: str = Field(..., description="Decomposition ID")
    approved_segment_ids: List[str] = Field(..., min_length=1, description="Approved segment IDs")
    mode: Literal["segments", "full_plan"] = Field(
        "segments",
        description="Preflight mode. Typically 'segments' for the decomposition workflow.",
    )
    strict: bool = Field(
        False,
        description=(
            "If true, treat some otherwise-warning checks as failures (stricter gate before validation)."
        ),
    )
    run_llm_checks: bool = Field(
        True,
        description=(
            "If true, attempt lightweight LLM-vision checks (e.g., signature block presence) when available. "
            "If LLM is unavailable, the server will fall back to heuristics."
        ),
    )


class SubmissionPreflightResponse(BaseModel):
    """Response with preflight results."""

    passed: bool = Field(..., description="Whether the submission meets the threshold")
    summary: str = Field(..., description="One-line Hebrew summary")
    checks: List[PreflightCheckResult] = Field(default_factory=list)
    preflight_id: Optional[str] = Field(default=None, description="Preflight run identifier")
    created_at: Optional[str] = Field(default=None, description="ISO timestamp when preflight ran")
    decomposition_id: Optional[str] = Field(default=None, description="Decomposition ID")
    approved_segment_ids: List[str] = Field(default_factory=list, description="Approved segment IDs")
    strict: Optional[bool] = Field(default=None, description="Strict mode")
    run_llm_checks: Optional[bool] = Field(default=None, description="Whether LLM checks ran")
    segment_count: Optional[int] = Field(default=None, description="Segments count in decomposition")
    plan_name: Optional[str] = Field(default=None, description="Plan name if available")


class InlineSubmissionPreflightRequest(BaseModel):
    """Local/testing request: run preflight on an inline decomposition payload.

    This is meant for local verification without Cosmos DB.
    """

    decomposition: Dict[str, Any] = Field(..., description="Decomposition document payload (type='decomposition')")
    approved_segment_ids: List[str] = Field(..., min_length=1, description="Approved segment IDs")
    strict: bool = Field(False, description="Same as SubmissionPreflightRequest.strict")
    run_llm_checks: bool = Field(True, description="Same as SubmissionPreflightRequest.run_llm_checks")
