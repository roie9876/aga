from src.services.mamad_validator import MamadValidator


def test_wall_thickness_conflicting_external_context_does_not_fail() -> None:
    """If inferred external sides conflict with a detected MAMAD door side, do not hard-fail on <25cm."""

    validator = MamadValidator()

    analysis_data = {
        "classification": {
            "primary_category": "ROOM_LAYOUT",
            "secondary_categories": ["DOOR_DETAILS"],
            "view_type": "top_view",
            "relevant_requirements": ["1.2"],
        },
        "summary": {"primary_function": "floor_plan"},
        "content_tags": ["mamad_plan_1_15"],
        "text_items": [
            {"text": "תכנית הממ\"ד", "language": "hebrew", "type": "title"},
            {"text": "קנ\"מ 1:50", "language": "hebrew", "type": "note"},
        ],
        # Cross-segment inference says the RIGHT wall is external.
        "external_wall_count": 3,
        "external_wall_count_source": "floor_plan_inference",
        "external_wall_count_confidence": 0.9,
        "external_sides_hint": ["right", "top", "bottom"],
        # But the detailed plan indicates a MAMAD door on the RIGHT wall (internal marker).
        "structural_elements": [
            {
                "type": "door",
                "location": "דלת ממ\"ד בקיר הימני (right)",
                "notes": "דלת הדף ממ\"ד",
            },
            {
                "type": "wall",
                "thickness": "20 cm",
                "location": "top wall (עליון)",
                "notes": "wall_thickness_focus",
                "evidence": ["סימון 20"],
            },
        ],
    }

    validator.validate_segment(analysis_data)

    ev = next((e for e in validator.requirement_evaluations if e.get("requirement_id") == "1.2"), None)
    assert ev is not None
    assert ev.get("status") == "not_checked"
    assert ev.get("reason_not_checked") in {
        "ambiguous_external_context_conflict",
        "ambiguous_thin_wall_candidate",
    }
