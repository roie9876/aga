from src.services.external_wall_context import (
    SegmentCandidate,
    select_floor_plan_candidate,
    select_mamad_reference_candidate,
)


def test_select_floor_plan_candidate_prefers_floor_plan_tag_over_mamad_plan() -> None:
    candidates = [
        SegmentCandidate(
            segment_id="seg_mamad",
            blob_url="https://example.com/mamad.png",
            segment_type="floor_plan",  # mis-typed
            description="Cropped image",
            analysis_data={
                "content_tags": [
                    {"tag": "mamad_plan_1_15", "confidence": 0.95},
                ],
                "summary": {"primary_function": "room_layout"},
            },
        ),
        SegmentCandidate(
            segment_id="seg_floor",
            blob_url="https://example.com/floor.png",
            segment_type="floor_plan",
            description="תכנית קומה 1:100",
            analysis_data={
                "content_tags": [
                    {"tag": "floor_plan", "confidence": 0.95},
                ],
                "summary": {"primary_function": "floor_plan"},
            },
        ),
    ]

    picked = select_floor_plan_candidate(candidates)
    assert picked is not None
    assert picked.segment_id == "seg_floor"


def test_select_mamad_reference_candidate_prefers_mamad_plan_tag() -> None:
    candidates = [
        SegmentCandidate(
            segment_id="seg_detail",
            blob_url="https://example.com/detail.png",
            segment_type="detail",
            description="(OCR missing)",
            analysis_data={
                "content_tags": [
                    {"tag": "window_opening_detail", "confidence": 0.95},
                ],
                "text_items": [{"text": "1:25", "type": "title"}],
            },
        ),
        SegmentCandidate(
            segment_id="seg_mamad",
            blob_url="https://example.com/mamad.png",
            segment_type="floor_plan",
            description="(OCR missing)",
            analysis_data={
                "content_tags": [
                    {"tag": "mamad_wall_drop_plan", "confidence": 0.95},
                ],
                "text_items": [{"text": "1:50", "type": "title"}],
            },
        ),
    ]

    picked = select_mamad_reference_candidate(candidates)
    assert picked is not None
    assert picked.segment_id == "seg_mamad"
