"""Plan extraction service using Azure OpenAI GPT-5.1."""
import base64
from typing import Optional, Dict, Any
from io import BytesIO

from src.models import ExtractedPlanData
from src.azure import get_openai_client
from src.utils.logging import get_logger

logger = get_logger(__name__)


class PlanExtractor:
    """Service for extracting measurements from architectural plans using GPT-5.1."""
    
    def __init__(self):
        """Initialize plan extractor with OpenAI client."""
        self.openai_client = get_openai_client()
    
    async def extract_from_plan(
        self, 
        file_bytes: bytes,
        file_name: str
    ) -> ExtractedPlanData:
        """Extract structured data from an architectural plan using GPT-5.1.
        
        Args:
            file_bytes: Binary content of the plan file
            file_name: Original filename (for logging)
            
        Returns:
            ExtractedPlanData with measurements and confidence score
            
        Raises:
            Exception: If extraction fails
        """
        logger.info("Starting plan extraction", file_name=file_name)
        
        try:
            # Encode image to base64
            base64_image = base64.b64encode(file_bytes).decode('utf-8')
            
            # Create the prompt for GPT-5.1
            prompt = self._build_extraction_prompt()
            
            # Call GPT-5.1 with reasoning
            # Note: GPT-5.1 does NOT support temperature, top_p, max_tokens, etc.
            from src.config import settings
            
            response = self.openai_client.client.chat.completions.create(
                model=settings.azure_openai_deployment_name,
                messages=[
                    {
                        "role": "system",
                        "content": "אתה מומחה לבחינת תוכניות אדריכליות של מרחבים מוגנים (ממ\"ד) בישראל. תפקידך לחלץ מידע מדויק מתוכניות אלו."
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                # GPT-5.1 reasoning models do NOT support these parameters:
                # temperature, top_p, presence_penalty, frequency_penalty,
                # logprobs, top_logprobs, logit_bias, max_tokens
            )
            
            # Parse the response
            content = response.choices[0].message.content
            logger.info("GPT-5.1 extraction completed", 
                       response_length=len(content) if content else 0)
            
            # Parse JSON response to ExtractedPlanData
            extracted_data = self._parse_response(content)
            
            logger.info("Plan extraction successful",
                       confidence=extracted_data.confidence_score,
                       wall_count=extracted_data.external_wall_count)
            
            return extracted_data
            
        except Exception as e:
            logger.error("Plan extraction failed", error=str(e), file_name=file_name)
            raise
    
    def _build_extraction_prompt(self) -> str:
        """Build the prompt for GPT-5.1 plan extraction.
        
        Returns:
            Detailed prompt string in Hebrew
        """
        return """נא לנתח את התוכנית האדריכלית המצורפת של מרחב מוגן דירתי (ממ"ד) ולחלץ את המידע הבא:

**1. קירות:**
- מספר קירות חיצוניים (1-4)
- עובי כל קיר בס"מ (רשימה)
- האם יש חלון בקיר כלשהו

**2. מידות חדר:**
- גובה החדר במטרים
- נפח החדר במ"ק (אם ניתן לחשב)

**3. דלת:**
- מרחק מקצה משקוף הדלת לקיר ניצב בתוך הממ"ד (בס"מ)
- מרחק מקצה הדלת לקיר ניצב מחוץ לממ"ד (בס"מ)

**4. חלון:**
- מרחק חלון הדף מקיר ניצב (בס"מ)
- מרחק בין חלון לדלת אם הם באותו קיר (בס"מ)

**5. תשתיות:**
- האם מסומן צינור כניסת אוויר 4"
- האם מסומן צינור פליטת אוויר 4"
- האם קיימת הערה: "מערכות האוורור והסינון יותקנו בהתאם לת״י 4570"

**6. מידע נוסף (אם זמין):**
- סוג בטון (לדוגמה: ב-30)
- האם הממ"ד משמש כמעבר בין חדרים
- האם יש ארונות קבועים צמודים לקירות
- האם הממ"ד נגיש ללא מעבר דרך חדרי רחצה/מטבח

**חשוב:**
- השתמש בהיגיון ובהנחות סבירות עבור מידע שלא מופיע בבירור
- ציין רמת ביטחון (0.0-1.0) עבור כל החילוץ
- אם מידע חסר, החזר null
- אם לא בטוח, הנמך את רמת הביטחון

**פורמט תשובה (JSON):**
```json
{
  "external_wall_count": <מספר או null>,
  "wall_thickness_cm": [<רשימת עוביים בס"מ>],
  "wall_with_window": <true/false/null>,
  "room_height_m": <גובה במטרים או null>,
  "room_volume_m3": <נפח במ"ק או null>,
  "door_spacing_internal_cm": <מרחק פנימי או null>,
  "door_spacing_external_cm": <מרחק חיצוני או null>,
  "window_spacing_cm": <מרחק או null>,
  "window_to_door_spacing_cm": <מרחק או null>,
  "has_ventilation_note": <true/false/null>,
  "has_air_inlet_pipe": <true/false/null>,
  "has_air_outlet_pipe": <true/false/null>,
  "annotations": {
    "concrete_grade": "<סוג בטון או null>",
    "is_passageway": <true/false/null>,
    "has_fixed_furniture": <true/false/null>,
    "accessible_without_bathroom": <true/false/null>
  },
  "confidence_score": <0.0-1.0>
}
```

נא להחזיר **רק** את ה-JSON, ללא טקסט נוסף."""
    
    def _parse_response(self, response_text: Optional[str]) -> ExtractedPlanData:
        """Parse GPT-5.1 response to ExtractedPlanData.
        
        Args:
            response_text: Raw response from GPT-5.1
            
        Returns:
            Parsed ExtractedPlanData
            
        Raises:
            ValueError: If response cannot be parsed
        """
        if not response_text:
            raise ValueError("Empty response from GPT-5.1")
        
        # Extract JSON from response (handle markdown code blocks)
        import json
        import re
        
        # Try to find JSON in code blocks
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try to parse the entire response as JSON
            json_str = response_text.strip()
        
        try:
            data_dict = json.loads(json_str)
            
            # Create ExtractedPlanData from parsed JSON
            extracted_data = ExtractedPlanData(**data_dict)
            
            logger.info("Successfully parsed GPT-5.1 response")
            return extracted_data
            
        except json.JSONDecodeError as e:
            logger.error("Failed to parse JSON response", error=str(e))
            raise ValueError(f"Invalid JSON response: {e}")
        except Exception as e:
            logger.error("Failed to create ExtractedPlanData", error=str(e))
            raise ValueError(f"Invalid data structure: {e}")


# Global singleton instance
_plan_extractor: Optional[PlanExtractor] = None


def get_plan_extractor() -> PlanExtractor:
    """Get the global plan extractor instance.
    
    Returns:
        PlanExtractor singleton
    """
    global _plan_extractor
    if _plan_extractor is None:
        _plan_extractor = PlanExtractor()
    return _plan_extractor
