#!/usr/bin/env python3
"""Debug REQ 1.2 (wall thickness) using ONLY an exported JSON report.

This script is meant for cases where you don't have server logs.
It extracts the data the validator used from the export itself:
- Which segment failed 1.2
- Which wall thickness evidence items were considered (incl. raw objects)
- Any external_wall_count context that was attached

Usage:
  python scripts/debug_req12_from_export.py /path/to/mamad-report-val-....json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _get(obj: Dict[str, Any], *keys: str) -> Any:
    cur: Any = obj
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def _iter_wall_thickness_evidence(evidence: List[Dict[str, Any]]) -> List[Tuple[Optional[float], Optional[str], str, Dict[str, Any]]]:
    out: List[Tuple[Optional[float], Optional[str], str, Dict[str, Any]]] = []
    for ev in evidence:
        if not isinstance(ev, dict):
            continue
        if ev.get("element") != "wall_thickness":
            continue
        value = ev.get("value")
        unit = ev.get("unit")
        location = str(ev.get("location") or "")
        raw = ev.get("raw") if isinstance(ev.get("raw"), dict) else {}
        out.append((value if isinstance(value, (int, float)) else None, unit if isinstance(unit, str) else None, location, raw))
    return out


def _iter_external_wall_count_evidence(evidence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for ev in evidence:
        if not isinstance(ev, dict):
            continue
        if ev.get("element") in ("external_wall_count", "external_wall_count_evidence"):
            out.append(ev)
    return out


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/debug_req12_from_export.py /path/to/mamad-report.json", file=sys.stderr)
        return 2

    path = Path(sys.argv[1]).expanduser().resolve()
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        return 2

    obj = _load_json(path)
    vr = _get(obj, "validation_result")
    if not isinstance(vr, dict):
        print("No validation_result in export", file=sys.stderr)
        return 1

    vid = vr.get("validation_id")
    print(f"validation_id: {vid}")

    req12 = _get(vr, "coverage", "requirements", "1.2")
    if not isinstance(req12, dict):
        print("No coverage.requirements['1.2'] in export", file=sys.stderr)
        return 1

    evals = req12.get("evaluations")
    if not isinstance(evals, list):
        print("coverage.requirements['1.2'].evaluations missing", file=sys.stderr)
        return 1

    print(f"REQ 1.2 evaluations: {len(evals)}")

    failed = [e for e in evals if isinstance(e, dict) and (e.get("status") == "failed" or e.get("passed") is False)]
    print(f"REQ 1.2 failures: {len(failed)}")

    for idx, e in enumerate(failed, 1):
        seg_id = e.get("segment_id")
        print("\n" + "=" * 80)
        print(f"FAILURE #{idx} | segment_id={seg_id}")
        print(f"status={e.get('status')} reason_not_checked={e.get('reason_not_checked')}")
        notes = e.get("notes_he") or e.get("message") or ""
        if notes:
            print(f"notes: {notes}")

        evidence = e.get("evidence") if isinstance(e.get("evidence"), list) else []

        # Wall thickness evidence
        w_evs = _iter_wall_thickness_evidence(evidence)
        print(f"wall_thickness evidence items: {len(w_evs)}")
        for (val, unit, loc, raw) in w_evs:
            raw_type = raw.get("type")
            raw_notes = raw.get("notes")
            print(f"- {val}{unit or ''} | location='{loc}' | raw.type={raw_type} raw.notes={raw_notes}")

        # External wall count evidence (if attached)
        c_evs = _iter_external_wall_count_evidence(evidence)
        print(f"external_wall_count evidence items: {len(c_evs)}")
        for ev in c_evs:
            print("-", json.dumps(ev, ensure_ascii=False))

    # Also show a quick per-segment summary for seg_001/seg_005 if present.
    analyzed_segments = vr.get("analyzed_segments")
    if isinstance(analyzed_segments, list):
        by_id: Dict[str, Dict[str, Any]] = {}
        for s in analyzed_segments:
            if isinstance(s, dict) and isinstance(s.get("segment_id"), str):
                by_id[s["segment_id"]] = s

        for seg_id in ["seg_001", "seg_005"]:
            seg = by_id.get(seg_id)
            if not isinstance(seg, dict):
                continue
            ad = seg.get("analysis_data") if isinstance(seg.get("analysis_data"), dict) else {}
            print("\n" + "-" * 80)
            print(f"Segment snapshot: {seg_id}")
            for k in [
                "external_wall_count",
                "external_wall_count_after_exceptions",
                "external_wall_count_source",
                "external_wall_count_confidence",
            ]:
                if k in ad:
                    print(f"{k}: {ad.get(k)}")

            # Focused extraction hints
            wtf = ad.get("wall_thickness_focus")
            if isinstance(wtf, dict) and isinstance(wtf.get("walls"), list):
                print(f"wall_thickness_focus.walls: {len(wtf.get('walls'))}")
            se = ad.get("structural_elements")
            if isinstance(se, list):
                print(f"structural_elements: {len(se)}")

            # Requirement evaluations for 1.2 inside segment validation block (if exists)
            v = seg.get("validation") if isinstance(seg.get("validation"), dict) else {}
            req_evals = v.get("requirement_evaluations") if isinstance(v.get("requirement_evaluations"), list) else []
            req12_evals = [x for x in req_evals if isinstance(x, dict) and (x.get("requirement_id") == "REQ_1_2" or x.get("section") == "1.2" or x.get("requirement") == "1.2")]
            if req12_evals:
                print(f"segment.validation.requirement_evaluations (1.2-ish): {len(req12_evals)}")
                # Print first one compactly
                x = req12_evals[0]
                print("- keys:", sorted(x.keys()))
                if x.get("notes_he"):
                    print("- notes_he:", x.get("notes_he"))

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
