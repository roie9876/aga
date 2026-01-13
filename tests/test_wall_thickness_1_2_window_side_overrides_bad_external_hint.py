from src.services.mamad_validator import MamadValidator


def test_wall_thickness_window_side_overrides_conflicting_external_sides_hint() -> None:
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
        # Cross-segment inference claims TOP/BOTTOM are external.
        "external_wall_count": 2,
        "external_wall_count_source": "floor_plan_inference",
        "external_wall_count_confidence": 0.86,
        "external_wall_count_evidence": ["הוסק 2 קירות חוץ (עליון/תחתון)"],
        "external_sides_hint": ["top", "bottom"],
        # Detailed plan indicates the blast window is on the RIGHT wall.
        "structural_elements": [
            {
                "type": "window",
                "location": "חלון הדף בקיר ימין (right)",
                "notes": "חלון הדף",
            },
            {
                "type": "wall",
                "thickness": "25 cm",
                "location": "קיר ימין (right)",
                "notes": "wall_thickness_focus",
                "evidence": ["25 ליד הקיר הימני"],
            },
            {
                "type": "wall",
                "thickness": "20 cm",
                "location": "קיר עליון (top)",
                "notes": "wall_thickness_focus",
                "evidence": ["20 ליד הקיר העליון"],
            },
        ],
    }

    validator.validate_segment(analysis_data)

    ev = next((e for e in validator.requirement_evaluations if e.get("requirement_id") == "1.2"), None)
    assert ev is not None
    assert ev.get("status") == "passed"
