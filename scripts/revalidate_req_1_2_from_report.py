#!/usr/bin/env python3
"""Re-run deterministic REQ 1.2 evaluation on segment analysis_data from an existing report.

This helps validate logic changes without re-calling OCR/LLM.

Usage:
  python scripts/revalidate_req_1_2_from_report.py /path/to/mamad-report-....json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict

from src.services.mamad_validator import MamadValidator


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        import orjson  # type: ignore

        return orjson.loads(path.read_bytes())
    except Exception:
        return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python scripts/revalidate_req_1_2_from_report.py /path/to/report.json")
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

    for seg in segs:
        if not isinstance(seg, dict):
            continue
        sid = str(seg.get("segment_id") or "")
        stype = str(seg.get("type") or "")
        data = seg.get("analysis_data")
        if not isinstance(data, dict):
            continue

        v = MamadValidator()
        v.validate_segment(data)
        ev = next((e for e in v.requirement_evaluations if e.get("requirement_id") == "1.2"), None)
        if not ev:
            continue

        status = ev.get("status")
        reason = ev.get("reason_not_checked") or ""
        # Only print segments where REQ 1.2 is relevantly evaluated/not_checked.
        if status in {"failed", "passed", "not_checked"}:
            print(f"{sid} type={stype} -> 1.2: {status} {reason}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
