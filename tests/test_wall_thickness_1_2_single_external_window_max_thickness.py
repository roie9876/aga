from src.services.mamad_validator import MamadValidator


def test_wall_thickness_single_external_wall_with_window_uses_max_thickness() -> None:
    """When there's exactly one external wall, it's typically the wall with the window.

    If the drawing doesn't explicitly label which wall is external but provides multiple thicknesses
    (e.g., 20cm internal + 25cm external), infer the external wall thickness as the maximum.

    This matches the spec: for 1 external wall with a non-sliding blast window, minimum is 25cm.
    """
    v = MamadValidator()
    analysis_data = {
        "classification": {
            "primary_category": "ROOM_LAYOUT",
            "secondary_categories": [],
            "view_type": "top_view",
            "relevant_requirements": ["1.2"],
        },
        "summary": {"primary_function": "mamad_plan"},
        "content_tags": ["mamad_plan_1_15"],
        "text_items": [
            {"text": "תכנית ממ\"ד", "language": "hebrew", "type": "title"},
            {"text": "קנ\"מ 1:50", "language": "hebrew", "type": "title"},
            {"text": "ממ\"ד", "language": "hebrew", "type": "label"},
            # Window is opening (not sliding): direction shown, but we don't rely on it here.
            {"text": "חלון הדף", "language": "hebrew", "type": "note"},
        ],
        "external_wall_count": 1,
        "structural_elements": [
            {"type": "window", "location": "חלון הדף", "notes": "נפתח"},
            # No explicit 'external' marker on wall callouts.
            {"type": "wall", "thickness": 20, "unit": "cm", "location": "קיר", "notes": ""},
            {"type": "wall", "thickness": 25, "unit": "cm", "location": "קיר", "notes": ""},
        ],
    }

    v.validate_segment(analysis_data)
    ev = next((e for e in v.requirement_evaluations if e.get("requirement_id") == "1.2"), None)
    assert ev is not None
    assert ev.get("status") == "passed"
