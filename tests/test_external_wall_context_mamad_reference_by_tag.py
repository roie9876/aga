from src.services.external_wall_context import SegmentCandidate, select_mamad_reference_candidate


def test_select_mamad_reference_candidate_uses_content_tag() -> None:
    candidates = [
        SegmentCandidate(
            segment_id="seg_a",
            blob_url="https://example.com/a.png",
            segment_type="detail",
            description="General notes",
            analysis_data={
                "content_tags": ["general_notes"],
                "text_items": [{"text": "כללי", "type": "note"}],
            },
        ),
        SegmentCandidate(
            segment_id="seg_b",
            blob_url="https://example.com/b.png",
            segment_type="detail",
            description="(OCR missing)",
            analysis_data={
                # No 'ממ\"ד' in any text fields, but the tag indicates MAMAD plan.
                "content_tags": ["mamad_plan_1_15"],
                "text_items": [{"text": "1:50", "type": "title"}],
            },
        ),
    ]

    picked = select_mamad_reference_candidate(candidates)
    assert picked is not None
    assert picked.segment_id == "seg_b"
