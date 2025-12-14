"""Service for analyzing individual plan segments using GPT-5.1."""
import asyncio
import base64
import json
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
            
            # 2. Analyze with GPT-5.1
            extracted_data = await self._analyze_with_gpt(
                image_bytes=image_bytes,
                segment_type=segment_type,
                segment_description=segment_description
            )
            
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

        prompt_text = f"""Return ONLY valid JSON.

Extract room/ceiling height measurements relevant to a ממ"ד.

Segment Type: {segment_type}
Description: {segment_description}

Return JSON:
{{
  "room_height_focus": {{
    "heights": [
      {{
        "height_m": 0.0,
        "confidence": 0.0,
        "location": "short description",
        "evidence": ["evidence strings"]
      }}
    ]
  }},
  "height_roi": {{"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0, "confidence": 0.0, "notes": "brief"}}
}}

Rules:
- Convert cm to meters if needed.
- If uncertain, include best candidates with lower confidence."""

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

        prompt_text = f"""Return ONLY valid JSON.

Extract evidence about window spacing / setbacks relevant to Requirement 3.2.
If exact numeric values are unclear, extract the best evidence strings.

Segment Type: {segment_type}
Description: {segment_description}

Return JSON:
{{
  "window_spacing_focus": {{
    "evidence_texts": ["..."],
    "confidence": 0.0,
    "notes": "brief"
  }},
  "window_roi": {{"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0, "confidence": 0.0, "notes": "brief"}}
}}"""

        extracted = await self._run_focused_extraction(
            image_bytes_list=[image_bytes],
            prompt_text=prompt_text,
        )
        if not isinstance(extracted, dict):
            return {"window_spacing_focus": {"evidence_texts": []}}
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
    
    async def _download_segment_image(self, blob_url: str) -> bytes:
        """Download segment image from blob storage.
        
        Args:
            blob_url: SAS URL to blob
            
        Returns:
            Image bytes
        """
        # NOTE: This runs as part of an async workflow (streaming validation).
        # `requests.get` is blocking, so run it in a worker thread to avoid
        # blocking the event loop and to allow streaming events to flush.
        import requests

        def _get() -> bytes:
            response = requests.get(blob_url, timeout=60)
            response.raise_for_status()
            return response.content

        return await asyncio.to_thread(_get)
    
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
    {{"type": "window", "width": 100, "height": 120, "unit": "cm", "location": "...", "notes": "..."}},
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
    "external_wall_count": null
}}

**Extra requirement for wall thickness (1.2):**
- When you extract wall thickness, try to label each wall as **קיר חיצוני** or **קיר פנימי** in `structural_elements[].location`.
    - If the wall borders an area explicitly labeled as internal (e.g., "אזור פנימי"), treat it as **קיר פנימי**.
    - If the wall clearly borders the outside/facade or has an exterior window, treat it as **קיר חיצוני**.
    - If you cannot infer reliably, use "לא ברור".
- If (and only if) this segment shows enough context to determine the TOTAL number of external walls of the ממ"ד (1-4), set `external_wall_count` to that number.
    Otherwise set it to null.

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
