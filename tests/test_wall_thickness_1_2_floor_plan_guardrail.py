from src.services.mamad_validator import MamadValidator


def test_wall_thickness_floor_plan_does_not_hard_fail() -> None:
    validator = MamadValidator()
    analysis_data = {
        "classification": {
            "primary_category": "ROOM_LAYOUT",
            "secondary_categories": [],
            "view_type": "top_view",
            "relevant_requirements": ["1.2"],
        },
        "summary": {"primary_function": "floor_plan"},
        "content_tags": ["floor_plan"],
        "text_items": [
            {"text": "תכנית קומה", "language": "hebrew", "type": "title"},
            {"text": "ממ\"ד", "language": "hebrew", "type": "label"},
        ],
        # Incidental thickness callouts in floor plans are common and can be misleading.
        "dimensions": [
            {"value": 20, "unit": "cm", "element": "wall thickness", "location": "קיר חיצוני"},
        ],
        "structural_elements": [
            {"type": "wall", "thickness": 20, "unit": "cm", "location": "קיר חיצוני", "notes": ""},
        ],
    }

    validator.validate_segment(analysis_data)
    ev = next((e for e in validator.requirement_evaluations if e.get("requirement_id") == "1.2"), None)
    assert ev is not None
    assert ev.get("status") == "not_checked"
    assert ev.get("reason_not_checked") == "floor_plan_thickness_not_reliable"


def test_wall_thickness_floor_plan_mis_tagged_as_mamad_plan_still_not_checked() -> None:
    """If a floor plan crop includes 'תכנית ממ"ד' somewhere, tagging can be noisy.

    We must not evaluate 1.2 from top-view segments unless an explicit 1:50 scale is present.
    """
    validator = MamadValidator()
    analysis_data = {
        "classification": {
            "primary_category": "ROOM_LAYOUT",
            "secondary_categories": [],
            "view_type": "top_view",
            "relevant_requirements": ["1.2"],
        },
        "summary": {"primary_function": "floor_plan"},
        # Noisy tag: could be set because the sheet contains the phrase "תכנית ממ\"ד".
        "content_tags": ["floor_plan", "mamad_plan_1_15"],
        "text_items": [
            {"text": "תכנית קומה", "language": "hebrew", "type": "title"},
            {"text": "תכנית ממ\"ד", "language": "hebrew", "type": "title"},
            {"text": "ממ\"ד", "language": "hebrew", "type": "label"},
            # Deliberately NO explicit 1:50 scale token.
        ],
        "dimensions": [
            {"value": 20, "unit": "cm", "element": "wall thickness", "location": "קיר חיצוני"},
        ],
        "structural_elements": [
            {"type": "wall", "thickness": 20, "unit": "cm", "location": "קיר חיצוני", "notes": ""},
        ],
    }

    validator.validate_segment(analysis_data)
    ev = next((e for e in validator.requirement_evaluations if e.get("requirement_id") == "1.2"), None)
    assert ev is not None
    assert ev.get("status") == "not_checked"
    assert ev.get("reason_not_checked") == "floor_plan_thickness_not_reliable"


def test_wall_thickness_top_view_with_1_50_does_not_fail_without_external_sides_hint() -> None:
    """MAMAD top-view segments may contain 1:50 tokens but still need external classification context.

    Without injected external_sides_hint, we avoid hard-failing 1.2 based purely on an 'external' label.
    """
    validator = MamadValidator()
    analysis_data = {
        "classification": {
            "primary_category": "ROOM_LAYOUT",
            "secondary_categories": [],
            "view_type": "top_view",
            "relevant_requirements": ["1.2"],
        },
        "summary": {"primary_function": "floor_plan"},
        "content_tags": ["mamad_plan_1_15"],
        "text_items": [
            {"text": "תכנית ממ\"ד", "language": "hebrew", "type": "title"},
            {"text": "קנ\"מ 1:50", "language": "hebrew", "type": "title"},
            {"text": "ממ\"ד", "language": "hebrew", "type": "label"},
        ],
        "structural_elements": [
            # A thin wall labeled as external; without external_sides_hint this must not hard-fail.
            {"type": "wall", "thickness": 20, "unit": "cm", "location": "קיר חיצוני", "notes": ""},
        ],
    }

    validator.validate_segment(analysis_data)
    ev = next((e for e in validator.requirement_evaluations if e.get("requirement_id") == "1.2"), None)
    assert ev is not None
    assert ev.get("status") == "not_checked"
    assert ev.get("reason_not_checked") in {
        "no_external_wall_thickness_identified",
        "external_wall_count_unknown",
    }
