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

    data = json.loads(content)
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


def _segment_text_corpus(seg: Dict[str, Any]) -> str:
    parts = [_segment_text_blob(seg)]
    parts.extend(_extract_checkable_text_items(seg))
    return " ".join([p for p in parts if p])


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

    checks: List[PreflightCheckResult] = []

    # PF-04: at least one floor plan
    floor_plans = by_type.get(SegmentType.FLOOR_PLAN, [])
    checks.append(
        _mk_result(
            check_id="PF-04",
            title='קיימת תוכנית קומה (1:100)',
            pages=[6],
            status=PreflightStatus.PASSED if floor_plans else PreflightStatus.FAILED,
            details='נמצאה לפחות תוכנית קומה אחת.' if floor_plans else 'לא נמצאה אף תוכנית קומה (floor_plan).',
            evidence=[str(s.get("segment_id")) for s in floor_plans[:10]],
            debug={"count": len(floor_plans)},
        )
    )

    # PF-05: at least 2 sections
    sections = by_type.get(SegmentType.SECTION, [])
    checks.append(
        _mk_result(
            check_id="PF-05",
            title='קיימים לפחות שני חתכים (1:100)',
            pages=[6],
            status=PreflightStatus.PASSED if len(sections) >= 2 else PreflightStatus.FAILED,
            details=f'נמצאו {len(sections)} חתכים.' if len(sections) >= 2 else f'נמצאו רק {len(sections)} חתכים (נדרש לפחות 2).',
            evidence=[str(s.get("segment_id")) for s in sections[:10]],
            debug={"count": len(sections)},
        )
    )

    # PF-06: at least one elevation
    elevations = by_type.get(SegmentType.ELEVATION, [])
    checks.append(
        _mk_result(
            check_id="PF-06",
            title='קיימות חזיתות (1:100)',
            pages=[6],
            status=PreflightStatus.PASSED if elevations else PreflightStatus.FAILED,
            details='נמצאה לפחות חזית אחת.' if elevations else 'לא נמצאה אף חזית (elevation).',
            evidence=[str(s.get("segment_id")) for s in elevations[:10]],
            debug={"count": len(elevations)},
        )
    )

    # PF-01: request summary table (require table + identifiers)
    request_table_candidates = by_type.get(SegmentType.TABLE, []) + _find_segments_by_keywords(approved_segments, "request_table")
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
    status = (
        PreflightStatus.PASSED if request_table_ids
        else (PreflightStatus.FAILED if strict else PreflightStatus.WARNING) if weak_ids
        else PreflightStatus.FAILED
    )
    checks.append(
        _mk_result(
            check_id="PF-01",
            title='קיימת טבלה מרכזת פרטי בקשה',
            pages=[5],
            status=status,
            details=(
                'נמצא סגמנט עם טבלת פרטי בקשה הכוללת מזהים/מספרים.'
                if request_table_ids
                else ('זוהה סגמנט טבלה אך ללא מזהים ברורים.' if weak_ids else 'לא זוהתה טבלה/דף ריכוז פרטי בקשה.')
            ),
            evidence=(request_table_ids or weak_ids)[:10],
        )
    )

    # PF-02: environment sketch + site plan (require keywords + scale/numeric signal)
    env_like = _find_segments_by_keywords(approved_segments, "env_sketch")
    site_like = _find_segments_by_keywords(approved_segments, "site_plan")
    env_strong = [s for s in env_like if _has_scale_token(_segment_text_corpus(s)) or _has_numeric_token(_segment_text_corpus(s), min_digits=2)]
    site_strong = [s for s in site_like if _has_scale_token(_segment_text_corpus(s)) or _has_numeric_token(_segment_text_corpus(s), min_digits=2)]
    env_ids = list({str(s.get("segment_id")) for s in env_strong if s.get("segment_id")})
    site_ids = list({str(s.get("segment_id")) for s in site_strong if s.get("segment_id")})
    weak_env_ids = list({str(s.get("segment_id")) for s in env_like if s.get("segment_id")})
    weak_site_ids = list({str(s.get("segment_id")) for s in site_like if s.get("segment_id")})
    status = (
        PreflightStatus.PASSED if (env_ids and site_ids)
        else (PreflightStatus.FAILED if strict else PreflightStatus.WARNING) if (weak_env_ids and weak_site_ids)
        else PreflightStatus.FAILED
    )
    checks.append(
        _mk_result(
            check_id="PF-02",
            title='קיים תשריט סביבה + מפה מצבית',
            pages=[5],
            status=status,
            details=(
                'זוהו תשריט סביבה ומפה מצבית עם אינדיקציה לקנ\"מ/מידות.'
                if status == PreflightStatus.PASSED
                else (
                    'זוהו תשריט סביבה ומפה מצבית אך ללא אינדיקציה לקנ\"מ/מידות.'
                    if (weak_env_ids and weak_site_ids)
                    else f'חסר: ' + ('' if weak_env_ids else 'תשריט סביבה ') + ('' if weak_site_ids else 'מפה מצבית')
                )
            ).strip(),
            evidence=(env_ids + site_ids or weak_env_ids + weak_site_ids)[:10],
            debug={"env": env_ids, "site": site_ids, "env_weak": weak_env_ids, "site_weak": weak_site_ids},
        )
    )

    # PF-03: signed declaration / signatures
    decl_like = _find_segments_by_keywords(approved_segments, "declaration")
    decl_ids = list({str(s.get("segment_id")) for s in decl_like if s.get("segment_id")})

    llm_debug: Dict[str, Any] = {}
    if run_llm_checks and decl_like:
        # Try LLM on a few likely declaration segments, in parallel.
        max_segments = max(1, int(getattr(settings, "preflight_llm_signature_max_segments", 4)))
        max_concurrency = max(1, int(getattr(settings, "preflight_llm_signature_concurrency", 4)))
        semaphore = asyncio.Semaphore(max_concurrency)

        async def _run_llm(seg: Dict[str, Any]) -> Optional[Tuple[str, _ArtifactSignals]]:
            seg_id = str(seg.get("segment_id"))
            blob_url = str(seg.get("blob_url") or "")
            async with semaphore:
                img = await _download_image_bytes(blob_url)
                if not img:
                    return None
                signals = await _llm_detect_artifact(image_bytes=img, hint_text=_segment_text_blob(seg))
                if not signals:
                    return None
                return seg_id, signals

        candidates = decl_like[:max_segments]
        results = await asyncio.gather(*[_run_llm(seg) for seg in candidates])
        for res in results:
            if not res:
                continue
            seg_id, signals = res
            llm_debug[seg_id] = {
                "artifact_type": signals.artifact_type,
                "signature_block_present": signals.signature_block_present,
                "signature_roles": signals.signature_roles,
                "detected_scale": signals.detected_scale,
            }

    signature_present = any(
        isinstance(v, dict) and v.get("signature_block_present") is True for v in llm_debug.values()
    ) if llm_debug else False

    # Require an actual detected signature block to pass.
    status = PreflightStatus.PASSED if signature_present else PreflightStatus.FAILED
    details = (
        'זוהה אזור חתימה בפועל במסמך.'
        if signature_present
        else 'לא זוהה אזור חתימה בפועל במסמך.'
    )

    checks.append(
        _mk_result(
            check_id="PF-03",
            title='קיימת הצהרה חתומה / חתימות נדרשות',
            pages=[5],
            status=status,
            details=details,
            evidence=decl_ids[:10],
            debug={"llm": llm_debug} if llm_debug else None,
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
    rishuy_status = (
        PreflightStatus.PASSED if rishuy_ids
        else (PreflightStatus.FAILED if strict else PreflightStatus.WARNING) if rishuy_weak_ids
        else (PreflightStatus.FAILED if strict else PreflightStatus.WARNING)
    )
    checks.append(
        _mk_result(
            check_id="PF-13",
            title='קיים טופס החלטה מרישוי זמין',
            pages=[5],
            status=rishuy_status,
            details=(
                'זוהה טופס החלטה מרישוי זמין (כולל אינדיקציה להחלטה).'
                if rishuy_ids
                else (
                    'זוהה אזכור לרישוי זמין אך ללא אינדיקציה ברורה לטופס החלטה.'
                    if rishuy_weak_ids
                    else 'לא זוהה טופס החלטה מרישוי זמין.'
                )
            ),
            evidence=(rishuy_ids or rishuy_weak_ids)[:10],
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
    if mamad_scale_ids:
        mamad_status = PreflightStatus.PASSED
    elif mamad_ids:
        mamad_status = PreflightStatus.FAILED if strict else PreflightStatus.WARNING
    else:
        mamad_status = PreflightStatus.FAILED if strict else PreflightStatus.WARNING
    checks.append(
        _mk_result(
            check_id="PF-07",
            title='קיימת תוכנית/פרט למרחב המוגן (1:50)',
            pages=[8, 9, 10],
            status=mamad_status,
            details=(
                'זוהה סגמנט מרחב מוגן עם קנ"מ 1:50.'
                if mamad_scale_ids
                else (
                    'זוהה סגמנט שמזכיר מרחב מוגן, אך ללא אינדיקציה לקנ"מ 1:50.'
                    if mamad_ids
                    else 'לא זוהה בוודאות סגמנט מרחב מוגן. מומלץ לוודא שסימנת/קראת שם לסגמנט הממ"ד.'
                )
            ),
            evidence=(mamad_scale_ids or mamad_ids)[:10],
        )
    )

    # PF-08: minimal markings (dimensions present in analysis)
    any_dims = any(_has_any_dimension(seg) for seg in approved_segments)
    dims_status = PreflightStatus.PASSED if any_dims else (PreflightStatus.FAILED if strict else PreflightStatus.WARNING)
    checks.append(
        _mk_result(
            check_id="PF-08",
            title='קיימים סימוני מידות/נתונים מינימליים (Best-effort)',
            pages=[7, 9, 10],
            status=dims_status,
            details='המערכת זיהתה לפחות מימד אחד/סימון מידה בסגמנטים.' if any_dims else 'לא זוהו מימדים מתוך ניתוח קיים. אם זה מסמך סרוק/לא קריא, ייתכן שצריך לבחור סגמנט אחר או להריץ ניתוח.',
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
    area_status = PreflightStatus.PASSED if area_ids else (PreflightStatus.WARNING if area_weak_ids else (PreflightStatus.WARNING if not strict else PreflightStatus.FAILED))
    checks.append(
        _mk_result(
            check_id="PF-09",
            title='קיימת טבלת חישוב שטחי מיגון (אם נדרש)',
            pages=[8],
            status=area_status,
            details=(
                'נמצאה טבלת שטחים עם ערכי מ\"ר.'
                if area_ids
                else ('זוהתה טבלת שטחים ללא ערכים ברורים.' if area_weak_ids else 'לא זוהתה טבלת שטחים. אם לא הועלתה עדיין טבלת שטחי מיגון – מומלץ להוסיף.')
            ),
            evidence=(area_ids or area_weak_ids)[:10],
        )
    )

    # PF-10: legend / verbal definitions
    legend_like = by_type.get(SegmentType.LEGEND, []) + _find_segments_by_keywords(approved_segments, "legend")
    legend_strong = [s for s in legend_like if _match_keywords(_segment_text_corpus(s), _HEBREW_KEYWORDS["legend"])]
    legend_ids = list({str(s.get("segment_id")) for s in legend_strong if s.get("segment_id")})
    legend_weak_ids = list({str(s.get("segment_id")) for s in legend_like if s.get("segment_id")})
    legend_status = PreflightStatus.PASSED if legend_ids else (PreflightStatus.WARNING if legend_weak_ids else (PreflightStatus.WARNING if not strict else PreflightStatus.FAILED))
    checks.append(
        _mk_result(
            check_id="PF-10",
            title='קיים מקרא/טבלת הגדרות לרכיבי המרחב המוגן',
            pages=[10, 11],
            status=legend_status,
            details=(
                'זוהה מקרא/טבלת הגדרות עם טקסט מזוהה.'
                if legend_ids
                else ('זוהה סגמנט מקרא ללא טקסט מזוהה.' if legend_weak_ids else 'לא זוהה מקרא/טבלת הגדרות. מומלץ לכלול מקרא/טבלת רכיבים כנדרש במסמך.')
            ),
            evidence=(legend_ids or legend_weak_ids)[:10],
        )
    )

    # PF-11: wall reduction plan
    wall_red_like = _find_segments_by_keywords(approved_segments, "wall_reduction")
    wall_red_ids = list({str(s.get("segment_id")) for s in wall_red_like if s.get("segment_id")})
    checks.append(
        _mk_result(
            check_id="PF-11",
            title='קיימת תכנית/חישוב ירידת קירות (אם רלוונטי)',
            pages=[12],
            status=PreflightStatus.PASSED if wall_red_ids else PreflightStatus.NOT_APPLICABLE,
            details='זוהתה תכנית ירידת קירות.' if wall_red_ids else 'לא זוהתה תכנית ירידת קירות (ייתכן שלא רלוונטי להגשה זו).',
            evidence=wall_red_ids[:10],
        )
    )

    # PF-12: structural details (require rebar signals or analysis evidence)
    structural_like = _find_segments_by_keywords(approved_segments, "structural")
    structural_signal = any(_has_structural_signal(seg) for seg in approved_segments)
    structural_strong = [s for s in structural_like if _has_rebar_signal(_segment_text_corpus(s))]
    structural_ids = list({str(s.get("segment_id")) for s in structural_strong if s.get("segment_id")})
    struct_ok = bool(structural_ids) or structural_signal
    struct_status = (
        PreflightStatus.PASSED if struct_ok
        else (PreflightStatus.FAILED if strict else PreflightStatus.WARNING)
    )
    checks.append(
        _mk_result(
            check_id="PF-12",
            title='קיימים פרטים הנדסיים (זיון/ריתום/פתחים) (Best-effort)',
            pages=[14, 15, 16],
            status=struct_status,
            details=(
                'זוהו פרטים הנדסיים עם אינדיקציות זיון/ברזל.'
                if struct_ok
                else 'לא זוהו פרטים הנדסיים. מומלץ להוסיף סגמנט עם פרטי זיון/ריתום/פתחים כנדרש.'
            ),
            evidence=structural_ids[:10],
            debug={"analysis_signal": structural_signal},
        )
    )

    # Gate: any FAILED check fails the preflight.
    passed = not any(c.status in (PreflightStatus.FAILED, PreflightStatus.ERROR) for c in checks)
    return passed, checks
