from src.services.mamad_validator import MamadValidator


def test_wall_thickness_discard_floor_plan_count_when_window_side_override_conflicts() -> None:
    validator = MamadValidator()

    analysis_data = {
        "classification": {
            "primary_category": "WALL_SECTION",
            "secondary_categories": [],
            "view_type": "top_view",
            "relevant_requirements": ["1.2"],
        },
        "summary": {"primary_function": "detail"},
        "content_tags": ["mamad_plan_1_15"],
        "text_items": [
            {"text": "תכנית הממ\"ד", "language": "hebrew", "type": "title"},
            {"text": "קנ\"מ 1:50", "language": "hebrew", "type": "note"},
        ],
        # Cross-segment inference claims 3 external walls on TOP/RIGHT/BOTTOM.
        "external_wall_count": 3,
        "external_wall_count_source": "floor_plan_inference",
        "external_wall_count_confidence": 0.86,
        "external_wall_count_evidence": ["הוסק 3 קירות חוץ (עליון/ימין/תחתון)"],
        "external_sides_hint": ["top", "right", "bottom"],
        # Detailed plan indicates the window is on the LEFT wall (single-side, strong signal).
        "structural_elements": [
            {
                "type": "window",
                "location": "חלון בקיר שמאל (left)",
                "notes": "חלון הדף",
            },
            {
                "type": "wall",
                "thickness": "25 cm",
                "location": "קיר שמאל (left)",
                "notes": "מסומן כקיר מעטפת",
                "evidence": ["25 ליד הקיר השמאלי"],
            },
        ],
    }

    validator.validate_segment(analysis_data)

    ev = next((e for e in validator.requirement_evaluations if e.get("requirement_id") == "1.2"), None)
    assert ev is not None

    # When side mapping is contradictory, do not hard-fail 30/40cm thresholds based on the
    # floor-plan-derived count. Instead, infer the count from the detailed-plan side evidence.
    assert ev.get("status") == "passed"

    count_ev = next(
        (
            e
            for e in (ev.get("evidence") or [])
            if isinstance(e, dict) and e.get("element") == "external_wall_count"
        ),
        None,
    )
    assert count_ev is not None
    assert (count_ev.get("raw") or {}).get("used_for_requirement") is False
