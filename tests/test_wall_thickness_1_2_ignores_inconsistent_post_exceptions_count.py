from src.services.mamad_validator import MamadValidator


def test_wall_thickness_ignores_inconsistent_post_exceptions_count_from_floor_plan_inference() -> None:
    """If floor-plan inference provides count+side hints, do not require 40cm due to an inflated post-exceptions count."""

    v = MamadValidator()

    analysis_data = {
        "classification": {
            "primary_category": "ROOM_LAYOUT",
            "secondary_categories": [],
            "view_type": "top_view",
            "relevant_requirements": ["1.2"],
        },
        "summary": {"primary_function": "floor_plan"},
        "content_tags": ["mamad_wall_drop_plan"],
        "text_items": [
            {"text": "תכנית ירידת קירות ממ\"ד", "language": "hebrew", "type": "title"},
            {"text": "קנ\"מ 1:50", "language": "hebrew", "type": "note"},
        ],
        # Base inference says 2 external walls with explicit side hints.
        "external_wall_count": 2,
        "external_sides_hint": ["left", "bottom"],
        "external_wall_count_source": "floor_plan_inference",
        "external_wall_count_confidence": 0.8,
        "external_wall_count_evidence": ["Left+bottom hatched, top+right not"],
        # Buggy downstream count after exceptions (should be ignored).
        "external_wall_count_after_exceptions": 4,
        "structural_elements": [
            {"type": "wall", "thickness": "25 cm", "location": "קיר שמאל (left)", "notes": "wall_thickness_focus"},
            {"type": "wall", "thickness": "25 cm", "location": "קיר תחתון (bottom)", "notes": "wall_thickness_focus"},
        ],
    }

    v.validate_segment(analysis_data)
    ev = next((e for e in v.requirement_evaluations if e.get("requirement_id") == "1.2"), None)
    assert ev is not None
    # With 2 external walls and 25cm thickness, it should pass (not require 40cm).
    assert ev.get("status") == "passed"
