"""API endpoints for submission preflight checks."""

from __future__ import annotations

import time
from datetime import datetime
from uuid import uuid4

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

        preflight_id = f"preflight_{uuid4().hex}"
        created_at = datetime.utcnow().isoformat()
        metadata = decomposition.get("metadata") if isinstance(decomposition, dict) else {}
        plan_name = (
            (metadata or {}).get("project_name")
            or (metadata or {}).get("plan_number")
            or f"תכנית {str(request.decomposition_id)[:8]}"
        )

        preflight_doc = {
            "id": preflight_id,
            "type": "submission_preflight",
            "preflight_id": preflight_id,
            "decomposition_id": request.decomposition_id,
            "approved_segment_ids": list(request.approved_segment_ids or []),
            "strict": bool(request.strict),
            "run_llm_checks": bool(request.run_llm_checks),
            "passed": bool(passed),
            "summary": summary,
            "checks": [c.model_dump() for c in checks],
            "created_at": created_at,
            "plan_name": plan_name,
            "segment_count": segment_count,
        }

        try:
            await cosmos_client.upsert_item(preflight_doc)
        except Exception as e:
            logger.error(
                "Failed to persist preflight history",
                decomposition_id=request.decomposition_id,
                error=str(e),
            )

        return SubmissionPreflightResponse(
            passed=passed,
            summary=summary,
            checks=checks,
            preflight_id=preflight_id,
            created_at=created_at,
            decomposition_id=request.decomposition_id,
            approved_segment_ids=list(request.approved_segment_ids or []),
            strict=bool(request.strict),
            run_llm_checks=bool(request.run_llm_checks),
            segment_count=segment_count,
            plan_name=plan_name,
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
        created_at = datetime.utcnow().isoformat()
        preflight_id = f"preflight_inline_{uuid4().hex}"
        return SubmissionPreflightResponse(
            passed=passed,
            summary=summary,
            checks=checks,
            preflight_id=preflight_id,
            created_at=created_at,
            approved_segment_ids=list(request.approved_segment_ids or []),
            strict=bool(request.strict),
            run_llm_checks=bool(request.run_llm_checks),
        )
    except Exception as e:
        logger.error("Inline preflight failed", error=str(e))
        raise HTTPException(status_code=500, detail="שגיאה בהרצת בדיקת תנאי סף")


@router.get("/history")
async def list_preflight_history():
    """List preflight history (newest first)."""
    logger.info("Fetching preflight history")

    try:
        cosmos_client = get_cosmos_client()
        query = """
            SELECT c.id, c.preflight_id, c.decomposition_id, c.plan_name,
                   c.segment_count, c.passed, c.summary, c.created_at
            FROM c
            WHERE c.type = 'submission_preflight'
            ORDER BY c._ts DESC
        """
        results = await cosmos_client.query_items(query, [])
        return {"total": len(results), "preflights": results}
    except Exception as e:
        logger.error("Failed to fetch preflight history", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to fetch preflight history: {str(e)}")


@router.get("/{preflight_id}")
async def get_preflight(preflight_id: str):
    """Get detailed preflight results by ID."""
    logger.info("Fetching preflight results", preflight_id=preflight_id)

    try:
        cosmos_client = get_cosmos_client()
        query = """
            SELECT * FROM c
            WHERE c.id = @preflight_id
            AND c.type = 'submission_preflight'
        """
        parameters = [{"name": "@preflight_id", "value": preflight_id}]
        results = await cosmos_client.query_items(query, parameters)
        if not results:
            raise HTTPException(status_code=404, detail=f"Preflight not found: {preflight_id}")
        return results[0]
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to fetch preflight results", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to fetch preflight results: {str(e)}")
