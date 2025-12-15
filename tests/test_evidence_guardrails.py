from typing import Optional

import pytest


def _assert_no_passed_or_failed_without_evidence(evaluations: list[dict]) -> None:
    for ev in evaluations:
        if not isinstance(ev, dict):
            continue
        status = ev.get("status")
        if status in {"passed", "failed"}:
            evidence = ev.get("evidence")
            assert isinstance(evidence, list) and len(evidence) > 0, (
                f"Evaluation {ev.get('requirement_id')} is '{status}' but has no evidence"
            )


def test_manual_roi_enabled_requirements_emits_not_checked_evals_only() -> None:
    """Manual/unknown ROI must not claim checks passed without evidence.

    When classification is missing/OTHER but the user explicitly enables requirements,
    we still run the validators and emit explicit not_checked evaluations.
    """

    from src.services.mamad_validator import MamadValidator

    validator = MamadValidator()
    analysis_data = {
        "classification": {},
        "text_items": [],
        "dimensions": [],
        "structural_elements": [],
        "annotations": [],
    }

    enabled = {"1.2", "2.1", "2.2", "3.1", "3.2"}
    result = validator.validate_segment(analysis_data, demo_mode=True, enabled_requirements=enabled)

    evals = result.get("requirement_evaluations")
    assert isinstance(evals, list)
    assert len(evals) == 5

    assert result.get("checked_requirements") == []
    assert result.get("debug", {}).get("ran_by_enabled_requirements") is True

    # None of the enabled requirements may be marked passed/failed without evidence.
    statuses = {ev.get("status") for ev in evals if isinstance(ev, dict)}
    assert statuses.issubset({"not_checked"})

    _assert_no_passed_or_failed_without_evidence(evals)


@pytest.mark.parametrize(
    "thickness,location,external_wall_count,expected_status",
    [
        ("30cm", "קיר חיצוני", 1, "passed"),
        ("20cm", "קיר חיצוני", 1, "failed"),
        ("20cm", "אזור פנימי ללא חלונות", None, "not_checked"),
    ],
)
def test_wall_thickness_pass_or_fail_requires_evidence(
    thickness: str,
    location: str,
    external_wall_count: Optional[int],
    expected_status: str,
) -> None:
    from src.services.mamad_validator import MamadValidator

    validator = MamadValidator()
    analysis_data = {
        "classification": {"primary_category": "WALL_SECTION"},
        "text_items": [],
        "dimensions": [],
        "annotations": [],
        "external_wall_count": external_wall_count,
        "structural_elements": [
            {"type": "wall", "thickness": thickness, "unit": "cm", "location": location},
        ],
    }

    result = validator.validate_segment(
        analysis_data,
        demo_mode=True,
        enabled_requirements={"1.2"},
    )

    evals = result.get("requirement_evaluations")
    assert isinstance(evals, list)
    ev_12 = next((e for e in evals if isinstance(e, dict) and e.get("requirement_id") == "1.2"), None)
    assert ev_12 is not None
    assert ev_12.get("status") == expected_status

    # Any pass/fail must contain evidence.
    _assert_no_passed_or_failed_without_evidence(evals)

    # If we got pass/fail, the requirement must be counted as checked.
    if expected_status in {"passed", "failed"}:
        assert "1.2" in (result.get("checked_requirements") or [])
    else:
        assert "1.2" not in (result.get("checked_requirements") or [])


def test_wall_thickness_runs_even_when_classified_as_room_layout_if_evidence_exists() -> None:
    from src.services.mamad_validator import MamadValidator

    validator = MamadValidator()
    analysis_data = {
        "classification": {"primary_category": "ROOM_LAYOUT"},
        "text_items": [],
        "dimensions": [{"value": 30, "unit": "cm", "element": "wall thickness", "location": "קיר חיצוני"}],
        "annotations": [],
        "external_wall_count": 1,
        "structural_elements": [
            {"type": "wall", "thickness": "30cm", "unit": "cm", "location": "קיר חיצוני"},
        ],
    }

    result = validator.validate_segment(
        analysis_data,
        demo_mode=True,
        enabled_requirements={"1.2"},
    )

    evals = result.get("requirement_evaluations")
    assert isinstance(evals, list)
    ev_12 = next((e for e in evals if isinstance(e, dict) and e.get("requirement_id") == "1.2"), None)
    assert ev_12 is not None
    assert ev_12.get("status") in {"passed", "failed", "not_checked"}
    if ev_12.get("status") in {"passed", "failed"}:
        assert "1.2" in (result.get("checked_requirements") or [])
        _assert_no_passed_or_failed_without_evidence(evals)


def test_wall_thickness_with_sliding_blast_window_requires_30cm_for_1_or_2_external_walls() -> None:
    from src.services.mamad_validator import MamadValidator

    v = MamadValidator()
    analysis_data = {
        "classification": {"primary_category": "ROOM_LAYOUT"},
        "text_items": [],
        "annotations": [],
        "dimensions": [],
        "external_wall_count": 1,
        "structural_elements": [
            {
                "type": "wall",
                "thickness": "25cm",
                "unit": "cm",
                "location": "קיר חיצוני",
                "notes": "wall_thickness_focus",
                "evidence": ["left", "top"],
            },
            {
                "type": "window",
                "location": "קיר חיצוני שמאלי",
                "notes": "חלון הדף נגרר (נישת גרירה) ת\"י 4422 ממ\"ד",
            },
        ],
    }

    result = v.validate_segment(
        analysis_data,
        demo_mode=True,
        enabled_requirements={"1.2"},
    )

    evals = result.get("requirement_evaluations")
    assert isinstance(evals, list)
    ev_12 = next((e for e in evals if isinstance(e, dict) and e.get("requirement_id") == "1.2"), None)
    assert ev_12 is not None
    assert ev_12.get("status") == "failed"
    assert "30" in str(ev_12.get("notes_he") or "")
    _assert_no_passed_or_failed_without_evidence(evals)


def test_wall_thickness_with_non_sliding_blast_window_does_not_require_30cm_for_1_or_2_external_walls() -> None:
    """Section 1.2 window-case (30cm) applies only to sliding blast windows.

    If the window is explicitly non-sliding (e.g., outward-opening), thickness should be evaluated
    as if there is no window.
    """

    from src.services.mamad_validator import MamadValidator

    v = MamadValidator()
    analysis_data = {
        "classification": {"primary_category": "ROOM_LAYOUT"},
        "text_items": [],
        "annotations": [],
        "dimensions": [],
        "external_wall_count": 1,
        "structural_elements": [
            {
                "type": "wall",
                "thickness": "25cm",
                "unit": "cm",
                "location": "קיר חיצוני",
                "notes": "wall_thickness_focus",
                "evidence": ["left"],
            },
            {
                "type": "window",
                "location": "קיר חיצוני שמאלי",
                "notes": "חלון הדף נפתח החוצה ת\"י 4422 ממ\"ד",
            },
        ],
    }

    result = v.validate_segment(
        analysis_data,
        demo_mode=True,
        enabled_requirements={"1.2"},
    )

    evals = result.get("requirement_evaluations")
    assert isinstance(evals, list)
    ev_12 = next((e for e in evals if isinstance(e, dict) and e.get("requirement_id") == "1.2"), None)
    assert ev_12 is not None
    assert ev_12.get("status") == "passed"
    _assert_no_passed_or_failed_without_evidence(evals)


def test_wall_thickness_rule_of_thumb_infers_external_internal_and_counts_walls() -> None:
    """Door=>internal, window=>external, perimeter sides=>external should allow a real 1.2 check.

    This mimics the common plan case where drawings don't explicitly say "external wall".
    """

    from src.services.mamad_validator import MamadValidator

    validator = MamadValidator()
    analysis_data = {
        "classification": {"primary_category": "ROOM_LAYOUT"},
        "text_items": [],
        "annotations": [],
        "dimensions": [],
        "external_wall_count": None,
        "structural_elements": [
            # Perimeter wall thickness callout referenced on multiple sides
            {
                "type": "wall",
                "thickness": "30cm",
                "unit": "cm",
                "location": "highlighted cyan perimeter wall",
                "notes": "wall_thickness_focus",
                "evidence": ["right side", "bottom-center", "top-left"],
            },
            # MAMAD door on the top wall => internal
            {
                "type": "door",
                "width": 80,
                "height": 200,
                "unit": "cm",
                "location": "קיר עליון (דלת ממ\"ד)",
                "notes": "ד.ה משוריינת",
            },
            # Window on the left wall => external
            {
                "type": "window",
                "width": 100,
                "height": 100,
                "unit": "cm",
                "location": "קיר שמאלי (חלון)",
                "notes": "חלון 100/100",
            },
        ],
    }

    result = validator.validate_segment(
        analysis_data,
        demo_mode=True,
        enabled_requirements={"1.2"},
    )

    evals = result.get("requirement_evaluations")
    assert isinstance(evals, list)
    ev_12 = next((e for e in evals if isinstance(e, dict) and e.get("requirement_id") == "1.2"), None)
    assert ev_12 is not None
    assert ev_12.get("status") == "passed"
    assert "1.2" in (result.get("checked_requirements") or [])
    _assert_no_passed_or_failed_without_evidence(evals)


def test_wall_thickness_does_not_treat_single_side_callout_as_external_due_to_window() -> None:
    """Regression: A single-side thickness (e.g., 20cm) near a window side must not be assumed external.

    This mirrors the real seg_001 case where a 20cm callout exists on the left side but is likely an
    internal/adjacent strip; only perimeter/multi-side callouts should drive 'external' classification.
    """

    from src.services.mamad_validator import MamadValidator

    v = MamadValidator()
    analysis_data = {
        "classification": {"primary_category": "ROOM_LAYOUT"},
        "text_items": [],
        "annotations": [],
        "dimensions": [],
        "external_wall_count": None,
        "structural_elements": [
            # Perimeter wall callout (multi-side) should be considered external.
            {
                "type": "wall",
                "thickness": "30cm",
                "unit": "cm",
                "location": "perimeter walls — top/left/right/bottom edges",
                "notes": "wall_thickness_focus",
                "evidence": ["top", "left", "right", "bottom"],
            },
            # Ambiguous single-side callout on the window side must NOT be auto-external.
            {
                "type": "wall",
                "thickness": "20cm",
                "unit": "cm",
                "location": "לא ברור",
                "notes": "סימון 20 בצד שמאל",
                "evidence": ["left"],
            },
            {
                "type": "door",
                "width": 80,
                "height": 200,
                "unit": "cm",
                "location": "קיר עליון (דלת ממ\"ד)",
                "notes": "ד.ה משוריינת",
            },
            {
                "type": "window",
                "width": 100,
                "height": 100,
                "unit": "cm",
                "location": "קיר שמאלי (חלון)",
                "notes": "חלון 100/100",
            },
        ],
    }

    result = v.validate_segment(
        analysis_data,
        demo_mode=True,
        enabled_requirements={"1.2"},
    )

    evals = result.get("requirement_evaluations")
    assert isinstance(evals, list)
    ev_12 = next((e for e in evals if isinstance(e, dict) and e.get("requirement_id") == "1.2"), None)
    assert ev_12 is not None
    assert ev_12.get("status") == "passed"
    assert "1.2" in (result.get("checked_requirements") or [])


def test_room_height_generic_h_marker_in_floor_plan_is_not_checked() -> None:
    """Regression: Non-section segments often contain multiple H= markers.

    A bare H=2.40 annotation (without explicit 'גובה חדר/תקרה' context) must not
    trigger a hard failure for 2.1, because it can refer to an opening/installation.
    """

    from src.services.mamad_validator import MamadValidator

    v = MamadValidator()
    analysis_data = {
        "classification": {"primary_category": "ROOM_LAYOUT"},
        "text_items": [
            {"text": "ממ\"ד", "language": "hebrew", "type": "label"},
            {"text": "H=2.40", "language": "hebrew", "type": "dimension"},
        ],
        # The segment pipeline currently injects this as a dimension element "room height".
        "dimensions": [
            {"value": 2.40, "unit": "m", "element": "room height", "location": "", "confidence": 0.95},
        ],
        "structural_elements": [],
        "annotations": [],
    }

    result = v.validate_segment(analysis_data, demo_mode=True, enabled_requirements={"2.1", "2.2"})
    evals = result.get("requirement_evaluations")
    assert isinstance(evals, list)
    ev_21 = next((e for e in evals if isinstance(e, dict) and e.get("requirement_id") == "2.1"), None)
    assert ev_21 is not None
    assert ev_21.get("status") == "not_checked"
    assert ev_21.get("reason_not_checked") in {
        "non_section_weak_height_evidence",
        "segment_not_section_like",
        "room_height_not_found",
    }


def test_room_height_word_present_but_opening_height_context_is_not_checked() -> None:
    """Regression: floor plans may include the word 'גובה' for opening/installation heights.

    Even if OCR includes 'גובה' and a Mamad label, 2.1 must NOT evaluate unless there is explicit
    room/ceiling height context (e.g., 'גובה תקרה', 'גובה חדר').
    """

    from src.services.mamad_validator import MamadValidator

    v = MamadValidator()
    analysis_data = {
        "classification": {"primary_category": "ROOM_LAYOUT"},
        "text_items": [
            {"text": 'ממ"ד', "language": "hebrew", "type": "label"},
            {"text": "גובה אדן חלון H=0.90", "language": "hebrew", "type": "note"},
            {"text": "H=2.40", "language": "hebrew", "type": "dimension"},
        ],
        # Simulate a mis-extraction where a floor plan height marker got injected as "room height".
        "dimensions": [
            {
                "value": 2.40,
                "unit": "m",
                "element": "room height",
                "location": "H=2.40",
                "confidence": 0.95,
            },
        ],
        "structural_elements": [],
        "annotations": [],
    }

    result = v.validate_segment(analysis_data, demo_mode=True, enabled_requirements={"2.1", "2.2"})
    evals = result.get("requirement_evaluations")
    assert isinstance(evals, list)
    ev_21 = next((e for e in evals if isinstance(e, dict) and e.get("requirement_id") == "2.1"), None)
    assert ev_21 is not None
    assert ev_21.get("status") == "not_checked"
    assert ev_21.get("reason_not_checked") in {
        "non_section_weak_height_evidence",
        "segment_not_section_like",
        "room_height_not_found",
        "segment_top_view",
    }


def test_room_height_not_checked_when_summary_marks_floor_plan_even_if_category_is_sections() -> None:
    """Regression: classification can be noisy; view signal should win.

    If the segment is a top-view floor plan, 2.1/2.2 must be not_checked even if:
    - primary_category is incorrectly set to SECTIONS
    - a height value was injected into dimensions
    """

    from src.services.mamad_validator import MamadValidator

    v = MamadValidator()
    analysis_data = {
        "classification": {"primary_category": "SECTIONS"},
        "summary": {"primary_function": "floor_plan"},
        "text_items": [
            {"text": 'ממ"ד', "language": "hebrew", "type": "label"},
            {"text": "H=2.40", "language": "hebrew", "type": "dimension"},
        ],
        "dimensions": [
            {"value": 2.40, "unit": "m", "element": "room height", "location": "H=2.40", "confidence": 0.95},
        ],
        "structural_elements": [],
        "annotations": [],
    }

    result = v.validate_segment(analysis_data, demo_mode=True, enabled_requirements={"2.1", "2.2"})
    evals = result.get("requirement_evaluations")
    assert isinstance(evals, list)
    ev_21 = next((e for e in evals if isinstance(e, dict) and e.get("requirement_id") == "2.1"), None)
    assert ev_21 is not None
    assert ev_21.get("status") == "not_checked"
    assert ev_21.get("reason_not_checked") == "segment_top_view"


def test_room_height_explicit_ceiling_height_text_fails_when_below_standard() -> None:
    """If the segment explicitly states ceiling/room height for the Mamad, 2.1 should evaluate."""

    from src.services.mamad_validator import MamadValidator

    v = MamadValidator()
    analysis_data = {
        "classification": {"primary_category": "ROOM_LAYOUT"},
        "text_items": [
            {"text": "ממ\"ד", "language": "hebrew", "type": "label"},
            {"text": "גובה תקרה 2.40", "language": "hebrew", "type": "note"},
        ],
        "dimensions": [
            {
                "value": 2.40,
                "unit": "m",
                "element": "room height",
                "location": "גובה תקרה בחלל הממ\"ד",
                "confidence": 0.95,
            },
        ],
        "structural_elements": [],
        "annotations": [],
    }

    result = v.validate_segment(analysis_data, demo_mode=True, enabled_requirements={"2.1", "2.2"})
    evals = result.get("requirement_evaluations")
    assert isinstance(evals, list)
    ev_21 = next((e for e in evals if isinstance(e, dict) and e.get("requirement_id") == "2.1"), None)
    assert ev_21 is not None
    assert ev_21.get("status") == "failed"

    # Any pass/fail must contain evidence.
    _assert_no_passed_or_failed_without_evidence(evals)


def test_wall_thickness_does_not_fail_on_top_bottom_location_noise_without_explicit_external_markers() -> None:
    """Regression: free-form location strings like 'base/top of section' must not infer external walls.

    This matches the 474c1df9 pattern where a 20cm dimension exists near the window detail and was
    incorrectly treated as an external wall thickness, causing a false 1.2 failure.
    """

    from src.services.mamad_validator import MamadValidator

    v = MamadValidator()
    analysis_data = {
        "classification": {"primary_category": "REBAR_DETAILS"},
        "text_items": [{"text": "חלון A1", "language": "hebrew", "type": "title"}],
        "annotations": [{"text": "פנים", "type": "label"}, {"text": "חוץ", "type": "label"}],
        "dimensions": [],
        "external_wall_count": None,
        "structural_elements": [
            {
                "type": "wall",
                "thickness": "20.0 cm",
                "unit": "cm",
                "location": "right-side vertical section detail, small horizontal dimension at base/top of section",
                "notes": "wall_thickness_focus",
                "evidence": ["dimension label '20' shown as a short horizontal thickness marker"],
            },
            {
                "type": "wall",
                "thickness": "25cm",
                "unit": "cm",
                "location": "לא ברור",
            },
            {
                "type": "window",
                "width": 100,
                "height": 115,
                "unit": "cm",
                "location": "פתח חלון A1",
            },
        ],
    }

    result = v.validate_segment(
        analysis_data,
        demo_mode=True,
        enabled_requirements={"1.2"},
    )

    evals = result.get("requirement_evaluations")
    assert isinstance(evals, list)
    ev_12 = next((e for e in evals if isinstance(e, dict) and e.get("requirement_id") == "1.2"), None)
    assert ev_12 is not None
    # Must not hard-fail based on ambiguous inferred-external 20cm.
    assert ev_12.get("status") in {"not_checked", "passed"}
    assert ev_12.get("status") != "failed"


def test_window_spacing_passes_when_all_3_2_base_checks_present_and_meet_thresholds() -> None:
    from src.services.mamad_validator import MamadValidator

    v = MamadValidator()
    analysis_data = {
        "classification": {"primary_category": "WINDOW_DETAILS"},
        "text_items": [],
        "dimensions": [],
        "annotations": [],
        "structural_elements": [
            {"type": "window", "location": "פרט חלון הדף", "notes": "חלון"},
        ],
        "window_spacing_focus": {
            "windows": [
                {
                    "niche_to_niche_cm": 20,
                    "light_openings_spacing_cm": 100,
                    "to_perpendicular_wall_cm": 20,
                    "same_wall_door_separation_cm": None,
                    "door_height_cm": None,
                    "has_concrete_wall_between_openings": None,
                    "concrete_wall_thickness_cm": None,
                    "confidence": 0.9,
                    "location": "חלון הדף",
                    "evidence": ["20", "100", "20"],
                }
            ]
        },
    }

    result = v.validate_segment(analysis_data, demo_mode=True, enabled_requirements={"3.2"})
    evals = result.get("requirement_evaluations")
    assert isinstance(evals, list)
    ev = next((e for e in evals if isinstance(e, dict) and e.get("requirement_id") == "3.2"), None)
    assert ev is not None
    assert ev.get("status") == "passed"
    assert "3.2" in (result.get("checked_requirements") or [])
    _assert_no_passed_or_failed_without_evidence(evals)


def test_window_spacing_passes_when_only_applicable_subrules_have_confident_numeric_evidence() -> None:
    from src.services.mamad_validator import MamadValidator

    v = MamadValidator()
    analysis_data = {
        "classification": {"primary_category": "WINDOW_DETAILS"},
        "text_items": [],
        "dimensions": [],
        "annotations": [],
        "structural_elements": [
            {"type": "window", "location": "פרט חלון הדף", "notes": "חלון"},
        ],
        # Simulates the real-world case: we can verify 100cm between openings and 20cm to a perpendicular wall,
        # but niche-to-niche is not applicable/available in this segment.
        "window_spacing_focus": {
            "windows": [
                {
                    "niche_to_niche_cm": None,
                    "light_openings_spacing_cm": 100,
                    "to_perpendicular_wall_cm": 20,
                    "same_wall_door_separation_cm": None,
                    "door_height_cm": None,
                    "has_concrete_wall_between_openings": None,
                    "concrete_wall_thickness_cm": None,
                    "confidence": 0.62,
                    "location": "חלון הדף",
                    "evidence": ["100", "20"],
                }
            ]
        },
    }

    result = v.validate_segment(analysis_data, demo_mode=True, enabled_requirements={"3.2"})
    evals = result.get("requirement_evaluations")
    assert isinstance(evals, list)
    ev = next((e for e in evals if isinstance(e, dict) and e.get("requirement_id") == "3.2"), None)
    assert ev is not None
    assert ev.get("status") == "passed"
    assert "3.2" in (result.get("checked_requirements") or [])
    _assert_no_passed_or_failed_without_evidence(evals)


def test_window_spacing_fails_when_any_base_threshold_violated_with_confident_numeric_evidence() -> None:
    from src.services.mamad_validator import MamadValidator

    v = MamadValidator()
    analysis_data = {
        "classification": {"primary_category": "WINDOW_DETAILS"},
        "text_items": [],
        "dimensions": [],
        "annotations": [],
        "structural_elements": [
            {"type": "window", "location": "פרט חלון הדף", "notes": "חלון"},
        ],
        "window_spacing_focus": {
            "windows": [
                {
                    "niche_to_niche_cm": 20,
                    "light_openings_spacing_cm": 100,
                    "to_perpendicular_wall_cm": 15,
                    "confidence": 0.9,
                    "location": "חלון הדף",
                    "evidence": ["15"],
                }
            ]
        },
    }

    result = v.validate_segment(analysis_data, demo_mode=True, enabled_requirements={"3.2"})
    evals = result.get("requirement_evaluations")
    assert isinstance(evals, list)
    ev = next((e for e in evals if isinstance(e, dict) and e.get("requirement_id") == "3.2"), None)
    assert ev is not None
    assert ev.get("status") == "failed"
    assert "3.2" in (result.get("checked_requirements") or [])
    _assert_no_passed_or_failed_without_evidence(evals)


def test_window_spacing_is_not_checked_when_focus_confidence_is_low() -> None:
    from src.services.mamad_validator import MamadValidator

    v = MamadValidator()
    analysis_data = {
        "classification": {"primary_category": "WINDOW_DETAILS"},
        "text_items": [],
        "dimensions": [],
        "annotations": [],
        "structural_elements": [
            {"type": "window", "location": "פרט חלון הדף", "notes": "חלון"},
        ],
        "window_spacing_focus": {
            "windows": [
                {
                    "niche_to_niche_cm": 20,
                    "light_openings_spacing_cm": 100,
                    "to_perpendicular_wall_cm": 20,
                    "confidence": 0.4,
                    "location": "חלון הדף",
                    "evidence": ["20", "100"],
                }
            ]
        },
    }

    result = v.validate_segment(analysis_data, demo_mode=True, enabled_requirements={"3.2"})
    evals = result.get("requirement_evaluations")
    assert isinstance(evals, list)
    ev = next((e for e in evals if isinstance(e, dict) and e.get("requirement_id") == "3.2"), None)
    assert ev is not None
    assert ev.get("status") == "not_checked"
    assert "3.2" not in (result.get("checked_requirements") or [])


def test_window_and_door_same_wall_rule_fails_when_separation_below_door_height_and_no_concrete_separator() -> None:
    from src.services.mamad_validator import MamadValidator

    v = MamadValidator()
    analysis_data = {
        "classification": {"primary_category": "WINDOW_DETAILS"},
        "text_items": [],
        "dimensions": [],
        "annotations": [],
        "structural_elements": [
            {"type": "window", "location": "קיר משותף", "notes": "חלון"},
        ],
        "window_spacing_focus": {
            "windows": [
                {
                    "niche_to_niche_cm": 20,
                    "light_openings_spacing_cm": 100,
                    "to_perpendicular_wall_cm": 20,
                    "same_wall_door_separation_cm": 150,
                    "door_height_cm": 200,
                    "has_concrete_wall_between_openings": False,
                    "confidence": 0.9,
                    "location": "קיר משותף",
                    "evidence": ["150", "200"],
                }
            ]
        },
    }

    result = v.validate_segment(analysis_data, demo_mode=True, enabled_requirements={"3.2"})
    evals = result.get("requirement_evaluations")
    assert isinstance(evals, list)
    ev = next((e for e in evals if isinstance(e, dict) and e.get("requirement_id") == "3.2"), None)
    assert ev is not None
    assert ev.get("status") == "failed"
    assert "3.2" in (result.get("checked_requirements") or [])
    _assert_no_passed_or_failed_without_evidence(evals)


def test_window_and_door_same_wall_rule_passes_when_concrete_wall_between_openings_is_at_least_20cm() -> None:
    from src.services.mamad_validator import MamadValidator

    v = MamadValidator()
    analysis_data = {
        "classification": {"primary_category": "WINDOW_DETAILS"},
        "text_items": [],
        "dimensions": [],
        "annotations": [],
        "structural_elements": [
            {"type": "window", "location": "קיר משותף", "notes": "חלון"},
        ],
        "window_spacing_focus": {
            "windows": [
                {
                    "niche_to_niche_cm": 20,
                    "light_openings_spacing_cm": 100,
                    "to_perpendicular_wall_cm": 20,
                    "has_concrete_wall_between_openings": True,
                    "concrete_wall_thickness_cm": 20,
                    "confidence": 0.9,
                    "location": "קיר משותף",
                    "evidence": ["קיר 20"],
                }
            ]
        },
    }

    result = v.validate_segment(analysis_data, demo_mode=True, enabled_requirements={"3.2"})
    evals = result.get("requirement_evaluations")
    assert isinstance(evals, list)
    ev = next((e for e in evals if isinstance(e, dict) and e.get("requirement_id") == "3.2"), None)
    assert ev is not None
    assert ev.get("status") == "passed"
    assert "3.2" in (result.get("checked_requirements") or [])
    _assert_no_passed_or_failed_without_evidence(evals)
    _assert_no_passed_or_failed_without_evidence(evals)


def test_room_height_evaluation_requires_evidence_when_failed() -> None:
    from src.services.mamad_validator import MamadValidator

    validator = MamadValidator()
    analysis_data = {
        "classification": {"primary_category": "SECTIONS"},
        "text_items": [{"text": "H=2.30"}],
        "annotations": [],
        "structural_elements": [],
        "dimensions": [
            {"value": 2.30, "unit": "m", "element": "room height", "location": "H=2.30"},
        ],
    }

    result = validator.validate_segment(
        analysis_data,
        demo_mode=True,
        enabled_requirements={"2.1", "2.2"},
    )

    evals = result.get("requirement_evaluations")
    assert isinstance(evals, list)
    ev_21 = next((e for e in evals if isinstance(e, dict) and e.get("requirement_id") == "2.1"), None)
    assert ev_21 is not None
    assert ev_21.get("status") == "failed"

    _assert_no_passed_or_failed_without_evidence(evals)
    assert "2.1" in (result.get("checked_requirements") or [])


def test_room_height_low_confidence_below_exception_is_not_checked() -> None:
    from src.services.mamad_validator import MamadValidator

    validator = MamadValidator()
    analysis_data = {
        "classification": {"primary_category": "SECTIONS"},
        "text_items": [],
        "annotations": [],
        "structural_elements": [],
        "dimensions": [
            {"value": 2.0, "unit": "m", "element": "room height", "location": "unclear", "confidence": 0.4},
        ],
    }

    result = validator.validate_segment(
        analysis_data,
        demo_mode=True,
        enabled_requirements={"2.1", "2.2"},
    )

    evals = result.get("requirement_evaluations")
    assert isinstance(evals, list)
    ev_21 = next((e for e in evals if isinstance(e, dict) and e.get("requirement_id") == "2.1"), None)
    ev_22 = next((e for e in evals if isinstance(e, dict) and e.get("requirement_id") == "2.2"), None)
    assert ev_21 is not None and ev_21.get("status") == "not_checked"
    assert ev_22 is not None and ev_22.get("status") == "not_checked"
    _assert_no_passed_or_failed_without_evidence(evals)


def test_room_height_implausible_height_is_not_checked() -> None:
    from src.services.mamad_validator import MamadValidator

    validator = MamadValidator()
    analysis_data = {
        "classification": {"primary_category": "SECTIONS"},
        "text_items": [],
        "annotations": [],
        "structural_elements": [],
        "dimensions": [
            {"value": 0.3, "unit": "m", "element": "room height", "location": "detail", "confidence": 0.2},
        ],
    }

    result = validator.validate_segment(
        analysis_data,
        demo_mode=True,
        enabled_requirements={"2.1", "2.2"},
    )

    evals = result.get("requirement_evaluations")
    assert isinstance(evals, list)
    ev_21 = next((e for e in evals if isinstance(e, dict) and e.get("requirement_id") == "2.1"), None)
    ev_22 = next((e for e in evals if isinstance(e, dict) and e.get("requirement_id") == "2.2"), None)
    assert ev_21 is not None and ev_21.get("status") == "not_checked"
    assert ev_22 is not None and ev_22.get("status") == "not_checked"
    _assert_no_passed_or_failed_without_evidence(evals)


def test_room_height_exception_22_passes_only_when_context_and_volume_present() -> None:
    """2.2 should be evaluated only when basement/addition context exists, and requires volume evidence."""

    from src.services.mamad_validator import MamadValidator

    v = MamadValidator()
    analysis_data = {
        "classification": {"primary_category": "SECTIONS"},
        "text_items": [{"text": "מרתף"}, {"text": "נפח 23 m3"}],
        "annotations": [],
        "structural_elements": [],
        "dimensions": [
            {"value": 2.30, "unit": "m", "element": "room height", "location": "H=2.30", "confidence": 0.9},
            {"value": 23.0, "unit": "m3", "element": "room volume", "location": "נפח", "confidence": 0.9},
        ],
    }

    result = v.validate_segment(analysis_data, demo_mode=True, enabled_requirements={"2.1", "2.2"})
    evals = result.get("requirement_evaluations")
    assert isinstance(evals, list)
    ev_21 = next((e for e in evals if isinstance(e, dict) and e.get("requirement_id") == "2.1"), None)
    ev_22 = next((e for e in evals if isinstance(e, dict) and e.get("requirement_id") == "2.2"), None)
    assert ev_21 is not None and ev_21.get("status") == "passed"
    assert ev_22 is not None and ev_22.get("status") == "passed"
    assert set(result.get("checked_requirements") or []) >= {"2.1", "2.2"}
    _assert_no_passed_or_failed_without_evidence(evals)


def test_requirement_11_external_wall_count_passes_with_explicit_count() -> None:
    from src.services.mamad_validator import MamadValidator

    v = MamadValidator()
    analysis_data = {
        "classification": {"primary_category": "ROOM_LAYOUT"},
        "text_items": [],
        "annotations": [],
        "dimensions": [],
        "structural_elements": [],
        "external_wall_count": 2,
    }

    result = v.validate_segment(analysis_data, demo_mode=True, enabled_requirements={"1.1"})
    evals = result.get("requirement_evaluations")
    assert isinstance(evals, list)
    ev = next((e for e in evals if isinstance(e, dict) and e.get("requirement_id") == "1.1"), None)
    assert ev is not None
    assert ev.get("status") == "passed"
    assert "1.1" in (result.get("checked_requirements") or [])
    _assert_no_passed_or_failed_without_evidence(evals)


def test_requirement_13_requires_protective_wall_when_claiming_not_external_near_exterior_line() -> None:
    from src.services.mamad_validator import MamadValidator

    v = MamadValidator()
    analysis_data = {
        "classification": {"primary_category": "ROOM_LAYOUT"},
        "text_items": [
            {"text": "קו חיצוני של הבניין 2m"},
            {"text": "לא נחשב קיר חיצוני"},
        ],
        "annotations": [],
        "dimensions": [],
        "structural_elements": [],
    }

    result = v.validate_segment(analysis_data, demo_mode=True, enabled_requirements={"1.3"})
    evals = result.get("requirement_evaluations")
    assert isinstance(evals, list)
    ev = next((e for e in evals if isinstance(e, dict) and e.get("requirement_id") == "1.3"), None)
    assert ev is not None
    assert ev.get("status") == "failed"
    assert "1.3" in (result.get("checked_requirements") or [])
    _assert_no_passed_or_failed_without_evidence(evals)


def test_requirement_14_is_not_applicable_when_clear_opening_not_above_28m() -> None:
    from src.services.mamad_validator import MamadValidator

    v = MamadValidator()
    analysis_data = {
        "classification": {"primary_category": "SECTIONS"},
        "text_items": [],
        "annotations": [],
        "structural_elements": [],
        "dimensions": [
            {"value": 2.70, "unit": "m", "element": "בטון-לבטון", "location": "חתך"},
        ],
    }

    result = v.validate_segment(analysis_data, demo_mode=True, enabled_requirements={"1.4"})
    evals = result.get("requirement_evaluations")
    assert isinstance(evals, list)
    ev = next((e for e in evals if isinstance(e, dict) and e.get("requirement_id") == "1.4"), None)
    assert ev is not None
    assert ev.get("status") == "not_checked"
    assert ev.get("reason_not_checked") == "not_applicable_not_high_wall"


def test_requirement_15_passes_when_tower_continuity_at_least_70_percent() -> None:
    from src.services.mamad_validator import MamadValidator

    v = MamadValidator()
    analysis_data = {
        "classification": {"primary_category": "ROOM_LAYOUT"},
        "text_items": [{"text": "מגדל ממ\"דים רציפות: 75%"}],
        "annotations": [],
        "dimensions": [],
        "structural_elements": [],
    }

    result = v.validate_segment(analysis_data, demo_mode=True, enabled_requirements={"1.5"})
    evals = result.get("requirement_evaluations")
    assert isinstance(evals, list)
    ev = next((e for e in evals if isinstance(e, dict) and e.get("requirement_id") == "1.5"), None)
    assert ev is not None
    assert ev.get("status") == "passed"
    assert "1.5" in (result.get("checked_requirements") or [])
    _assert_no_passed_or_failed_without_evidence(evals)


def test_wall_thickness_uses_post_exception_external_wall_count_when_provided() -> None:
    """1.2 must depend on the *final* external wall count after applying 1.1–1.3 exceptions."""

    from src.services.mamad_validator import MamadValidator

    v = MamadValidator()
    analysis_data = {
        "classification": {"primary_category": "ROOM_LAYOUT"},
        "text_items": [],
        "annotations": [],
        "dimensions": [],
        # Base count might be uncertain/earlier; final count after exceptions is stricter.
        "external_wall_count": 2,
        "external_wall_count_after_exceptions": 4,
        "structural_elements": [
            {"type": "wall", "thickness": "30cm", "unit": "cm", "location": "קיר חיצוני"},
        ],
    }

    result = v.validate_segment(analysis_data, demo_mode=True, enabled_requirements={"1.2"})
    evals = result.get("requirement_evaluations")
    assert isinstance(evals, list)
    ev_12 = next((e for e in evals if isinstance(e, dict) and e.get("requirement_id") == "1.2"), None)
    assert ev_12 is not None
    # With 4 external walls, required thickness is 40cm; 30cm must fail.
    assert ev_12.get("status") == "failed"
    assert "1.2" in (result.get("checked_requirements") or [])
    _assert_no_passed_or_failed_without_evidence(evals)


def test_wall_thickness_wall_section_without_external_labels_does_not_skip() -> None:
    from src.services.mamad_validator import MamadValidator

    v = MamadValidator()
    analysis_data = {
        "classification": {"primary_category": "WALL_SECTION"},
        "text_items": [],
        "annotations": [],
        "dimensions": [],
        "structural_elements": [
            {"type": "wall", "thickness": "30", "location": "", "notes": ""},
            {"type": "wall", "thickness": "25", "location": "", "notes": ""},
        ],
    }

    result = v.validate_segment(
        analysis_data,
        demo_mode=True,
        enabled_requirements={"1.2"},
    )

    evals = result.get("requirement_evaluations")
    assert isinstance(evals, list)
    ev_12 = next((e for e in evals if isinstance(e, dict) and e.get("requirement_id") == "1.2"), None)
    assert ev_12 is not None
    # We shouldn't bail out with no_external... just because labels are missing.
    assert ev_12.get("reason_not_checked") != "no_external_wall_thickness_identified"
    _assert_no_passed_or_failed_without_evidence(evals)


def test_wall_thickness_unknown_count_but_internal_side_and_30cm_passes() -> None:
    from src.services.mamad_validator import MamadValidator

    v = MamadValidator()
    analysis_data = {
        "classification": {"primary_category": "ROOM_LAYOUT"},
        "text_items": [],
        "annotations": [],
        "dimensions": [],
        "structural_elements": [
            # Door indicates an internal side (top)
            {"type": "door", "location": "בחלק העליון של הממ\"ד (כניסה)", "notes": 'דלת ממ"ד 80/200'},
            # Window suggests an external wall exists (left)
            {"type": "window", "location": "בקיר שמאלי", "notes": 'חלון 100/100'},
            # Perimeter thickness callout references multiple sides -> classified as external
            {
                "type": "wall",
                "thickness": "30",
                "location": "Perimeter wall thickness marked along top/left/bottom",
                "notes": "",
                "evidence": ["top", "left", "bottom"],
            },
        ],
    }

    result = v.validate_segment(
        analysis_data,
        demo_mode=True,
        enabled_requirements={"1.2"},
    )

    evals = result.get("requirement_evaluations")
    assert isinstance(evals, list)
    ev_12 = next((e for e in evals if isinstance(e, dict) and e.get("requirement_id") == "1.2"), None)
    assert ev_12 is not None
    assert ev_12.get("status") == "passed"


def test_door_spacing_pass_requires_both_sides_and_evidence():
    from src.services.mamad_validator import MamadValidator

    v = MamadValidator()
    analysis_data = {
        "classification": {"primary_category": "DOOR_DETAILS"},
        "text_items": [],
        "dimensions": [],
        "structural_elements": [
            {
                "type": "door",
                "spacing_internal_cm": 300,
                "spacing_external_cm": 200,
                "spacing_confidence": 0.95,
                "location": "test",
            }
        ],
    }

    result = v.validate_segment(analysis_data, demo_mode=True, enabled_requirements={"3.1"})
    assert "3.1" in (result.get("checked_requirements") or [])
    evs = result.get("requirement_evaluations") or []
    ev_31 = [e for e in evs if e.get("requirement_id") == "3.1"]
    assert ev_31 and ev_31[-1].get("status") == "passed"
    assert ev_31[-1].get("evidence"), "3.1 passed must include evidence"


def test_door_spacing_low_confidence_is_not_checked():
    from src.services.mamad_validator import MamadValidator

    v = MamadValidator()
    analysis_data = {
        "classification": {"primary_category": "DOOR_DETAILS"},
        "text_items": [],
        "dimensions": [],
        "structural_elements": [
            {
                "type": "door",
                "spacing_internal_cm": 300,
                "spacing_external_cm": 200,
                "spacing_confidence": 0.2,
                "location": "test",
            }
        ],
    }

    result = v.validate_segment(analysis_data, demo_mode=True, enabled_requirements={"3.1"})
    assert "3.1" not in (result.get("checked_requirements") or [])
    evs = result.get("requirement_evaluations") or []
    ev_31 = [e for e in evs if e.get("requirement_id") == "3.1"]
    assert ev_31 and ev_31[-1].get("status") == "not_checked"
