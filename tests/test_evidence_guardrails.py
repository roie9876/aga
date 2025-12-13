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
    "thickness,expected_status",
    [
        ("30cm", "passed"),
        ("20cm", "failed"),
    ],
)
def test_wall_thickness_pass_or_fail_requires_evidence(thickness: str, expected_status: str) -> None:
    from src.services.mamad_validator import MamadValidator

    validator = MamadValidator()
    analysis_data = {
        "classification": {"primary_category": "WALL_SECTION"},
        "text_items": [],
        "dimensions": [],
        "annotations": [],
        "structural_elements": [
            {"type": "wall", "thickness": thickness, "unit": "cm", "location": "test-wall"},
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
    assert "1.2" in (result.get("checked_requirements") or [])


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
