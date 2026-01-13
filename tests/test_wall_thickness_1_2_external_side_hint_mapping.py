from src.services.mamad_validator import MamadValidator


def test_wall_thickness_uses_external_sides_hint() -> None:
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
        # Cross-segment inference from floor plan (seg_001): only the LEFT wall is external.
        "external_wall_count": 1,
        "external_wall_count_source": "floor_plan_inference",
        "external_wall_count_confidence": 0.9,
        "external_wall_count_evidence": ["ממ\"ד צמוד למעטפת רק בצד שמאל"],
        "external_sides_hint": ["left"],
        # Focus-extracted thicknesses with side hints.
        "structural_elements": [
            {
                "type": "wall",
                "thickness": "25 cm",
                "location": "קיר שמאל (left)",
                "notes": "wall_thickness_focus",
                "evidence": ["25 ליד הקיר השמאלי"],
            },
            {
                "type": "wall",
                "thickness": "20 cm",
                "location": "קיר ימין (right)",
                "notes": "wall_thickness_focus",
                "evidence": ["20 ליד הקיר הימני"],
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
    assert ev.get("status") in {"passed", "failed"}
    # With one external wall and 25cm thickness on that external side, it should pass.
    assert ev.get("status") == "passed"
