#!/usr/bin/env python3
"""Generate a full, self-contained HTML report from a MAMAD validation JSON export.

Goal:
- Work offline (no server logs needed)
- Include *segment images themselves* by downloading each segment's blob_url (or thumbnail_url fallback)
- Summarize validation status + show per-segment violations and 1.2 evidence

Usage:
  python scripts/generate_full_report_from_export.py /path/to/mamad-report.json

Output:
  reports/<validation_id or exported_at>/report.html
  reports/<...>/assets/<segment_id>.png
"""

from __future__ import annotations

import html
import json
import os
import re
import sys
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class SegmentInfo:
    segment_id: str
    seg_type: str
    title: str
    description: str
    blob_url: Optional[str]
    thumbnail_url: Optional[str]


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_filename(name: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9._-]+", "_", name.strip())
    return name or "file"


def _download(url: str, dest: Path, timeout_s: int = 45) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "aga-report-generator/1.0"})
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            data = resp.read()
        dest.write_bytes(data)
        return True
    except Exception:
        return False


def _html_page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang=\"he\" dir=\"rtl\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: system-ui, -apple-system, Segoe UI, Arial, sans-serif; margin: 18px; }}
    h1 {{ margin: 0 0 8px 0; }}
    .meta {{ color: #444; font-size: 14px; margin-bottom: 16px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 16px; }}
    .card {{ border: 1px solid #ddd; border-radius: 10px; padding: 12px; }}
    .k {{ color: #666; }}
    img {{ max-width: 100%; height: auto; border: 1px solid #eee; border-radius: 6px; }}
    .pill {{ display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: 12px; border: 1px solid #ddd; }}
    .ok {{ background: #f3fff3; }}
    .warn {{ background: #fffaf0; }}
    .bad {{ background: #fff3f3; }}
    .mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 12px; }}
    details summary {{ cursor: pointer; }}
    .small {{ font-size: 13px; color: #333; }}
    .list {{ margin: 8px 0 0 0; padding-right: 18px; }}
  </style>
</head>
<body>
{body}
</body>
</html>"""


def _as_text(x: Any, limit: int = 700) -> str:
    try:
        s = json.dumps(x, ensure_ascii=False)
    except Exception:
        s = str(x)
    if len(s) > limit:
        return s[:limit] + "…"
    return s


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/generate_full_report_from_export.py /path/to/mamad-report.json", file=sys.stderr)
        return 2

    input_path = Path(sys.argv[1]).expanduser().resolve()
    if not input_path.exists():
        print(f"File not found: {input_path}", file=sys.stderr)
        return 2

    obj = _load_json(input_path)

    exported_at = obj.get("exported_at") or ""
    vr = obj.get("validation_result") if isinstance(obj.get("validation_result"), dict) else {}
    validation_id = str(vr.get("validation_id") or "")
    decomp = obj.get("decomposition") if isinstance(obj.get("decomposition"), dict) else {}

    code_version = obj.get("code_version")
    if not isinstance(code_version, dict):
        code_version = vr.get("code_version")
    if not isinstance(code_version, dict):
        code_version = {}

    out_key = validation_id or exported_at or datetime.utcnow().isoformat()
    out_key = _safe_filename(out_key)

    out_dir = Path("/Users/robenhai/aga/reports") / out_key
    assets_dir = out_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    # Build segment registry (from decomposition.segments)
    segs_raw = decomp.get("segments") if isinstance(decomp.get("segments"), list) else []
    segments: Dict[str, SegmentInfo] = {}
    for s in segs_raw:
        if not isinstance(s, dict):
            continue
        seg_id = str(s.get("segment_id") or "")
        if not seg_id:
            continue
        segments[seg_id] = SegmentInfo(
            segment_id=seg_id,
            seg_type=str(s.get("type") or ""),
            title=str(s.get("title") or ""),
            description=str(s.get("description") or ""),
            blob_url=str(s.get("blob_url") or "") or None,
            thumbnail_url=str(s.get("thumbnail_url") or "") or None,
        )

    # Validation per-segment block
    v_segments = vr.get("segments") if isinstance(vr.get("segments"), list) else []

    # Coverage summary
    stats = (((vr.get("coverage") or {}).get("statistics")) if isinstance(vr.get("coverage"), dict) else {})
    if not isinstance(stats, dict):
        stats = {}

    def pill_for_status(status: str) -> str:
        s = (status or "").lower()
        if s in ("passed", "ok", "success"):
            return '<span class="pill ok">עבר</span>'
        if s in ("failed", "error"):
            return '<span class="pill bad">נכשל</span>'
        if s in ("warning", "warn"):
            return '<span class="pill warn">אזהרה</span>'
        return f'<span class="pill">{html.escape(status or "")}</span>'

    # Download images (best-effort)
    downloads: Dict[str, str] = {}
    for vs in v_segments:
        if not isinstance(vs, dict):
            continue
        seg_id = str(vs.get("segment_id") or "")
        if not seg_id:
            continue
        info = segments.get(seg_id)
        if not info:
            continue
        # Keep original extension best-effort
        target_path = assets_dir / f"{_safe_filename(seg_id)}.png"
        if target_path.exists():
            downloads[seg_id] = target_path.name
            continue
        url = info.blob_url or info.thumbnail_url
        if not url:
            continue
        ok = _download(url, target_path)
        if not ok and info.thumbnail_url and url != info.thumbnail_url:
            ok = _download(info.thumbnail_url, target_path)
        if ok:
            downloads[seg_id] = target_path.name

    # Build HTML
    header = f"""
<h1>דוח בדיקה מלא</h1>
<div class="meta">
  <div><span class="k">validation_id:</span> <span class="mono">{html.escape(validation_id)}</span></div>
  <div><span class="k">decomposition_id:</span> <span class="mono">{html.escape(str(decomp.get('id') or ''))}</span></div>
  <div><span class="k">exported_at:</span> <span class="mono">{html.escape(str(exported_at))}</span></div>
    <div><span class="k">code_version:</span> <span class="mono">{html.escape(_as_text(code_version, limit=400))}</span></div>
</div>

<div class="card">
  <div class="small"><b>סיכום</b></div>
  <div class="small">
    עברו: <b>{vr.get('passed')}</b> | נכשלו: <b>{vr.get('failed')}</b> | אזהרות: <b>{vr.get('warnings')}</b> | סה"כ סגמנטים: <b>{vr.get('total_segments')}</b>
  </div>
  <div class="small">
    כיסוי דרישות: <b>{stats.get('coverage_percentage')}</b>% (נבדקו {stats.get('checked')} מתוך {stats.get('total_requirements')})
  </div>
</div>

<h2>סגמנטים</h2>
<div class="grid">
"""

    cards: List[str] = []
    for vs in v_segments:
        if not isinstance(vs, dict):
            continue
        seg_id = str(vs.get("segment_id") or "")
        status = str(vs.get("status") or "")
        info = segments.get(seg_id)
        vblock = vs.get("validation") if isinstance(vs.get("validation"), dict) else {}
        violations = vblock.get("violations") if isinstance(vblock.get("violations"), list) else []

        img_html = ""
        if seg_id in downloads:
            img_html = f'<img src="assets/{html.escape(downloads[seg_id])}" alt="{html.escape(seg_id)}" />'
        else:
            # fall back to links if we couldn't download
            if info and info.blob_url:
                img_html = f'<div class="small"><a href="{html.escape(info.blob_url)}" target="_blank">פתיחת תמונת סגמנט</a></div>'
            elif info and info.thumbnail_url:
                img_html = f'<div class="small"><a href="{html.escape(info.thumbnail_url)}" target="_blank">פתיחת Thumbnail</a></div>'

        vio_list = ""
        if violations:
            items = []
            for v in violations[:12]:
                if not isinstance(v, dict):
                    continue
                desc = str(v.get("description") or "")
                rid = str(v.get("rule_id") or "")
                sev = str(v.get("severity") or "")
                items.append(f"<li><span class='mono'>{html.escape(rid)}</span> ({html.escape(sev)}): {html.escape(desc)}</li>")
            vio_list = "<ul class='list'>" + "".join(items) + "</ul>"

        # Include 1.2-ish requirement evaluation evidence if present
        req_evals = vblock.get("requirement_evaluations") if isinstance(vblock.get("requirement_evaluations"), list) else []
        req12 = None
        for e in req_evals:
            if not isinstance(e, dict):
                continue
            if e.get("requirement_id") == "REQ_1_2" or e.get("section") == "1.2" or e.get("requirement") == "1.2":
                req12 = e
                break
        req12_html = ""
        if isinstance(req12, dict):
            notes_he = str(req12.get("notes_he") or "")
            evidence = req12.get("evidence") if isinstance(req12.get("evidence"), list) else []
            req12_html = "<details><summary>פירוט 1.2 (כפי שנבדק)</summary>"
            if notes_he:
                req12_html += f"<div class='small'>{html.escape(notes_he)}</div>"
            if evidence:
                req12_html += f"<div class='small mono'>{html.escape(_as_text(evidence, limit=1800))}</div>"
            req12_html += "</details>"

        title = info.title if info else ""
        seg_type = info.seg_type if info else ""
        desc = info.description if info else ""

        cards.append(
            "<div class='card'>"
            f"<div><b class='mono'>{html.escape(seg_id)}</b> {pill_for_status(status)}</div>"
            f"<div class='small'><span class='k'>type:</span> {html.escape(seg_type)}" + (f" | <span class='k'>title:</span> {html.escape(title)}" if title else "") + "</div>"
            + (f"<div class='small'>{html.escape(desc)}</div>" if desc else "")
            + img_html
            + ("<div class='small'><b>הפרות</b></div>" + vio_list if violations else "<div class='small k'>אין הפרות בסגמנט זה</div>")
            + req12_html
            + "</div>"
        )

    footer = "</div>"  # grid

    body = header + "\n".join(cards) + footer
    report_html = _html_page(title=f"MAMAD Report {validation_id}", body=body)

    out_path = out_dir / "report.html"
    out_path.write_text(report_html, encoding="utf-8")

    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
