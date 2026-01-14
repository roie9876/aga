from src.services.mamad_validator import MamadValidator


def test_wall_thickness_uses_base_count_when_after_exceptions_is_none() -> None:
    """Regression: a present-but-null after-exceptions key must not shadow external_wall_count.

    Without this, REQ 1.2 can incorrectly emit `external_wall_count_unknown` even when
    `external_wall_count` (with provenance) is present.
    """

    v = MamadValidator()

    analysis_data = {
        "classification": {
            "primary_category": "ROOM_LAYOUT",
            "secondary_categories": [],
            "view_type": "top_view",
            "relevant_requirements": ["1.2"],
        },
        "summary": {"primary_function": "floor_plan"},
        "text_items": [
            {"text": "תכנית ירידת קירות ממ\"ד", "language": "hebrew", "type": "title"},
            {"text": "קנ\"מ 1:50", "language": "hebrew", "type": "note"},
        ],
        # Provenanced count from cross-segment inference.
        "external_wall_count": 2,
        "external_sides_hint": ["left", "bottom"],
        "external_wall_count_source": "floor_plan_inference",
        "external_wall_count_confidence": 0.8,
        "external_wall_count_evidence": ["Left+bottom hatched"],
        # Buggy/null value that used to shadow the base count.
        "external_wall_count_after_exceptions": None,
        "structural_elements": [
            {"type": "wall", "thickness": "25 cm", "location": "קיר חיצוני שמאל", "notes": "wall_thickness_focus"},
            {"type": "wall", "thickness": "25 cm", "location": "קיר חיצוני תחתון", "notes": "wall_thickness_focus"},
        ],
    }

    v.validate_segment(analysis_data)
    ev = next((e for e in v.requirement_evaluations if e.get("requirement_id") == "1.2"), None)
    assert ev is not None
    assert ev.get("status") == "passed"
