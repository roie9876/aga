"""Cross-segment helpers for inferring MAMAD external wall count.

In segment-based validation mode, Requirement 1.2 depends on the number of external
walls of the ממ"ד, which often cannot be determined from a single cropped detail.

This module provides:
- Candidate selection: pick a floor-plan segment and a MAMAD-detail segment.
- Injection: propagate the inferred wall count into segment analysis data.

No Azure clients are used here; the calling layer supplies an analyzer instance.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Dict, List, Optional


_MAMAD_RE = re.compile(r"\bממ\"?ד\b|\bממד\b", re.IGNORECASE)


def _norm_text(value: Any) -> str:
    try:
        return str(value or "").strip()
    except Exception:
        return ""


def _contains_mamad(value: Any) -> bool:
    text = _norm_text(value)
    if not text:
        return False
    return bool(_MAMAD_RE.search(text))


def _analysis_text_corpus(analysis_data: Dict[str, Any]) -> str:
    parts: List[str] = []

    classification = analysis_data.get("classification")
    if isinstance(classification, dict):
        parts.append(_norm_text(classification.get("description")))
        parts.append(_norm_text(classification.get("explanation_he")))
        ev = classification.get("evidence")
        if isinstance(ev, list):
            parts.extend([_norm_text(x) for x in ev[:10]])

    summary = analysis_data.get("summary")
    if isinstance(summary, dict):
        parts.append(_norm_text(summary.get("primary_function")))
        parts.append(_norm_text(summary.get("special_notes")))

    text_items = analysis_data.get("text_items")
    if isinstance(text_items, list):
        for item in text_items[:30]:
            if isinstance(item, dict):
                parts.append(_norm_text(item.get("text")))
            else:
                parts.append(_norm_text(item))

    return " ".join([p for p in parts if p])


@dataclass(frozen=True)
class SegmentCandidate:
    segment_id: str
    blob_url: str
    segment_type: str
    description: str
    analysis_data: Dict[str, Any]


def _is_floor_plan(candidate: SegmentCandidate) -> bool:
    if candidate.segment_type == "floor_plan":
        return True
    summary = candidate.analysis_data.get("summary")
    if isinstance(summary, dict) and _norm_text(summary.get("primary_function")).lower() == "floor_plan":
        return True
    classification = candidate.analysis_data.get("classification")
    if isinstance(classification, dict):
        view_type = _norm_text(classification.get("view_type")).lower()
        if view_type in {"top_view", "floor_plan", "plan"}:
            # Not all top_view are floor plans, but it's a strong hint.
            return True
    # Heuristic: description contains תכנית קומה
    if "תכנית" in candidate.description and "קומה" in candidate.description:
        return True
    return False


def _is_mamad_reference(candidate: SegmentCandidate) -> bool:
    if _contains_mamad(candidate.description):
        return True
    corpus = _analysis_text_corpus(candidate.analysis_data)
    return _contains_mamad(corpus)


def select_floor_plan_candidate(candidates: List[SegmentCandidate]) -> Optional[SegmentCandidate]:
    """Pick the best floor-plan candidate among analyzed segments."""
    floor_plans = [c for c in candidates if _is_floor_plan(c)]
    if not floor_plans:
        return None

    def _score(c: SegmentCandidate) -> int:
        score = 0
        if c.segment_type == "floor_plan":
            score += 3
        summary = c.analysis_data.get("summary")
        if isinstance(summary, dict) and _norm_text(summary.get("primary_function")).lower() == "floor_plan":
            score += 2
        if "תכנית" in c.description and "קומה" in c.description:
            score += 1
        return score

    floor_plans.sort(key=_score, reverse=True)
    return floor_plans[0]


def select_mamad_reference_candidate(candidates: List[SegmentCandidate]) -> Optional[SegmentCandidate]:
    """Pick a MAMAD-related candidate (detail/layout/any segment containing ממ"ד hints)."""
    mamads = [c for c in candidates if _is_mamad_reference(c)]
    if not mamads:
        return None

    def _score(c: SegmentCandidate) -> int:
        score = 0
        # Prefer non-floor-plan as the reference detail
        if c.segment_type != "floor_plan":
            score += 2
        if _contains_mamad(c.description):
            score += 2
        # Prefer detail-ish segments
        if c.segment_type in {"detail", "section", "elevation"}:
            score += 1
        return score

    mamads.sort(key=_score, reverse=True)
    return mamads[0]


def coerce_external_wall_count(value: Any) -> Optional[int]:
    try:
        count = int(value)
    except Exception:
        return None
    return count if 1 <= count <= 4 else None


def _coerce_confidence(value: Any) -> float:
    try:
        c = float(value)
    except Exception:
        return 0.0
    if c < 0.0:
        return 0.0
    if c > 1.0:
        return 1.0
    return c


def _coerce_evidence(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    out: List[str] = []
    for item in value[:12]:
        s = _norm_text(item)
        if s:
            out.append(s)
    return out


async def infer_external_wall_count(
    *,
    analyzer: Any,
    floor_plan: SegmentCandidate,
    mamad_reference: SegmentCandidate,
) -> Optional[int]:
    """Use the provided analyzer to infer the MAMAD external wall count from a floor plan + reference."""
    if analyzer is None:
        return None

    # Prefer an explicit count already extracted from the floor-plan analysis.
    direct = coerce_external_wall_count(floor_plan.analysis_data.get("external_wall_count"))
    if direct is not None:
        return direct
    direct_after = coerce_external_wall_count(floor_plan.analysis_data.get("external_wall_count_after_exceptions"))
    if direct_after is not None:
        return direct_after

    if not hasattr(analyzer, "infer_mamad_external_wall_count"):
        return None

    result = await analyzer.infer_mamad_external_wall_count(
        floor_plan_blob_url=floor_plan.blob_url,
        floor_plan_description=floor_plan.description,
        mamad_segment_blob_url=mamad_reference.blob_url,
        mamad_segment_description=mamad_reference.description,
    )

    if not isinstance(result, dict):
        return None

    inferred = coerce_external_wall_count(result.get("external_wall_count"))
    return inferred


async def infer_external_wall_context(
    *,
    analyzer: Any,
    floor_plan: SegmentCandidate,
    mamad_reference: SegmentCandidate,
) -> Optional[Dict[str, Any]]:
    """Infer external wall count along with evidence/context."""
    if floor_plan.segment_id == mamad_reference.segment_id:
        return None

    if analyzer is None or not hasattr(analyzer, "infer_mamad_external_wall_count"):
        return None

    result = await analyzer.infer_mamad_external_wall_count(
        floor_plan_blob_url=floor_plan.blob_url,
        floor_plan_description=floor_plan.description,
        mamad_segment_blob_url=mamad_reference.blob_url,
        mamad_segment_description=mamad_reference.description,
    )
    if not isinstance(result, dict):
        return None

    count = coerce_external_wall_count(result.get("external_wall_count"))
    if count is None:
        return None

    return {
        "external_wall_count": count,
        "internal_wall_count": coerce_external_wall_count(result.get("internal_wall_count")),
        "external_sides_hint": result.get("external_sides_hint") if isinstance(result.get("external_sides_hint"), list) else [],
        "confidence": _coerce_confidence(result.get("confidence")),
        "evidence": _coerce_evidence(result.get("evidence")),
        "source": "floor_plan_inference",
        "floor_plan_segment_id": floor_plan.segment_id,
        "mamad_reference_segment_id": mamad_reference.segment_id,
    }


def inject_external_wall_count(
    *,
    analyzed_segments: List[Dict[str, Any]],
    external_wall_count: int,
    context: Optional[Dict[str, Any]] = None,
) -> int:
    """Inject external wall count into segment analysis_data when missing.

    Returns the number of segments updated.
    """
    updated = 0
    for seg in analyzed_segments:
        if not isinstance(seg, dict):
            continue
        if seg.get("status") != "analyzed":
            continue
        analysis_data = seg.get("analysis_data")
        if not isinstance(analysis_data, dict):
            continue

        # If the segment already carries a count (or after-exceptions count), do not override.
        existing = coerce_external_wall_count(
            analysis_data.get("external_wall_count_after_exceptions")
        )
        if existing is None:
            existing = coerce_external_wall_count(analysis_data.get("external_wall_count"))
        if existing is not None:
            continue

        analysis_data["external_wall_count"] = external_wall_count
        if isinstance(context, dict):
            analysis_data.setdefault("external_wall_count_source", context.get("source"))
            analysis_data.setdefault("external_wall_count_confidence", context.get("confidence"))
            if isinstance(context.get("evidence"), list):
                analysis_data.setdefault("external_wall_count_evidence", context.get("evidence"))
            analysis_data.setdefault(
                "external_wall_count_reference_segments",
                {
                    "floor_plan_segment_id": context.get("floor_plan_segment_id"),
                    "mamad_reference_segment_id": context.get("mamad_reference_segment_id"),
                },
            )
        updated += 1

    return updated
