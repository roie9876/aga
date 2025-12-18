"""API endpoints for submission preflight checks."""

from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException

from src.azure import get_cosmos_client
from src.config import settings
from src.models.preflight import (
    InlineSubmissionPreflightRequest,
    SubmissionPreflightRequest,
    SubmissionPreflightResponse,
)
from src.services.submission_preflight import run_submission_preflight
from src.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/preflight", tags=["Preflight"])


@router.post("", response_model=SubmissionPreflightResponse)
async def run_preflight(request: SubmissionPreflightRequest) -> SubmissionPreflightResponse:
    """Run completeness (threshold) checks before starting validation."""
    if request.mode != "segments":
        # For now: preflight is designed for the segment workflow.
        raise HTTPException(status_code=400, detail="מצב preflight נתמך כרגע רק עבור segments")

    t0 = time.monotonic()
    logger.info(
        "Preflight started",
        decomposition_id=request.decomposition_id,
        approved_segments=len(request.approved_segment_ids or []),
        strict=bool(request.strict),
        run_llm_checks=bool(request.run_llm_checks),
    )

    try:
        cosmos_client = get_cosmos_client()
        query = """
            SELECT * FROM c
            WHERE c.id = @decomposition_id
            AND c.type = 'decomposition'
        """
        items = await cosmos_client.query_items(
            query=query,
            parameters=[{"name": "@decomposition_id", "value": request.decomposition_id}],
        )
        if not items:
            raise HTTPException(status_code=404, detail="פירוק לא נמצא")

        decomposition = items[0]

        segment_count = 0
        try:
            segment_count = len(decomposition.get("segments", []) or [])
        except Exception:
            segment_count = 0

        passed, checks = await run_submission_preflight(
            decomposition=decomposition,
            approved_segment_ids=request.approved_segment_ids,
            strict=bool(request.strict),
            run_llm_checks=bool(request.run_llm_checks),
        )

        duration_ms = int((time.monotonic() - t0) * 1000)
        logger.info(
            "Preflight completed",
            decomposition_id=request.decomposition_id,
            duration_ms=duration_ms,
            passed=bool(passed),
            check_count=len(checks or []),
            segment_count=segment_count,
        )

        summary = "כל תנאי הסף עברו בהצלחה" if passed else "חלק מתנאי הסף נכשלו – יש להשלים מסמכים/חתימות"
        return SubmissionPreflightResponse(
            passed=passed,
            summary=summary,
            checks=checks,
        )

    except HTTPException:
        raise
    except Exception as e:
        duration_ms = int((time.monotonic() - t0) * 1000)
        logger.error("Preflight failed", decomposition_id=request.decomposition_id, error=str(e))
        logger.error("Preflight failed timing", decomposition_id=request.decomposition_id, duration_ms=duration_ms)
        raise HTTPException(status_code=500, detail="שגיאה בהרצת בדיקת תנאי סף")


@router.post("/inline", response_model=SubmissionPreflightResponse)
async def run_preflight_inline(request: InlineSubmissionPreflightRequest) -> SubmissionPreflightResponse:
    """Local-only helper: run preflight using an inline decomposition payload.

    This avoids Cosmos/Azure dependencies and is useful for quickly validating the
    preflight engine in development.
    """
    if settings.is_production:
        raise HTTPException(status_code=404, detail="Not found")

    try:
        passed, checks = await run_submission_preflight(
            decomposition=request.decomposition,
            approved_segment_ids=request.approved_segment_ids,
            strict=bool(request.strict),
            run_llm_checks=bool(request.run_llm_checks),
        )

        summary = "כל תנאי הסף עברו בהצלחה" if passed else "חלק מתנאי הסף נכשלו – יש להשלים מסמכים/חתימות"
        return SubmissionPreflightResponse(passed=passed, summary=summary, checks=checks)
    except Exception as e:
        logger.error("Inline preflight failed", error=str(e))
        raise HTTPException(status_code=500, detail="שגיאה בהרצת בדיקת תנאי סף")
