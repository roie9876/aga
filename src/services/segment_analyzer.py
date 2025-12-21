"""Service for analyzing individual plan segments using GPT-5.1."""
import asyncio
import base64
import json
import subprocess
import tempfile
from collections import OrderedDict
from typing import Dict, Any, Optional, List
from io import BytesIO

from PIL import Image

from src.azure import get_openai_client, get_blob_client
from src.config import settings
from src.utils.logging import get_logger

logger = get_logger(__name__)


class SegmentAnalyzer:
    """Analyzes architectural plan segments to extract detailed information."""
    
    def __init__(self):
        """Initialize the segment analyzer."""
        self.openai_client = get_openai_client()
        self.blob_client = get_blob_client()

        # Global throttles (per process) to keep parallel work safe and stable.
        self._llm_semaphore = asyncio.Semaphore(
            max(1, int(getattr(settings, "validation_max_concurrent_llm_requests", 4)))
        )
        self._download_semaphore = asyncio.Semaphore(
            max(1, int(getattr(settings, "validation_max_concurrent_downloads", 12)))
        )

        # Small bounded cache to avoid re-downloading the same segment image multiple
        # times within the same request (base analysis + multiple focused passes).
        self._image_cache_max_items = max(
            0, int(getattr(settings, "segment_image_cache_max_items", 32))
        )
        self._image_cache: "OrderedDict[str, bytes]" = OrderedDict()
        self._image_cache_lock = asyncio.Lock()

        logger.info("SegmentAnalyzer initialized")
    
    async def analyze_segment(
        self,
        segment_id: str,
        segment_blob_url: str,
        segment_type: str,
        segment_description: str
    ) -> Dict[str, Any]:
        """Analyze a single segment to extract all information.
        
        Args:
            segment_id: Segment identifier
            segment_blob_url: URL to cropped segment image in blob storage
            segment_type: Type of segment (floor_plan, section, detail, etc.)
            segment_description: Brief description of segment
            
        Returns:
            Dictionary with extracted data including text, dimensions, elements
        """
        logger.info("Analyzing segment",
                   segment_id=segment_id,
                   type=segment_type)
        
        try:
            # 1. Download segment image from blob storage
            image_bytes = await self._download_segment_image(segment_blob_url)

            # 1b. OCR pass for scanned/bitmap-heavy documents (best-effort).
            ocr_items = self._run_ocr(image_bytes)
            
            # 2. Analyze with GPT-5.1
            extracted_data = await self._analyze_with_gpt(
                image_bytes=image_bytes,
                segment_type=segment_type,
                segment_description=segment_description
            )

            if ocr_items:
                existing = extracted_data.get("text_items")
                if not isinstance(existing, list):
                    existing = []
                merged = self._merge_text_items(existing, ocr_items)
                extracted_data["text_items"] = merged
                extracted_data.setdefault("ocr_text_items", ocr_items)
            
            logger.info("Segment analysis complete",
                       segment_id=segment_id,
                       text_items=len(extracted_data.get("text_items", [])),
                       dimensions_found=len(extracted_data.get("dimensions", [])))
            
            return {
                "segment_id": segment_id,
                "status": "analyzed",
                "analysis_data": extracted_data  # Wrap in analysis_data key
            }
            
        except Exception as e:
            logger.error("Segment analysis failed",
                        segment_id=segment_id,
                        error=str(e))
            return {
                "segment_id": segment_id,
                "status": "error",
                "error": str(e)
            }

    def _run_ocr(self, image_bytes: bytes) -> List[Dict[str, str]]:
        """Run OCR on image bytes using Tesseract (best-effort)."""
        if not getattr(settings, "ocr_enabled", True):
            return []

        ocr_cmd = str(getattr(settings, "ocr_tesseract_cmd", "tesseract"))
        ocr_langs = str(getattr(settings, "ocr_languages", "heb+eng")).strip() or "eng"
        ocr_psm = str(getattr(settings, "ocr_psm", 6))
        ocr_oem = str(getattr(settings, "ocr_oem", 1))

        try:
            with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
                with Image.open(BytesIO(image_bytes)) as img:
                    img = img.convert("RGB")
                    img.save(tmp.name, format="PNG")

                cmd = [
                    ocr_cmd,
                    tmp.name,
                    "stdout",
                    "-l",
                    ocr_langs,
                    "--oem",
                    ocr_oem,
                    "--psm",
                    ocr_psm,
                ]
                try:
                    result = subprocess.run(
                        cmd,
                        check=True,
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )
                    text = result.stdout or ""
                except subprocess.CalledProcessError as e:
                    logger.info("OCR failed; retrying with English only", error=str(e))
                    cmd = [
                        ocr_cmd,
                        tmp.name,
                        "stdout",
                        "-l",
                        "eng",
                        "--oem",
                        ocr_oem,
                        "--psm",
                        ocr_psm,
                    ]
                    result = subprocess.run(
                        cmd,
                        check=True,
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )
                    text = result.stdout or ""
        except Exception as e:
            logger.info("OCR failed; continuing without OCR", error=str(e))
            return []

        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if not lines:
            return []

        items: List[Dict[str, str]] = []
        for line in lines[:200]:
            items.append(
                {
                    "text": line,
                    "language": "hebrew" if self._contains_hebrew(line) else "english",
                    "type": "note",
                }
            )
        return items

    def _merge_text_items(
        self, existing: List[Dict[str, Any]], ocr_items: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        seen = set()
        merged: List[Dict[str, Any]] = []
        for item in existing + ocr_items:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
        return merged

    def _contains_hebrew(self, text: str) -> bool:
        return any("\u0590" <= ch <= "\u05FF" for ch in text)

    def _crop_image_bytes_by_bbox_with_padding(
        self,
        *,
        image_bytes: bytes,
        bbox: Dict[str, Any],
        pad_ratio: float,
    ) -> bytes:
        """Crop image bytes by bbox (pixels or percentages) with padding.

        `bbox` may be in percent (0-100) or pixels; we treat values >100 as pixels.
        """
        x_val = float(bbox.get("x", 0.0))
        y_val = float(bbox.get("y", 0.0))
        w_val = float(bbox.get("width", 100.0))
        h_val = float(bbox.get("height", 100.0))

        use_pixels = any(v > 100.0 for v in [x_val, y_val, w_val, h_val])

        with Image.open(BytesIO(image_bytes)) as img:
            img_width, img_height = img.size
            if use_pixels:
                left = x_val
                top = y_val
                right = x_val + w_val
                bottom = y_val + h_val
            else:
                left = (x_val / 100.0) * img_width
                top = (y_val / 100.0) * img_height
                right = ((x_val + w_val) / 100.0) * img_width
                bottom = ((y_val + h_val) / 100.0) * img_height

            pad_x = (right - left) * max(0.0, pad_ratio)
            pad_y = (bottom - top) * max(0.0, pad_ratio)

            left_i = int(max(0, left - pad_x))
            top_i = int(max(0, top - pad_y))
            right_i = int(min(img_width, right + pad_x))
            bottom_i = int(min(img_height, bottom + pad_y))

            right_i = max(left_i + 1, right_i)
            bottom_i = max(top_i + 1, bottom_i)

            cropped = img.crop((left_i, top_i, right_i, bottom_i))
            buf = BytesIO()
            cropped.save(buf, format="PNG")
            return buf.getvalue()

    def _resize_image_bytes_max_side(self, *, image_bytes: bytes, max_side_px: int) -> bytes:
        """Resize image bytes so the larger side is <= max_side_px (keeps aspect ratio)."""
        if max_side_px <= 0:
            return image_bytes
        with Image.open(BytesIO(image_bytes)) as img:
            width, height = img.size
            max_side = max(width, height)
            if max_side <= max_side_px:
                return image_bytes

            scale = float(max_side_px) / float(max_side)
            new_w = max(1, int(width * scale))
            new_h = max(1, int(height * scale))
            resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            buf = BytesIO()
            resized.save(buf, format="PNG")
            return buf.getvalue()

    async def _locate_mamad_roi_in_floor_plan(
        self,
        *,
        floor_plan_bytes: bytes,
        mamad_bytes: bytes,
        floor_plan_description: str,
        mamad_segment_description: str,
    ) -> Optional[Dict[str, Any]]:
        """Try to locate the ממ"ד room ROI in the floor plan as a percent bbox.

        Returns a bbox dict: {x,y,width,height,confidence,notes} in PERCENT (0-100),
        or None if not found.
        """
        # Use a downscaled floor plan for the locator pass to reduce tokens.
        locator_floor_plan = self._resize_image_bytes_max_side(
            image_bytes=floor_plan_bytes,
            max_side_px=2048,
        )

        prompt_text = f"""You are a strict locator for Israeli architectural plans.
Return ONLY valid JSON. No markdown. No explanations.

Task: Locate the ממ\"ד (mamad) room in the FLOOR PLAN.

Inputs:
- Image #1: FLOOR PLAN (may be zoomed-out)
- Image #2: MAMAD reference/detail crop (helps match geometry/labels)

Floor plan description: {floor_plan_description}
MAMAD reference description: {mamad_segment_description}

Guidance:
- The word ממ\"ד / ממד may be very small in the floor plan. If you can read it, use it.
- If you cannot read the label, try to match the room by geometry / adjacent walls / openings relative to the reference crop.
- If you are not confident, return null with confidence < 0.5.

Return JSON:
{{
  "mamad_roi": {{"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0, "confidence": 0.0, "notes": "brief"}},
  "evidence": ["short evidence strings"]
}}"""

        extracted = await self._run_focused_extraction(
            image_bytes_list=[locator_floor_plan, mamad_bytes],
            prompt_text=prompt_text,
        )
        if not isinstance(extracted, dict):
            return None
        roi = extracted.get("mamad_roi")
        if not isinstance(roi, dict):
            return None

        try:
            x = float(roi.get("x"))
            y = float(roi.get("y"))
            w = float(roi.get("width"))
            h = float(roi.get("height"))
            conf = float(roi.get("confidence") or 0.0)
        except Exception:
            return None

        if conf < 0.45:
            return None
        if w <= 0 or h <= 0:
            return None
        if not (0.0 <= x <= 100.0 and 0.0 <= y <= 100.0 and 0.0 < w <= 100.0 and 0.0 < h <= 100.0):
            return None
        # Clamp bbox to image bounds
        if x + w > 100.0:
            w = max(0.1, 100.0 - x)
        if y + h > 100.0:
            h = max(0.1, 100.0 - y)

        return {
            "x": x,
            "y": y,
            "width": w,
            "height": h,
            "confidence": conf,
            "notes": str(roi.get("notes") or ""),
        }

    def _build_user_message_with_images(
        self,
        *,
        prompt_text: str,
        image_bytes_list: List[bytes],
    ) -> List[Dict[str, Any]]:
        content: List[Dict[str, Any]] = [{"type": "text", "text": prompt_text}]
        for img_bytes in image_bytes_list:
            img_b64 = base64.b64encode(img_bytes).decode("utf-8")
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{img_b64}"},
                }
            )
        return content

    async def _run_focused_extraction(
        self,
        *,
        image_bytes_list: List[bytes],
        prompt_text: str,
    ) -> Dict[str, Any]:
        """Run a focused GPT pass and parse JSON response."""
        async with self._llm_semaphore:
            response = await asyncio.to_thread(
                self.openai_client.chat_completions_create,
                model=settings.azure_openai_deployment_name,
                messages=[
                    {
                        "role": "user",
                        "content": self._build_user_message_with_images(
                            prompt_text=prompt_text,
                            image_bytes_list=image_bytes_list,
                        ),
                    }
                ],
            )
        content = response.choices[0].message.content
        extracted = self._parse_gpt_response(content)
        if response.usage:
            extracted["tokens_used"] = response.usage.total_tokens
        return extracted

    async def extract_door_spacing(
        self,
        *,
        segment_id: str,
        segment_blob_url: str,
        segment_type: str,
        segment_description: str,
        full_plan_blob_url: Optional[str] = None,
        segment_bbox: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Focused extractor for Requirement 3.1 (door clearances)."""
        logger.info("Running focused door-spacing extraction", segment_id=segment_id)

        detail_bytes = await self._download_segment_image(segment_blob_url)

        image_bytes_list: List[bytes] = [detail_bytes]
        if full_plan_blob_url and isinstance(segment_bbox, dict) and segment_bbox:
            try:
                full_plan_bytes = await self._download_segment_image(full_plan_blob_url)
                context_crop_bytes = self._crop_image_bytes_by_bbox_with_padding(
                    image_bytes=full_plan_bytes,
                    bbox=segment_bbox,
                    pad_ratio=1.0,
                )
                image_bytes_list = [context_crop_bytes, detail_bytes]
            except Exception as e:
                logger.info(
                    "Failed to build door-spacing context crop; continuing without context",
                    segment_id=segment_id,
                    error=str(e),
                )

        prompt_text = f"""You are a strict extractor for Israeli ממ"ד requirements.
Return ONLY valid JSON. No markdown. No explanations.

Task: Extract door-to-perpendicular-wall clearances for Requirement 3.1.

Input:
- Segment Type: {segment_type}
- Description: {segment_description}

If TWO images are provided:
- Image #1 is a zoomed-out CONTEXT crop (helps infer inside/outside of the ממ"ד).
- Image #2 is the zoomed-in DETAIL crop (use this to read dimensions precisely).
If only ONE image is provided, it is the DETAIL.

Return JSON with this shape:
{{
  "door_spacing_focus": {{
    "doors": [
      {{
        "internal_clearance_cm": 0.0,
        "external_clearance_cm": 0.0,
        "confidence": 0.0,
        "location": "short description",
        "evidence": ["short evidence strings of what you saw (dimension text / arrows / labels)"]
      }}
    ],
    "door_inside_outside_hint": "optional hebrew hint"
  }},
  "door_roi": {{"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0, "confidence": 0.0, "notes": "brief"}}
}}

Rules:
- Units: if not specified in the drawing, assume centimeters (cm).
- If you cannot find clearances, still return one door object with null values and confidence < 0.5 and explain in evidence.
- ROI coords are PERCENT (0-100) relative to the DETAIL image."""

        extracted = await self._run_focused_extraction(
            image_bytes_list=image_bytes_list,
            prompt_text=prompt_text,
        )
        if not isinstance(extracted, dict):
            return {"door_spacing_focus": {"doors": []}}

        return {
            "door_spacing_focus": extracted.get("door_spacing_focus"),
            "door_roi": extracted.get("door_roi"),
        }

    async def extract_wall_thickness(
        self,
        *,
        segment_id: str,
        segment_blob_url: str,
        segment_type: str,
        segment_description: str,
    ) -> Dict[str, Any]:
        """Focused extractor for wall thickness (Requirement 1.2)."""
        logger.info("Running focused wall-thickness extraction", segment_id=segment_id)
        image_bytes = await self._download_segment_image(segment_blob_url)

        prompt_text = f"""Return ONLY valid JSON.

Extract wall thickness measurements from this segment.

Segment Type: {segment_type}
Description: {segment_description}

Return JSON:
{{
  "wall_thickness_focus": {{
    "walls": [
      {{
        "thickness_cm": 0.0,
        "confidence": 0.0,
        "location": "short description",
        "evidence": ["evidence strings"]
      }}
    ]
  }},
  "wall_roi": {{"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0, "confidence": 0.0, "notes": "brief"}}
}}

Rules:
- If units are absent, assume cm.
- If unsure, include best candidates with confidence < 0.7."""

        extracted = await self._run_focused_extraction(
            image_bytes_list=[image_bytes],
            prompt_text=prompt_text,
        )
        if not isinstance(extracted, dict):
            return {"wall_thickness_focus": {"walls": []}}
        return {
            "wall_thickness_focus": extracted.get("wall_thickness_focus"),
            "wall_roi": extracted.get("wall_roi"),
        }

    async def extract_room_height(
        self,
        *,
        segment_id: str,
        segment_blob_url: str,
        segment_type: str,
        segment_description: str,
    ) -> Dict[str, Any]:
        """Focused extractor for room height (Requirements 2.1/2.2)."""
        logger.info("Running focused room-height extraction", segment_id=segment_id)
        image_bytes = await self._download_segment_image(segment_blob_url)

        prompt_text = f"""You are a strict extractor for Israeli ממ"ד validation.
Return ONLY valid JSON. No markdown. No explanations.

Task: Extract the Mamad ROOM/CEILING height (Requirement 2.1/2.2).

Segment Type: {segment_type}
Description: {segment_description}

CRITICAL RULES (to avoid false failures):
- Only return a height if it is explicitly the ROOM/CEILING height of the ממ"ד (e.g., mentions "גובה חדר", "גובה תקרה", "תקרה", or clearly indicates the room height).
- Do NOT treat generic "H=..." markers as room height unless the surrounding text clearly indicates it's the room/ceiling height.
- Do NOT return sill/opening/installation heights (e.g., window sill "אדן", door jamb "משקוף", "חלון", "דלת").
- If you cannot be sure the height is the Mamad room/ceiling height, return one item with null height_m and confidence < 0.5, and explain why in evidence.

Return JSON:
{{
    "room_height_focus": {{
        "heights": [
            {{
                "height_m": null,
                "confidence": 0.0,
                "location": "Describe WHAT the height refers to (e.g., 'גובה תקרה בחלל הממ\"ד', 'גובה אדן חלון', 'גובה משקוף דלת')",
                "evidence": ["Short evidence strings (exact text you saw, like 'גובה תקרה 2.40', NOT guesses)"]
            }}
        ]
    }},
    "height_roi": {{"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0, "confidence": 0.0, "notes": "brief"}}
}}

Units:
- Prefer meters. Convert cm to meters if needed."""

        extracted = await self._run_focused_extraction(
            image_bytes_list=[image_bytes],
            prompt_text=prompt_text,
        )
        if not isinstance(extracted, dict):
            return {"room_height_focus": {"heights": []}}
        return {
            "room_height_focus": extracted.get("room_height_focus"),
            "height_roi": extracted.get("height_roi"),
        }

    async def extract_window_spacing(
        self,
        *,
        segment_id: str,
        segment_blob_url: str,
        segment_type: str,
        segment_description: str,
    ) -> Dict[str, Any]:
        """Focused extractor for window spacing (Requirement 3.2)."""
        logger.info("Running focused window-spacing extraction", segment_id=segment_id)
        image_bytes = await self._download_segment_image(segment_blob_url)

        prompt_text = f"""You are a strict extractor for Israeli ממ"ד requirements.
Return ONLY valid JSON. No markdown. No explanations.

Task: Extract window (חלון הדף) spacing evidence for Requirement 3.2, aligned with the architectural guide.

Segment Type: {segment_type}
Description: {segment_description}

Requirement 3.2 subchecks (extract what you can):
1) Distance between sliding niches (מרחק בין נישות גרירה): >= 20 cm
2) Distance between light openings (מרחק בין פתחי אור): >= 100 cm
3) Distance from blast window to perpendicular wall (מרחק חלון הדף מקיר ניצב): >= 20 cm
4) If window and door are on the SAME wall: separation >= door height, OR a 20cm concrete wall exists between the openings.

Return JSON with this shape:
{{
    "window_spacing_focus": {{
        "windows": [
            {{
                "niche_to_niche_cm": null,
                "light_openings_spacing_cm": null,
                "to_perpendicular_wall_cm": null,
                "same_wall_door_separation_cm": null,
                "door_height_cm": null,
                "has_concrete_wall_between_openings": null,
                "concrete_wall_thickness_cm": null,
                "confidence": 0.0,
                "location": "short description",
                "evidence": ["short evidence strings of what you saw (dimension text / arrows / labels)"]
            }}
        ],
        "notes": "brief"
    }},
    "window_roi": {{"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0, "confidence": 0.0, "notes": "brief"}}
}}

Rules:
- Units: if not specified in the drawing, assume centimeters (cm).
- Extract numeric values as numbers (not strings).
- If the segment includes multiple windows/openings, include multiple objects.
- If you cannot find ANY numeric spacing values, still return one object with all null values and confidence < 0.5,
    and put your best evidence strings (e.g., labels you saw) in evidence.
- ROI coords are PERCENT (0-100) relative to the image."""

        try:
            extracted = await self._run_focused_extraction(
                image_bytes_list=[image_bytes],
                prompt_text=prompt_text,
            )
        except Exception as e:
            # Evidence-first fallback: if the focused pass is unavailable (e.g., 429 NoCapacity),
            # return a low-confidence payload instead of raising.
            msg = str(e)
            if len(msg) > 240:
                msg = msg[:240] + "..."
            logger.warning(
                "Focused window-spacing extraction failed; returning fallback",
                segment_id=segment_id,
                error=msg,
            )
            return {
                "window_spacing_focus": {
                    "windows": [
                        {
                            "niche_to_niche_cm": None,
                            "light_openings_spacing_cm": None,
                            "to_perpendicular_wall_cm": None,
                            "same_wall_door_separation_cm": None,
                            "door_height_cm": None,
                            "has_concrete_wall_between_openings": None,
                            "concrete_wall_thickness_cm": None,
                            "confidence": 0.0,
                            "location": "",
                            "evidence": [
                                "Focused window-spacing extraction unavailable (likely temporary capacity).",
                                f"error: {msg}",
                            ],
                        }
                    ],
                    "notes": "focus_unavailable",
                },
                "window_roi": {
                    "x": 0.0,
                    "y": 0.0,
                    "width": 0.0,
                    "height": 0.0,
                    "confidence": 0.0,
                    "notes": "focus_unavailable",
                },
            }

        if not isinstance(extracted, dict):
            return {"window_spacing_focus": {"windows": [], "evidence_texts": []}}
        return {
            "window_spacing_focus": extracted.get("window_spacing_focus"),
            "window_roi": extracted.get("window_roi"),
        }

    async def extract_materials_specs(
        self,
        *,
        segment_id: str,
        segment_blob_url: str,
        segment_type: str,
        segment_description: str,
    ) -> Dict[str, Any]:
        """Focused extractor for materials specs (Requirements 6.1/6.2)."""
        logger.info("Running focused materials extraction", segment_id=segment_id)
        image_bytes = await self._download_segment_image(segment_blob_url)

        prompt_text = f"""Return ONLY valid JSON.

Extract materials specifications relevant to a ממ"ד (e.g., concrete grade, steel grade, notes).

Segment Type: {segment_type}
Description: {segment_description}

Return JSON:
{{
  "materials_focus": {{
    "materials": [
      {{"type": "concrete|steel|other", "grade": "...", "notes": "...", "confidence": 0.0, "evidence": ["..."]}}
    ]
  }},
  "materials_roi": {{"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0, "confidence": 0.0, "notes": "brief"}}
}}"""

        extracted = await self._run_focused_extraction(
            image_bytes_list=[image_bytes],
            prompt_text=prompt_text,
        )
        if not isinstance(extracted, dict):
            return {"materials_focus": {"materials": []}}
        return {
            "materials_focus": extracted.get("materials_focus"),
            "materials_roi": extracted.get("materials_roi"),
        }

    async def extract_rebar_specs(
        self,
        *,
        segment_id: str,
        segment_blob_url: str,
        segment_type: str,
        segment_description: str,
    ) -> Dict[str, Any]:
        """Focused extractor for rebar specs (Requirement 6.3)."""
        logger.info("Running focused rebar extraction", segment_id=segment_id)
        image_bytes = await self._download_segment_image(segment_blob_url)

        prompt_text = f"""Return ONLY valid JSON.

Extract rebar / reinforcement spacing details relevant to a ממ"ד.

Segment Type: {segment_type}
Description: {segment_description}

Return JSON:
{{
  "rebar_focus": {{
    "rebars": [
      {{"spacing_cm": 0.0, "location": "...", "confidence": 0.0, "evidence": ["..."]}}
    ]
  }},
  "rebar_roi": {{"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0, "confidence": 0.0, "notes": "brief"}}
}}"""

        extracted = await self._run_focused_extraction(
            image_bytes_list=[image_bytes],
            prompt_text=prompt_text,
        )
        if not isinstance(extracted, dict):
            return {"rebar_focus": {"rebars": []}}
        return {
            "rebar_focus": extracted.get("rebar_focus"),
            "rebar_roi": extracted.get("rebar_roi"),
        }

    async def extract_general_notes(
        self,
        *,
        segment_id: str,
        segment_blob_url: str,
        segment_type: str,
        segment_description: str,
    ) -> Dict[str, Any]:
        """Focused extractor for general notes (e.g., Requirement 4.2).

        This is intentionally shallow: it extracts key evidence strings.
        """
        logger.info("Running focused notes extraction", segment_id=segment_id)
        image_bytes = await self._download_segment_image(segment_blob_url)

        prompt_text = f"""Return ONLY valid JSON.

Extract general notes / annotations that might be relevant to ממ"ד compliance.

Segment Type: {segment_type}
Description: {segment_description}

Return JSON:
{{
  "notes_focus": {{
    "evidence_texts": ["..."],
    "confidence": 0.0,
    "notes": "brief"
  }},
  "notes_roi": {{"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0, "confidence": 0.0, "notes": "brief"}}
}}"""

        extracted = await self._run_focused_extraction(
            image_bytes_list=[image_bytes],
            prompt_text=prompt_text,
        )
        if not isinstance(extracted, dict):
            return {"notes_focus": {"evidence_texts": []}}
        return {
            "notes_focus": extracted.get("notes_focus"),
            "notes_roi": extracted.get("notes_roi"),
        }

    async def infer_mamad_external_wall_count(
        self,
        *,
        floor_plan_blob_url: str,
        floor_plan_description: str,
        mamad_segment_blob_url: str,
        mamad_segment_description: str,
    ) -> Dict[str, Any]:
        """Infer the number of external walls of the ממ"ד from a floor plan + a MAMAD reference crop.

        This exists because many wall-thickness/detail crops do not include enough context
        to determine whether a wall is internal vs. external; the floor plan provides
        the building envelope context.
        """
        logger.info(
            "Running focused external-wall-count inference",
            floor_plan_description=floor_plan_description,
            mamad_description=mamad_segment_description,
        )

        floor_plan_bytes = await self._download_segment_image(floor_plan_blob_url)
        mamad_bytes = await self._download_segment_image(mamad_segment_blob_url)

        # Two-step improvement:
        # 1) Locate MAMAD ROI on a downscaled floor plan using the MAMAD reference.
        # 2) Crop the ORIGINAL floor plan around that ROI (zoomed context + zoomed detail)
        #    so small labels ("ממ\"ד") become readable.
        roi = None
        try:
            roi = await self._locate_mamad_roi_in_floor_plan(
                floor_plan_bytes=floor_plan_bytes,
                mamad_bytes=mamad_bytes,
                floor_plan_description=floor_plan_description,
                mamad_segment_description=mamad_segment_description,
            )
        except Exception as e:
            logger.info("MAMAD ROI locator failed; falling back to single-pass inference", error=str(e))
            roi = None

        if isinstance(roi, dict):
            try:
                detail_crop = self._crop_image_bytes_by_bbox_with_padding(
                    image_bytes=floor_plan_bytes,
                    bbox=roi,
                    pad_ratio=0.35,
                )
                context_crop = self._crop_image_bytes_by_bbox_with_padding(
                    image_bytes=floor_plan_bytes,
                    bbox=roi,
                    pad_ratio=1.5,
                )

                prompt_text = f"""You are a strict extractor for Israeli ממ\"ד validation.
Return ONLY valid JSON. No markdown. No explanations.

Task: Determine how many walls of the ממ\"ד are EXTERNAL (touch the outside/facade of the building) vs INTERNAL.

Inputs:
- Image #1: FLOOR PLAN context crop (zoomed around the ממ\"ד area; includes nearby building envelope)
- Image #2: FLOOR PLAN detail crop (tighter zoom; should make small labels readable)
- Image #3: MAMAD DETAIL / reference (helps confirm you're looking at the correct room)

Floor plan description: {floor_plan_description}
MAMAD reference description: {mamad_segment_description}

Rules:
- External wall = a wall segment of the ממ\"ד that borders the outside/facade (the building envelope) in the floor plan.
- Internal wall = borders interior spaces (other rooms, corridor, shafts) in the floor plan.
- Count TOTAL external walls of the ממ\"ד as an integer in [1..4].
- If you cannot determine confidently from these images, return null and set confidence < 0.6.

Return JSON:
{{
  "external_wall_count": null,
  "internal_wall_count": null,
  "external_sides_hint": ["left", "right", "top", "bottom"],
  "confidence": 0.0,
  "evidence": ["short evidence strings (what you saw)"]
}}"""

                extracted = await self._run_focused_extraction(
                    image_bytes_list=[context_crop, detail_crop, mamad_bytes],
                    prompt_text=prompt_text,
                )
            except Exception as e:
                logger.info(
                    "High-res ROI inference failed; falling back to single-pass inference",
                    error=str(e),
                )
                extracted = None
        else:
            extracted = None

        if extracted is None:
            prompt_text = f"""You are a strict extractor for Israeli ממ\"ד validation.
Return ONLY valid JSON. No markdown. No explanations.

Task: Determine how many walls of the ממ\"ד are EXTERNAL (touch the outside/facade of the building) vs INTERNAL.

Inputs:
- Image #1: FLOOR PLAN context (apartment / building outline + room placement)
- Image #2: MAMAD DETAIL / reference (helps you locate the same room in the floor plan)

Floor plan description: {floor_plan_description}
MAMAD reference description: {mamad_segment_description}

Rules:
- External wall = a wall segment of the ממ\"ד that borders the outside/facade (the building envelope) in the floor plan.
- Internal wall = borders interior spaces (other rooms, corridor, shafts) in the floor plan.
- Count TOTAL external walls of the ממ\"ד as an integer in [1..4].
- If you cannot determine confidently from these images, return null and set confidence < 0.6.

Return JSON:
{{
  "external_wall_count": null,
  "internal_wall_count": null,
  "external_sides_hint": ["left", "right", "top", "bottom"],
  "confidence": 0.0,
  "evidence": ["short evidence strings (what you saw)"]
}}"""

            extracted = await self._run_focused_extraction(
                image_bytes_list=[floor_plan_bytes, mamad_bytes],
                prompt_text=prompt_text,
            )
        if not isinstance(extracted, dict):
            return {
                "external_wall_count": None,
                "internal_wall_count": None,
                "external_sides_hint": [],
                "confidence": 0.0,
                "evidence": ["invalid_response"],
            }

        # Normalize for safety
        try:
            count_raw = extracted.get("external_wall_count")
            count = int(count_raw) if count_raw is not None else None
            if count is not None and not (1 <= count <= 4):
                count = None
        except Exception:
            count = None

        extracted["external_wall_count"] = count
        return extracted
    
    async def _download_segment_image(self, blob_url: str) -> bytes:
        """Download segment image from blob storage.
        
        Args:
            blob_url: SAS URL to blob
            
        Returns:
            Image bytes
        """
        if not blob_url:
            raise ValueError("blob_url is required")

        if self._image_cache_max_items > 0:
            async with self._image_cache_lock:
                cached = self._image_cache.get(blob_url)
                if cached is not None:
                    # LRU refresh
                    self._image_cache.move_to_end(blob_url)
                    return cached

        # NOTE: `requests.get` is blocking, so run it in a worker thread.
        import requests

        def _get() -> bytes:
            response = requests.get(blob_url, timeout=60)
            response.raise_for_status()
            return response.content

        async with self._download_semaphore:
            image_bytes = await asyncio.to_thread(_get)

        if self._image_cache_max_items > 0:
            async with self._image_cache_lock:
                self._image_cache[blob_url] = image_bytes
                self._image_cache.move_to_end(blob_url)
                while len(self._image_cache) > self._image_cache_max_items:
                    self._image_cache.popitem(last=False)

        return image_bytes
    
    async def _analyze_with_gpt(
        self,
        image_bytes: bytes,
        segment_type: str,
        segment_description: str
    ) -> Dict[str, Any]:
        """Analyze segment image with GPT-5.1 to extract all information.
        
        Args:
            image_bytes: Cropped segment image
            segment_type: Type of segment
            segment_description: Brief description
            
        Returns:
            Extracted data dictionary
        """
        # Encode image to base64
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
        
        # System prompt for segment classification AND analysis
        system_prompt = """You are an expert architectural plan analyzer specializing in Israeli ממ"ד (bomb shelter) specifications.

Your task has TWO PARTS:
1. **CLASSIFY** what this segment shows (what topic/aspect of the MAMAD)
2. **EXTRACT** all relevant information from the segment

**Classification Categories:**
- WALL_SECTION: Shows wall cross-section with thickness, materials, rebar
- ROOM_LAYOUT: Shows room dimensions, floor plan layout
- DOOR_DETAILS: Shows door specifications, spacing, dimensions
- WINDOW_DETAILS: Shows window specifications, spacing, dimensions  
- REBAR_DETAILS: Shows reinforcement specifications, spacing, layout
- MATERIALS_SPECS: Shows concrete grades, steel types, material specifications
- GENERAL_NOTES: Shows general notes, ventilation requirements, standards
- SECTIONS: Shows vertical sections with heights, elevations
- OTHER: Doesn't fit above categories

**Be thorough and precise.**"""

        user_prompt = f"""Analyze this architectural drawing segment.

**Segment Type:** {segment_type}
**Description:** {segment_description}

**STEP 1: CLASSIFY THIS SEGMENT**
What does this segment primarily show? Choose ONE or MORE categories:
- WALL_SECTION, ROOM_LAYOUT, DOOR_DETAILS, WINDOW_DETAILS, REBAR_DETAILS, MATERIALS_SPECS, GENERAL_NOTES, SECTIONS, OTHER

Additionally, determine the **VIEW TYPE**:
- top_view: floor plan / looking from above (you can often see door swing arcs and window opening direction)
- side_section: vertical section / cut view showing heights/elevations
- unknown: unclear from this crop

**IMPORTANT: Write the description in HEBREW (עברית)!**

**STEP 2: EXTRACT ALL RELEVANT INFORMATION:**

**IMPORTANT (SAFETY):**
- Do NOT reveal private chain-of-thought or step-by-step hidden reasoning.
- You MAY provide a short, user-facing explanation summary (in Hebrew) of what you saw and why you classified it.

**CRITICAL: Return ONLY valid JSON. NO comments (//) allowed in JSON!**

1. **Text Content:**
   - List EVERY piece of text you see (Hebrew and English)
   - Include labels, titles, notes, annotations
   - Preserve original language

2. **Dimensions & Measurements:**
   - All measurements with units (cm, mm, m)
   - Wall thickness measurements
   - Room dimensions (length × width × height)
   - Door/window dimensions
   - Spacing between elements
   - Elevation heights

   **MAMAD plan (קנ"מ 1:50) rule (IMPORTANT):**
   - If this segment shows a ממ"ד plan/detail at scale 1:50, extract the **internal length and width**
     of the ממ"ד (from dimension lines inside the room).
   - Record them in `dimensions[]` with elements like:
     - "mamad room length" / "אורך ממ\"ד פנימי"
     - "mamad room width" / "רוחב ממ\"ד פנימי"
   - If units are not specified, assume **centimeters (cm)**.
   - Include short evidence strings pointing to the exact numbers you saw.

     **Wall thickness interpretation rule (VERY IMPORTANT):**
     - If you see small dimensions placed directly on/along a wall (or between inner and outer wall lines),
         treat them as **wall thickness** even if the drawing does not explicitly label "עובי".
     - In typical Israeli architectural plans, if units are not written next to the number, you may assume
         **centimeters (cm)** for wall thickness (unless the drawing clearly indicates mm or m elsewhere).
     - Record these as wall thickness in BOTH `dimensions[]` (element: "wall thickness") and
         `structural_elements[]` (type: "wall").
     - Always include `evidence` strings that point to what you saw (e.g., "dimension 25 between wall lines").
     - If there are multiple candidate thickness values, include all with a confidence note rather than omitting.

     **Door spacing interpretation rule (VERY IMPORTANT):**
     - If this segment contains a door (especially a ממ"ד door), actively look for dimension chains near the jamb/door frame.
     - The required values are:
         - **Internal**: distance from the door frame/jamb to the nearest perpendicular wall *inside* the ממ"ד.
         - **External**: distance from the door edge/frame to the nearest perpendicular wall *outside* the ממ"ד.
     - If the drawing shows numeric distances near the door but does not explicitly write units, assume **centimeters (cm)**.
     - Even if you are not 100% sure, include your best candidate values and add a short note in `evidence`.
     - Prefer returning a value rather than saying "not specified" when clear dimension numbers exist near the door.

3. **Structural Elements:**
   - Walls: thickness, material, type
   - Doors: width, height, location, type
     - Windows: width, height, location, type
         - IMPORTANT: If you identify a window, state in `notes` whether it is **sliding** ("נגרר" / "נישת גרירה" / "גרירה")
             or **outward-opening** ("נפתח החוצה" / "כנף" / casement). If unclear, say "לא ברור".
   - Beams: dimensions, material
   - Columns: dimensions, location
   - Slabs: thickness

4. **Rebar & Reinforcement:**
   - Rebar diameter (e.g., Ø12, Ø16)
   - Spacing (e.g., @20cm, @15cm)
   - Location (top/bottom, horizontal/vertical)
   - Quantity and configuration

5. **Materials:**
   - Concrete specifications
   - Steel grades
   - Any material notes

6. **Annotations:**
   - Construction notes
   - Detail references (e.g., "ראה פרט A1")
   - Section markers
   - Dimension lines and leaders

**OUTPUT FORMAT (JSON):**
{{
  "classification": {{
    "primary_category": "WALL_SECTION|ROOM_LAYOUT|DOOR_DETAILS|etc.",
    "secondary_categories": ["...", "..."],
                "view_type": "top_view|side_section|unknown",
        "description": "Brief description of what this segment shows (HEBREW)",
        "confidence": 0.0,
        "explanation_he": "Short user-facing explanation (HEBREW) of why this classification fits",
        "evidence": ["Short pointers to visible cues used (e.g., labels, dimensions, symbols)"],
        "missing_information": ["What is missing in THIS segment for validation"],
        "relevant_requirements": ["1.2", "6.3"]
  }},
  "text_items": [
    {{"text": "...", "language": "hebrew|english", "type": "title|label|note|dimension"}},
    ...
  ],
  "dimensions": [
        {{"value": 20, "unit": "cm", "element": "wall thickness", "location": "קיר חיצוני"}},
    {{"value": 80, "unit": "cm", "element": "door width", "location": "entrance"}},
    ...
  ],
  "structural_elements": [
        {{"type": "wall", "thickness": 20, "unit": "cm", "material": "בטון", "location": "קיר חיצוני|קיר פנימי|לא ברור", "notes": "..."}},
    {{"type": "door", "width": 80, "height": 210, "unit": "cm", "location": "...", "notes": "..."}},
        {{"type": "window", "width": 100, "height": 120, "unit": "cm", "location": "...", "notes": "חלון הדף נגרר / חלון נפתח החוצה / לא ברור"}},
    ...
  ],
  "rebar_details": [
    {{"diameter": 12, "spacing": 20, "unit": "cm", "location": "...", "orientation": "horizontal|vertical", "layer": "top|bottom"}},
    ...
  ],
  "materials": [
    {{"type": "concrete", "grade": "B30", "notes": "..."}},
    {{"type": "steel", "grade": "...", "notes": "..."}}
  ],
  "annotations": [
    {{"text": "...", "type": "construction_note|reference|warning"}},
    ...
  ],
  "summary": {{
    "primary_function": "floor_plan|section|detail|elevation",
    "key_measurements": "Brief summary of critical dimensions",
    "special_notes": "Any important observations"
    }},
    "external_wall_count": null,
    "external_wall_count_after_exceptions": null
}}

**Extra requirement for wall thickness (1.2):**
- When you extract wall thickness, try to label each wall as **קיר חיצוני** or **קיר פנימי** in `structural_elements[].location`.
    - If the wall borders an area explicitly labeled as internal (e.g., "אזור פנימי"), treat it as **קיר פנימי**.
    - If the wall clearly borders the outside/facade or has an exterior window, treat it as **קיר חיצוני**.
    - If you cannot infer reliably, use "לא ברור".
- If (and only if) this segment shows enough context to determine the TOTAL number of external walls of the ממ"ד (1-4), set `external_wall_count` to that number.
    Otherwise set it to null.

**Counting dependency (1.1–1.3 → 1.2):**
- If (and only if) this segment shows enough context to determine the TOTAL number of external walls *after applying the counting exceptions in 1.3* (e.g., wall <2m from exterior line with/without protective wall), set `external_wall_count_after_exceptions`.
    - If you cannot confidently apply the 1.3 exceptions from this segment alone, set it to null.

**IMPORTANT:**
- Extract EVERYTHING visible
- If you're not sure about a measurement, include it with a note
- Preserve Hebrew text exactly as written
- Include units for all measurements
- Be comprehensive - this data will be used for compliance validation"""

        # Call Azure OpenAI deployment configured via AZURE_OPENAI_DEPLOYMENT_NAME.
        # This is a potentially long-running, blocking network call. Run it in a
        # worker thread so the event loop can keep flushing NDJSON stream events.
        try:
            async with self._llm_semaphore:
                response = await asyncio.to_thread(
                    self.openai_client.chat_completions_create,
                    model=settings.azure_openai_deployment_name,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": system_prompt + "\n\n" + user_prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:image/png;base64,{image_base64}"},
                                },
                            ],
                        }
                    ],
                )
            
            content = response.choices[0].message.content
            tokens_used = response.usage.total_tokens if response.usage else 0
            
            logger.info("GPT analysis response received",
                       content_length=len(content),
                       tokens_used=tokens_used)
            
            # Extract JSON from response
            extracted_data = self._parse_gpt_response(content)
            extracted_data["tokens_used"] = tokens_used
            
            return extracted_data
            
        except Exception as e:
            logger.error("GPT analysis failed", error=str(e))
            raise
    
    def _parse_gpt_response(self, content: str) -> Dict[str, Any]:
        """Parse GPT response to extract JSON data.
        
        Args:
            content: GPT response content
            
        Returns:
            Parsed data dictionary
        """
        # Try to find JSON in the response
        # GPT-5.1 might wrap JSON in markdown code blocks
        
        # Remove markdown code blocks if present
        if "```json" in content:
            start = content.find("```json") + 7
            end = content.find("```", start)
            json_str = content[start:end].strip()
        elif "```" in content:
            start = content.find("```") + 3
            end = content.find("```", start)
            json_str = content[start:end].strip()
        else:
            # Try to find JSON object
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                json_str = content[start:end]
            else:
                json_str = content
        
        try:
            data = json.loads(json_str)
            logger.info("Successfully parsed JSON response")
            return data
        except json.JSONDecodeError as e:
            logger.error("Failed to parse JSON from GPT response",
                        error=str(e),
                        content_preview=content[:500])
            # Return minimal structure
            return {
                "text_items": [],
                "dimensions": [],
                "structural_elements": [],
                "rebar_details": [],
                "materials": [],
                "annotations": [],
                "summary": {
                    "primary_function": "unknown",
                    "key_measurements": "Failed to parse",
                    "special_notes": f"Parse error: {str(e)}"
                },
                "raw_response": content[:1000]  # Include first 1000 chars for debugging
            }


# Singleton instance
_segment_analyzer: Optional[SegmentAnalyzer] = None


def get_segment_analyzer() -> SegmentAnalyzer:
    """Get singleton SegmentAnalyzer instance."""
    global _segment_analyzer
    if _segment_analyzer is None:
        _segment_analyzer = SegmentAnalyzer()
    return _segment_analyzer
