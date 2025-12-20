import pytest
from fastapi.testclient import TestClient


@pytest.mark.asyncio
async def test_run_submission_preflight_reports_for_complete_package() -> None:
    from src.services.submission_preflight import run_submission_preflight
    from src.models.preflight import PreflightStatus

    decomposition = {
        "id": "decomp-1",
        "type": "decomposition",
        "segments": [
            {"segment_id": "s-floor", "type": "floor_plan", "title": "תוכנית קומה 1:100"},
            {"segment_id": "s-sec-1", "type": "section", "title": "חתך א-א 1:100"},
            {"segment_id": "s-sec-2", "type": "section", "title": "חתך ב-ב 1:100"},
            {"segment_id": "s-elev", "type": "elevation", "title": "חזית צפונית 1:100"},
            {"segment_id": "s-table", "type": "table", "title": "טבלה מרכזת פרטי בקשה 123456"},
            {"segment_id": "s-env", "type": "other", "title": "תשריט סביבה 1:250"},
            {"segment_id": "s-site", "type": "other", "title": "מפה מצבית 1:250"},
            {"segment_id": "s-decl", "type": "other", "title": "הצהרה חתומה"},
            {
                "segment_id": "s-mamad",
                "type": "detail",
                "title": "תכנית ממ\"ד 1:50",
                "analysis_data": {"text_items": [{"text": "ממ\"ד"}], "dimensions": [{"value": 1, "unit": "m"}]},
            },
            {"segment_id": "s-legend", "type": "legend", "title": "מקרא"},
            {
                "segment_id": "s-struct",
                "type": "detail",
                "title": "פרטי זיון",
                "analysis_data": {"rebar_details": [{"note": "stub"}]},
            },
        ],
    }

    approved = [s["segment_id"] for s in decomposition["segments"]]
    passed, checks = await run_submission_preflight(
        decomposition=decomposition,
        approved_segment_ids=approved,
        strict=False,
        run_llm_checks=False,
    )

    assert passed is False
    assert isinstance(checks, list)
    # Spot-check required preflight IDs exist
    check_ids = {c.check_id for c in checks}
    assert {"PF-01", "PF-02", "PF-03", "PF-04", "PF-05", "PF-06", "PF-07", "PF-13"}.issubset(check_ids)

    pf03 = next((c for c in checks if c.check_id == "PF-03"), None)
    assert pf03 is not None
    assert pf03.status in {PreflightStatus.FAILED, PreflightStatus.ERROR}


@pytest.mark.asyncio
async def test_run_submission_preflight_strict_fails_when_mamad_missing() -> None:
    from src.services.submission_preflight import run_submission_preflight
    from src.models.preflight import PreflightStatus

    decomposition = {
        "id": "decomp-2",
        "type": "decomposition",
        "segments": [
            {"segment_id": "s-floor", "type": "floor_plan", "title": "תוכנית קומה 1:100"},
            {"segment_id": "s-sec-1", "type": "section", "title": "חתך א-א 1:100"},
            {"segment_id": "s-sec-2", "type": "section", "title": "חתך ב-ב 1:100"},
            {"segment_id": "s-elev", "type": "elevation", "title": "חזית צפונית 1:100"},
            {"segment_id": "s-table", "type": "table", "title": "טבלה מרכזת פרטי בקשה"},
            {"segment_id": "s-env", "type": "other", "title": "תשריט סביבה"},
            {"segment_id": "s-site", "type": "other", "title": "מפה מצבית"},
            {"segment_id": "s-decl", "type": "other", "title": "הצהרה חתומה"},
        ],
    }

    approved = [s["segment_id"] for s in decomposition["segments"]]
    passed, checks = await run_submission_preflight(
        decomposition=decomposition,
        approved_segment_ids=approved,
        strict=True,
        run_llm_checks=False,
    )

    assert passed is False
    pf07 = next((c for c in checks if c.check_id == "PF-07"), None)
    assert pf07 is not None
    assert pf07.status in {PreflightStatus.FAILED, PreflightStatus.ERROR}


def test_preflight_route_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.api.main import app
    import src.api.routes.preflight as preflight_route

    decomposition = {"id": "decomp-3", "type": "decomposition", "segments": []}

    class DummyCosmos:
        async def query_items(self, query: str, parameters: list[dict]):  # noqa: ANN001
            return [decomposition]

    async def dummy_run_submission_preflight(**kwargs):  # noqa: ANN001
        return True, []

    monkeypatch.setattr(preflight_route, "get_cosmos_client", lambda: DummyCosmos())
    monkeypatch.setattr(preflight_route, "run_submission_preflight", dummy_run_submission_preflight)

    client = TestClient(app)
    resp = client.post(
        "/api/v1/preflight",
        json={
            "decomposition_id": "decomp-3",
            "approved_segment_ids": ["x"],
            "mode": "segments",
            "strict": False,
            "run_llm_checks": False,
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["passed"] is True
    assert isinstance(data.get("checks"), list)


def test_preflight_route_rejects_full_plan_mode() -> None:
    from src.api.main import app

    client = TestClient(app)
    resp = client.post(
        "/api/v1/preflight",
        json={
            "decomposition_id": "decomp-4",
            "approved_segment_ids": ["x"],
            "mode": "full_plan",
            "strict": False,
            "run_llm_checks": False,
        },
    )

    assert resp.status_code == 400
