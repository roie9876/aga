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
