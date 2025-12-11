"""LLM-based validation engine using GPT-5.1 reasoning with requirements-mamad.md."""
import json
from typing import List, Dict, Any, Optional
from pathlib import Path

from src.models import (
    ExtractedPlanData,
    ValidationViolation,
    ValidationResult,
    ValidationStatus,
    ValidationSeverity,
    BoundingBox,
    IndividualCheck,
    CheckStatus,
)
from src.azure.openai_client import get_openai_client
from src.utils.logging import get_logger

logger = get_logger(__name__)


class LLMValidator:
    """Validation engine powered by GPT-5.1 reasoning against requirements-mamad.md."""
    
    def __init__(self, requirements_path: str = "requirements-mamad.md"):
        """Initialize LLM validator.
        
        Args:
            requirements_path: Path to requirements markdown file
        """
        self.requirements_path = Path(requirements_path)
        self.openai_client = get_openai_client()
        
        # Load requirements content
        if not self.requirements_path.exists():
            raise FileNotFoundError(f"Requirements file not found: {self.requirements_path}")
        
        self.requirements_content = self.requirements_path.read_text(encoding="utf-8")
        logger.info("LLM Validator initialized", 
                   requirements_file=str(self.requirements_path),
                   requirements_length=len(self.requirements_content))
    
    def validate(
        self,
        validation_id: str,
        project_id: str,
        plan_name: str,
        plan_blob_url: str,
        extracted_data: ExtractedPlanData,
        plan_image_bytes: Optional[bytes] = None,
    ) -> ValidationResult:
        """Run validation using GPT-5.1 against requirements-mamad.md.
        
        Args:
            validation_id: Unique validation ID
            project_id: Project identifier
            plan_name: Name of the architectural plan
            plan_blob_url: Azure Blob Storage URL
            extracted_data: Data extracted from the plan by GPT-5.1
            plan_image_bytes: Optional image bytes for visual bounding box identification
            
        Returns:
            Complete ValidationResult with all violations
        """
        logger.info("Starting LLM-based validation", 
                   validation_id=validation_id,
                   project_id=project_id)
        
        try:
            # Step 0: Identify Mamad location (sanity check)
            mamad_identification = None
            if plan_image_bytes:
                logger.info("Running Mamad identification check")
                mamad_identification = self._identify_mamad_sync(
                    plan_image_bytes=plan_image_bytes,
                    extracted_data=extracted_data
                )
            
            # Build prompt for GPT-5.1 (include Mamad identification from Step 0)
            prompt = self._build_validation_prompt(extracted_data, mamad_identification)
        
            # Build messages for GPT-5.1
            messages = [
                {
                    "role": "system",
                    "content": self._get_system_prompt()
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }
            ]
            
            # If we have the image, include it so GPT can provide bounding boxes
            if plan_image_bytes:
                import base64
                base64_image = base64.b64encode(plan_image_bytes).decode('utf-8')
                messages[1]["content"].append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{base64_image}"
                    }
                })
            
            # Call GPT-5.1 for validation
            response = self.openai_client.client.chat.completions.create(
                model="gpt-5.1",
                messages=messages
            )
            
            # Parse response
            response_text = response.choices[0].message.content
            logger.info("GPT-5.1 validation completed", 
                       response_length=len(response_text))
            
            # Extract JSON from response
            violations = self._parse_validation_response(response_text)
            
            # Build result with individual checks
            result = self._build_validation_result(
                validation_id=validation_id,
                project_id=project_id,
                plan_name=plan_name,
                plan_blob_url=plan_blob_url,
                extracted_data=extracted_data,
                violations=violations,
                mamad_identification=mamad_identification
            )
            
            logger.info("Validation completed",
                       status=result.status.value,
                       total_checks=result.total_checks,
                       failed_checks=result.failed_checks)
            
            return result
            
        except Exception as e:
            logger.error("Validation failed", error=str(e), validation_id=validation_id)
            raise
    
    async def identify_mamad_location(
        self,
        plan_blob_url: str,
        extracted_data: ExtractedPlanData
    ) -> Dict[str, Any]:
        """Identify and locate the Mamad room in the architectural plan.
        
        This is a sanity check to ensure the system is analyzing the correct room.
        Returns bounding box of the identified Mamad.
        
        Args:
            plan_blob_url: URL to the plan image
            extracted_data: Extracted plan data
            
        Returns:
            Dict with: identified (bool), room_label (str), bounding_box (BoundingBox), confidence (float)
        """
        logger.info("Starting Mamad identification sanity check")
        
        prompt = f"""נתונים שזוהו:
- מספר קירות חיצוניים: {extracted_data.external_wall_count}
- עובי קירות: {extracted_data.wall_thickness_cm}
- גובה חדר: {extracted_data.room_height_m}

**משימה:**
1. זהה את חדר הממ"ד בתוכנית האדריכלית
2. ודא שאתה מנתח את החדר הנכון ולא שירותים/ארון/מחסן
3. סמן את הממ"ד במלבן אדום

**החזר JSON:**
{{
  "identified": true/false,
  "room_label": "תיאור החדר שזוהה (למשל: 'ממ״ד - חדר 4x6 מטר')",
  "confidence": 0.0-1.0,
  "bounding_box": {{"x": float, "y": float, "width": float, "height": float}},
  "reasoning": "הסבר איך זיהית את הממ״ד ומדוע אתה בטוח שזה לא שירותים/מחסן"
}}"""
        
        try:
            response = self.openai_client.client.chat.completions.create(
                model="gpt-5.1",
                messages=[
                    {
                        "role": "system",
                        "content": "אתה מומחה לזיהוי חדרי ממ\"ד בתוכניות אדריכליות. תפקידך לוודא שהמערכת מנתחת את החדר הנכון."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )
            
            response_text = response.choices[0].message.content
            
            # Parse JSON
            json_start = response_text.find("{")
            json_end = response_text.rfind("}") + 1
            json_text = response_text[json_start:json_end]
            result = json.loads(json_text)
            
            logger.info("Mamad identification completed", 
                       identified=result.get("identified"),
                       confidence=result.get("confidence"))
            
            return result
            
        except Exception as e:
            logger.error("Mamad identification failed", error=str(e))
            return {
                "identified": False,
                "room_label": "שגיאה בזיהוי",
                "confidence": 0.0,
                "bounding_box": None,
                "reasoning": f"שגיאה: {str(e)}"
            }
    
    def _identify_mamad_sync(
        self,
        plan_image_bytes: bytes,
        extracted_data: ExtractedPlanData
    ) -> Dict[str, Any]:
        """Synchronous version: Identify and locate the Mamad room.
        
        This is Check #0 - sanity check to ensure we're analyzing the correct room.
        
        Args:
            plan_image_bytes: Image bytes of the architectural plan
            extracted_data: Extracted plan data
            
        Returns:
            Dict with: identified (bool), room_label (str), bounding_box (dict), confidence (float)
        """
        logger.info("Starting Mamad identification sanity check")
        
        import base64
        base64_image = base64.b64encode(plan_image_bytes).decode('utf-8')
        
        prompt = f"""**משימה קריטית - זיהוי ממ״ד:**

נתונים שזוהו בשלב ראשון:
- מספר קירות חיצוניים: {extracted_data.external_wall_count if extracted_data.external_wall_count else "לא זוהה"}
- עובי קירות: {extracted_data.wall_thickness_cm if extracted_data.wall_thickness_cm else "לא זוהה"}
- גובה חדר: {extracted_data.room_height_m if extracted_data.room_height_m else "לא זוהה"} מטר

**חשוב מאוד:** זו תוכנית אדריכלית של דירת מגורים שיש בה ממ"ד. אתה **חייב** למצוא אותו!

**תהליך הזיהוי:**
1. **סרוק את כל התוכנית** - חפש חדרים עם קירות עבים (שחורים מודגשים)
2. **זהה את החדר עם הקירות הכי עבים** - זה כנראה הממ״ד
3. **אל תתבלבל:** 
   - שירותים = חדר קטן עם אסלה/מקלחת (סימן סניטרי)
   - מחסן = מסומן "מחסן" או קטן מאוד
   - מטבח = יש כיור/ארונות מטבח
   - ממ״ד = חדר רגיל עם קירות עבים במיוחד
4. **מדוד בדיוק** את המלבן התוחם (רשת 100x100)

**סימנים חזקים לממ״ד:**
- ✅ קירות עבים (20-40 ס״מ) - השחורים ביותר בתוכנית
- ✅ לפחות 2 קירות חיצוניים (קצה הדירה)
- ✅ גודל של חדר שינה (6-12 מ״ר)
- ✅ יכול להיות מסומן "ממ״ד" או "מ.מ.ד"
- ✅ אין סימני סניטציה (אסלה/מקלחת)

**החזר JSON:**
{{
  "identified": true,  // כמעט תמיד true - אלא אם התמונה לא ברורה בכלל
  "room_label": "ממ״ד - חדר X מ״ר",
  "confidence": 0.0-1.0,  // 0.9+ = בטוח מאוד, 0.7-0.9 = סביר, מתחת ל-0.7 = לא בטוח
  "bounding_box": {{"x": 10.0, "y": 15.0, "width": 20.0, "height": 25.0}},
  "reasoning": "הסבר מפורט: היכן מצאתי את הממ״ד, איך אני יודע שזה לא שירותים/מחסן"
}}

**הוראות למדידת bounding_box (באחוזים 0-100):**
- x = מרחק מהשמאל (0=שמאל, 100=ימין)
- y = מרחק מלמעלה (0=למעלה, 100=למטה)
- width = רוחב החדר באחוזים מרוחב התמונה
- height = גובה החדר באחוזים מגובה התמונה

**רק במקרה שהתמונה לא ברורה בכלל** (מטושטשת/חסרה) - `identified: false`"""
        
        try:
            response = self.openai_client.client.chat.completions.create(
                model="gpt-5.1",
                messages=[
                    {
                        "role": "system",
                        "content": "אתה מומחה אדריכלות עם ניסיון רב בקריאת תוכניות ישראליות. במיוחד, אתה מתמחה בזיהוי חדרי ממ״ד (מרחב מוגן דירתי) - חדרים עם קירות מחוזקים. כל דירה בישראל חייבת לכלול ממ״ד אחד לפחות. תפקידך: (1) למצוא את הממ״ד בתוכנית - תמיד יש אחד! (2) להבדיל בינו לבין שירותים/מחסן, (3) למדוד את מיקומו בדיוק. חשוב: התמונה שאתה רואה היא רשת 100x100 - ספור באחוזים מהשוליים."
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
                ]
            )
            
            response_text = response.choices[0].message.content
            logger.info("Mamad identification GPT response received", 
                       response_length=len(response_text),
                       full_response=response_text[:1000])  # Log first 1000 chars for debugging
            
            # Parse JSON
            json_start = response_text.find("{")
            json_end = response_text.rfind("}") + 1
            
            if json_start == -1 or json_end == 0:
                logger.error("No JSON in Mamad identification response")
                return {
                    "identified": False,
                    "room_label": "לא זוהה",
                    "confidence": 0.0,
                    "bounding_box": None,
                    "reasoning": "המודל לא החזיר JSON תקין"
                }
            
            json_text = response_text[json_start:json_end]
            result = json.loads(json_text)
            
            # המר bounding box מ-0-1 ל-0-100 אם צריך
            if result.get("bounding_box"):
                bbox = result["bounding_box"]
                # אם הערכים קטנים מ-1, כנראה שהם בטווח 0-1 וצריך להכפיל ב-100
                if bbox.get("x", 100) < 1 or bbox.get("y", 100) < 1:
                    logger.info("Converting bounding box from 0-1 to 0-100 range")
                    result["bounding_box"] = {
                        "x": bbox.get("x", 0) * 100,
                        "y": bbox.get("y", 0) * 100,
                        "width": bbox.get("width", 0) * 100,
                        "height": bbox.get("height", 0) * 100
                    }
            
            logger.info("Mamad identification completed", 
                       identified=result.get("identified"),
                       confidence=result.get("confidence"),
                       room_label=result.get("room_label"),
                       bounding_box=result.get("bounding_box"))
            
            return result
            
        except Exception as e:
            logger.error("Mamad identification failed", error=str(e))
            return {
                "identified": False,
                "room_label": "שגיאה בזיהוי",
                "confidence": 0.0,
                "bounding_box": None,
                "reasoning": f"שגיאה טכנית: {str(e)}"
            }
    
    def _get_system_prompt(self) -> str:
        """Get system prompt for GPT-5.1."""
        return f"""אתה מומחה לבדיקת תוכניות אדריכליות של ממ"ד (מרחב מוגן דירתי) בהתאם לדרישות פיקוד העורף.

תפקידך: לבדוק את הנתונים שזוהו בתוכנית האדריכלית אל מול מסמך הדרישות המלא.

# מסמך הדרישות המלא (requirements-mamad.md):

{self.requirements_content}

---

**הוראות:**

1. בדוק את כל הנתונים שזוהו בתוכנית אל מול כל סעיף במסמך הדרישות
2. זהה כל הפרה/חריגה מהדרישות
3. עבור כל הפרה, ציין:
   - rule_id: מזהה הכלל (למשל: "1.2_wall_thickness")
   - section: מספר הסעיף (למשל: "1.2")
   - category: קטגוריה (למשל: "wall_thickness", "room_height", "door_spacing")
   - severity: רמת חומרה - "critical" (קריטי), "major" (משמעותי), או "minor" (קל)
   - description: תיאור ההפרה בעברית
   - field: השדה שנבדק
   - actual_value: הערך בפועל שזוהה
   - expected_value: הערך הנדרש לפי הדרישות
   - reasoning: הסבר מפורט למה זו הפרה
   - location_description: תיאור מדויק של המיקום בתוכנית (למשל: "הדלת הממוקמת בקיר העליון של הממ״ד, במרכז התוכנית")
   - bounding_box: **חובה** - זהה את המיקום המדויק בתמונה כאחוזים:
     * מערכת קואורדינטות: (0,0) = פינה שמאלית עליונה, (100,100) = פינה ימנית תחתונה
     * x: אחוז המרחק מקצה שמאל של התמונה (0-100)
     * y: אחוז המרחק מקצה עליון של התמונה (0-100)
     * width: אחוז רוחב האלמנט ביחס לרוחב התמונה (0-100)
     * height: אחוז גובה האלמנט ביחס לגובה התמונה (0-100)
     * **דוגמאות קונקרטיות:**
       - דלת בקיר העליון במרכז: {{"x": 40, "y": 5, "width": 15, "height": 8}}
       - קיר שמאלי: {{"x": 5, "y": 10, "width": 3, "height": 75}}
       - חלון בקיר ימני: {{"x": 85, "y": 20, "width": 10, "height": 12}}
       - כל החדר: {{"x": 10, "y": 10, "width": 80, "height": 80}}
     * אם לא ניתן לזהות מיקום - השתמש ב-null

4. **דוגמה להפרה מלאה:**
{{
  "rule_id": "2.2_door_spacing",
  "section": "2.2",
  "category": "door_spacing",
  "severity": "major",
  "description": "מרווח בין דלת הממ״ד לדלת הדירה: 30 ס״מ במקום 90 ס״מ נדרש",
  "field": "door_spacing_cm",
  "actual_value": "30",
  "expected_value": "90",
  "reasoning": "המרווח הנמדד בין הדלתות קטן מהנדרש, מה שעלול לפגוע ביעילות האטימה",
  "location_description": "הדלת של הממ״ד בקיר העליון, קרוב מדי לדלת הכניסה הראשית",
  "bounding_box": {{"x": 42, "y": 8, "width": 12, "height": 6}}
}}

5. החזר תשובה בפורמט JSON בלבד:
{{
  "violations": [
    {{
      "rule_id": "1.2_wall_thickness",
      "section": "1.2",
      "category": "wall_thickness",
      "severity": "critical",
      "description": "עובי קירות: 35 ס״מ במקום 40 ס״מ נדרש (4 קירות חוץ)",
      "field": "wall_thickness_cm",
      "actual_value": "35",
      "expected_value": "40",
      "reasoning": "זוהו 4 קירות חוץ, לכן נדרש עובי של 40 ס״מ לפי סעיף 1.2",
      "location_description": "כל 4 קירות החיצוניים של הממ״ד",
      "bounding_box": {{"x": 10, "y": 15, "width": 80, "height": 75}}
    }},
    {{
      "rule_id": "2.2_door_spacing",
      "section": "2.2",
      "category": "door_spacing",
      "severity": "major",
      "description": "מרווח בין דלת הממ״ד לדלת הדירה: 30 ס״מ במקום 90 ס״מ",
      "field": "door_spacing_cm",
      "actual_value": "30",
      "expected_value": "90",
      "reasoning": "המרווח קטן מדי ועלול לפגוע באטימות",
      "location_description": "הדלת בקיר העליון של הממ״ד",
      "bounding_box": {{"x": 42, "y": 8, "width": 12, "height": 6}}
    }}
  ],
  "total_checks_performed": 20,
  "reasoning_summary": "בוצעו 20 בדיקות, נמצאו 2 הפרות",
  "mamad_identified": {{
    "room_label": "ממ״ד - חדר 6x4 מטר",
    "bounding_box": {{"x": 15, "y": 20, "width": 70, "height": 65}}
  }}
}}

**חשוב:** אם אין הפרות, החזר מערך violations ריק.
"""
    
    def _build_validation_prompt(self, extracted_data: ExtractedPlanData, mamad_identification: Optional[Dict[str, Any]] = None) -> str:
        """Build validation prompt with extracted data and Mamad location from Step 0."""
        
        data_dict = {
            "external_wall_count": extracted_data.external_wall_count,
            "wall_thickness_cm": extracted_data.wall_thickness_cm,
            "wall_with_window": extracted_data.wall_with_window,
            "room_height_m": extracted_data.room_height_m,
            "room_volume_m3": extracted_data.room_volume_m3,
            "door_spacing_internal_cm": extracted_data.door_spacing_internal_cm,
            "door_spacing_external_cm": extracted_data.door_spacing_external_cm,
            "window_spacing_cm": extracted_data.window_spacing_cm,
            "window_to_door_spacing_cm": extracted_data.window_to_door_spacing_cm,
            "has_ventilation_note": extracted_data.has_ventilation_note,
            "has_air_inlet_pipe": extracted_data.has_air_inlet_pipe,
            "has_air_outlet_pipe": extracted_data.has_air_outlet_pipe,
            "annotations": extracted_data.annotations,
            "confidence_score": extracted_data.confidence_score
        }
        
        # Build base prompt
        prompt = f"""# נתונים שזוהו בתוכנית האדריכלית:

```json
{json.dumps(data_dict, ensure_ascii=False, indent=2)}
```
"""
        
        # Add Mamad identification from Step 0 if available
        if mamad_identification and mamad_identification.get("identified"):
            bbox = mamad_identification.get("bounding_box", {})
            prompt += f"""

# 🎯 **מיקום הממ״ד שזוהה (שלב 0):**

**חשוב מאוד:** הממ״ד כבר זוהה בשלב קודם. השתמש במידע הזה!

- **תיאור:** {mamad_identification.get('room_label', 'לא זוהה')}
- **מיקום בתמונה:** x={bbox.get('x', 0):.1f}%, y={bbox.get('y', 0):.1f}%, רוחב={bbox.get('width', 0):.1f}%, גובה={bbox.get('height', 0):.1f}%
- **הסבר:** {mamad_identification.get('reasoning', '')}
- **רמת ביטחון:** {mamad_identification.get('confidence', 0)*100:.0f}%

**כל הבדיקות צריכות להתבצע על החדר הזה בדיוק!** 
אל תחפש את הממ״ד מחדש - הוא כבר מסומן בקואורדינטות למעלה.
"""
        
        prompt += """
בדוק את כל הנתונים הללו אל מול מסמך הדרישות המלא שקיבלת בהודעת המערכת.
זהה את כל ההפרות והחזר תשובה בפורמט JSON כפי שהוגדר.
"""
        
        return prompt
    
    def _parse_validation_response(self, response_text: str) -> List[ValidationViolation]:
        """Parse GPT-5.1 validation response into violations list."""
        
        try:
            # Extract JSON from response (handle markdown code blocks)
            json_start = response_text.find("{")
            json_end = response_text.rfind("}") + 1
            
            if json_start == -1 or json_end == 0:
                logger.error("No JSON found in response", response=response_text[:200])
                return []
            
            json_text = response_text[json_start:json_end]
            data = json.loads(json_text)
            
            # Log the parsed response to debug bounding boxes
            logger.info("GPT Response Parsed", 
                       violations_count=len(data.get("violations", [])),
                       first_violation_keys=list(data.get("violations", [{}])[0].keys()) if data.get("violations") else [],
                       has_bounding_boxes=any(v.get("bounding_box") for v in data.get("violations", [])))
            
            violations = []
            for v in data.get("violations", []):
                # Map severity string to enum
                severity_map = {
                    "critical": ValidationSeverity.CRITICAL,
                    "major": ValidationSeverity.MAJOR,
                    "minor": ValidationSeverity.MINOR
                }
                severity = severity_map.get(v.get("severity", "major"), ValidationSeverity.MAJOR)
                
                # Parse bounding box if provided
                bbox_data = v.get("bounding_box")
                bounding_box = None
                if bbox_data and isinstance(bbox_data, dict):
                    try:
                        from src.models.schemas import BoundingBox
                        bounding_box = BoundingBox(**bbox_data)
                    except Exception as e:
                        logger.warning("Failed to parse bounding box", error=str(e), bbox=bbox_data)
                
                violation = ValidationViolation(
                    rule_id=v.get("rule_id", "unknown"),
                    section_reference=v.get("section", "unknown"),
                    category=v.get("category", "unknown"),
                    severity=severity,
                    description=v.get("description", ""),
                    actual_value=str(v.get("actual_value", "")),
                    expected_value=str(v.get("expected_value", "")),
                    location_description=v.get("location_description"),
                    bounding_box=bounding_box
                )
                violations.append(violation)
            
            logger.info("Parsed validation response",
                       violations_count=len(violations),
                       total_checks=data.get("total_checks_performed", 0))
            
            return violations
            
        except json.JSONDecodeError as e:
            logger.error("Failed to parse validation JSON", 
                        error=str(e),
                        response=response_text[:500])
            return []
        except Exception as e:
            logger.error("Failed to parse validation response",
                        error=str(e))
            return []
    
    def _build_validation_result(
        self,
        validation_id: str,
        project_id: str,
        plan_name: str,
        plan_blob_url: str,
        extracted_data: ExtractedPlanData,
        violations: List[ValidationViolation],
        mamad_identification: Optional[Dict[str, Any]] = None
    ) -> ValidationResult:
        """Build final validation result with individual checks."""
        
        checks = []
        
        # Check 0: Sanity check - Mamad identification
        if mamad_identification:
            bbox = mamad_identification.get("bounding_box")
            is_identified = mamad_identification.get("identified", False)
            confidence = mamad_identification.get("confidence", 0)
            
            # Only show bounding box if Mamad was successfully identified
            bbox_obj = None
            if is_identified and bbox and isinstance(bbox, dict):
                # Verify bbox has non-zero dimensions
                if bbox.get("width", 0) > 0 and bbox.get("height", 0) > 0:
                    bbox_obj = BoundingBox(**bbox)
            
            sanity_check = IndividualCheck(
                check_id="0_mamad_identification",
                check_name="זיהוי ממ״ד בתוכנית",
                description="וידוא שהמערכת מזהה נכון את חדר הממ״ד ולא שירותים/מחסן/ארון",
                status=CheckStatus.PASS if is_identified and confidence > 0.7 else CheckStatus.FAIL,
                plan_image_url=plan_blob_url,
                bounding_box=bbox_obj,
                reasoning=mamad_identification.get("reasoning", "") + f" (רמת ביטחון: {int(confidence*100)}%)",
                violation=None if is_identified else ValidationViolation(
                    rule_id="mamad_id",
                    section_reference="0",
                    category="זיהוי ממ״ד",
                    severity="CRITICAL",
                    description="המערכת לא הצליחה לזהות חדר ממ״ד בתוכנית",
                    actual_value="לא זוהה",
                    expected_value="זיהוי חד-משמעי של חדר ממ״ד",
                    location_description="התמונה כולה",
                    bounding_box=None
                )
            )
            checks.append(sanity_check)
        
        # Check data quality
        confidence = extracted_data.confidence_score if extracted_data.confidence_score is not None else 0.0
        is_low_confidence = confidence < 0.3
        
        missing_critical_fields = []
        if extracted_data.external_wall_count is None:
            missing_critical_fields.append("מספר קירות חיצוניים")
        if not extracted_data.wall_thickness_cm:
            missing_critical_fields.append("עובי קירות")
        if extracted_data.room_height_m is None:
            missing_critical_fields.append("גובה חדר")
        
        # Check 1: Data quality
        if is_low_confidence or missing_critical_fields:
            data_quality_violation = ValidationViolation(
                rule_id="1_data_quality",
                section_reference="0.0",
                category="data_quality",
                severity=ValidationSeverity.CRITICAL,
                description=f"איכות נתונים לא מספקת. ביטחון: {confidence*100:.1f}%. חסר: {', '.join(missing_critical_fields) if missing_critical_fields else 'אין'}",
                expected_value="ביטחון ≥30% + נתונים קריטיים",
                actual_value=f"{confidence*100:.1f}%",
                location_description="כלל התוכנית",
                bounding_box=None
            )
            
            data_quality_check = IndividualCheck(
                check_id="1_data_quality",
                check_name="איכות זיהוי נתונים",
                description="בדיקה שהמערכת הצליחה לחלץ מספיק נתונים מהתוכנית",
                status=CheckStatus.FAIL,
                plan_image_url=plan_blob_url,
                bounding_box=None,
                reasoning=f"ביטחון נמוך ({confidence*100:.1f}%) או נתונים חסרים: {', '.join(missing_critical_fields)}",
                violation=data_quality_violation
            )
            checks.append(data_quality_check)
        else:
            # Data quality passed
            data_quality_check = IndividualCheck(
                check_id="1_data_quality",
                check_name="איכות זיהוי נתונים",
                description="בדיקה שהמערכת הצליחה לחלץ מספיק נתונים מהתוכנית",
                status=CheckStatus.PASS,
                plan_image_url=plan_blob_url,
                bounding_box=None,
                reasoning=f"ביטחון גבוה ({confidence*100:.1f}%) וכל הנתונים הקריטיים זוהו",
                violation=None
            )
            checks.append(data_quality_check)
        
        # Create individual checks for each violation category
        check_id_counter = 2
        violation_by_category = {}
        
        for v in violations:
            if v.category not in violation_by_category:
                violation_by_category[v.category] = []
            violation_by_category[v.category].append(v)
        
        # Create a check for each violation
        for violation in violations:
            # Skip data quality violations (already handled)
            if violation.category == "data_quality":
                continue
                
            check = IndividualCheck(
                check_id=f"{check_id_counter}_{violation.category}",
                check_name=self._get_check_name_hebrew(violation.category),
                description=violation.description,
                status=CheckStatus.FAIL,
                plan_image_url=plan_blob_url,
                bounding_box=violation.bounding_box,
                reasoning=f"{violation.description}. נמדד: {violation.actual_value}, נדרש: {violation.expected_value}",
                violation=violation
            )
            checks.append(check)
            check_id_counter += 1
        
        # Add passed checks for categories without violations
        all_categories = {
            "wall_thickness": "עובי קירות",
            "wall_count": "מספר קירות חיצוניים", 
            "room_height": "גובה חדר",
            "room_volume": "נפח חדר",
            "door_spacing": "מרחקי דלת",
            "window_spacing": "מרחקי חלון",
            "ventilation": "אוורור",
        }
        
        for category, name in all_categories.items():
            if category not in violation_by_category and extracted_data:
                # Check if we have data for this category
                has_data = self._has_data_for_category(category, extracted_data)
                if has_data:
                    check = IndividualCheck(
                        check_id=f"{check_id_counter}_{category}",
                        check_name=name,
                        description=f"בדיקת {name} - עבר בהצלחה",
                        status=CheckStatus.PASS,
                        plan_image_url=plan_blob_url,
                        bounding_box=None,
                        reasoning=f"{name} עומד בדרישות התקן",
                        violation=None
                    )
                    checks.append(check)
                    check_id_counter += 1
        
        # Calculate totals
        total_checks = len(checks)
        failed_checks = sum(1 for c in checks if c.status == CheckStatus.FAIL)
        passed_checks = sum(1 for c in checks if c.status == CheckStatus.PASS)
        
        # Determine overall status
        has_critical = any(c.violation and c.violation.severity == ValidationSeverity.CRITICAL for c in checks if c.violation)
        status = ValidationStatus.FAIL if has_critical or failed_checks > 0 else ValidationStatus.PASS
        
        return ValidationResult(
            id=validation_id,
            project_id=project_id,
            plan_name=plan_name,
            plan_blob_url=plan_blob_url,
            extracted_data=extracted_data,
            checks=checks,
            violations=violations,  # Keep for backward compatibility
            total_checks=total_checks,
            passed_checks=passed_checks,
            failed_checks=failed_checks,
            status=status
        )
    
    def _get_check_name_hebrew(self, category: str) -> str:
        """Get Hebrew name for check category."""
        names = {
            "wall_thickness": "עובי קירות",
            "wall_count": "מספר קירות חיצוניים",
            "room_height": "גובה חדר",
            "room_volume": "נפח חדר",
            "door_spacing": "מרחקי דלת",
            "window_spacing": "מרחקי חלון",
            "ventilation": "אוורור",
            "data_quality": "איכות נתונים"
        }
        return names.get(category, category)
    
    def _has_data_for_category(self, category: str, data: ExtractedPlanData) -> bool:
        """Check if we have data for a specific category."""
        category_fields = {
            "wall_thickness": lambda d: d.wall_thickness_cm is not None and len(d.wall_thickness_cm) > 0,
            "wall_count": lambda d: d.external_wall_count is not None,
            "room_height": lambda d: d.room_height_m is not None,
            "room_volume": lambda d: d.room_volume_m3 is not None,
            "door_spacing": lambda d: d.door_spacing_internal_cm is not None or d.door_spacing_external_cm is not None,
            "window_spacing": lambda d: d.window_spacing_cm is not None,
            "ventilation": lambda d: d.has_ventilation_note is not None or d.has_air_inlet_pipe is not None,
        }
        
        checker = category_fields.get(category)
        return checker(data) if checker else False


# Singleton instance
_llm_validator_instance = None


def get_llm_validator() -> LLMValidator:
    """Get singleton LLM validator instance."""
    global _llm_validator_instance
    if _llm_validator_instance is None:
        _llm_validator_instance = LLMValidator()
    return _llm_validator_instance
