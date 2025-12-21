"""Segment-based validation API endpoints for decomposed plans."""
import asyncio
import json
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Literal

from src.azure import get_cosmos_client, get_openai_client
from src.azure.blob_client import get_blob_client
from src.config import settings
from src.services.segment_analyzer import get_segment_analyzer
from src.services.mamad_validator import get_mamad_validator
from src.services.requirements_coverage import get_coverage_tracker
from src.services.external_wall_context import (
    SegmentCandidate,
    select_floor_plan_candidate,
    select_mamad_reference_candidate,
    infer_external_wall_context,
    inject_external_wall_count,
)
from src.utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


LEGACY_DEFAULT_CHECK_GROUPS: List[str] = ["walls", "heights", "doors", "windows"]


def _ndjson(obj: Dict[str, Any]) -> bytes:
    return (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")


class SegmentValidationRequest(BaseModel):
    """Request to validate approved segments."""
    decomposition_id: str = Field(..., description="Decomposition ID")
    approved_segment_ids: List[str] = Field(..., description="List of approved segment IDs to validate")
    mode: Literal["segments", "full_plan"] = Field(
        "segments",
        description="Validation mode: 'segments' validates selected segment crops; 'full_plan' validates the full plan image as a single unit"
    )
    demo_mode: bool = Field(
        False,
        description=(
            "If true, run a reduced subset of validations for demo purposes (does not remove rules from the system)."
        ),
    )

    check_groups: List[
        Literal["walls", "heights", "doors", "windows", "materials", "rebar", "notes"]
    ] = Field(
        default_factory=lambda: ["walls", "heights", "doors", "windows"],
        description=(
            "Which groups of checks to run. The app still decides which validators are relevant per segment category; "
            "this list only enables/disables groups to save time during early testing."
        ),
    )
    enabled_requirements: Optional[List[str]] = Field(
        default=None,
        description="Explicit list of requirement IDs to run (e.g., ['1.2','2.3']). Overrides check_groups if provided.",
    )


class SegmentValidationResponse(BaseModel):
    """Response from segment validation."""
    validation_id: str = Field(..., description="Validation result ID")
    created_at: Optional[str] = Field(None, description="UTC timestamp when this validation run was created")
    total_segments: int = Field(..., description="Total segments validated")
    passed: int = Field(..., description="Segments that passed")
    failed: int = Field(..., description="Segments that failed")
    warnings: int = Field(..., description="Segments with warnings")
    analyzed_segments: List[Dict[str, Any]] = Field(default_factory=list, description="Detailed analysis for each segment")
    coverage: Optional[Dict[str, Any]] = Field(None, description="Requirements coverage report")
    demo_mode: bool = Field(False, description="Whether demo_mode was enabled for this validation run")
    demo_focus: Optional[str] = Field(None, description="Optional note describing the demo focus")


@router.post("/validate-segments", response_model=SegmentValidationResponse)
async def validate_segments(request: SegmentValidationRequest):
    """Validate approved segments from decomposition.
    
    This endpoint:
    1. Fetches the decomposition and approved segments
    2. For each segment, analyzes the cropped image with GPT
    3. Extracts measurements, text, and structural details
    4. Validates against ממ"ד requirements
    5. Stores validation results
    
    Args:
        request: Validation request with decomposition ID and segment IDs
        
    Returns:
        Validation summary with pass/fail counts
    """
    logger.info("Starting segment validation",
               decomposition_id=request.decomposition_id,
               segment_count=len(request.approved_segment_ids))
    
    try:
        # 1. Fetch decomposition from Cosmos DB
        cosmos_client = get_cosmos_client()
        
        query = """
            SELECT * FROM c 
            WHERE c.id = @decomposition_id 
            AND c.type = 'decomposition'
        """
        parameters = [{"name": "@decomposition_id", "value": request.decomposition_id}]
        
        results = await cosmos_client.query_items(query, parameters)
        
        if not results:
            raise HTTPException(
                status_code=404,
                detail=f"Decomposition not found: {request.decomposition_id}"
            )
        
        decomposition = results[0]
        full_plan_url = decomposition.get("full_plan_url")
        
        # 2. Determine what to validate (segments vs full plan)
        all_segments = decomposition.get("segments", [])

        if request.mode == "full_plan":
            full_plan_url = decomposition.get("full_plan_url")
            if not full_plan_url:
                raise HTTPException(status_code=400, detail="Decomposition missing full_plan_url")
            approved_segments = [
                {
                    "segment_id": "full_plan",
                    "blob_url": full_plan_url,
                    "type": "floor_plan",
                    "description": "תוכנית מלאה (ללא חיתוך)"
                }
            ]
        else:
            approved_segments = [
                seg for seg in all_segments
                if seg.get("segment_id") in request.approved_segment_ids
            ]

            if not approved_segments:
                raise HTTPException(
                    status_code=400,
                    detail="No approved segments found"
                )
        
        logger.info("Found approved segments",
                   total=len(all_segments),
                   approved=len(approved_segments))
        
        # 3. Analyze each segment with GPT (Part 3 - OCR + Interpretation)
        logger.info("Starting segment analysis with GPT-5.1",
                   segment_count=len(approved_segments))
        
        analyzer = get_segment_analyzer()
        validator = get_mamad_validator()
        analyzed_segments = []
        passed_requirements_global: set[str] = set()

        demo_focus_note = None
        if request.demo_mode:
            demo_focus_note = "בדמו המערכת מתמקדת בדרישות 1–3 (קירות, גובה/נפח, פתחים) כדי לקצר זמן ריצה." 
        
        # IMPORTANT: Frontend may send an explicit empty list; treat it as "use defaults".
        # Back-compat: the legacy default of 4 groups is treated as "run all validations"
        # (i.e., don't restrict enabled_requirements) so we can cover materials/rebar/notes too.
        effective_check_groups = request.check_groups or LEGACY_DEFAULT_CHECK_GROUPS

        # Prefer floor plan first so we can infer external wall count for REQ 1.2 early.
        approved_segments.sort(key=lambda s: 0 if str(s.get("type")) == "floor_plan" else 1)

        # Stage A: Base GPT analysis for all segments (parallel).
        async def _safe_analyze(seg: Dict[str, Any]) -> Dict[str, Any]:
            seg_id = str(seg.get("segment_id"))
            try:
                return await analyzer.analyze_segment(
                    segment_id=seg_id,
                    segment_blob_url=str(seg.get("blob_url")),
                    segment_type=str(seg.get("type")),
                    segment_description=str(seg.get("description") or ""),
                )
            except Exception as e:
                logger.error(
                    "Failed to analyze segment",
                    segment_id=seg_id,
                    error=str(e),
                )
                return {
                    "segment_id": seg_id,
                    "status": "error",
                    "error": str(e),
                }

        base_results: List[Dict[str, Any]] = await asyncio.gather(
            *[_safe_analyze(seg) for seg in approved_segments]
        )

        analysis_by_id: Dict[str, Dict[str, Any]] = {}
        for res in base_results:
            if isinstance(res, dict) and isinstance(res.get("segment_id"), str):
                analysis_by_id[res["segment_id"]] = res

        # Stage B: Cross-segment external-wall inference (1.2 prerequisite) + injection.
        analysis_candidates: List[SegmentCandidate] = []
        for seg in approved_segments:
            seg_id = str(seg.get("segment_id"))
            res = analysis_by_id.get(seg_id)
            if not isinstance(res, dict):
                continue
            if res.get("status") != "analyzed":
                continue
            data = res.get("analysis_data")
            if not isinstance(data, dict):
                continue
            analysis_candidates.append(
                SegmentCandidate(
                    segment_id=seg_id,
                    blob_url=str(seg.get("blob_url")),
                    segment_type=str(seg.get("type")),
                    description=str(seg.get("description") or ""),
                    analysis_data=data,
                )
            )

        external_wall_ctx: Optional[Dict[str, Any]] = None
        if analysis_candidates:
            floor_plan = select_floor_plan_candidate(analysis_candidates)
            mamad_ref = select_mamad_reference_candidate(analysis_candidates)
            if floor_plan and mamad_ref and floor_plan.segment_id != mamad_ref.segment_id:
                try:
                    external_wall_ctx = await infer_external_wall_context(
                        analyzer=analyzer,
                        floor_plan=floor_plan,
                        mamad_reference=mamad_ref,
                    )
                except Exception as e:
                    logger.info(
                        "External wall count inference failed; continuing without it",
                        error=str(e),
                    )

        if (
            external_wall_ctx
            and isinstance(external_wall_ctx, dict)
            and external_wall_ctx.get("external_wall_count") is not None
        ):
            inject_external_wall_count(
                analyzed_segments=list(analysis_by_id.values()),
                external_wall_count=int(external_wall_ctx.get("external_wall_count")),
                context=external_wall_ctx,
            )

        # Stage C: Focused extraction passes (parallel, per segment).
        async def _apply_focused_extraction(seg: Dict[str, Any], analysis_result: Dict[str, Any]) -> None:
            if analysis_result.get("status") != "analyzed":
                return

            data = analysis_result.get("analysis_data")
            if not isinstance(data, dict):
                return

            classification = data.get("classification", {}) if isinstance(data, dict) else {}
            primary_category = str(classification.get("primary_category") or "")
            secondary_categories = classification.get("secondary_categories") if isinstance(classification.get("secondary_categories"), list) else []
            cat_joined = "|".join([primary_category] + [str(x) for x in secondary_categories])
            cat_upper = cat_joined.upper()

            # Doors
            if ("doors" in effective_check_groups) or ("DOOR_DETAILS" in cat_upper):
                try:
                    focus = await analyzer.extract_door_spacing(
                        segment_id=str(seg.get("segment_id")),
                        segment_blob_url=str(seg.get("blob_url")),
                        segment_type=str(seg.get("type") or "unknown"),
                        segment_description=str(seg.get("description") or ""),
                        full_plan_blob_url=full_plan_url,
                        segment_bbox=seg.get("bounding_box"),
                    )

                    base = analysis_result.get("analysis_data") or {}
                    if isinstance(base, dict) and isinstance(focus, dict):
                        base.setdefault("door_spacing_focus", focus.get("door_spacing_focus"))
                        if focus.get("door_roi"):
                            base.setdefault("door_roi", focus.get("door_roi"))
                        base.setdefault("structural_elements", [])
                        base.setdefault("dimensions", [])
                        base.setdefault("text_items", [])

                        focus_payload = focus.get("door_spacing_focus")
                        if isinstance(focus_payload, dict):
                            doors = focus_payload.get("doors")
                            if isinstance(doors, list):
                                for d in doors:
                                    if not isinstance(d, dict):
                                        continue
                                    internal_cm = d.get("internal_clearance_cm")
                                    external_cm = d.get("external_clearance_cm")
                                    confidence = d.get("confidence")
                                    location = d.get("location")

                                    base["structural_elements"].append(
                                        {
                                            "type": "door",
                                            "spacing_internal_cm": internal_cm,
                                            "spacing_external_cm": external_cm,
                                            "spacing_confidence": confidence,
                                            "location": location,
                                            "notes": "door_spacing_focus",
                                            "evidence": d.get("evidence"),
                                        }
                                    )

                                    if internal_cm is not None:
                                        base["dimensions"].append(
                                            {
                                                "value": internal_cm,
                                                "unit": "cm",
                                                "element": "door_spacing_internal",
                                                "location": location or "",
                                            }
                                        )
                                    if external_cm is not None:
                                        base["dimensions"].append(
                                            {
                                                "value": external_cm,
                                                "unit": "cm",
                                                "element": "door_spacing_external",
                                                "location": location or "",
                                            }
                                        )

                                    ev_list = d.get("evidence")
                                    if isinstance(ev_list, list):
                                        for ev in ev_list[:6]:
                                            if not isinstance(ev, str) or not ev.strip():
                                                continue
                                            base["text_items"].append(
                                                {
                                                    "text": ev.strip(),
                                                    "language": "hebrew",
                                                    "type": "dimension",
                                                }
                                            )

                        analysis_result["analysis_data"] = base
                except Exception as e:
                    logger.warning(
                        "Focused door-spacing extraction failed; continuing with base analysis",
                        segment_id=str(seg.get("segment_id")),
                        error=str(e),
                    )

            # Walls
            if ("walls" in effective_check_groups) or ("WALL_SECTION" in cat_upper):
                try:
                    wall_focus = await analyzer.extract_wall_thickness(
                        segment_id=str(seg.get("segment_id")),
                        segment_blob_url=str(seg.get("blob_url")),
                        segment_type=str(seg.get("type") or "unknown"),
                        segment_description=str(seg.get("description") or ""),
                    )
                    base = analysis_result.get("analysis_data") or {}
                    if isinstance(base, dict) and isinstance(wall_focus, dict):
                        base.setdefault("wall_thickness_focus", wall_focus.get("wall_thickness_focus"))
                        if wall_focus.get("wall_roi"):
                            base.setdefault("wall_roi", wall_focus.get("wall_roi"))
                        base.setdefault("structural_elements", [])
                        base.setdefault("dimensions", [])
                        base.setdefault("text_items", [])

                        payload = wall_focus.get("wall_thickness_focus")
                        if isinstance(payload, dict) and isinstance(payload.get("walls"), list):
                            for w in payload.get("walls"):
                                if not isinstance(w, dict):
                                    continue
                                thickness_cm = w.get("thickness_cm")
                                conf = w.get("confidence")
                                location = w.get("location")
                                evidence = w.get("evidence")
                                if thickness_cm is not None:
                                    base["structural_elements"].append(
                                        {
                                            "type": "wall",
                                            "thickness": f"{thickness_cm} cm",
                                            "location": location or "",
                                            "notes": "wall_thickness_focus",
                                            "confidence": conf,
                                            "evidence": evidence,
                                        }
                                    )
                                    base["dimensions"].append(
                                        {
                                            "value": thickness_cm,
                                            "unit": "cm",
                                            "element": "wall thickness",
                                            "location": location or "",
                                        }
                                    )
                                if isinstance(evidence, list):
                                    for ev in evidence[:6]:
                                        if isinstance(ev, str) and ev.strip():
                                            base["text_items"].append(
                                                {"text": ev.strip(), "language": "hebrew", "type": "dimension"}
                                            )
                        analysis_result["analysis_data"] = base
                except Exception as e:
                    logger.warning(
                        "Focused wall-thickness extraction failed; continuing with base analysis",
                        segment_id=str(seg.get("segment_id")),
                        error=str(e),
                    )

            # Heights
            if ("heights" in effective_check_groups) or ("SECTIONS" in cat_upper) or ("ROOM_LAYOUT" in cat_upper):
                try:
                    height_focus = await analyzer.extract_room_height(
                        segment_id=str(seg.get("segment_id")),
                        segment_blob_url=str(seg.get("blob_url")),
                        segment_type=str(seg.get("type") or "unknown"),
                        segment_description=str(seg.get("description") or ""),
                    )
                    base = analysis_result.get("analysis_data") or {}
                    if isinstance(base, dict) and isinstance(height_focus, dict):
                        base.setdefault("room_height_focus", height_focus.get("room_height_focus"))
                        if height_focus.get("height_roi"):
                            base.setdefault("height_roi", height_focus.get("height_roi"))
                        base.setdefault("dimensions", [])
                        base.setdefault("text_items", [])

                        payload = height_focus.get("room_height_focus")
                        if isinstance(payload, dict) and isinstance(payload.get("heights"), list):
                            for h in payload.get("heights"):
                                if not isinstance(h, dict):
                                    continue
                                height_m = h.get("height_m")
                                conf = h.get("confidence")
                                location = h.get("location")
                                evidence = h.get("evidence")
                                if height_m is not None:
                                    base["dimensions"].append(
                                        {
                                            "value": height_m,
                                            "unit": "m",
                                            "element": "room height",
                                            "location": location or "",
                                            "confidence": conf,
                                        }
                                    )
                                if isinstance(evidence, list):
                                    for ev in evidence[:6]:
                                        if isinstance(ev, str) and ev.strip():
                                            base["text_items"].append(
                                                {"text": ev.strip(), "language": "hebrew", "type": "dimension"}
                                            )
                        analysis_result["analysis_data"] = base
                except Exception as e:
                    logger.warning(
                        "Focused room-height extraction failed; continuing with base analysis",
                        segment_id=str(seg.get("segment_id")),
                        error=str(e),
                    )

            # Windows
            if ("windows" in effective_check_groups) or ("WINDOW_DETAILS" in cat_upper):
                try:
                    window_focus = await analyzer.extract_window_spacing(
                        segment_id=str(seg.get("segment_id")),
                        segment_blob_url=str(seg.get("blob_url")),
                        segment_type=str(seg.get("type") or "unknown"),
                        segment_description=str(seg.get("description") or ""),
                    )
                    base = analysis_result.get("analysis_data") or {}
                    if isinstance(base, dict) and isinstance(window_focus, dict):
                        base.setdefault("window_spacing_focus", window_focus.get("window_spacing_focus"))
                        if window_focus.get("window_roi"):
                            base.setdefault("window_roi", window_focus.get("window_roi"))
                        base.setdefault("text_items", [])
                        base.setdefault("dimensions", [])

                        payload = window_focus.get("window_spacing_focus")
                        if isinstance(payload, dict):
                            ev_texts = payload.get("evidence_texts")
                            if isinstance(ev_texts, list):
                                for ev in ev_texts[:10]:
                                    if isinstance(ev, str) and ev.strip():
                                        base["text_items"].append(
                                            {"text": ev.strip(), "language": "hebrew", "type": "dimension"}
                                        )

                            windows_payload = payload.get("windows")
                            if isinstance(windows_payload, list):
                                for w in windows_payload[:6]:
                                    if not isinstance(w, dict):
                                        continue
                                    conf = w.get("confidence")
                                    location = w.get("location") or ""

                                    def _add_dim(key: str, element: str) -> None:
                                        val = w.get(key)
                                        if isinstance(val, (int, float)):
                                            base["dimensions"].append(
                                                {
                                                    "value": float(val),
                                                    "unit": "cm",
                                                    "element": element,
                                                    "location": location,
                                                    "confidence": conf,
                                                }
                                            )

                                    _add_dim("niche_to_niche_cm", "window niche spacing")
                                    _add_dim("light_openings_spacing_cm", "window light openings spacing")
                                    _add_dim("to_perpendicular_wall_cm", "window to perpendicular wall")
                                    _add_dim("same_wall_door_separation_cm", "window-door separation")
                                    _add_dim("door_height_cm", "door height")
                                    _add_dim("concrete_wall_thickness_cm", "concrete wall thickness")

                                    ev_list = w.get("evidence")
                                    if isinstance(ev_list, list):
                                        for ev in ev_list[:8]:
                                            if isinstance(ev, str) and ev.strip():
                                                base["text_items"].append(
                                                    {"text": ev.strip(), "language": "hebrew", "type": "dimension"}
                                                )

                                    if w.get("has_concrete_wall_between_openings") is True:
                                        base["text_items"].append(
                                            {
                                                "text": "קיים קיר בטון בין דלת לחלון (לפי זיהוי ממוקד)",
                                                "language": "hebrew",
                                                "type": "note",
                                            }
                                        )
                        analysis_result["analysis_data"] = base
                except Exception as e:
                    logger.warning(
                        "Focused window-spacing extraction failed; continuing with base analysis",
                        segment_id=str(seg.get("segment_id")),
                        error=str(e),
                    )

            # Materials
            if ("materials" in effective_check_groups) or ("MATERIALS_SPECS" in cat_upper):
                try:
                    materials_focus = await analyzer.extract_materials_specs(
                        segment_id=str(seg.get("segment_id")),
                        segment_blob_url=str(seg.get("blob_url")),
                        segment_type=str(seg.get("type") or "unknown"),
                        segment_description=str(seg.get("description") or ""),
                    )
                    base = analysis_result.get("analysis_data") or {}
                    if isinstance(base, dict) and isinstance(materials_focus, dict):
                        base.setdefault("materials_focus", materials_focus.get("materials_focus"))
                        if materials_focus.get("materials_roi"):
                            base.setdefault("materials_roi", materials_focus.get("materials_roi"))
                        base.setdefault("materials", [])
                        base.setdefault("text_items", [])

                        payload = materials_focus.get("materials_focus")
                        if isinstance(payload, dict) and isinstance(payload.get("materials"), list):
                            for m in payload.get("materials"):
                                if not isinstance(m, dict):
                                    continue
                                base["materials"].append(
                                    {
                                        "type": m.get("type"),
                                        "grade": m.get("grade"),
                                        "notes": m.get("notes"),
                                        "confidence": m.get("confidence"),
                                        "evidence": m.get("evidence"),
                                    }
                                )
                                ev_list = m.get("evidence")
                                if isinstance(ev_list, list):
                                    for ev in ev_list[:6]:
                                        if isinstance(ev, str) and ev.strip():
                                            base["text_items"].append(
                                                {"text": ev.strip(), "language": "hebrew", "type": "note"}
                                            )
                        analysis_result["analysis_data"] = base
                except Exception as e:
                    logger.warning(
                        "Focused materials extraction failed; continuing with base analysis",
                        segment_id=str(seg.get("segment_id")),
                        error=str(e),
                    )

            # Rebar
            if ("rebar" in effective_check_groups) or ("REBAR_DETAILS" in cat_upper):
                try:
                    rebar_focus = await analyzer.extract_rebar_specs(
                        segment_id=str(seg.get("segment_id")),
                        segment_blob_url=str(seg.get("blob_url")),
                        segment_type=str(seg.get("type") or "unknown"),
                        segment_description=str(seg.get("description") or ""),
                    )
                    base = analysis_result.get("analysis_data") or {}
                    if isinstance(base, dict) and isinstance(rebar_focus, dict):
                        base.setdefault("rebar_focus", rebar_focus.get("rebar_focus"))
                        if rebar_focus.get("rebar_roi"):
                            base.setdefault("rebar_roi", rebar_focus.get("rebar_roi"))
                        base.setdefault("rebar_details", [])
                        base.setdefault("text_items", [])

                        payload = rebar_focus.get("rebar_focus")
                        if isinstance(payload, dict) and isinstance(payload.get("rebars"), list):
                            for r in payload.get("rebars"):
                                if not isinstance(r, dict):
                                    continue
                                spacing_cm = r.get("spacing_cm")
                                location = r.get("location")
                                conf = r.get("confidence")
                                evidence = r.get("evidence")
                                if spacing_cm is not None:
                                    base["rebar_details"].append(
                                        {
                                            "spacing": f"{spacing_cm} cm",
                                            "location": location or "",
                                            "notes": "rebar_focus",
                                            "confidence": conf,
                                            "evidence": evidence,
                                        }
                                    )
                                if isinstance(evidence, list):
                                    for ev in evidence[:6]:
                                        if isinstance(ev, str) and ev.strip():
                                            base["text_items"].append(
                                                {"text": ev.strip(), "language": "hebrew", "type": "note"}
                                            )
                        analysis_result["analysis_data"] = base
                except Exception as e:
                    logger.warning(
                        "Focused rebar extraction failed; continuing with base analysis",
                        segment_id=str(seg.get("segment_id")),
                        error=str(e),
                    )

            # Notes
            if ("notes" in effective_check_groups) or ("GENERAL_NOTES" in cat_upper):
                try:
                    notes_focus = await analyzer.extract_general_notes(
                        segment_id=str(seg.get("segment_id")),
                        segment_blob_url=str(seg.get("blob_url")),
                        segment_type=str(seg.get("type") or "unknown"),
                        segment_description=str(seg.get("description") or ""),
                    )
                    base = analysis_result.get("analysis_data") or {}
                    if isinstance(base, dict) and isinstance(notes_focus, dict):
                        base.setdefault("notes_focus", notes_focus.get("notes_focus"))
                        if notes_focus.get("notes_roi"):
                            base.setdefault("notes_roi", notes_focus.get("notes_roi"))
                        base.setdefault("text_items", [])

                        payload = notes_focus.get("notes_focus")
                        if isinstance(payload, dict) and isinstance(payload.get("evidence_texts"), list):
                            for ev in payload.get("evidence_texts")[:10]:
                                if isinstance(ev, str) and ev.strip():
                                    base["text_items"].append(
                                        {"text": ev.strip(), "language": "hebrew", "type": "note"}
                                    )
                        analysis_result["analysis_data"] = base
                except Exception as e:
                    logger.warning(
                        "Focused notes extraction failed; continuing with base analysis",
                        segment_id=str(seg.get("segment_id")),
                        error=str(e),
                    )

        await asyncio.gather(
            *[
                _apply_focused_extraction(seg, analysis_by_id[str(seg.get("segment_id"))])
                for seg in approved_segments
                if str(seg.get("segment_id")) in analysis_by_id
            ]
        )

        # Stage D: Run validations in a deterministic order (keeps skip_requirements behavior stable).
        group_to_requirements: Dict[str, List[str]] = {
            "walls": ["1.1", "1.2"],
            "heights": ["2.1", "2.2"],
            "doors": ["3.1"],
            "windows": ["3.2"],
            "notes": ["4.2"],
            "materials": ["6.1", "6.2"],
            "rebar": ["6.3"],
        }

        restrict_by_groups = bool(request.check_groups) and (
            set(effective_check_groups) != set(LEGACY_DEFAULT_CHECK_GROUPS)
        )

        enabled_requirements = None
        if request.enabled_requirements:
            enabled_requirements = set(str(rid) for rid in request.enabled_requirements if str(rid).strip())
            restrict_by_groups = True
        elif restrict_by_groups:
            enabled_set: set[str] = set()
            for g in effective_check_groups:
                enabled_set.update(group_to_requirements.get(g, []))
            enabled_requirements = enabled_set

        analyzed_segments = []
        for seg in approved_segments:
            seg_id = str(seg.get("segment_id"))
            analysis_result = analysis_by_id.get(seg_id) or {
                "segment_id": seg_id,
                "status": "error",
                "error": "missing_analysis_result",
            }

            if analysis_result.get("status") == "analyzed":
                validation_result = validator.validate_segment(
                    analysis_result.get("analysis_data", {}),
                    demo_mode=request.demo_mode,
                    enabled_requirements=enabled_requirements,
                    skip_requirements=passed_requirements_global,
                )
                analysis_result["validation"] = validation_result

                for ev in (validation_result.get("requirement_evaluations") or []):
                    if isinstance(ev, dict) and ev.get("status") == "passed":
                        req_id = ev.get("requirement_id")
                        if isinstance(req_id, str) and req_id:
                            passed_requirements_global.add(req_id)

                classification = (
                    analysis_result.get("analysis_data", {}).get("classification", {})
                    if isinstance(analysis_result.get("analysis_data"), dict)
                    else {}
                )
                logger.info(
                    "Segment analyzed and validated",
                    segment_id=seg_id,
                    classification=classification.get("primary_category") if isinstance(classification, dict) else None,
                    relevant_requirements=classification.get("relevant_requirements") if isinstance(classification, dict) else None,
                    validation_passed=validation_result.get("passed", False),
                )
            else:
                analysis_result["validation"] = {
                    "status": "skipped" if analysis_result.get("status") != "error" else "error",
                    "passed": False,
                    "violations": [],
                }

            analyzed_segments.append(analysis_result)
        
        # 4. Store analysis results in Cosmos DB
        validation_id = f"val-{uuid.uuid4()}"
        created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        
        validation_doc = {
            "id": validation_id,
            "type": "segment_validation",
            "decomposition_id": request.decomposition_id,
            "validation_id": decomposition.get("validation_id"),
            "project_id": decomposition.get("project_id"),
            "analyzed_segments": analyzed_segments,
            "demo_mode": request.demo_mode,
            "demo_focus": demo_focus_note,
            "created_at": created_at,
        }
        
        await cosmos_client.create_item(validation_doc)
        
        # 5. Calculate pass/fail stats based on actual validation results
        passed = sum(
            1
            for s in analyzed_segments
            if s.get("validation", {}).get("status") == "passed"
        )
        failed = sum(
            1
            for s in analyzed_segments
            if s.get("status") == "error" or s.get("validation", {}).get("status") == "failed"
        )
        
        # Count warnings across all segments
        warnings = sum(
            s.get("validation", {}).get("warning_count", 0) 
            for s in analyzed_segments
        )
        
        # 6. Calculate requirements coverage
        tracker = get_coverage_tracker()
        coverage_report = tracker.calculate_coverage({
            "analyzed_segments": analyzed_segments
        })
        
        logger.info("Validation complete",
                   validation_id=validation_id,
                   passed=passed,
                   failed=failed,
                   warnings=warnings,
                   coverage_percentage=coverage_report["statistics"]["coverage_percentage"],
                   pass_percentage=coverage_report["statistics"]["pass_percentage"])
        
        return {
            "validation_id": validation_id,
            "created_at": created_at,
            "total_segments": len(approved_segments),
            "passed": passed,
            "failed": failed,
            "warnings": warnings,
            "analyzed_segments": analyzed_segments,  # Include detailed analysis
            "coverage": coverage_report,  # Include requirements coverage
            "demo_mode": request.demo_mode,
            "demo_focus": demo_focus_note,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Segment validation failed", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Validation failed: {str(e)}"
        )


@router.post("/validate-segments-stream")
async def validate_segments_stream(request: SegmentValidationRequest):
    """Validate approved segments and stream progress as NDJSON.

    Each line is a JSON object with an `event` field.
    The last line will be `{ "event": "final", "result": { ... } }`.
    """

    async def _gen():
        logger.info(
            "Starting segment validation (stream)",
            decomposition_id=request.decomposition_id,
            segment_count=len(request.approved_segment_ids),
        )

        # Emit an immediate heartbeat so the client can render UI even if the next
        # Azure/Cosmos call takes time.
        yield _ndjson(
            {
                "event": "stream_open",
                "decomposition_id": request.decomposition_id,
            }
        )

        # Some proxies/clients may buffer very small first chunks; emit a second
        # tiny event immediately to encourage early flush.
        yield _ndjson({"event": "prelude"})
        await asyncio.sleep(0)

        # 1. Fetch decomposition
        yield _ndjson({"event": "decomposition_fetch_start"})
        cosmos_client = get_cosmos_client()
        query = """
            SELECT * FROM c 
            WHERE c.id = @decomposition_id 
            AND c.type = 'decomposition'
        """
        parameters = [{"name": "@decomposition_id", "value": request.decomposition_id}]
        results = await cosmos_client.query_items(query, parameters)
        yield _ndjson({"event": "decomposition_fetch_done", "result_count": len(results)})
        if not results:
            yield _ndjson({"event": "error", "message": f"Decomposition not found: {request.decomposition_id}"})
            return
        decomposition = results[0]
        # Always keep this available for optional zoom-out context crops.
        full_plan_url = decomposition.get("full_plan_url")

        # 2. Determine segments
        all_segments = decomposition.get("segments", [])
        if request.mode == "full_plan":
            if not full_plan_url:
                yield _ndjson({"event": "error", "message": "Decomposition missing full_plan_url"})
                return
            approved_segments = [
                {
                    "segment_id": "full_plan",
                    "blob_url": full_plan_url,
                    "type": "floor_plan",
                    "description": "תוכנית מלאה (ללא חיתוך)",
                }
            ]
        else:
            approved_segments = [
                seg for seg in all_segments if seg.get("segment_id") in request.approved_segment_ids
            ]
            if not approved_segments:
                yield _ndjson({"event": "error", "message": "No approved segments found"})
                return

        total = len(approved_segments)
        yield _ndjson(
            {
                "event": "start",
                "decomposition_id": request.decomposition_id,
                "total_segments": total,
                "demo_mode": bool(request.demo_mode),
                "mode": request.mode,
            }
        )

        analyzer = get_segment_analyzer()
        validator = get_mamad_validator()
        analyzed_segments: List[Dict[str, Any]] = []
        passed_requirements_global: set[str] = set()

        demo_focus_note = None
        if request.demo_mode:
            demo_focus_note = "בדמו המערכת מתמקדת בדרישות 1–3 (קירות, גובה/נפח, פתחים) כדי לקצר זמן ריצה." 

        # IMPORTANT: Frontend may send an explicit empty list; treat it as "use defaults".
        # Back-compat: the legacy default of 4 groups is treated as "run all validations"
        # (i.e., don't restrict enabled_requirements) so we can cover materials/rebar/notes too.
        effective_check_groups = request.check_groups or LEGACY_DEFAULT_CHECK_GROUPS

        group_to_requirements: Dict[str, List[str]] = {
            "walls": ["1.1", "1.2"],
            "heights": ["2.1", "2.2"],
            "doors": ["3.1"],
            "windows": ["3.2"],
            "notes": ["4.2"],
            "materials": ["6.1", "6.2"],
            "rebar": ["6.3"],
        }

        # Only restrict enabled_requirements if the user explicitly selected a subset.
        # If they send the legacy default groups, treat it as "run everything relevant".
        restrict_by_groups = bool(request.check_groups) and (
            set(effective_check_groups) != set(LEGACY_DEFAULT_CHECK_GROUPS)
        )

        enabled_requirements = None
        if request.enabled_requirements:
            enabled_requirements = set(str(rid) for rid in request.enabled_requirements if str(rid).strip())
            restrict_by_groups = True
        elif restrict_by_groups:
            enabled_set: set[str] = set()
            for g in effective_check_groups:
                enabled_set.update(group_to_requirements.get(g, []))
            enabled_requirements = enabled_set

        yield _ndjson(
            {
                "event": "config",
                "check_groups": effective_check_groups,
                "enabled_requirements": sorted(enabled_requirements) if enabled_requirements is not None else None,
                "restricted": enabled_requirements is not None,
            }
        )

        # Prefer floor plan first so we can infer external wall count for REQ 1.2 early.
        approved_segments.sort(key=lambda s: 0 if str(s.get("type")) == "floor_plan" else 1)
        analysis_candidates: List[SegmentCandidate] = []
        analysis_results_by_id: Dict[str, Dict[str, Any]] = {}
        external_wall_ctx: Optional[Dict[str, Any]] = None
        external_wall_lock = asyncio.Lock()

        max_parallel_segments = max(1, int(settings.validation_max_concurrent_llm_requests or 1))
        segment_semaphore = asyncio.Semaphore(max_parallel_segments)

        async def _prepare_segment(segment: Dict[str, Any]) -> Dict[str, Any]:
            """Run analysis + focused extractors for a segment.

            Returns a dict with:
            - analysis_result: the analyzed segment dict (without sequential validation applied)
            - events: list of NDJSON bytes to emit AFTER analysis_start
            - emit_segment_done: whether to emit segment_done (preserves legacy behavior)
            """
            nonlocal external_wall_ctx
            seg_id = segment.get("segment_id")
            events: List[bytes] = []

            async with segment_semaphore:
                try:
                    analysis_result = await analyzer.analyze_segment(
                        segment_id=seg_id,
                        segment_blob_url=segment.get("blob_url"),
                        segment_type=segment.get("type"),
                        segment_description=segment.get("description"),
                    )

                    if analysis_result.get("status") != "analyzed":
                        analysis_result["validation"] = {"status": "skipped", "passed": False, "violations": []}
                        events.append(_ndjson({"event": "segment_error", "segment_id": seg_id, "message": "analysis_failed"}))
                        return {"analysis_result": analysis_result, "events": events, "emit_segment_done": True}

                    data = analysis_result.get("analysis_data") or {}

                    # Cross-segment wall-count inference: as soon as we have a floor plan + a MAMAD reference,
                    # infer the TOTAL external wall count and inject it into segments that don't have it.
                    if isinstance(data, dict):
                        candidate = SegmentCandidate(
                            segment_id=str(segment.get("segment_id")),
                            blob_url=str(segment.get("blob_url")),
                            segment_type=str(segment.get("type")),
                            description=str(segment.get("description") or ""),
                            analysis_data=data,
                        )
                    else:
                        candidate = None

                    async with external_wall_lock:
                        analysis_results_by_id[str(seg_id)] = analysis_result
                        if candidate is not None:
                            analysis_candidates.append(candidate)

                        if external_wall_ctx is None and analysis_candidates:
                            floor_plan = select_floor_plan_candidate(analysis_candidates)
                            mamad_ref = select_mamad_reference_candidate(analysis_candidates)
                            if floor_plan and mamad_ref and floor_plan.segment_id != mamad_ref.segment_id:
                                try:
                                    inferred = await infer_external_wall_context(
                                        analyzer=analyzer,
                                        floor_plan=floor_plan,
                                        mamad_reference=mamad_ref,
                                    )
                                    if isinstance(inferred, dict) and inferred.get("external_wall_count") is not None:
                                        external_wall_ctx = inferred
                                except Exception as e:
                                    logger.info(
                                        "External wall count inference failed; continuing without it",
                                        error=str(e),
                                    )

                        if (
                            external_wall_ctx
                            and isinstance(external_wall_ctx, dict)
                            and external_wall_ctx.get("external_wall_count") is not None
                        ):
                            # Inject into all completed analysis results so far.
                            try:
                                for _seg_id, _res in list(analysis_results_by_id.items()):
                                    if not isinstance(_res.get("analysis_data"), dict):
                                        continue
                                    inject_external_wall_count(
                                        analyzed_segments=[_res],
                                        external_wall_count=int(external_wall_ctx.get("external_wall_count")),
                                        context=external_wall_ctx,
                                    )
                            except Exception as e:
                                logger.info(
                                    "External wall count injection failed; continuing without it",
                                    error=str(e),
                                )

                    classification = data.get("classification", {}) if isinstance(data, dict) else {}
                    primary_category = str(classification.get("primary_category") or "")
                    secondary_categories = (
                        classification.get("secondary_categories")
                        if isinstance(classification.get("secondary_categories"), list)
                        else []
                    )
                    cat_joined = "|".join([primary_category] + [str(x) for x in secondary_categories])
                    cat_upper = cat_joined.upper()

                    events.append(
                        _ndjson(
                            {
                                "event": "analysis_done",
                                "segment_id": seg_id,
                                "text_items": len(data.get("text_items", []) or []) if isinstance(data, dict) else 0,
                                "dimensions": len(data.get("dimensions", []) or []) if isinstance(data, dict) else 0,
                                "structural_elements": len(data.get("structural_elements", []) or [])
                                if isinstance(data, dict)
                                else 0,
                                "tokens_used": data.get("tokens_used") if isinstance(data, dict) else None,
                            }
                        )
                    )

                    # Emit a user-facing (non-CoT) summary to display in real time.
                    evidence_list = classification.get("evidence") if isinstance(classification, dict) else None
                    events.append(
                        _ndjson(
                            {
                                "event": "analysis_summary",
                                "segment_id": seg_id,
                                "primary_category": primary_category,
                                "description_he": classification.get("description")
                                if isinstance(classification, dict)
                                else None,
                                "explanation_he": classification.get("explanation_he")
                                if isinstance(classification, dict)
                                else None,
                                "relevant_requirements": classification.get("relevant_requirements")
                                if isinstance(classification, dict)
                                else None,
                                "evidence": [e for e in (evidence_list or []) if isinstance(e, str) and e.strip()][:4],
                            }
                        )
                    )

                    if ("doors" in effective_check_groups) or ("DOOR_DETAILS" in cat_upper):
                        events.append(_ndjson({"event": "door_focus_start", "segment_id": seg_id}))
                        try:
                            focus = await analyzer.extract_door_spacing(
                                segment_id=seg_id,
                                segment_blob_url=segment.get("blob_url"),
                                segment_type=segment.get("type", "unknown"),
                                segment_description=segment.get("description", ""),
                                full_plan_blob_url=full_plan_url,
                                segment_bbox=segment.get("bounding_box"),
                            )

                            base = analysis_result.get("analysis_data") or {}
                            if isinstance(base, dict) and isinstance(focus, dict):
                                base.setdefault("door_spacing_focus", focus.get("door_spacing_focus"))
                                if focus.get("door_roi"):
                                    base.setdefault("door_roi", focus.get("door_roi"))
                                base.setdefault("structural_elements", [])
                                base.setdefault("dimensions", [])
                                base.setdefault("text_items", [])

                                focus_payload = focus.get("door_spacing_focus")
                                door_count = 0
                                best_conf = None
                                if isinstance(focus_payload, dict):
                                    doors = focus_payload.get("doors")
                                    if isinstance(doors, list):
                                        door_count = len([d for d in doors if isinstance(d, dict)])
                                        confidences = [
                                            d.get("confidence")
                                            for d in doors
                                            if isinstance(d, dict)
                                            and isinstance(d.get("confidence"), (int, float))
                                        ]
                                        best_conf = max(confidences) if confidences else None

                                        for d in doors:
                                            if not isinstance(d, dict):
                                                continue
                                            internal_cm = d.get("internal_clearance_cm")
                                            external_cm = d.get("external_clearance_cm")
                                            confidence = d.get("confidence")
                                            location = d.get("location")

                                            base["structural_elements"].append(
                                                {
                                                    "type": "door",
                                                    "spacing_internal_cm": internal_cm,
                                                    "spacing_external_cm": external_cm,
                                                    "spacing_confidence": confidence,
                                                    "location": location,
                                                    "notes": "door_spacing_focus",
                                                    "evidence": d.get("evidence"),
                                                }
                                            )

                                            if internal_cm is not None:
                                                base["dimensions"].append(
                                                    {
                                                        "value": internal_cm,
                                                        "unit": "cm",
                                                        "element": "door_spacing_internal",
                                                        "location": location or "",
                                                    }
                                                )
                                            if external_cm is not None:
                                                base["dimensions"].append(
                                                    {
                                                        "value": external_cm,
                                                        "unit": "cm",
                                                        "element": "door_spacing_external",
                                                        "location": location or "",
                                                    }
                                                )

                                            ev_list = d.get("evidence")
                                            if isinstance(ev_list, list):
                                                for ev in ev_list[:6]:
                                                    if not isinstance(ev, str) or not ev.strip():
                                                        continue
                                                    base["text_items"].append(
                                                        {
                                                            "text": ev.strip(),
                                                            "language": "hebrew",
                                                            "type": "dimension",
                                                        }
                                                    )

                                analysis_result["analysis_data"] = base

                            events.append(
                                _ndjson(
                                    {
                                        "event": "door_focus_done",
                                        "segment_id": seg_id,
                                        "doors_found": door_count,
                                        "best_confidence": best_conf,
                                    }
                                )
                            )

                            # Emit compact best-door summary for UX.
                            best_door = None
                            inside_outside_hint = None
                            evidence = []
                            if isinstance(focus_payload, dict):
                                inside_outside_hint = focus_payload.get("door_inside_outside_hint")
                                doors = focus_payload.get("doors")
                                if isinstance(doors, list):
                                    scored = [d for d in doors if isinstance(d, dict)]
                                    scored.sort(key=lambda d: float(d.get("confidence") or 0.0), reverse=True)
                                    best_door = scored[0] if scored else None
                                    evs = best_door.get("evidence") if isinstance(best_door, dict) else None
                                    if isinstance(evs, list):
                                        evidence = [e for e in evs if isinstance(e, str) and e.strip()][:4]

                            if isinstance(best_door, dict):
                                events.append(
                                    _ndjson(
                                        {
                                            "event": "door_focus_summary",
                                            "segment_id": seg_id,
                                            "internal_clearance_cm": best_door.get("internal_clearance_cm"),
                                            "external_clearance_cm": best_door.get("external_clearance_cm"),
                                            "confidence": best_door.get("confidence"),
                                            "inside_outside_hint": inside_outside_hint,
                                            "evidence": evidence,
                                        }
                                    )
                                )
                        except Exception as e:
                            events.append(
                                _ndjson(
                                    {
                                        "event": "door_focus_error",
                                        "segment_id": seg_id,
                                        "message": str(e),
                                    }
                                )
                            )

                    if ("walls" in effective_check_groups) or ("WALL_SECTION" in cat_upper):
                        events.append(_ndjson({"event": "wall_focus_start", "segment_id": seg_id}))
                        try:
                            wall_focus = await analyzer.extract_wall_thickness(
                                segment_id=seg_id,
                                segment_blob_url=segment.get("blob_url"),
                                segment_type=segment.get("type", "unknown"),
                                segment_description=segment.get("description", ""),
                            )

                            base = analysis_result.get("analysis_data") or {}
                            wall_count = 0
                            if isinstance(base, dict) and isinstance(wall_focus, dict):
                                base.setdefault("wall_thickness_focus", wall_focus.get("wall_thickness_focus"))
                                if wall_focus.get("wall_roi"):
                                    base.setdefault("wall_roi", wall_focus.get("wall_roi"))
                                base.setdefault("structural_elements", [])
                                base.setdefault("dimensions", [])
                                base.setdefault("text_items", [])

                                payload = wall_focus.get("wall_thickness_focus")
                                if isinstance(payload, dict) and isinstance(payload.get("walls"), list):
                                    for w in payload.get("walls"):
                                        if not isinstance(w, dict):
                                            continue
                                        wall_count += 1
                                        thickness_cm = w.get("thickness_cm")
                                        conf = w.get("confidence")
                                        location = w.get("location")
                                        evidence = w.get("evidence")
                                        if thickness_cm is not None:
                                            base["structural_elements"].append(
                                                {
                                                    "type": "wall",
                                                    "thickness": f"{thickness_cm} cm",
                                                    "location": location or "",
                                                    "notes": "wall_thickness_focus",
                                                    "confidence": conf,
                                                    "evidence": evidence,
                                                }
                                            )
                                            base["dimensions"].append(
                                                {
                                                    "value": thickness_cm,
                                                    "unit": "cm",
                                                    "element": "wall thickness",
                                                    "location": location or "",
                                                }
                                            )
                                        if isinstance(evidence, list):
                                            for ev in evidence[:6]:
                                                if isinstance(ev, str) and ev.strip():
                                                    base["text_items"].append(
                                                        {"text": ev.strip(), "language": "hebrew", "type": "dimension"}
                                                    )
                                analysis_result["analysis_data"] = base

                            events.append(_ndjson({"event": "wall_focus_done", "segment_id": seg_id, "walls_found": wall_count}))
                        except Exception as e:
                            events.append(_ndjson({"event": "wall_focus_error", "segment_id": seg_id, "message": str(e)}))

                    if ("heights" in effective_check_groups) or ("SECTIONS" in cat_upper) or ("ROOM_LAYOUT" in cat_upper):
                        events.append(_ndjson({"event": "height_focus_start", "segment_id": seg_id}))
                        try:
                            height_focus = await analyzer.extract_room_height(
                                segment_id=seg_id,
                                segment_blob_url=segment.get("blob_url"),
                                segment_type=segment.get("type", "unknown"),
                                segment_description=segment.get("description", ""),
                            )
                            base = analysis_result.get("analysis_data") or {}
                            height_count = 0
                            if isinstance(base, dict) and isinstance(height_focus, dict):
                                base.setdefault("room_height_focus", height_focus.get("room_height_focus"))
                                if height_focus.get("height_roi"):
                                    base.setdefault("height_roi", height_focus.get("height_roi"))
                                base.setdefault("dimensions", [])
                                base.setdefault("text_items", [])

                                payload = height_focus.get("room_height_focus")
                                if isinstance(payload, dict) and isinstance(payload.get("heights"), list):
                                    for h in payload.get("heights"):
                                        if not isinstance(h, dict):
                                            continue
                                        height_count += 1
                                        height_m = h.get("height_m")
                                        conf = h.get("confidence")
                                        location = h.get("location")
                                        evidence = h.get("evidence")
                                        if height_m is not None:
                                            base["dimensions"].append(
                                                {
                                                    "value": height_m,
                                                    "unit": "m",
                                                    "element": "room height",
                                                    "location": location or "",
                                                    "confidence": conf,
                                                }
                                            )
                                        if isinstance(evidence, list):
                                            for ev in evidence[:6]:
                                                if isinstance(ev, str) and ev.strip():
                                                    base["text_items"].append(
                                                        {"text": ev.strip(), "language": "hebrew", "type": "dimension"}
                                                    )
                                analysis_result["analysis_data"] = base

                            events.append(_ndjson({"event": "height_focus_done", "segment_id": seg_id, "heights_found": height_count}))
                        except Exception as e:
                            events.append(_ndjson({"event": "height_focus_error", "segment_id": seg_id, "message": str(e)}))

                    if ("windows" in effective_check_groups) or ("WINDOW_DETAILS" in cat_upper):
                        events.append(_ndjson({"event": "window_focus_start", "segment_id": seg_id}))
                        try:
                            window_focus = await analyzer.extract_window_spacing(
                                segment_id=seg_id,
                                segment_blob_url=segment.get("blob_url"),
                                segment_type=segment.get("type", "unknown"),
                                segment_description=segment.get("description", ""),
                            )
                            base = analysis_result.get("analysis_data") or {}
                            evidence_count = 0
                            if isinstance(base, dict) and isinstance(window_focus, dict):
                                base.setdefault("window_spacing_focus", window_focus.get("window_spacing_focus"))
                                if window_focus.get("window_roi"):
                                    base.setdefault("window_roi", window_focus.get("window_roi"))
                                base.setdefault("text_items", [])
                                base.setdefault("dimensions", [])

                                payload = window_focus.get("window_spacing_focus")
                                if isinstance(payload, dict):
                                    ev_texts = payload.get("evidence_texts")
                                    if isinstance(ev_texts, list):
                                        for ev in ev_texts[:10]:
                                            if isinstance(ev, str) and ev.strip():
                                                evidence_count += 1
                                                base["text_items"].append(
                                                    {"text": ev.strip(), "language": "hebrew", "type": "dimension"}
                                                )

                                    windows_payload = payload.get("windows")
                                    if isinstance(windows_payload, list):
                                        for w in windows_payload[:6]:
                                            if not isinstance(w, dict):
                                                continue
                                            conf = w.get("confidence")
                                            location = w.get("location") or ""

                                            def _add_dim(key: str, element: str) -> None:
                                                val = w.get(key)
                                                if isinstance(val, (int, float)):
                                                    base["dimensions"].append(
                                                        {
                                                            "value": float(val),
                                                            "unit": "cm",
                                                            "element": element,
                                                            "location": location,
                                                            "confidence": conf,
                                                        }
                                                    )

                                            _add_dim("niche_to_niche_cm", "window niche spacing")
                                            _add_dim("light_openings_spacing_cm", "window light openings spacing")
                                            _add_dim("to_perpendicular_wall_cm", "window to perpendicular wall")
                                            _add_dim("same_wall_door_separation_cm", "window-door separation")
                                            _add_dim("door_height_cm", "door height")
                                            _add_dim("concrete_wall_thickness_cm", "concrete wall thickness")

                                            ev_list = w.get("evidence")
                                            if isinstance(ev_list, list):
                                                for ev in ev_list[:8]:
                                                    if isinstance(ev, str) and ev.strip():
                                                        evidence_count += 1
                                                        base["text_items"].append(
                                                            {"text": ev.strip(), "language": "hebrew", "type": "dimension"}
                                                        )

                                            if w.get("has_concrete_wall_between_openings") is True:
                                                evidence_count += 1
                                                base["text_items"].append(
                                                    {
                                                        "text": "קיים קיר בטון בין דלת לחלון (לפי זיהוי ממוקד)",
                                                        "language": "hebrew",
                                                        "type": "note",
                                                    }
                                                )
                                analysis_result["analysis_data"] = base

                            events.append(_ndjson({"event": "window_focus_done", "segment_id": seg_id, "evidence_texts": evidence_count}))
                        except Exception as e:
                            events.append(_ndjson({"event": "window_focus_error", "segment_id": seg_id, "message": str(e)}))

                    if ("materials" in effective_check_groups) or ("MATERIALS_SPECS" in cat_upper):
                        events.append(_ndjson({"event": "materials_focus_start", "segment_id": seg_id}))
                        try:
                            materials_focus = await analyzer.extract_materials_specs(
                                segment_id=seg_id,
                                segment_blob_url=segment.get("blob_url"),
                                segment_type=segment.get("type", "unknown"),
                                segment_description=segment.get("description", ""),
                            )
                            base = analysis_result.get("analysis_data") or {}
                            added = 0
                            if isinstance(base, dict) and isinstance(materials_focus, dict):
                                base.setdefault("materials_focus", materials_focus.get("materials_focus"))
                                if materials_focus.get("materials_roi"):
                                    base.setdefault("materials_roi", materials_focus.get("materials_roi"))
                                base.setdefault("materials", [])
                                base.setdefault("text_items", [])
                                payload = materials_focus.get("materials_focus")
                                if isinstance(payload, dict) and isinstance(payload.get("materials"), list):
                                    for m in payload.get("materials"):
                                        if not isinstance(m, dict):
                                            continue
                                        added += 1
                                        base["materials"].append(
                                            {
                                                "type": m.get("type"),
                                                "grade": m.get("grade"),
                                                "notes": m.get("notes"),
                                                "confidence": m.get("confidence"),
                                                "evidence": m.get("evidence"),
                                            }
                                        )
                                        ev_list = m.get("evidence")
                                        if isinstance(ev_list, list):
                                            for ev in ev_list[:6]:
                                                if isinstance(ev, str) and ev.strip():
                                                    base["text_items"].append(
                                                        {"text": ev.strip(), "language": "hebrew", "type": "note"}
                                                    )
                                analysis_result["analysis_data"] = base

                            events.append(_ndjson({"event": "materials_focus_done", "segment_id": seg_id, "materials_found": added}))
                        except Exception as e:
                            events.append(_ndjson({"event": "materials_focus_error", "segment_id": seg_id, "message": str(e)}))

                    if ("rebar" in effective_check_groups) or ("REBAR_DETAILS" in cat_upper):
                        events.append(_ndjson({"event": "rebar_focus_start", "segment_id": seg_id}))
                        try:
                            rebar_focus = await analyzer.extract_rebar_specs(
                                segment_id=seg_id,
                                segment_blob_url=segment.get("blob_url"),
                                segment_type=segment.get("type", "unknown"),
                                segment_description=segment.get("description", ""),
                            )
                            base = analysis_result.get("analysis_data") or {}
                            added = 0
                            if isinstance(base, dict) and isinstance(rebar_focus, dict):
                                base.setdefault("rebar_focus", rebar_focus.get("rebar_focus"))
                                if rebar_focus.get("rebar_roi"):
                                    base.setdefault("rebar_roi", rebar_focus.get("rebar_roi"))
                                base.setdefault("rebar_details", [])
                                base.setdefault("text_items", [])
                                payload = rebar_focus.get("rebar_focus")
                                if isinstance(payload, dict) and isinstance(payload.get("rebars"), list):
                                    for r in payload.get("rebars"):
                                        if not isinstance(r, dict):
                                            continue
                                        spacing_cm = r.get("spacing_cm")
                                        location = r.get("location")
                                        conf = r.get("confidence")
                                        evidence = r.get("evidence")
                                        if spacing_cm is not None:
                                            added += 1
                                            base["rebar_details"].append(
                                                {
                                                    "spacing": f"{spacing_cm} cm",
                                                    "location": location or "",
                                                    "notes": "rebar_focus",
                                                    "confidence": conf,
                                                    "evidence": evidence,
                                                }
                                            )
                                        if isinstance(evidence, list):
                                            for ev in evidence[:6]:
                                                if isinstance(ev, str) and ev.strip():
                                                    base["text_items"].append(
                                                        {"text": ev.strip(), "language": "hebrew", "type": "note"}
                                                    )
                                analysis_result["analysis_data"] = base

                            events.append(_ndjson({"event": "rebar_focus_done", "segment_id": seg_id, "rebars_found": added}))
                        except Exception as e:
                            events.append(_ndjson({"event": "rebar_focus_error", "segment_id": seg_id, "message": str(e)}))

                    if ("notes" in effective_check_groups) or ("GENERAL_NOTES" in cat_upper):
                        events.append(_ndjson({"event": "notes_focus_start", "segment_id": seg_id}))
                        try:
                            notes_focus = await analyzer.extract_general_notes(
                                segment_id=seg_id,
                                segment_blob_url=segment.get("blob_url"),
                                segment_type=segment.get("type", "unknown"),
                                segment_description=segment.get("description", ""),
                            )
                            base = analysis_result.get("analysis_data") or {}
                            added = 0
                            if isinstance(base, dict) and isinstance(notes_focus, dict):
                                base.setdefault("notes_focus", notes_focus.get("notes_focus"))
                                if notes_focus.get("notes_roi"):
                                    base.setdefault("notes_roi", notes_focus.get("notes_roi"))
                                base.setdefault("text_items", [])
                                payload = notes_focus.get("notes_focus")
                                if isinstance(payload, dict) and isinstance(payload.get("evidence_texts"), list):
                                    for ev in payload.get("evidence_texts")[:10]:
                                        if isinstance(ev, str) and ev.strip():
                                            added += 1
                                            base["text_items"].append(
                                                {"text": ev.strip(), "language": "hebrew", "type": "note"}
                                            )
                                analysis_result["analysis_data"] = base

                            events.append(_ndjson({"event": "notes_focus_done", "segment_id": seg_id, "evidence_texts": added}))
                        except Exception as e:
                            events.append(_ndjson({"event": "notes_focus_error", "segment_id": seg_id, "message": str(e)}))

                    return {"analysis_result": analysis_result, "events": events, "emit_segment_done": True}
                except Exception as e:
                    logger.error("Failed to analyze segment (stream)", segment_id=seg_id, error=str(e))
                    analysis_result = {
                        "segment_id": seg_id,
                        "status": "error",
                        "error": str(e),
                        "validation": {"status": "error", "passed": False, "violations": []},
                    }
                    events.append(_ndjson({"event": "segment_error", "segment_id": seg_id, "message": str(e)}))
                    # Preserve legacy behavior: on exception we do NOT emit segment_done.
                    return {"analysis_result": analysis_result, "events": events, "emit_segment_done": False}

        # Kick off analysis+focus for all segments concurrently (bounded).
        prep_tasks: Dict[str, asyncio.Task] = {}
        for segment in approved_segments:
            seg_id = str(segment.get("segment_id"))
            prep_tasks[seg_id] = asyncio.create_task(_prepare_segment(segment))

        try:
            for idx, segment in enumerate(approved_segments, start=1):
                seg_id = segment.get("segment_id")
                yield _ndjson(
                    {
                        "event": "segment_start",
                        "current": idx,
                        "total": total,
                        "segment_id": seg_id,
                        "segment_type": segment.get("type"),
                        "description": segment.get("description"),
                    }
                )

                yield _ndjson({"event": "analysis_start", "segment_id": seg_id})

                prepared = await prep_tasks[str(seg_id)]
                analysis_result = prepared.get("analysis_result")
                for ev in prepared.get("events") or []:
                    yield ev

                if isinstance(analysis_result, dict) and analysis_result.get("status") == "analyzed":
                    yield _ndjson({"event": "validation_start", "segment_id": seg_id})
                    validation_result = validator.validate_segment(
                        analysis_result.get("analysis_data", {}),
                        demo_mode=request.demo_mode,
                        enabled_requirements=enabled_requirements,
                        skip_requirements=passed_requirements_global,
                    )
                    analysis_result["validation"] = validation_result

                    # Update global pass-state: once a requirement passed in any segment,
                    # skip re-running it in later segments.
                    for ev in (validation_result.get("requirement_evaluations") or []):
                        if isinstance(ev, dict) and ev.get("status") == "passed":
                            req_id = ev.get("requirement_id")
                            if isinstance(req_id, str) and req_id:
                                passed_requirements_global.add(req_id)

                    # Emit a compact summary (and door 3.1 status if present)
                    door_31 = None
                    for ev in (validation_result.get("requirement_evaluations") or []):
                        if isinstance(ev, dict) and ev.get("requirement_id") == "3.1":
                            door_31 = {
                                "status": ev.get("status"),
                                "reason_not_checked": ev.get("reason_not_checked"),
                            }
                            break

                    yield _ndjson(
                        {
                            "event": "validation_done",
                            "segment_id": seg_id,
                            "status": validation_result.get("status"),
                            "checked_requirements": validation_result.get("checked_requirements") or [],
                            "checks_performed": bool(validation_result.get("checks_performed")),
                            "checks_attempted": bool(validation_result.get("checks_attempted")),
                            "door_3_1": door_31,
                            "decision_summary_he": validation_result.get("decision_summary_he"),
                            "violation_count": len(validation_result.get("violations") or [])
                            if isinstance(validation_result.get("violations"), list)
                            else None,
                        }
                    )

                if isinstance(analysis_result, dict):
                    analyzed_segments.append(analysis_result)

                if prepared.get("emit_segment_done") is True:
                    yield _ndjson({"event": "segment_done", "current": idx, "total": total, "segment_id": seg_id})
        finally:
            for t in prep_tasks.values():
                if not t.done():
                    t.cancel()

        # 4. Store results
        validation_id = f"val-{uuid.uuid4()}"
        created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        validation_doc = {
            "id": validation_id,
            "type": "segment_validation",
            "decomposition_id": request.decomposition_id,
            "validation_id": decomposition.get("validation_id"),
            "project_id": decomposition.get("project_id"),
            "analyzed_segments": analyzed_segments,
            "demo_mode": request.demo_mode,
            "demo_focus": demo_focus_note,
            "check_groups": effective_check_groups,
            "created_at": created_at,
        }
        await cosmos_client.create_item(validation_doc)

        passed = sum(1 for s in analyzed_segments if s.get("validation", {}).get("status") == "passed")
        failed = sum(
            1
            for s in analyzed_segments
            if s.get("status") == "error" or s.get("validation", {}).get("status") == "failed"
        )
        warnings = sum(s.get("validation", {}).get("warning_count", 0) for s in analyzed_segments)

        tracker = get_coverage_tracker()
        coverage_report = tracker.calculate_coverage({"analyzed_segments": analyzed_segments})

        result = {
            "validation_id": validation_id,
            "created_at": created_at,
            "total_segments": total,
            "passed": passed,
            "failed": failed,
            "warnings": warnings,
            "analyzed_segments": analyzed_segments,
            "coverage": coverage_report,
            "demo_mode": request.demo_mode,
            "demo_focus": demo_focus_note,
        }

        yield _ndjson({"event": "final", "result": result})

    return StreamingResponse(
        _gen(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/validations")
async def list_validations():
    """List all validation history.
    
    Returns:
        List of all validations sorted by date (newest first)
    """
    logger.info("Fetching validation history")
    
    try:
        cosmos_client = get_cosmos_client()
        
        # Get all validations
        query = """
            SELECT c.id, c.decomposition_id, c.validation_id, c.project_id,
                   c.total_segments, c.passed, c.failed, c.warnings, 
                   c.created_at, c.coverage
            FROM c 
            WHERE c.type = 'segment_validation'
            ORDER BY c._ts DESC
        """
        
        results = await cosmos_client.query_items(query, [])
        
        # Enrich with plan names from decomposition in batch
        decomposition_ids = list(set([r.get("decomposition_id") for r in results if r.get("decomposition_id")]))
        
        # Fetch all decompositions in one query
        decomposition_map = {}
        if decomposition_ids:
            decomp_query = f"""
                SELECT c.id, c.metadata.project_name, c.metadata.plan_number, c.created_at
                FROM c 
                WHERE c.type = 'decomposition'
                AND c.id IN ({','.join([f"'{did}'" for did in decomposition_ids])})
            """
            decomp_results = await cosmos_client.query_items(decomp_query, [])
            decomposition_map = {d["id"]: d for d in decomp_results}
        
        # Enrich results
        enriched_results = []
        for result in results:
            decomp_id = result.get("decomposition_id")
            decomp_data = decomposition_map.get(decomp_id) if decomp_id else None
            
            # Get plan name
            plan_name = "תכנית ללא שם"
            created_at = result.get("created_at", "2025-12-11T00:00:00Z")
            
            if decomp_data:
                plan_name = (
                    decomp_data.get("project_name") or 
                    decomp_data.get("plan_number") or 
                    f"תכנית {decomp_id[:8]}"
                )
                # Use decomposition created_at if available
                if decomp_data.get("created_at"):
                    created_at = decomp_data["created_at"]
            
            # Calculate status
            passed = result.get("passed", 0)
            failed = result.get("failed", 0)
            status = "pass" if failed == 0 and passed > 0 else "fail" if failed > 0 else "needs_review"
            
            enriched_results.append({
                **result,
                "plan_name": plan_name,
                "status": status,
                "created_at": created_at
            })
        
        logger.info(f"Returning {len(enriched_results)} validations")
        
        return {
            "total": len(enriched_results),
            "validations": enriched_results
        }
        
    except Exception as e:
        logger.error("Failed to fetch validation history", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch history: {str(e)}"
        )


@router.get("/validation/{validation_id}")
async def get_validation_results(validation_id: str):
    """Get detailed validation results.
    
    Args:
        validation_id: Validation ID
        
    Returns:
        Detailed validation results with per-segment analysis
    """
    logger.info("Fetching validation results", validation_id=validation_id)
    
    try:
        cosmos_client = get_cosmos_client()
        
        query = """
            SELECT * FROM c 
            WHERE c.id = @validation_id 
            AND c.type = 'segment_validation'
        """
        parameters = [{"name": "@validation_id", "value": validation_id}]
        
        results = await cosmos_client.query_items(query, parameters)
        
        if not results:
            raise HTTPException(
                status_code=404,
                detail=f"Validation not found: {validation_id}"
            )
        
        doc = results[0]

        enriched_segments = []
        for seg in doc.get("analyzed_segments", []) or []:
            analysis_data = seg.get("analysis_data", {}) or {}
            classification = analysis_data.get("classification", {}) or {}
            primary_category = classification.get("primary_category", "OTHER")

            validation = seg.get("validation", {}) or {}
            # IMPORTANT: Never backfill checked_requirements from category mapping.
            # Doing so re-introduces false "green" checks and can contradict requirement_evaluations.

            if not validation.get("decision_summary_he"):
                checked = validation.get("checked_requirements") or []
                checks_performed = bool(validation.get("checks_performed")) or bool(checked)

                if checks_performed and checked:
                    validation["decision_summary_he"] = (
                        f"הופעלו בדיקות לפי קטגוריית הסגמנט '{primary_category}'. "
                        f"דרישות שנבדקו בסגמנט זה: {', '.join(checked)}."
                    )
                else:
                    validation["decision_summary_he"] = (
                        "לא בוצעו בדיקות בפועל בסגמנט זה (אין ראיות מספיקות או שלא הופעלו קבוצות בדיקה מתאימות)."
                    )

            enriched_segments.append({
                **seg,
                "validation": validation,
            })

        doc = {
            **doc,
            "analyzed_segments": enriched_segments,
        }

        # Always (re)compute coverage on read so history reflects latest mapping logic
        tracker = get_coverage_tracker()
        coverage_report = tracker.calculate_coverage({
            "analyzed_segments": doc.get("analyzed_segments", [])
        })

        return {
            **doc,
            "coverage": coverage_report,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to fetch validation results", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch results: {str(e)}"
        )


@router.delete("/validation/{validation_id}")
async def delete_validation_result(validation_id: str):
    """Delete a segment validation history record (and any related blobs if present)."""
    logger.info("Deleting segment validation history", validation_id=validation_id)
    cosmos_client = get_cosmos_client()
    blob_client = get_blob_client()

    try:
        query = """
            SELECT * FROM c
            WHERE c.id = @validation_id
            AND c.type = 'segment_validation'
        """
        parameters = [{"name": "@validation_id", "value": validation_id}]
        results = await cosmos_client.query_items(query, parameters)
        if not results:
            raise HTTPException(status_code=404, detail=f"Validation not found: {validation_id}")
        item = results[0]

        partition_key = item.get("project_id") or item.get("decomposition_id") or item.get("id")
        deleted = await cosmos_client.delete_item(item_id=item.get("id"), partition_key=partition_key)

        blob_prefix = item.get("blob_prefix") or item.get("artifacts_prefix")
        deleted_blobs = 0
        if isinstance(blob_prefix, str) and blob_prefix.strip():
            deleted_blobs = await blob_client.delete_blobs_with_prefix(blob_prefix.strip())

        return {
            "deleted": bool(deleted),
            "validation_id": validation_id,
            "deleted_blobs": deleted_blobs,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete validation history", validation_id=validation_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to delete validation history: {str(e)}")


@router.delete("/validations")
async def delete_all_validations():
    """Delete all segment validation history records."""
    logger.info("Deleting all validation history")
    cosmos_client = get_cosmos_client()
    blob_client = get_blob_client()

    try:
        query = """
            SELECT c.id, c.project_id, c.decomposition_id, c.blob_prefix, c.artifacts_prefix
            FROM c
            WHERE c.type = 'segment_validation'
        """
        results = await cosmos_client.query_items(query, [])
        deleted_count = 0
        deleted_blobs = 0
        for item in results:
            partition_key = item.get("project_id") or item.get("decomposition_id") or item.get("id")
            if await cosmos_client.delete_item(item_id=item.get("id"), partition_key=partition_key):
                deleted_count += 1
            blob_prefix = item.get("blob_prefix") or item.get("artifacts_prefix")
            if isinstance(blob_prefix, str) and blob_prefix.strip():
                deleted_blobs += await blob_client.delete_blobs_with_prefix(blob_prefix.strip())

        return {
            "deleted": deleted_count,
            "deleted_blobs": deleted_blobs,
        }
    except Exception as e:
        logger.error("Failed to delete all validation history", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to delete all validation history: {str(e)}")
