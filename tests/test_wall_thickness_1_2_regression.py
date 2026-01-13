import asyncio

from src.services.external_wall_context import SegmentCandidate, infer_external_wall_context
from src.services.mamad_validator import MamadValidator


class _DummyAnalyzer:
    def __init__(self, payload):
        self._payload = payload

    async def infer_mamad_external_wall_count(self, **kwargs):
        return dict(self._payload)


def test_external_wall_context_requires_confidence_and_evidence():
    analyzer = _DummyAnalyzer(
        {
            "external_wall_count": 3,
            "internal_wall_count": 1,
            "confidence": 0.45,
            "evidence": ["guess"],
        }
    )

    floor_plan = SegmentCandidate(
        segment_id="seg_floor",
        blob_url="https://example.com/floor.png",
        segment_type="floor_plan",
        description="floor plan",
        analysis_data={},
    )
    mamad_ref = SegmentCandidate(
        segment_id="seg_ref",
        blob_url="https://example.com/ref.png",
        segment_type="detail",
        description="mamad detail",
        analysis_data={"text_items": [{"text": 'ממ"ד'}]},
    )

    ctx = asyncio.run(
        infer_external_wall_context(analyzer=analyzer, floor_plan=floor_plan, mamad_reference=mamad_ref)
    )
    assert ctx is None


def test_wall_thickness_does_not_hard_fail_on_opening_detail_segment():
    v = MamadValidator()

    analysis_data = {
        "classification": {
            "primary_category": "DOOR_DETAILS",
            "secondary_categories": [],
            "relevant_requirements": ["1.2"],
        },
        "text_items": [
            {"text": 'ממ"ד'},
            {"text": 'קנ"מ 1:50'},
        ],
        "structural_elements": [
            # Simulate a local opening/jamb thickness callout that should not be treated as
            # explicit external-wall evidence for a hard failure.
            {"type": "wall", "thickness": "20 cm", "location": "קיר חיצוני", "notes": "door detail"},
            {"type": "wall", "thickness": "25 cm", "location": "", "notes": "door detail"},
        ],
        "dimensions": [
            {"value": 20, "unit": "cm", "element": "wall thickness", "location": "קיר חיצוני"},
            {"value": 25, "unit": "cm", "element": "wall thickness", "location": ""},
        ],
    }

    result = v.validate_segment(analysis_data, demo_mode=True)
    ev_12 = [e for e in result.get("requirement_evaluations", []) if e.get("requirement_id") == "1.2"]
    assert ev_12, "Expected a 1.2 evaluation"

    # The key regression: do not mark as FAILED based on ambiguous opening-detail thickness.
    assert ev_12[0].get("status") != "failed"
