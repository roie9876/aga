#!/usr/bin/env python3
"""Summarize external-wall inference injection + REQ 1.1/1.2 outcomes from a report JSON.

Usage:
  python scripts/debug_report_wall_context.py /path/to/mamad-report-....json

This script intentionally prints a small, stable output to avoid hanging terminals.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        import orjson  # type: ignore

        return orjson.loads(path.read_bytes())
    except Exception:
        return json.loads(path.read_text(encoding="utf-8"))


def _iter_req_evals(seg: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    v = seg.get("validation") or {}
    ev = v.get("requirement_evaluations")
    if isinstance(ev, list):
        for item in ev:
            if isinstance(item, dict):
                yield item
        return

    reqs = v.get("requirements")
    if isinstance(reqs, list):
        for item in reqs:
            if isinstance(item, dict):
                yield item
        return

    if isinstance(reqs, dict):
        for item in reqs.values():
            if isinstance(item, dict):
                yield item


def _get_eval(seg: Dict[str, Any], requirement_id: str) -> Optional[Dict[str, Any]]:
    for e in _iter_req_evals(seg):
        if e.get("requirement_id") == requirement_id:
            return e
    return None


def _short(s: Any, n: int = 180) -> str:
    try:
        text = str(s or "")
    except Exception:
        return ""
    text = " ".join(text.split())
    return text[:n]


def _has_injection_fields(data: Dict[str, Any]) -> bool:
    return any(
        k in data
        for k in [
            "external_wall_count_source",
            "external_sides_hint",
            "external_wall_count_reference_segments",
        ]
    )


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python scripts/debug_report_wall_context.py /path/to/report.json")
        return 2

    path = Path(sys.argv[1]).expanduser()
    if not path.exists():
        print(f"File not found: {path}")
        return 2

    obj = _load_json(path)
    vr = obj.get("validation_result") or {}
    segs = vr.get("segments") or vr.get("analyzed_segments") or []
    if not isinstance(segs, list):
        print("No segments list in validation_result")
        return 1

    print(f"validation_id: {vr.get('validation_id')}")
    print(f"segments: {len(segs)}")

    injection_refs: List[Tuple[str, Dict[str, Any]]] = []
    injected_segments: List[str] = []
    floor_plans: List[str] = []

    interesting: List[Dict[str, Any]] = []
    for seg in segs:
        if not isinstance(seg, dict):
            continue
        sid = str(seg.get("segment_id") or "")
        stype = str(seg.get("type") or "")
        data = seg.get("analysis_data")
        if not isinstance(data, dict):
            data = {}

        if stype == "floor_plan":
            floor_plans.append(sid)

        has_11 = _get_eval(seg, "1.1") is not None
        has_12 = _get_eval(seg, "1.2") is not None
        has_injected = _has_injection_fields(data)

        if has_injected:
            injected_segments.append(sid)
            ref = data.get("external_wall_count_reference_segments")
            if isinstance(ref, dict) and ref:
                injection_refs.append((sid, ref))

        if has_injected or has_11 or has_12 or stype == "floor_plan":
            interesting.append(seg)

    print(f"floor_plan_segments: {floor_plans}")
    print(f"segments_with_injection_fields: {injected_segments}")

    # Determine which floor_plan/mamad_reference were used (if any)
    used_floor = set()
    used_ref = set()
    for _, ref in injection_refs:
        fp = ref.get("floor_plan_segment_id")
        mr = ref.get("mamad_reference_segment_id")
        if fp:
            used_floor.add(fp)
        if mr:
            used_ref.add(mr)

    if used_floor or used_ref:
        print(f"inference_used_floor_plan_segment_ids: {sorted(used_floor)}")
        print(f"inference_used_mamad_reference_segment_ids: {sorted(used_ref)}")

    # Print small per-segment summary
    for seg in interesting:
        sid = str(seg.get("segment_id") or "")
        stype = str(seg.get("type") or "")
        data = seg.get("analysis_data")
        if not isinstance(data, dict):
            data = {}

        cls = data.get("classification")
        if not isinstance(cls, dict):
            cls = {}
        summ = data.get("summary")
        if not isinstance(summ, dict):
            summ = {}

        print("\n==", sid, f"type={stype}")
        print(
            " classification:",
            _short(cls.get("primary_category"), 60),
            "view=",
            _short(cls.get("view_type"), 30),
            "func=",
            _short(summ.get("primary_function"), 30),
        )

        # Show injected fields if present
        for k in [
            "external_wall_count_source",
            "external_wall_count",
            "external_wall_count_confidence",
            "external_sides_hint",
            "external_wall_count_reference_segments",
        ]:
            if k in data:
                print(f" {k}: {data.get(k)}")

        for rid in ["1.1", "1.2"]:
            e = _get_eval(seg, rid)
            if not e:
                continue
            print(
                f" {rid}:",
                e.get("status"),
                (e.get("reason_not_checked") or "").strip(),
            )
            notes = e.get("notes_he")
            if isinstance(notes, str) and notes.strip():
                print("  notes:", _short(notes, 220))

    failed12 = []
    for seg in segs:
        if not isinstance(seg, dict):
            continue
        e12 = _get_eval(seg, "1.2")
        if isinstance(e12, dict) and e12.get("status") == "failed":
            failed12.append(str(seg.get("segment_id") or ""))
    print("\n1.2_failed_segments:", failed12)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
