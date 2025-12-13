"""Service for analyzing individual plan segments using GPT-5.1."""
import base64
import json
from typing import Dict, Any, Optional
from io import BytesIO

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
    
    async def _download_segment_image(self, blob_url: str) -> bytes:
        """Download segment image from blob storage.
        
        Args:
            blob_url: SAS URL to blob
            
        Returns:
            Image bytes
        """
        # Extract blob name from URL (simple approach - assumes URL format)
        # Format: https://account.blob.core.windows.net/container/path?sas
        import requests
        
        response = requests.get(blob_url)
        response.raise_for_status()
        
        return response.content
    
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
    {{"value": 20, "unit": "cm", "element": "wall thickness", "location": "outer wall"}},
    {{"value": 80, "unit": "cm", "element": "door width", "location": "entrance"}},
    ...
  ],
  "structural_elements": [
    {{"type": "wall", "thickness": 20, "unit": "cm", "material": "בטון", "location": "...", "notes": "..."}},
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
  }}
}}

**IMPORTANT:**
- Extract EVERYTHING visible
- If you're not sure about a measurement, include it with a note
- Preserve Hebrew text exactly as written
- Include units for all measurements
- Be comprehensive - this data will be used for compliance validation"""

        # Call Azure OpenAI deployment configured via AZURE_OPENAI_DEPLOYMENT_NAME
        try:
            response = self.openai_client.chat_completions_create(
                model=settings.azure_openai_deployment_name,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": system_prompt + "\n\n" + user_prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{image_base64}"
                                }
                            }
                        ]
                    }
                ]
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
