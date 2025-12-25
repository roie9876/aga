"""Submission preflight checks based on the Home Front Command submission guide.

This module focuses on *completeness* (did the user upload the required drawings / signatures),
not on engineering correctness.
"""

from __future__ import annotations

import asyncio
import base64
import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.azure import get_openai_client
from src.config import settings
from src.models.decomposition import SegmentType
from src.models.preflight import PreflightCheckResult, PreflightStatus
from src.utils.logging import get_logger
from src.services.segment_analyzer import TAG_DEFINITIONS

logger = get_logger(__name__)


_HEBREW_KEYWORDS = {
    # PF-01: prefer specific phrases to avoid matching every random table.
    "request_table": [
        "טבלה מרכזת",
        "טבלת ריכוז",
        "ריכוז פרטי",
        "ריכוז פרטי בקשה",
        "פרטי בקשה",
        "פרטי הבקשה",
        "טבלת פרטי",
        "פרטי מגיש",
        "בקשה להיתר",
        "מספר בקשה",
    ],
    "env_sketch": [
        "תשריט סביבה",
        "שרטוט סביבה",
        "סביבה",
        "תכנית סביבה",
        "תוכנית סביבה",
        "מפת סביבה",
    ],
    "site_plan": [
        "מפה מצבית",
        "מצבית",
        "מפת מצב",
        "תכנית מצב",
        "תוכנית מצב",
        "תכנית מצבית",
        "תוכנית מצבית",
        "תכנית מדידה",
        "תוכנית מדידה",
        "מפת מדידה",
        "קווי מגרש",
        "גבולות המגרש",
        "גבולות מגרש",
        "קו מגרש",
        "מגרש",
    ],
    "declaration": [
        "הצהרה",
        "נספח א",
        "נספח א'",
        "חתימה",
        "חתימות",
        "חתום",
        "תצהיר",
        "הצהרת",
        "מורשה",
        "מתכנן",
        "אדריכל",
        "מהנדס",
        "מבקש",
        "שם וחתימה",
    ],
    # PF-09: area calculations / protected-area table (best-effort).
    "area_table": [
        "טבלת שטחים",
        "טבלת חישוב",
        "חישוב שטחים",
        "חישוב שטחי",
        "שטחי מיגון",
        "שטח מיגון",
        "מ" + "ר",
    ],
    # PF-10: legend / definitions.
    "legend": [
        "מקרא",
        "לג'נד",
        "טבלת הגדרות",
        "הגדרות",
        "סימונים",
        "סימבולים",
    ],
    "rishuy_zamin": [
        "מערכת רישוי זמין",
        "רישוי זמין",
        "מנהל התכנון",
        "ועדה מקומית",
    ],
    "decision_form": [
        "טופס החלטה",
        "החלטת רשות",
        "החלטה",
        "החלטת ועדה",
        "פרוטוקול החלטה",
    ],
    "mamad": ["ממ\"ד", "ממד", "מרחב מוגן", "ממ"],
    "wall_reduction": ["ירידת קירות", "ירידה", "קירות יורדים"],
    "structural": ["זיון", "ברזל", "ריתום", "פרטי פתחים", "פתח", "תקרה", "רצפה"],
}


_CHECK_EXPLANATIONS: Dict[str, str] = {
    "PF-01": "מחפש דף/טבלה של \"פרטי בקשה\" (ריכוז נתונים) — בדרך כלל עמוד עם טבלה של פרטי המגיש/נכס/מספר בקשה. אם זה נמצא בתוך עמוד גדול, חשוב לאשר סגמנט שמכיל את הטבלה.",
    "PF-02": "מחפש שני מסמכים: (1) תשריט סביבה, (2) מפה מצבית/תכנית מדידה (גבולות מגרש/קווי מגרש). אם אחד מהם לא אושר כסגמנט — הבדיקה תיכשל.",
    "PF-03": "מחפש עמוד \"הצהרה/תצהיר\" או עמוד חתימות (שם+חתימה של מבקש/אדריכל/מהנדס). אם החתימות מופיעות בתחתית עמוד אחר — צריך לאשר סגמנט שמכיל את אזור החתימות.",
    "PF-04": "בודק שקיימת לפחות תוכנית קומה בקנ" + "מ 1:100 (floor plan) כחלק מחבילת ההגשה.",
    "PF-05": "בודק שקיימים לפחות שני חתכים בקנ" + "מ 1:100 (sections) כחלק מחבילת ההגשה.",
    "PF-06": "בודק שקיימת לפחות חזית אחת בקנ" + "מ 1:100 (elevation) כחלק מחבילת ההגשה.",
    "PF-07": "בודק (Best-effort) שיש לפחות סגמנט אחד שמייצג/מזכיר את הממ" + "ד בקנ" + "מ 1:50.",
    "PF-08": "בודק (Best-effort) שיש בסגמנטים סימוני מידות/נתונים מינימליים (למשל מימדים), כדי שהמשך הבדיקות יהיה אפשרי.",
    "PF-09": "בודק (אם נדרש) האם צורפה טבלת חישוב שטחים/שטחי מיגון. אם לא מזוהה – מוצגת אזהרה כדי לוודא שלא שכחתם לצרף.",
    "PF-10": "בודק האם צורף מקרא/טבלת הגדרות/סימונים לרכיבים, כדי להבין סימבולים והערות בתכניות.",
    "PF-11": "בודק (אם רלוונטי) האם צורפה תכנית/חישוב ירידת קירות.",
    "PF-12": "בודק (Best-effort) האם צורפו פרטים הנדסיים כמו זיון/ריתום/פתחים, או לפחות אותרו אינדיקציות לכך בניתוח.",
    "PF-13": "בודק האם צורף טופס החלטה מרישוי זמין (מנהל התכנון/רשות מקומית) עם פרטי הבקשה והחלטה.",
}


def _norm(s: Any) -> str:
    return str(s or "").strip()


def _match_keywords(text: str, keywords: Sequence[str]) -> bool:
    t = _norm(text)
    if not t:
        return False
    return any(k in t for k in keywords)


def _segment_text_blob(seg: Dict[str, Any]) -> str:
    return " | ".join(
        [
            _norm(seg.get("title")),
            _norm(seg.get("description")),
            _norm(seg.get("type")),
        ]
    )


def _safe_segment_type(raw: Any) -> SegmentType:
    try:
        return SegmentType(str(raw))
    except Exception:
        return SegmentType.UNKNOWN


@dataclass(frozen=True)
class _ArtifactSignals:
    artifact_type: str
    signature_block_present: Optional[bool]
    signature_roles: List[str]
    detected_scale: Optional[str]


async def _llm_detect_artifact(*, image_bytes: bytes, hint_text: str) -> Optional[_ArtifactSignals]:
    """Lightweight vision pass to detect artifact type and signatures.

    Returns None if LLM is not configured/available.
    """
    if not getattr(settings, "azure_openai_deployment_name", None):
        return None

    try:
        client = get_openai_client()
    except Exception as e:
        logger.info("OpenAI client unavailable for preflight", error=str(e))
        return None

    img_b64 = base64.b64encode(image_bytes).decode("utf-8")

    prompt = f"""You are a strict reviewer for an Israeli Home Front Command (Pakar) protected-room submission package.
Return ONLY valid JSON. No markdown.

Task: For the provided plan segment image, classify what it is and detect whether a signature block exists.

Hint text (may be user-provided title/description): {hint_text}

Return JSON with this exact shape:
{{
  "artifact_type": "request_summary_table|environment_sketch|site_plan|declaration_signature|building_floor_plans_1_100|building_sections_1_100|building_elevations_1_100|mamad_arch_plan_1_50|mamad_arch_sections_1_50|mamad_legend_or_tables|wall_reduction_plan|structural_rebar_plans|anchorage_details|openings_details|other",
  "signature_block_present": true,
  "signature_roles": ["architect", "engineer", "applicant", "other"],
  "detected_scale": "1:50|1:100|other|null",
  "evidence": ["short evidence strings"]
}}"""

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
            ],
        }
    ]

    response = await asyncio.to_thread(
        client.chat_completions_create,
        model=settings.azure_openai_deployment_name,
        messages=messages,
    )
    content = response.choices[0].message.content

    data = _parse_llm_json(content)
    if not isinstance(data, dict):
        return None

    roles = data.get("signature_roles")
    if not isinstance(roles, list):
        roles = []
    roles_norm = [str(r) for r in roles if isinstance(r, (str, int, float))]

    sig_present = data.get("signature_block_present")
    if isinstance(sig_present, bool):
        pass
    else:
        sig_present = None

    scale = data.get("detected_scale")
    if isinstance(scale, str):
        scale = scale.strip() or None
    else:
        scale = None

    artifact_type = str(data.get("artifact_type") or "other").strip() or "other"
    return _ArtifactSignals(
        artifact_type=artifact_type,
        signature_block_present=sig_present,
        signature_roles=roles_norm,
        detected_scale=scale,
    )


def _parse_llm_json(content: str) -> Optional[Dict[str, Any]]:
    if not content:
        return None
    payload = content
    if "```json" in payload:
        start = payload.find("```json") + 7
        end = payload.find("```", start)
        payload = payload[start:end].strip()
    elif "```" in payload:
        start = payload.find("```") + 3
        end = payload.find("```", start)
        payload = payload[start:end].strip()
    else:
        start = payload.find("{")
        end = payload.rfind("}") + 1
        if start >= 0 and end > start:
            payload = payload[start:end]
    try:
        return json.loads(payload)
    except Exception:
        return None


def _sanitize_ocr_text(text: str) -> str:
    if not text:
        return ""
    lines = text.splitlines()
    blocked = ("ignore", "system", "assistant", "developer", "prompt", "jailbreak", "instruction")
    safe_lines: List[str] = []
    for line in lines:
        low = line.lower()
        if any(tok in low for tok in blocked):
            continue
        safe_lines.append(line)
    cleaned = "\n".join(safe_lines)
    cleaned = re.sub(r"[^\w\s\u0590-\u05FF\-\.,:;/()\"'₪%]", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


async def _llm_detect_area_table(*, image_bytes: bytes, ocr_text: str) -> Optional[Dict[str, Any]]:
    if not getattr(settings, "azure_openai_deployment_name", None):
        return None

    try:
        client = get_openai_client()
    except Exception as e:
        logger.info("OpenAI client unavailable for preflight area table", error=str(e))
        return None

    img_b64 = base64.b64encode(image_bytes).decode("utf-8")
    ocr_hint = (ocr_text or "").strip()
    if len(ocr_hint) > 2000:
        ocr_hint = ocr_hint[:2000] + "…"

    prompt = f"""You are a strict reviewer for an Israeli Home Front Command (Pakar) submission.

Task: Determine if this image contains a **protected-area area calculation table**, even if it is empty, and whether it has **area values**.

OCR text (may be noisy):
{ocr_hint}

Return ONLY valid JSON:
{{
  "area_table_present": true|false,
  "area_values_present": true|false,
  "confidence": 0.0-1.0,
  "evidence": ["short evidence strings in Hebrew"]
}}

Rules:
- "area_table_present" should be true if the image clearly shows a table intended for area calculations (טבלת חישוב שטחים/שטחי מיגון),
  even if the table cells are empty. Look for a grid of rows/columns, headers, or a table title.
- "area_values_present" should be true ONLY if numeric area values appear in the table (e.g., m²/מ״ר or numeric cells).
"""

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
            ],
        }
    ]

    response = await asyncio.to_thread(
        client.chat_completions_create,
        model=settings.azure_openai_deployment_name,
        messages=messages,
    )
    content = response.choices[0].message.content
    data = _parse_llm_json(content)
    if not isinstance(data, dict):
        return None

    area_table_present = data.get("area_table_present")
    area_values_present = data.get("area_values_present")
    confidence = data.get("confidence")
    evidence = data.get("evidence")

    return {
        "area_table_present": bool(area_table_present) if isinstance(area_table_present, bool) else None,
        "area_values_present": bool(area_values_present) if isinstance(area_values_present, bool) else None,
        "confidence": confidence if isinstance(confidence, (int, float)) else None,
        "evidence": evidence if isinstance(evidence, list) else [],
        "prompt": prompt,
        "raw_response": content,
    }


def _unique_segments(segments: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: set[str] = set()
    out: List[Dict[str, Any]] = []
    for seg in segments:
        seg_id = str(seg.get("segment_id"))
        if not seg_id or seg_id in seen:
            continue
        seen.add(seg_id)
        out.append(seg)
    return out


def _collect_ocr_debug(segments: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    ocr_debug: Dict[str, Any] = {}
    for seg in segments:
        seg_id = str(seg.get("segment_id"))
        if not seg_id:
            continue
        ocr_items = _extract_ocr_items(seg)
        if ocr_items:
            ocr_debug[seg_id] = {"ocr_text_items": ocr_items}
    return ocr_debug


def _segment_ocr_text(seg: Dict[str, Any]) -> str:
    ocr_items = _extract_ocr_items(seg)
    joined = " ".join(
        [
            str(it.get("text"))
            for it in ocr_items
            if isinstance(it, dict) and isinstance(it.get("text"), str)
        ]
    ).strip()
    return _sanitize_ocr_text(joined)


def _build_preflight_prompt(check_id: str, *, ocr_text: str, hint_text: str) -> str:
    ocr_hint = _sanitize_ocr_text(ocr_text or "")
    if len(ocr_hint) > 2000:
        ocr_hint = ocr_hint[:2000] + "…"
    hint_text = (hint_text or "").strip()

    if check_id == "PF-01":
        return f"""You are a strict reviewer for an Israeli Home Front Command (Pakar) submission.
Task: Determine if this segment contains a **request summary table**, includes identifying details, and has a **signature block**.

Hint: {hint_text}
OCR text (may be noisy):
{ocr_hint}

Return ONLY valid JSON:
{{
  "request_table_present": true|false,
  "identifiers_present": true|false,
  "signature_present": true|false,
  "confidence": 0.0-1.0,
  "evidence": ["short evidence strings in Hebrew"]
}}"""

    if check_id == "PF-02":
        return f"""You are a strict reviewer for an Israeli Home Front Command (Pakar) submission.
Task: Determine the document type and whether it includes scale/dimensions.

Hint: {hint_text}
OCR text (may be noisy):
{ocr_hint}

Return ONLY valid JSON:
{{
  "doc_type": "environment_sketch|site_plan|both|other",
  "scale_or_dimensions_present": true|false,
  "confidence": 0.0-1.0,
  "evidence": ["short evidence strings in Hebrew"]
}}"""

    if check_id == "PF-03":
        return f"""You are a strict reviewer for an Israeli Home Front Command (Pakar) submission.
Task: Detect whether a **signature block** exists (names + signature area).

Hint: {hint_text}
OCR text (may be noisy):
{ocr_hint}

Return ONLY valid JSON:
{{
  "signature_block_present": true|false,
  "signature_roles": ["architect", "engineer", "applicant", "other"],
  "confidence": 0.0-1.0,
  "evidence": ["short evidence strings in Hebrew"]
}}"""

    if check_id == "PF-04":
        return f"""You are a strict reviewer for an Israeli Home Front Command (Pakar) submission.
Task: Determine if this segment is a **floor plan** and whether it shows scale 1:100.

Hint: {hint_text}
OCR text (may be noisy):
{ocr_hint}

Return ONLY valid JSON:
{{
  "floor_plan_present": true|false,
  "scale_1_100_present": true|false,
  "confidence": 0.0-1.0,
  "evidence": ["short evidence strings in Hebrew"]
}}"""

    if check_id == "PF-05":
        return f"""You are a strict reviewer for an Israeli Home Front Command (Pakar) submission.
Task: Determine if this segment is a **section** and whether it shows scale 1:100.

Hint: {hint_text}
OCR text (may be noisy):
{ocr_hint}

Return ONLY valid JSON:
{{
  "section_present": true|false,
  "scale_1_100_present": true|false,
  "confidence": 0.0-1.0,
  "evidence": ["short evidence strings in Hebrew"]
}}"""

    if check_id == "PF-06":
        return f"""You are a strict reviewer for an Israeli Home Front Command (Pakar) submission.
Task: Determine if this segment is an **elevation** and whether it shows scale 1:100.

Hint: {hint_text}
OCR text (may be noisy):
{ocr_hint}

Return ONLY valid JSON:
{{
  "elevation_present": true|false,
  "scale_1_100_present": true|false,
  "confidence": 0.0-1.0,
  "evidence": ["short evidence strings in Hebrew"]
}}"""

    if check_id == "PF-07":
        return f"""You are a strict reviewer for an Israeli Home Front Command (Pakar) submission.
Task: Determine if this segment is a **ממ\"ד plan/detail** and whether it shows scale 1:50.

Hint: {hint_text}
OCR text (may be noisy):
{ocr_hint}

Return ONLY valid JSON:
{{
  "mamad_plan_present": true|false,
  "scale_1_50_present": true|false,
  "confidence": 0.0-1.0,
  "evidence": ["short evidence strings in Hebrew"]
}}"""

    if check_id == "PF-08":
        return f"""You are a strict reviewer for an Israeli Home Front Command (Pakar) submission.
Task: Determine if this segment contains **dimension markings/measurements**.

Hint: {hint_text}
OCR text (may be noisy):
{ocr_hint}

Return ONLY valid JSON:
{{
  "dimensions_present": true|false,
  "confidence": 0.0-1.0,
  "evidence": ["short evidence strings in Hebrew"]
}}"""

    if check_id == "PF-09":
        return f"""You are a strict reviewer for an Israeli Home Front Command (Pakar) submission.
Task: Determine if this segment contains an **area calculation table** and whether the table has values (not empty).

Hint: {hint_text}
OCR text (may be noisy):
{ocr_hint}

Return ONLY valid JSON:
{{
  "area_table_present": true|false,
  "area_values_present": true|false,
  "confidence": 0.0-1.0,
  "evidence": ["short evidence strings in Hebrew"]
}}"""

    if check_id == "PF-10":
        return f"""You are a strict reviewer for an Israeli Home Front Command (Pakar) submission.
Task: Determine if this segment contains a **legend / definitions table** for symbols.

Hint: {hint_text}
OCR text (may be noisy):
{ocr_hint}

Return ONLY valid JSON:
{{
  "legend_present": true|false,
  "confidence": 0.0-1.0,
  "evidence": ["short evidence strings in Hebrew"]
}}"""

    if check_id == "PF-11":
        return f"""You are a strict reviewer for an Israeli Home Front Command (Pakar) submission.
Task: Determine if this segment contains a **wall reduction plan** (ירידת קירות).

Hint: {hint_text}
OCR text (may be noisy):
{ocr_hint}

Return ONLY valid JSON:
{{
  "wall_reduction_present": true|false,
  "confidence": 0.0-1.0,
  "evidence": ["short evidence strings in Hebrew"]
}}"""

    if check_id == "PF-12":
        return f"""You are a strict reviewer for an Israeli Home Front Command (Pakar) submission.
Task: Determine if this segment contains **structural details** (rebar/anchorage/openings).

Hint: {hint_text}
OCR text (may be noisy):
{ocr_hint}

Return ONLY valid JSON:
{{
  "structural_details_present": true|false,
  "confidence": 0.0-1.0,
  "evidence": ["short evidence strings in Hebrew"]
}}"""

    if check_id == "PF-13":
        return f"""You are a strict reviewer for an Israeli Home Front Command (Pakar) submission.
Task: Determine if this segment is a **Rishuy Zamin decision form** and if it includes a **signature**.

Hint: {hint_text}
OCR text (may be noisy):
{ocr_hint}

Return ONLY valid JSON:
{{
  "rishuy_zamin_present": true|false,
  "decision_form_present": true|false,
  "signature_present": true|false,
  "confidence": 0.0-1.0,
  "evidence": ["short evidence strings in Hebrew"]
}}"""

    return f"""Return ONLY valid JSON: {{"confidence": 0.0, "evidence": []}}"""


async def _llm_detect_preflight_check(
    *,
    check_id: str,
    image_bytes: bytes,
    ocr_text: str,
    hint_text: str,
) -> Optional[Dict[str, Any]]:
    if not getattr(settings, "azure_openai_deployment_name", None):
        return None

    try:
        client = get_openai_client()
    except Exception as e:
        logger.info("OpenAI client unavailable for preflight check", error=str(e), check_id=check_id)
        return None

    prompt = _build_preflight_prompt(check_id, ocr_text=ocr_text, hint_text=hint_text)
    img_b64 = base64.b64encode(image_bytes).decode("utf-8")
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
            ],
        }
    ]

    try:
        response = await asyncio.to_thread(
            client.chat_completions_create,
            model=settings.azure_openai_deployment_name,
            messages=messages,
        )
        content = response.choices[0].message.content
        data = _parse_llm_json(content)
        if not isinstance(data, dict):
            return None
        data["prompt"] = prompt
        data["raw_response"] = content
        return data
    except Exception as e:
        logger.error("Preflight LLM check failed", check_id=check_id, error=str(e))
        return {
            "error": str(e),
            "prompt": prompt,
            "raw_response": None,
        }


async def _download_image_bytes(blob_url: str) -> Optional[bytes]:
    """Download a segment image from a SAS URL.

    Uses a blocking HTTP GET in a worker thread (same approach as SegmentAnalyzer).
    """
    if not blob_url:
        return None

    import requests

    def _get() -> bytes:
        r = requests.get(blob_url, timeout=60)
        r.raise_for_status()
        return r.content

    try:
        return await asyncio.to_thread(_get)
    except Exception as e:
        logger.info("Failed downloading segment image for preflight", error=str(e))
        return None


def _mk_result(
    *,
    check_id: str,
    title: str,
    pages: List[int],
    status: PreflightStatus,
    details: str,
    evidence: Optional[List[str]] = None,
    debug: Optional[Dict[str, Any]] = None,
    explanation: Optional[str] = None,
) -> PreflightCheckResult:
    return PreflightCheckResult(
        check_id=check_id,
        title=title,
        explanation=explanation or _CHECK_EXPLANATIONS.get(check_id),
        source_pages=pages,
        status=status,
        details=details,
        evidence_segment_ids=evidence or [],
        debug=debug,
    )


def _collect_by_type(segments: Sequence[Dict[str, Any]]) -> Dict[SegmentType, List[Dict[str, Any]]]:
    out: Dict[SegmentType, List[Dict[str, Any]]] = {}
    for seg in segments:
        st = _safe_segment_type(seg.get("type"))
        out.setdefault(st, []).append(seg)
    return out


def _find_segments_by_keywords(segments: Sequence[Dict[str, Any]], key: str) -> List[Dict[str, Any]]:
    kws = _HEBREW_KEYWORDS.get(key, [])
    out: List[Dict[str, Any]] = []
    for seg in segments:
        blob = _segment_text_blob(seg)
        txt_items = " ".join(_extract_checkable_text_items(seg))
        if _match_keywords(blob, kws) or _match_keywords(txt_items, kws):
            out.append(seg)
    return out


def _extract_checkable_text_items(seg: Dict[str, Any]) -> List[str]:
    items: List[str] = []
    ad = seg.get("analysis_data")
    if isinstance(ad, dict):
        txt = ad.get("text_items")
        if isinstance(txt, list):
            for t in txt:
                if isinstance(t, dict) and isinstance(t.get("text"), str):
                    items.append(t["text"])
    return items


def _extract_ocr_items(seg: Dict[str, Any]) -> List[Dict[str, Any]]:
    ad = seg.get("analysis_data")
    if not isinstance(ad, dict):
        return []
    ocr = ad.get("ocr_text_items")
    return ocr if isinstance(ocr, list) else []


def _segment_text_corpus(seg: Dict[str, Any]) -> str:
    parts = [_segment_text_blob(seg)]
    parts.extend(_extract_checkable_text_items(seg))
    return " ".join([p for p in parts if p])


def _normalize_text_for_tags(value: str) -> str:
    normalized = value or ""
    normalized = normalized.replace("״", '"').replace("”", '"').replace("“", '"')
    normalized = normalized.replace("׳", "'")
    return normalized.lower()


def _extract_scales_for_tags(text: str) -> List[int]:
    if not text:
        return []
    matches = re.findall(r"1\s*[:/]\s*(\d{2,4})", text)
    scales: List[int] = []
    for m in matches:
        try:
            scales.append(int(m))
        except ValueError:
            continue
    return list(sorted(set(scales)))


def _find_hits_for_tags(text: str, phrases: List[str]) -> List[str]:
    hits: List[str] = []
    for phrase in phrases:
        if not phrase:
            continue
        if phrase.lower() in text:
            hits.append(phrase)
    return hits


def _collect_text_for_tags(seg: Dict[str, Any]) -> str:
    parts: List[str] = []
    parts.append(_segment_text_blob(seg))
    parts.extend(_extract_checkable_text_items(seg))
    ocr_items = _extract_ocr_items(seg)
    for item in ocr_items:
        if isinstance(item, dict) and isinstance(item.get("text"), str):
            parts.append(item["text"])
    return "\n".join([p for p in parts if p])


def _detect_content_tags_light(seg: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw_text = _collect_text_for_tags(seg)
    normalized = _normalize_text_for_tags(raw_text)
    scales = _extract_scales_for_tags(normalized)

    tags: List[Dict[str, Any]] = []
    for tag in TAG_DEFINITIONS:
        required = tag.get("required_phrases", [])
        optional = tag.get("optional_phrases", [])
        scale_values = tag.get("scale_values") or []

        required_hits = _find_hits_for_tags(normalized, required)
        optional_hits = _find_hits_for_tags(normalized, optional)
        scale_hits = [s for s in scales if s in scale_values]

        score = 0.0
        score += len(required_hits) * 0.6
        score += len(optional_hits) * 0.2
        if scale_hits:
            score += 0.4

        has_required = len(required_hits) > 0
        has_scale = bool(scale_hits)
        has_optional = len(optional_hits) > 0

        if not (has_required or (has_scale and has_optional)):
            continue

        tags.append(
            {
                "tag": tag["id"],
                "label": tag["label"],
                "description": tag["description"],
                "confidence": round(min(0.95, max(0.15, score)), 2),
                "evidence": list(dict.fromkeys(required_hits + optional_hits))[:8],
                "scales_detected": scale_hits,
            }
        )

    return tags


def _get_content_tags(seg: Dict[str, Any]) -> List[Dict[str, Any]]:
    ad = seg.get("analysis_data")
    if isinstance(ad, dict):
        tags = ad.get("content_tags")
        if isinstance(tags, list) and tags:
            return tags
    return _detect_content_tags_light(seg)


def _filter_segments_by_tags(segments: Sequence[Dict[str, Any]], tag_ids: Sequence[str]) -> List[Dict[str, Any]]:
    wanted = {str(t).strip() for t in tag_ids if str(t).strip()}
    if not wanted:
        return []
    out: List[Dict[str, Any]] = []
    for seg in segments:
        tags = _get_content_tags(seg)
        if not isinstance(tags, list):
            continue
        for t in tags:
            if isinstance(t, dict) and t.get("tag") in wanted:
                out.append(seg)
                break
    return out


def _is_site_plan_like(seg: Dict[str, Any]) -> bool:
    return _match_keywords(_segment_text_corpus(seg), _HEBREW_KEYWORDS["site_plan"])


def _is_manual_segment(seg: Dict[str, Any]) -> bool:
    return str(seg.get("llm_reasoning") or "") == "MANUAL_ROI"


def _is_drawing_like(seg: Dict[str, Any]) -> bool:
    st = _safe_segment_type(seg.get("type"))
    return st in {
        SegmentType.FLOOR_PLAN,
        SegmentType.SECTION,
        SegmentType.DETAIL,
        SegmentType.ELEVATION,
    }


def _has_table_token(text: str) -> bool:
    if not text:
        return False
    return any(tok in text for tok in ["טבלה", "טבלת", "טבלא"])


def _contains_scale_1_50(text: str) -> bool:
    if not text:
        return False
    return bool(re.search(r"\b1\s*[:/]\s*50\b", text))


def _has_area_table_signal(text: str) -> bool:
    if not text:
        return False
    table_tokens = ["טבלה", "טבלת", "טבלא"]
    area_tokens = ["שטח", "שטחים", "חישוב", "מיגון", "מ\"ר", "מ״ר"]
    has_table = any(tok in text for tok in table_tokens)
    has_area = any(tok in text for tok in area_tokens)
    return has_table and has_area


def _score_area_table_candidate(seg: Dict[str, Any]) -> int:
    """Heuristic score for PF-09 candidates (higher = more likely area table)."""
    corpus = _segment_text_corpus(seg)
    score = 0
    if _has_area_table_signal(corpus) and _has_area_values(corpus):
        score += 6
    elif _has_area_table_signal(corpus):
        score += 4
    elif _has_table_token(corpus):
        score += 2
    # Empty tables may have very little OCR text; give a small boost.
    if 0 < len(corpus) < 80:
        score += 1
    st = _safe_segment_type(seg.get("type"))
    if st == SegmentType.LEGEND:
        score += 1
    return score


def _has_numeric_token(text: str, *, min_digits: int = 2) -> bool:
    if not text:
        return False
    return bool(re.search(rf"\b\d{{{min_digits},}}\b", text))


def _has_scale_token(text: str) -> bool:
    if not text:
        return False
    return bool(re.search(r"\b1\s*[:/]\s*\d+\b", text)) or ("קנ\"מ" in text) or ("קנה מידה" in text)


def _has_area_values(text: str) -> bool:
    if not text:
        return False
    return bool(re.search(r"\b\d+(?:\.\d+)?\s*(?:מ\"ר|מ״ר|m2|m²)\b", text, re.IGNORECASE))


def _has_request_table_signal(text: str) -> bool:
    if not text:
        return False
    id_tokens = ["מספר", "בקשה", "תיק", "גוש", "חלקה", "מגרש"]
    return _has_numeric_token(text, min_digits=3) and any(tok in text for tok in id_tokens)


def _has_rebar_signal(text: str) -> bool:
    if not text:
        return False
    return bool(
        re.search(r"(Ø|Φ|ϕ|φ)\s*\d{2}", text)
        or re.search(r"\b\d{2}\s*(?:מ\"מ|מ״מ|mm)\b", text)
        or ("ברזל" in text and _has_numeric_token(text, min_digits=2))
        or ("זיון" in text and _has_numeric_token(text, min_digits=2))
    )


def _has_rishuy_zamin_decision(text: str) -> bool:
    if not text:
        return False
    has_system = _match_keywords(text, _HEBREW_KEYWORDS["rishuy_zamin"])
    has_decision = _match_keywords(text, _HEBREW_KEYWORDS["decision_form"])
    return has_system and has_decision


def _has_any_dimension(seg: Dict[str, Any]) -> bool:
    ad = seg.get("analysis_data")
    if not isinstance(ad, dict):
        return False
    dims = ad.get("dimensions")
    return isinstance(dims, list) and len(dims) > 0


def _has_structural_signal(seg: Dict[str, Any]) -> bool:
    ad = seg.get("analysis_data")
    if not isinstance(ad, dict):
        return False
    if isinstance(ad.get("rebar_details"), list) and ad.get("rebar_details"):
        return True
    prim = str(((ad.get("classification") or {}) if isinstance(ad.get("classification"), dict) else {}).get("primary_category") or "")
    return "REBAR" in prim.upper()


async def run_submission_preflight(
    *,
    decomposition: Dict[str, Any],
    approved_segment_ids: Sequence[str],
    strict: bool,
    run_llm_checks: bool,
) -> Tuple[bool, List[PreflightCheckResult]]:
    """Run completeness checks for a set of approved segments."""
    all_segments: List[Dict[str, Any]] = list(decomposition.get("segments") or [])
    approved_set = {str(s) for s in approved_segment_ids}
    approved_segments = [s for s in all_segments if str(s.get("segment_id")) in approved_set]

    by_type = _collect_by_type(approved_segments)

    request_table_candidates = _unique_segments(
        by_type.get(SegmentType.TABLE, []) + _find_segments_by_keywords(approved_segments, "request_table")
    )
    env_like = _find_segments_by_keywords(approved_segments, "env_sketch")
    site_like = _find_segments_by_keywords(approved_segments, "site_plan")
    env_site_candidates = _unique_segments(env_like + site_like)
    decl_like = _find_segments_by_keywords(approved_segments, "declaration")
    decl_candidates = _unique_segments(decl_like)
    floor_plan_candidates = _unique_segments(
        [s for s in by_type.get(SegmentType.FLOOR_PLAN, []) if not _is_site_plan_like(s)]
    )
    if not floor_plan_candidates:
        fallback = [
            s
            for s in approved_segments
            if _is_drawing_like(s) and not _is_site_plan_like(s)
        ]
        floor_plan_candidates = _unique_segments(fallback)
    section_candidates = _unique_segments(by_type.get(SegmentType.SECTION, []))
    elevation_candidates = _unique_segments(by_type.get(SegmentType.ELEVATION, []))
    mamad_keyword = [
        s
        for s in approved_segments
        if _match_keywords(_segment_text_corpus(s), _HEBREW_KEYWORDS["mamad"])
    ]
    mamad_scale = [
        s
        for s in approved_segments
        if _contains_scale_1_50(_segment_text_corpus(s))
    ]
    mamad_manual = [
        s
        for s in approved_segments
        if _is_manual_segment(s) and not _is_site_plan_like(s)
    ]
    mamad_drawings = [
        s
        for s in approved_segments
        if _is_drawing_like(s) and not _is_site_plan_like(s)
    ]
    mamad_candidates = _unique_segments(
        mamad_keyword + mamad_scale + mamad_manual + mamad_drawings
    )
    legend_candidates = _unique_segments(
        by_type.get(SegmentType.LEGEND, []) + _find_segments_by_keywords(approved_segments, "legend")
    )
    wall_reduction_candidates = _unique_segments(
        _find_segments_by_keywords(approved_segments, "wall_reduction")
    )
    structural_candidates = _unique_segments(
        _find_segments_by_keywords(approved_segments, "structural")
    )
    rishuy_candidates = _unique_segments(
        _find_segments_by_keywords(approved_segments, "rishuy_zamin")
    )
    dims_candidates = _unique_segments(approved_segments)
    area_candidates = _unique_segments(
        sorted(
            approved_segments,
            key=_score_area_table_candidate,
            reverse=True,
        )
    )
    # Tag-based prioritization (content_tags or lightweight tagger).
    tag_area = _filter_segments_by_tags(approved_segments, ["area_calculation_table"])
    tag_floor = _filter_segments_by_tags(approved_segments, ["floor_plan"])
    tag_mamad = _filter_segments_by_tags(approved_segments, ["mamad_plan_1_15"])
    tag_site = _filter_segments_by_tags(approved_segments, ["site_plan_map"])
    tag_wall_drop = _filter_segments_by_tags(approved_segments, ["mamad_wall_drop_plan"])
    tag_request = _filter_segments_by_tags(approved_segments, ["permit_application_form"])

    if tag_area:
        area_candidates = _unique_segments(tag_area + area_candidates)
    if tag_floor:
        floor_plan_candidates = _unique_segments(tag_floor + floor_plan_candidates)
    if tag_mamad:
        mamad_candidates = _unique_segments(tag_mamad + mamad_candidates)
    if tag_site:
        env_site_candidates = _unique_segments(tag_site + env_site_candidates)
    if tag_wall_drop:
        wall_reduction_candidates = _unique_segments(tag_wall_drop + wall_reduction_candidates)
    if tag_request:
        request_table_candidates = _unique_segments(tag_request + request_table_candidates)

    llm_results: Dict[str, Dict[str, Any]] = {}
    ocr_debug_all = _collect_ocr_debug(approved_segments)
    if run_llm_checks:
        raw_max_segments = int(getattr(settings, "preflight_llm_check_max_segments", 4))
        max_segments = None if raw_max_segments <= 0 else max(1, raw_max_segments)
        max_concurrency = max(1, int(getattr(settings, "preflight_llm_check_concurrency", 4)))
        semaphore = asyncio.Semaphore(max_concurrency)

        async def _run_llm_check(check_id: str, candidates: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
            selected = _unique_segments(list(candidates) if candidates else approved_segments)
            local_max_segments = max_segments
            if check_id == "PF-09" and local_max_segments is not None:
                # PF-09 (area table) benefits from a wider scan to catch empty tables with weak OCR.
                local_max_segments = max(local_max_segments, 10)
            if local_max_segments is not None:
                selected = selected[:local_max_segments]

            async def _one(seg: Dict[str, Any]) -> Optional[Tuple[str, Dict[str, Any]]]:
                seg_id = str(seg.get("segment_id"))
                blob_url = str(seg.get("blob_url") or "")
                async with semaphore:
                    img = await _download_image_bytes(blob_url)
                    if not img:
                        return None
                    try:
                        data = await _llm_detect_preflight_check(
                            check_id=check_id,
                            image_bytes=img,
                            ocr_text=_segment_ocr_text(seg),
                            hint_text=_segment_text_blob(seg),
                        )
                    except Exception as e:
                        logger.error("Preflight LLM check crashed", check_id=check_id, segment_id=seg_id, error=str(e))
                        return seg_id, {"error": str(e), "prompt": None, "raw_response": None}
                    if not data:
                        return None
                    return seg_id, data

            results = await asyncio.gather(*[_one(seg) for seg in selected])
            out: Dict[str, Any] = {}
            for res in results:
                if not res:
                    continue
                seg_id, data = res
                out[seg_id] = data
            return out

        llm_tasks = {
            "PF-01": asyncio.create_task(_run_llm_check("PF-01", request_table_candidates)),
            "PF-02": asyncio.create_task(_run_llm_check("PF-02", env_site_candidates)),
            "PF-03": asyncio.create_task(_run_llm_check("PF-03", decl_candidates)),
            "PF-04": asyncio.create_task(_run_llm_check("PF-04", floor_plan_candidates)),
            "PF-05": asyncio.create_task(_run_llm_check("PF-05", section_candidates)),
            "PF-06": asyncio.create_task(_run_llm_check("PF-06", elevation_candidates)),
            "PF-07": asyncio.create_task(_run_llm_check("PF-07", mamad_candidates)),
            "PF-08": asyncio.create_task(_run_llm_check("PF-08", dims_candidates)),
            "PF-10": asyncio.create_task(_run_llm_check("PF-10", legend_candidates)),
            "PF-11": asyncio.create_task(_run_llm_check("PF-11", wall_reduction_candidates)),
            "PF-12": asyncio.create_task(_run_llm_check("PF-12", structural_candidates)),
            "PF-13": asyncio.create_task(_run_llm_check("PF-13", rishuy_candidates)),
        }

        llm_tasks["PF-09"] = asyncio.create_task(_run_llm_check("PF-09", area_candidates))

        done = await asyncio.gather(*llm_tasks.values())
        llm_results = dict(zip(llm_tasks.keys(), done))

    checks: List[PreflightCheckResult] = []

    # PF-04: at least one floor plan
    floor_plans = by_type.get(SegmentType.FLOOR_PLAN, [])
    llm_floor = llm_results.get("PF-04", {})
    if llm_floor:
        floor_ids = [
            seg_id for seg_id, data in llm_floor.items() if data.get("floor_plan_present") is True
        ]
        floor_scale_ids = [
            seg_id
            for seg_id, data in llm_floor.items()
            if data.get("floor_plan_present") is True and data.get("scale_1_100_present") is True
        ]
        status = PreflightStatus.PASSED if floor_scale_ids else PreflightStatus.FAILED
        details = (
            'נמצאה לפחות תוכנית קומה אחת בקנ"מ 1:100.'
            if floor_scale_ids
            else ('זוהתה תוכנית קומה אך ללא קנ"מ 1:100.' if floor_ids else 'לא נמצאה אף תוכנית קומה (floor_plan).')
        )
        evidence = (floor_scale_ids or floor_ids)[:10]
        debug = {
            "ocr": ocr_debug_all or None,
            "llm": llm_floor,
        }
    else:
        status = PreflightStatus.PASSED if floor_plans else PreflightStatus.FAILED
        details = 'נמצאה לפחות תוכנית קומה אחת.' if floor_plans else 'לא נמצאה אף תוכנית קומה (floor_plan).'
        evidence = [str(s.get("segment_id")) for s in floor_plans[:10]]
        debug = {"count": len(floor_plans), "ocr": ocr_debug_all or None}
    checks.append(
        _mk_result(
            check_id="PF-04",
            title='קיימת תוכנית קומה (1:100)',
            pages=[6],
            status=status,
            details=details,
            evidence=evidence,
            debug=debug,
        )
    )

    # PF-05: at least 2 sections
    sections = by_type.get(SegmentType.SECTION, [])
    llm_sections = llm_results.get("PF-05", {})
    if llm_sections:
        section_ids = [
            seg_id for seg_id, data in llm_sections.items() if data.get("section_present") is True
        ]
        section_scale_ids = [
            seg_id
            for seg_id, data in llm_sections.items()
            if data.get("section_present") is True and data.get("scale_1_100_present") is True
        ]
        status = PreflightStatus.PASSED if len(section_scale_ids) >= 2 else PreflightStatus.FAILED
        if len(section_scale_ids) >= 2:
            details = f'נמצאו {len(section_scale_ids)} חתכים בקנ"מ 1:100.'
        elif section_ids:
            details = f'נמצאו {len(section_ids)} חתכים אך ללא קנ"מ 1:100 (נדרש לפחות 2).'
        else:
            details = 'לא נמצאו חתכים (sections).'
        evidence = (section_scale_ids or section_ids)[:10]
        debug = {
            "ocr": ocr_debug_all or None,
            "llm": llm_sections,
        }
    else:
        status = PreflightStatus.PASSED if len(sections) >= 2 else PreflightStatus.FAILED
        details = f'נמצאו {len(sections)} חתכים.' if len(sections) >= 2 else f'נמצאו רק {len(sections)} חתכים (נדרש לפחות 2).'
        evidence = [str(s.get("segment_id")) for s in sections[:10]]
        debug = {"count": len(sections), "ocr": ocr_debug_all or None}
    checks.append(
        _mk_result(
            check_id="PF-05",
            title='קיימים לפחות שני חתכים (1:100)',
            pages=[6],
            status=status,
            details=details,
            evidence=evidence,
            debug=debug,
        )
    )

    # PF-06: at least one elevation
    elevations = by_type.get(SegmentType.ELEVATION, [])
    llm_elev = llm_results.get("PF-06", {})
    if llm_elev:
        elev_ids = [
            seg_id for seg_id, data in llm_elev.items() if data.get("elevation_present") is True
        ]
        elev_scale_ids = [
            seg_id
            for seg_id, data in llm_elev.items()
            if data.get("elevation_present") is True and data.get("scale_1_100_present") is True
        ]
        status = PreflightStatus.PASSED if elev_scale_ids else PreflightStatus.FAILED
        details = (
            'נמצאה לפחות חזית אחת בקנ"מ 1:100.'
            if elev_scale_ids
            else ('זוהתה חזית אך ללא קנ"מ 1:100.' if elev_ids else 'לא נמצאה אף חזית (elevation).')
        )
        evidence = (elev_scale_ids or elev_ids)[:10]
        debug = {
            "ocr": ocr_debug_all or None,
            "llm": llm_elev,
        }
    else:
        status = PreflightStatus.PASSED if elevations else PreflightStatus.FAILED
        details = 'נמצאה לפחות חזית אחת.' if elevations else 'לא נמצאה אף חזית (elevation).'
        evidence = [str(s.get("segment_id")) for s in elevations[:10]]
        debug = {"count": len(elevations), "ocr": ocr_debug_all or None}
    checks.append(
        _mk_result(
            check_id="PF-06",
            title='קיימות חזיתות (1:100)',
            pages=[6],
            status=status,
            details=details,
            evidence=evidence,
            debug=debug,
        )
    )

    # PF-01: request summary table (require table + identifiers)
    request_table_strong: List[Dict[str, Any]] = []
    request_table_weak: List[Dict[str, Any]] = []
    for seg in request_table_candidates:
        corpus = _segment_text_corpus(seg)
        if _has_request_table_signal(corpus):
            request_table_strong.append(seg)
        else:
            request_table_weak.append(seg)
    request_table_ids = list({str(s.get("segment_id")) for s in request_table_strong if s.get("segment_id")})
    weak_ids = list({str(s.get("segment_id")) for s in request_table_weak if s.get("segment_id")})

    llm_req = llm_results.get("PF-01", {})
    if llm_req:
        req_ids = [
            seg_id
            for seg_id, data in llm_req.items()
            if data.get("request_table_present") is True
            and data.get("identifiers_present") is True
            and data.get("signature_present") is True
        ]
        req_missing_sig_ids = [
            seg_id
            for seg_id, data in llm_req.items()
            if data.get("request_table_present") is True
            and data.get("identifiers_present") is True
            and data.get("signature_present") is not True
        ]
        req_weak_ids = [
            seg_id for seg_id, data in llm_req.items() if data.get("request_table_present") is True
        ]
        status = (
            PreflightStatus.PASSED if req_ids
            else (PreflightStatus.FAILED if strict else PreflightStatus.WARNING) if (req_missing_sig_ids or req_weak_ids)
            else PreflightStatus.FAILED
        )
        details = (
            'נמצא סגמנט עם טבלת פרטי בקשה הכוללת מזהים וחתימה (LLM).'
            if req_ids
            else (
                'זוהתה טבלת פרטי בקשה עם מזהים אך ללא חתימה (LLM).'
                if req_missing_sig_ids
                else ('זוהה סגמנט טבלה אך ללא מזהים ברורים (LLM).' if req_weak_ids else 'לא זוהתה טבלה/דף ריכוז פרטי בקשה (LLM).')
            )
        )
        evidence = (req_ids or req_missing_sig_ids or req_weak_ids)[:10]
        debug = {
            "ocr": ocr_debug_all or None,
            "llm": llm_req,
        }
    else:
        status = (
            PreflightStatus.PASSED if request_table_ids
            else (PreflightStatus.FAILED if strict else PreflightStatus.WARNING) if weak_ids
            else PreflightStatus.FAILED
        )
        details = (
            'נמצא סגמנט עם טבלת פרטי בקשה הכוללת מזהים/מספרים.'
            if request_table_ids
            else ('זוהה סגמנט טבלה אך ללא מזהים ברורים.' if weak_ids else 'לא זוהתה טבלה/דף ריכוז פרטי בקשה.')
        )
        evidence = (request_table_ids or weak_ids)[:10]
        debug = {"ocr": ocr_debug_all or None}
    checks.append(
        _mk_result(
            check_id="PF-01",
            title='קיימת טבלה מרכזת פרטי בקשה',
            pages=[5],
            status=status,
            details=details,
            evidence=evidence,
            debug=debug,
        )
    )

    # PF-02: environment sketch + site plan (require keywords + scale/numeric signal)
    env_strong = [s for s in env_like if _has_scale_token(_segment_text_corpus(s)) or _has_numeric_token(_segment_text_corpus(s), min_digits=2)]
    site_strong = [s for s in site_like if _has_scale_token(_segment_text_corpus(s)) or _has_numeric_token(_segment_text_corpus(s), min_digits=2)]
    env_ids = list({str(s.get("segment_id")) for s in env_strong if s.get("segment_id")})
    site_ids = list({str(s.get("segment_id")) for s in site_strong if s.get("segment_id")})
    weak_env_ids = list({str(s.get("segment_id")) for s in env_like if s.get("segment_id")})
    weak_site_ids = list({str(s.get("segment_id")) for s in site_like if s.get("segment_id")})

    llm_env = llm_results.get("PF-02", {})
    if llm_env:
        seg_by_id = {
            str(s.get("segment_id")): s
            for s in approved_segments
            if s.get("segment_id")
        }
        env_llm_ids = [
            seg_id
            for seg_id, data in llm_env.items()
            if data.get("doc_type") in {"environment_sketch", "both"}
            and data.get("scale_or_dimensions_present") is True
        ]
        site_llm_ids = [
            seg_id
            for seg_id, data in llm_env.items()
            if data.get("doc_type") in {"site_plan", "both"}
            and data.get("scale_or_dimensions_present") is True
        ]
        env_llm_weak = [
            seg_id
            for seg_id, data in llm_env.items()
            if data.get("doc_type") in {"environment_sketch", "both"}
        ]
        site_llm_weak = [
            seg_id
            for seg_id, data in llm_env.items()
            if data.get("doc_type") in {"site_plan", "both"}
        ]
        env_llm_ids = list(dict.fromkeys(env_llm_ids))
        site_llm_ids = list(dict.fromkeys(site_llm_ids))
        env_llm_weak = list(dict.fromkeys(env_llm_weak))
        site_llm_weak = list(dict.fromkeys(site_llm_weak))

        env_assumed_from_site = False
        if not env_llm_ids:
            env_from_site = [
                seg_id
                for seg_id, data in llm_env.items()
                if data.get("doc_type") == "site_plan"
                and _match_keywords(_segment_text_corpus(seg_by_id.get(seg_id, {})), _HEBREW_KEYWORDS["env_sketch"])
            ]
            if env_from_site:
                env_llm_ids = list(dict.fromkeys(env_from_site))
        if not env_llm_ids and len(site_llm_ids) >= 2:
            env_llm_ids = [site_llm_ids[0]]
            env_assumed_from_site = True
        status = (
            PreflightStatus.PASSED if (env_llm_ids and site_llm_ids)
            else (PreflightStatus.FAILED if strict else PreflightStatus.WARNING) if (env_llm_weak and site_llm_weak)
            else PreflightStatus.FAILED
        )
        details = (
            (
                'זוהו תשריט סביבה ומפה מצבית עם אינדיקציה לקנ\"מ/מידות (LLM).'
                if not env_assumed_from_site
                else 'זוהו שתי מפות מצבית עם קנ\"מ/מידות; אחת נספרה כתשריט סביבה (Best-effort).'
            )
            if status == PreflightStatus.PASSED
            else (
                'זוהו תשריט סביבה ומפה מצבית אך ללא אינדיקציה לקנ\"מ/מידות (LLM).'
                if (env_llm_weak and site_llm_weak)
                else f'חסר: ' + ('' if env_llm_weak else 'תשריט סביבה ') + ('' if site_llm_weak else 'מפה מצבית')
            )
        ).strip()
        evidence = list(dict.fromkeys(env_llm_ids + site_llm_ids or env_llm_weak + site_llm_weak))[:10]
        debug = {
            "ocr": ocr_debug_all or None,
            "llm": llm_env,
        }
    else:
        status = (
            PreflightStatus.PASSED if (env_ids and site_ids)
            else (PreflightStatus.FAILED if strict else PreflightStatus.WARNING) if (weak_env_ids and weak_site_ids)
            else PreflightStatus.FAILED
        )
        details = (
            'זוהו תשריט סביבה ומפה מצבית עם אינדיקציה לקנ\"מ/מידות.'
            if status == PreflightStatus.PASSED
            else (
                'זוהו תשריט סביבה ומפה מצבית אך ללא אינדיקציה לקנ\"מ/מידות.'
                if (weak_env_ids and weak_site_ids)
                else f'חסר: ' + ('' if weak_env_ids else 'תשריט סביבה ') + ('' if weak_site_ids else 'מפה מצבית')
            )
        ).strip()
        evidence = (env_ids + site_ids or weak_env_ids + weak_site_ids)[:10]
        debug = {"env": env_ids, "site": site_ids, "env_weak": weak_env_ids, "site_weak": weak_site_ids, "ocr": ocr_debug_all or None}
    checks.append(
        _mk_result(
            check_id="PF-02",
            title='קיים תשריט סביבה + מפה מצבית',
            pages=[5],
            status=status,
            details=details,
            evidence=evidence,
            debug=debug,
        )
    )

    # PF-03: signed declaration / signatures
    decl_ids = list({str(s.get("segment_id")) for s in decl_like if s.get("segment_id")})
    llm_decl = llm_results.get("PF-03", {})
    if llm_decl:
        sig_ids = [
            seg_id for seg_id, data in llm_decl.items() if data.get("signature_block_present") is True
        ]
        signature_present = bool(sig_ids)
        status = PreflightStatus.PASSED if signature_present else PreflightStatus.FAILED
        details = (
            'זוהה אזור חתימה בפועל במסמך (LLM).'
            if signature_present
            else 'לא זוהה אזור חתימה בפועל במסמך (LLM).'
        )
        evidence = sig_ids[:10]
        debug = {
            "ocr": ocr_debug_all or None,
            "llm": llm_decl,
        }
    else:
        status = PreflightStatus.FAILED
        details = 'לא זוהה אזור חתימה בפועל במסמך.'
        evidence = decl_ids[:10]
        debug = {"ocr": ocr_debug_all or None}

    checks.append(
        _mk_result(
            check_id="PF-03",
            title='קיימת הצהרה חתומה / חתימות נדרשות',
            pages=[5],
            status=status,
            details=details,
            evidence=evidence,
            debug=debug,
        )
    )

    # PF-13: decision form from "Rishuy Zamin" (best-effort unless strict)
    rishuy_like: List[Dict[str, Any]] = []
    rishuy_strong: List[Dict[str, Any]] = []
    for seg in approved_segments:
        corpus = _segment_text_corpus(seg)
        if _match_keywords(corpus, _HEBREW_KEYWORDS["rishuy_zamin"]):
            rishuy_like.append(seg)
            if _has_rishuy_zamin_decision(corpus):
                rishuy_strong.append(seg)

    rishuy_ids = list({str(s.get("segment_id")) for s in rishuy_strong if s.get("segment_id")})
    rishuy_weak_ids = list({str(s.get("segment_id")) for s in rishuy_like if s.get("segment_id")})

    llm_rishuy = llm_results.get("PF-13", {})
    if llm_rishuy:
        rishuy_llm_ids = [
            seg_id
            for seg_id, data in llm_rishuy.items()
            if data.get("rishuy_zamin_present") is True
            and data.get("decision_form_present") is True
            and data.get("signature_present") is True
        ]
        rishuy_missing_sig_ids = [
            seg_id
            for seg_id, data in llm_rishuy.items()
            if data.get("rishuy_zamin_present") is True
            and data.get("decision_form_present") is True
            and data.get("signature_present") is not True
        ]
        rishuy_llm_weak = [
            seg_id for seg_id, data in llm_rishuy.items() if data.get("rishuy_zamin_present") is True
        ]
        rishuy_status = (
            PreflightStatus.PASSED if rishuy_llm_ids
            else (PreflightStatus.FAILED if strict else PreflightStatus.WARNING) if (rishuy_missing_sig_ids or rishuy_llm_weak)
            else (PreflightStatus.FAILED if strict else PreflightStatus.WARNING)
        )
        details = (
            'זוהה טופס החלטה מרישוי זמין עם חתימה (LLM).'
            if rishuy_llm_ids
            else (
                'זוהה טופס החלטה מרישוי זמין אך ללא חתימה (LLM).'
                if rishuy_missing_sig_ids
                else (
                    'זוהה אזכור לרישוי זמין אך ללא אינדיקציה ברורה לטופס החלטה (LLM).'
                    if rishuy_llm_weak
                    else 'לא זוהה טופס החלטה מרישוי זמין (LLM).'
                )
            )
        )
        evidence = (rishuy_llm_ids or rishuy_missing_sig_ids or rishuy_llm_weak)[:10]
        debug = {
            "ocr": ocr_debug_all or None,
            "llm": llm_rishuy,
        }
    else:
        rishuy_status = (
            PreflightStatus.PASSED if rishuy_ids
            else (PreflightStatus.FAILED if strict else PreflightStatus.WARNING) if rishuy_weak_ids
            else (PreflightStatus.FAILED if strict else PreflightStatus.WARNING)
        )
        details = (
            'זוהה טופס החלטה מרישוי זמין (כולל אינדיקציה להחלטה).'
            if rishuy_ids
            else (
                'זוהה אזכור לרישוי זמין אך ללא אינדיקציה ברורה לטופס החלטה.'
                if rishuy_weak_ids
                else 'לא זוהה טופס החלטה מרישוי זמין.'
            )
        )
        evidence = (rishuy_ids or rishuy_weak_ids)[:10]
        debug = {"ocr": ocr_debug_all or None}

    checks.append(
        _mk_result(
            check_id="PF-13",
            title='קיים טופס החלטה מרישוי זמין',
            pages=[5],
            status=rishuy_status,
            details=details,
            evidence=evidence,
            debug=debug,
        )
    )

    # PF-07: mamad plan exists (best-effort) with 1:50 scale signal
    mamad_like: List[Dict[str, Any]] = []
    mamad_scale_like: List[Dict[str, Any]] = []
    for seg in approved_segments:
        corpus = _segment_text_corpus(seg)
        if _match_keywords(corpus, _HEBREW_KEYWORDS["mamad"]):
            mamad_like.append(seg)
            if _contains_scale_1_50(corpus):
                mamad_scale_like.append(seg)

    mamad_ids = list({str(s.get("segment_id")) for s in mamad_like if s.get("segment_id")})
    mamad_scale_ids = list({str(s.get("segment_id")) for s in mamad_scale_like if s.get("segment_id")})

    llm_mamad = llm_results.get("PF-07", {})
    if llm_mamad:
        mamad_llm_ids = [
            seg_id for seg_id, data in llm_mamad.items() if data.get("mamad_plan_present") is True
        ]
        mamad_llm_scale_ids = [
            seg_id
            for seg_id, data in llm_mamad.items()
            if data.get("mamad_plan_present") is True and data.get("scale_1_50_present") is True
        ]
        if mamad_llm_scale_ids:
            mamad_status = PreflightStatus.PASSED
        elif mamad_llm_ids:
            mamad_status = PreflightStatus.FAILED if strict else PreflightStatus.WARNING
        else:
            mamad_status = PreflightStatus.FAILED if strict else PreflightStatus.WARNING
        details = (
            'זוהה סגמנט מרחב מוגן עם קנ"מ 1:50 (LLM).'
            if mamad_llm_scale_ids
            else (
                'זוהה סגמנט שמזכיר מרחב מוגן, אך ללא אינדיקציה לקנ"מ 1:50 (LLM).'
                if mamad_llm_ids
                else 'לא זוהה בוודאות סגמנט מרחב מוגן (LLM).'
            )
        )
        evidence = (mamad_llm_scale_ids or mamad_llm_ids)[:10]
        debug = {
            "ocr": ocr_debug_all or None,
            "llm": llm_mamad,
        }
    else:
        if mamad_scale_ids:
            mamad_status = PreflightStatus.PASSED
        elif mamad_ids:
            mamad_status = PreflightStatus.FAILED if strict else PreflightStatus.WARNING
        else:
            mamad_status = PreflightStatus.FAILED if strict else PreflightStatus.WARNING
        details = (
            'זוהה סגמנט מרחב מוגן עם קנ"מ 1:50.'
            if mamad_scale_ids
            else (
                'זוהה סגמנט שמזכיר מרחב מוגן, אך ללא אינדיקציה לקנ"מ 1:50.'
                if mamad_ids
                else 'לא זוהה בוודאות סגמנט מרחב מוגן. מומלץ לוודא שסימנת/קראת שם לסגמנט הממ"ד.'
            )
        )
        evidence = (mamad_scale_ids or mamad_ids)[:10]
        debug = {"ocr": ocr_debug_all or None}
    checks.append(
        _mk_result(
            check_id="PF-07",
            title='קיימת תוכנית/פרט למרחב המוגן (1:50)',
            pages=[8, 9, 10],
            status=mamad_status,
            details=details,
            evidence=evidence,
            debug=debug,
        )
    )

    # PF-08: minimal markings (dimensions present in analysis)
    dims_segments = [seg for seg in approved_segments if _has_any_dimension(seg)]
    dims_ids = list({str(s.get("segment_id")) for s in dims_segments if s.get("segment_id")})
    any_dims = bool(dims_ids)

    llm_dims = llm_results.get("PF-08", {})
    if llm_dims:
        llm_dim_ids = [
            seg_id for seg_id, data in llm_dims.items() if data.get("dimensions_present") is True
        ]
        dims_status = PreflightStatus.PASSED if llm_dim_ids else (PreflightStatus.FAILED if strict else PreflightStatus.WARNING)
        details = (
            'המערכת זיהתה לפחות מימד אחד/סימון מידה בסגמנטים (LLM).'
            if llm_dim_ids
            else 'לא זוהו מימדים מתוך ניתוח קיים (LLM). אם זה מסמך סרוק/לא קריא, ייתכן שצריך לבחור סגמנט אחר או להריץ ניתוח.'
        )
        evidence = llm_dim_ids[:10]
        debug = {
            "ocr": ocr_debug_all or None,
            "llm": llm_dims,
        }
    else:
        dims_status = PreflightStatus.PASSED if any_dims else (PreflightStatus.FAILED if strict else PreflightStatus.WARNING)
        details = 'המערכת זיהתה לפחות מימד אחד/סימון מידה בסגמנטים.' if any_dims else 'לא זוהו מימדים מתוך ניתוח קיים. אם זה מסמך סרוק/לא קריא, ייתכן שצריך לבחור סגמנט אחר או להריץ ניתוח.'
        evidence = dims_ids[:10]
        debug = {"ocr": ocr_debug_all or None}

    checks.append(
        _mk_result(
            check_id="PF-08",
            title='קיימים סימוני מידות/נתונים מינימליים (Best-effort)',
            pages=[7, 9, 10],
            status=dims_status,
            details=details,
            evidence=evidence,
            debug=debug,
        )
    )

    # PF-09: area calculation table (require area values)
    area_strong: List[Dict[str, Any]] = []
    area_weak: List[Dict[str, Any]] = []
    for seg in approved_segments:
        corpus = _segment_text_corpus(seg)
        if _has_area_table_signal(corpus) and _has_area_values(corpus):
            area_strong.append(seg)
        elif _has_area_table_signal(corpus):
            area_weak.append(seg)
    area_ids = list({str(s.get("segment_id")) for s in area_strong if s.get("segment_id")})
    area_weak_ids = list({str(s.get("segment_id")) for s in area_weak if s.get("segment_id")})

    llm_area = llm_results.get("PF-09", {})
    if llm_area:
        def _has_table_evidence(ev: Any) -> bool:
            if not isinstance(ev, list):
                return False
            table_tokens = ["טבלה", "טבלא", "תאים", "שורות", "עמודות", "grid"]
            for item in ev:
                if not isinstance(item, str):
                    continue
                low = item.lower()
                if any(tok in low for tok in table_tokens):
                    return True
            return False

        def _score_llm_area_candidate(seg_id: str, data: Dict[str, Any]) -> float:
            score = 0.0
            if data.get("area_table_present") is True:
                score += 3.0
            if data.get("area_values_present") is True:
                score += 2.0
            if _has_table_evidence(data.get("evidence")):
                score += 2.0
            seg = next((s for s in approved_segments if str(s.get("segment_id")) == seg_id), None)
            tags = _get_content_tags(seg or {})
            if any(isinstance(t, dict) and t.get("tag") == "area_calculation_table" for t in tags):
                score += 3.0
            if any(isinstance(t, dict) and t.get("tag") == "floor_plan" for t in tags):
                score -= 2.5
            conf = data.get("confidence")
            if isinstance(conf, (int, float)):
                score += float(conf)
            return score

        llm_candidates = [
            (seg_id, data)
            for seg_id, data in llm_area.items()
            if isinstance(data, dict) and data.get("area_table_present") is True
        ]
        llm_candidates.sort(key=lambda x: _score_llm_area_candidate(x[0], x[1]), reverse=True)
        best = llm_candidates[0] if llm_candidates else None

        if best:
            seg_id, data = best
            has_values = data.get("area_values_present") is True
            if has_values:
                area_status = PreflightStatus.PASSED
                area_details = 'נמצאה טבלת שטחים עם ערכי מ\"ר (LLM).'
            else:
                area_status = PreflightStatus.WARNING if not strict else PreflightStatus.FAILED
                area_details = 'נמצאה טבלת שטחים אך היא ריקה/ללא ערכים (LLM).'
            area_evidence = [seg_id]
        else:
            area_status = PreflightStatus.WARNING if not strict else PreflightStatus.FAILED
            area_details = 'ה‑LLM לא זיהה טבלת שטחים.'
            area_evidence = []
        debug_payload: Dict[str, Any] = {
            "ocr": ocr_debug_all or None,
            "llm": llm_area,
        }
    else:
        area_status = (
            PreflightStatus.PASSED
            if area_ids
            else (PreflightStatus.WARNING if area_weak_ids else (PreflightStatus.WARNING if not strict else PreflightStatus.FAILED))
        )
        area_details = (
            'נמצאה טבלת שטחים עם ערכי מ\"ר.'
            if area_ids
            else ('זוהתה טבלת שטחים ללא ערכים ברורים.' if area_weak_ids else 'לא זוהתה טבלת שטחים. אם לא הועלתה עדיין טבלת שטחי מיגון – מומלץ להוסיף.')
        )
        area_evidence = (area_ids or area_weak_ids)[:10]
        debug_payload = {"ocr": ocr_debug_all or None}

    checks.append(
        _mk_result(
            check_id="PF-09",
            title='קיימת טבלת חישוב שטחי מיגון (אם נדרש)',
            pages=[8],
            status=area_status,
            details=area_details,
            evidence=area_evidence,
            debug=debug_payload or None,
        )
    )

    # PF-10: legend / verbal definitions
    legend_like = by_type.get(SegmentType.LEGEND, []) + _find_segments_by_keywords(approved_segments, "legend")
    legend_strong = [s for s in legend_like if _match_keywords(_segment_text_corpus(s), _HEBREW_KEYWORDS["legend"])]
    legend_ids = list({str(s.get("segment_id")) for s in legend_strong if s.get("segment_id")})
    legend_weak_ids = list({str(s.get("segment_id")) for s in legend_like if s.get("segment_id")})

    llm_legend = llm_results.get("PF-10", {})
    if llm_legend:
        legend_llm_ids = [
            seg_id for seg_id, data in llm_legend.items() if data.get("legend_present") is True
        ]
        legend_status = PreflightStatus.PASSED if legend_llm_ids else (PreflightStatus.WARNING if not strict else PreflightStatus.FAILED)
        details = (
            'זוהה מקרא/טבלת הגדרות עם טקסט מזוהה (LLM).'
            if legend_llm_ids
            else 'לא זוהה מקרא/טבלת הגדרות (LLM).'
        )
        evidence = legend_llm_ids[:10]
        debug = {
            "ocr": ocr_debug_all or None,
            "llm": llm_legend,
        }
    else:
        legend_status = PreflightStatus.PASSED if legend_ids else (PreflightStatus.WARNING if legend_weak_ids else (PreflightStatus.WARNING if not strict else PreflightStatus.FAILED))
        details = (
            'זוהה מקרא/טבלת הגדרות עם טקסט מזוהה.'
            if legend_ids
            else ('זוהה סגמנט מקרא ללא טקסט מזוהה.' if legend_weak_ids else 'לא זוהה מקרא/טבלת הגדרות. מומלץ לכלול מקרא/טבלת רכיבים כנדרש במסמך.')
        )
        evidence = (legend_ids or legend_weak_ids)[:10]
        debug = {"ocr": ocr_debug_all or None}

    checks.append(
        _mk_result(
            check_id="PF-10",
            title='קיים מקרא/טבלת הגדרות לרכיבי המרחב המוגן',
            pages=[10, 11],
            status=legend_status,
            details=details,
            evidence=evidence,
            debug=debug,
        )
    )

    # PF-11: wall reduction plan
    wall_red_like = _find_segments_by_keywords(approved_segments, "wall_reduction")
    wall_red_ids = list({str(s.get("segment_id")) for s in wall_red_like if s.get("segment_id")})

    llm_wall = llm_results.get("PF-11", {})
    if llm_wall:
        wall_llm_ids = [
            seg_id for seg_id, data in llm_wall.items() if data.get("wall_reduction_present") is True
        ]
        status = PreflightStatus.PASSED if wall_llm_ids else PreflightStatus.NOT_APPLICABLE
        details = 'זוהתה תכנית ירידת קירות (LLM).' if wall_llm_ids else 'לא זוהתה תכנית ירידת קירות (LLM).'
        evidence = wall_llm_ids[:10]
        debug = {
            "ocr": ocr_debug_all or None,
            "llm": llm_wall,
        }
    else:
        status = PreflightStatus.PASSED if wall_red_ids else PreflightStatus.NOT_APPLICABLE
        details = 'זוהתה תכנית ירידת קירות.' if wall_red_ids else 'לא זוהתה תכנית ירידת קירות (ייתכן שלא רלוונטי להגשה זו).'
        evidence = wall_red_ids[:10]
        debug = {"ocr": ocr_debug_all or None}

    checks.append(
        _mk_result(
            check_id="PF-11",
            title='קיימת תכנית/חישוב ירידת קירות (אם רלוונטי)',
            pages=[12],
            status=status,
            details=details,
            evidence=evidence,
            debug=debug,
        )
    )

    # PF-12: structural details (require rebar signals or analysis evidence)
    structural_like = _find_segments_by_keywords(approved_segments, "structural")
    structural_signal = any(_has_structural_signal(seg) for seg in approved_segments)
    structural_strong = [s for s in structural_like if _has_rebar_signal(_segment_text_corpus(s))]
    structural_ids = list({str(s.get("segment_id")) for s in structural_strong if s.get("segment_id")})
    struct_ok = bool(structural_ids) or structural_signal

    llm_struct = llm_results.get("PF-12", {})
    if llm_struct:
        struct_llm_ids = [
            seg_id for seg_id, data in llm_struct.items() if data.get("structural_details_present") is True
        ]
        struct_status = PreflightStatus.PASSED if struct_llm_ids else (PreflightStatus.FAILED if strict else PreflightStatus.WARNING)
        details = (
            'זוהו פרטים הנדסיים עם אינדיקציות זיון/ברזל (LLM).'
            if struct_llm_ids
            else 'לא זוהו פרטים הנדסיים (LLM). מומלץ להוסיף סגמנט עם פרטי זיון/ריתום/פתחים כנדרש.'
        )
        evidence = struct_llm_ids[:10]
        debug = {
            "ocr": ocr_debug_all or None,
            "llm": llm_struct,
        }
    else:
        struct_status = (
            PreflightStatus.PASSED if struct_ok
            else (PreflightStatus.FAILED if strict else PreflightStatus.WARNING)
        )
        details = (
            'זוהו פרטים הנדסיים עם אינדיקציות זיון/ברזל.'
            if struct_ok
            else 'לא זוהו פרטים הנדסיים. מומלץ להוסיף סגמנט עם פרטי זיון/ריתום/פתחים כנדרש.'
        )
        evidence = structural_ids[:10]
        debug = {"analysis_signal": structural_signal, "ocr": ocr_debug_all or None}

    checks.append(
        _mk_result(
            check_id="PF-12",
            title='קיימים פרטים הנדסיים (זיון/ריתום/פתחים) (Best-effort)',
            pages=[14, 15, 16],
            status=struct_status,
            details=details,
            evidence=evidence,
            debug=debug,
        )
    )

    # Gate: any FAILED check fails the preflight.
    passed = not any(c.status in (PreflightStatus.FAILED, PreflightStatus.ERROR) for c in checks)
    return passed, checks
