"""Plan decomposition service using GPT-5.1 for intelligent segmentation."""
import json
import time
import uuid
from typing import List, Dict, Any, Optional, Tuple
from io import BytesIO
from PIL import Image
import base64

from src.models.decomposition import (
    PlanDecomposition,
    PlanSegment,
    SegmentType,
    ProjectMetadata,
    ProcessingStats,
    DecompositionStatus,
    BoundingBox,
)
from src.config import settings
from src.azure import get_openai_client
from src.azure.blob_client import get_blob_client
from src.utils.image_cropper import get_image_cropper
from src.utils.logging import get_logger

logger = get_logger(__name__)


class PlanDecompositionService:
    """Service for decomposing architectural plans into segments using GPT-5.1."""
    
    def __init__(self):
        """Initialize the decomposition service."""
        self.openai_client = get_openai_client().client  # Get the actual AzureOpenAI client
        self.blob_client = get_blob_client()
        self.image_cropper = get_image_cropper()
        logger.info("PlanDecompositionService initialized")
    
    def decompose_plan(
        self,
        validation_id: str,
        project_id: str,
        plan_image_bytes: bytes,
        file_size_mb: float
    ) -> PlanDecomposition:
        """Decompose architectural plan into segments.
        
        Args:
            validation_id: Parent validation ID
            project_id: Project ID for partitioning
            plan_image_bytes: Full plan image bytes
            file_size_mb: File size in MB
            
        Returns:
            PlanDecomposition with all segments
        """
        decomp_id = f"decomp-{uuid.uuid4()}"
        start_time = time.time()
        
        logger.info("Starting plan decomposition",
                   decomposition_id=decomp_id,
                   validation_id=validation_id)
        
        try:
            # Step 1: Get image dimensions
            image = Image.open(BytesIO(plan_image_bytes))
            width, height = image.size
            logger.info("Plan image loaded", width=width, height=height)
            
            # Step 2: Analyze plan with GPT-5.1
            analysis_start = time.time()
            segments_data, metadata_data, tokens_used = self._analyze_plan_with_gpt(
                plan_image_bytes=plan_image_bytes
            )
            analysis_time = time.time() - analysis_start
            logger.info("GPT analysis complete", 
                       segments_found=len(segments_data),
                       analysis_time=analysis_time)
            
            # Step 3: Create segment objects
            segments = []
            for idx, seg_data in enumerate(segments_data, 1):
                segment = self._create_segment(
                    segment_id=f"seg_{idx:03d}",
                    segment_data=seg_data,
                    decomp_id=decomp_id,
                    validation_id=validation_id
                )
                segments.append(segment)
            
            # Step 4: Create metadata object
            metadata = ProjectMetadata(**metadata_data) if metadata_data else ProjectMetadata()
            
            # Step 5: Create decomposition object
            total_time = time.time() - start_time
            
            decomposition = PlanDecomposition(
                id=decomp_id,
                validation_id=validation_id,
                project_id=project_id,
                status=DecompositionStatus.COMPLETE,
                full_plan_url=f"https://placeholder.blob.core.windows.net/{validation_id}/full_plan.png",
                full_plan_width=width,
                full_plan_height=height,
                file_size_mb=file_size_mb,
                metadata=metadata,
                segments=segments,
                processing_stats=ProcessingStats(
                    total_segments=len(segments),
                    processing_time_seconds=total_time,
                    llm_tokens_used=tokens_used,
                    analysis_time_seconds=analysis_time
                )
            )
            
            logger.info("Decomposition complete",
                       decomposition_id=decomp_id,
                       total_segments=len(segments),
                       total_time=total_time)
            
            return decomposition
            
        except Exception as e:
            logger.error("Decomposition failed",
                        decomposition_id=decomp_id,
                        error=str(e))
            
            # Return failed decomposition
            return PlanDecomposition(
                id=decomp_id,
                validation_id=validation_id,
                project_id=project_id,
                status=DecompositionStatus.FAILED,
                full_plan_url="",
                full_plan_width=0,
                full_plan_height=0,
                file_size_mb=file_size_mb,
                metadata=ProjectMetadata(),
                segments=[],
                processing_stats=ProcessingStats(
                    total_segments=0,
                    processing_time_seconds=time.time() - start_time,
                    llm_tokens_used=0
                ),
                error_message=str(e)
            )
    
    def _analyze_plan_with_gpt(
        self,
        plan_image_bytes: bytes
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any], int]:
        """Analyze plan using GPT-5.1 to identify segments and metadata.
        
        Args:
            plan_image_bytes: Full plan image
            
        Returns:
            Tuple of (segments_data, metadata_data, tokens_used)
        """
        # Encode image to base64
        image_base64 = base64.b64encode(plan_image_bytes).decode('utf-8')
        
        # System prompt for decomposition
        system_prompt = """אתה מומחה לניתוח תוכניות אדריכליות ישראליות, במיוחד תוכניות ממ"ד (מרחב מוגן דירתי).

תפקידך: לנתח תוכנית אדריכלית מלאה ולזהות את כל הסגמנטים החשובים לבדיקת תקנות ממ"ד.

**עדיפויות לזיהוי:**
1. **תוכנית קומה ראשית** - החלק הכי גדול והכי חשוב! זו התוכנית שמציגה את החדרים, הקירות, הפתחים
   - לרוב תופסת 50-70% משטח הדף
   - מכילה קווי מתאר של חדרים, קירות, דלתות, חלונות
   - עשויה להכיל מידות וכיתובים בעברית
   
2. **חתכים (sections)** - לרוב מסומנים AA-AA, AB-AB, 1-1, 2-2
   - מציגים את המבנה בחתך אנכי
   - חשובים למדידת גובה תקרה, עובי תקרה
   
3. **פרטי בניה (details)** - זומים על חיבורים, פרטי ביצוע
   - קטנים יחסית
   - מראים פרטים טכניים ספציפיים
   
4. **מקרא (legend)** - בדרך כלל בפינה ימנית תחתונה
   - טבלה עם פרטי הפרויקט, אדריכל, תאריך
   
5. **סימני מים/כיתובים** - התעלם מסימוני Aspose.CAD או evaluation
   - אל תסווג אותם כסגמנטים נפרדים

**חשוב מאוד:**
- תוכנית הקומה הראשית היא הסגמנט הכי חשוב! אל תפספס אותה
- היא בדרך כלל הגדולה ביותר במרכז הדף
- אם אתה רואה קירות, חדרים, דלתות - זו תוכנית קומה!"""

        user_prompt = """נתח את התוכנית האדריכלית הזו של ממ"ד:

**המטרה:** למצוא את תוכנית הקומה הראשית ואת כל הסגמנטים הרלוונטיים לבדיקת תקנות ממ"ד.

**הוראות:**
1. **חפש תחילה את תוכנית הקומה הראשית** - זו התוכנית שמראה את חדר הממ"ד, הקירות, הדלתות והחלונות
2. זהה חתכים (sections) - מסומנים בדרך כלל AA-AA, 1-1 וכו'
3. זהה פרטי בניה - זומים קטנים על חיבורים
4. מצא את המקרא (legend) - הטבלה עם פרטי הפרויקט
5. **התעלם מסימני מים** של Aspose.CAD או evaluation only

**לכל סגמנט תן:**
- כותרת בעברית (אם אין כותרת ברורה, תאר מה רואים)
- סוג: floor_plan (עדיפות ראשונה!), section, detail, legend, table, או unknown
- bounding box מדויק באחוזים (x, y, width, height מ-0 עד 100)
- תיאור מפורט
- ציון ביטחון (0-1)
- הסבר קצר למה בחרת בסיווג

**פורמט החזרה - JSON בלבד:**
{
  "segments": [
    {
      "title": "תוכנית קומה - ממ\"ד דירה 4 חדרים",
      "type": "floor_plan",
      "description": "תוכנית הקומה הראשית מראה את חדר הממ\"ד עם 4 קירות חיצוניים...",
      "bounding_box": {"x": 5, "y": 15, "width": 60, "height": 70},
      "confidence": 0.95,
      "reasoning": "תוכנית גדולה במרכז הדף עם קירות, חדרים, דלתות וחלונות"
    }
  ],
  "metadata": {
    "project_name": "שם הפרויקט (מהמקרא)",
    "architect": "שם אדריכל",
    "date": "תאריך",
    "plan_number": "מספר תוכנית",
    "scale": "קנה מידה",
    "floor": "קומה",
    "apartment": "דירה"
  }
}

**החזר רק JSON, ללא טקסט נוסף.**"""

        # Call GPT-5.1
        try:
            response = self.openai_client.chat.completions.create(
                model=settings.azure_openai_deployment_name,  # Use deployment name from settings
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_prompt},
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
            
            # Parse response
            content = response.choices[0].message.content
            tokens_used = response.usage.total_tokens if response.usage else 0
            
            # Extract JSON from response
            try:
                # Try to find JSON in the response
                start_idx = content.find('{')
                end_idx = content.rfind('}') + 1
                if start_idx != -1 and end_idx > start_idx:
                    json_str = content[start_idx:end_idx]
                    result = json.loads(json_str)
                else:
                    result = json.loads(content)
                
                segments_data = result.get("segments", [])
                metadata_data = result.get("metadata", {})
                
                logger.info("GPT response parsed successfully",
                           segments_found=len(segments_data),
                           tokens=tokens_used)
                
                return segments_data, metadata_data, tokens_used
                
            except json.JSONDecodeError as e:
                logger.error("Failed to parse GPT JSON response",
                            error=str(e),
                            content=content[:500])
                return [], {}, tokens_used
                
        except Exception as e:
            logger.error("GPT analysis failed", error=str(e))
            raise
    
    def _create_segment(
        self,
        segment_id: str,
        segment_data: Dict[str, Any],
        decomp_id: str,
        validation_id: str
    ) -> PlanSegment:
        """Create a PlanSegment from GPT response data.
        
        Args:
            segment_id: Unique segment ID
            segment_data: Data from GPT response
            decomp_id: Decomposition ID
            validation_id: Validation ID
            
        Returns:
            PlanSegment object
        """
        # Parse segment type
        type_str = segment_data.get("type", "unknown")
        try:
            seg_type = SegmentType(type_str)
        except ValueError:
            seg_type = SegmentType.UNKNOWN
        
        # Parse bounding box
        bbox_data = segment_data.get("bounding_box", {})
        bounding_box = BoundingBox(
            x=bbox_data.get("x", 0),
            y=bbox_data.get("y", 0),
            width=bbox_data.get("width", 10),
            height=bbox_data.get("height", 10)
        )
        
        # Create blob URLs (placeholders for now)
        blob_url = f"https://placeholder.blob.core.windows.net/{validation_id}/segments/{segment_id}.png"
        thumbnail_url = f"https://placeholder.blob.core.windows.net/{validation_id}/segments/{segment_id}_thumb.png"
        
        return PlanSegment(
            segment_id=segment_id,
            type=seg_type,
            title=segment_data.get("title", "ללא כותרת"),
            description=segment_data.get("description", ""),
            bounding_box=bounding_box,
            blob_url=blob_url,
            thumbnail_url=thumbnail_url,
            confidence=segment_data.get("confidence", 0.5),
            llm_reasoning=segment_data.get("reasoning"),
            approved_by_user=False,
            used_in_checks=[]
        )
    
    async def crop_and_upload_segments(
        self,
        decomposition: PlanDecomposition,
        plan_image_path: str
    ) -> PlanDecomposition:
        """Crop segments from full plan and upload to Blob Storage.
        
        Args:
            decomposition: PlanDecomposition object with segments
            plan_image_path: Path to full plan image
            
        Returns:
            Updated decomposition with blob URLs
        """
        logger.info("Cropping and uploading segments",
                   decomposition_id=decomposition.id,
                   total_segments=len(decomposition.segments))
        
        try:
            # Upload full plan first
            with open(plan_image_path, 'rb') as f:
                full_plan_blob = f"{decomposition.validation_id}/full_plan.png"
                full_plan_url = await self.blob_client.upload_blob(
                    blob_name=full_plan_blob,
                    data=f
                )
                decomposition.full_plan_url = full_plan_url
                logger.info("Full plan uploaded", url=full_plan_url[:100] + "...")
            
            # Crop and upload each segment
            for segment in decomposition.segments:
                try:
                    # Crop segment and create thumbnail
                    cropped_buffer, thumb_buffer = self.image_cropper.crop_and_create_thumbnail(
                        image_path=plan_image_path,
                        bounding_box=segment.bounding_box.model_dump()
                    )
                    
                    # Upload cropped segment
                    segment_blob = f"{decomposition.validation_id}/segments/{segment.segment_id}.png"
                    segment_url = await self.blob_client.upload_blob(
                        blob_name=segment_blob,
                        data=cropped_buffer
                    )
                    segment.blob_url = segment_url
                    
                    # Upload thumbnail
                    thumb_blob = f"{decomposition.validation_id}/segments/{segment.segment_id}_thumb.png"
                    thumb_url = await self.blob_client.upload_blob(
                        blob_name=thumb_blob,
                        data=thumb_buffer
                    )
                    segment.thumbnail_url = thumb_url
                    
                    logger.info("Segment uploaded",
                               segment_id=segment.segment_id,
                               segment_url=segment_url[:100] + "...")
                
                except Exception as e:
                    logger.error("Failed to crop/upload segment",
                                segment_id=segment.segment_id,
                                error=str(e))
                    # Keep placeholder URLs on error
            
            logger.info("All segments processed",
                       decomposition_id=decomposition.id)
            
            return decomposition
            
        except Exception as e:
            logger.error("Failed to crop and upload segments",
                        decomposition_id=decomposition.id,
                        error=str(e))
            raise


# Singleton instance
_decomposition_service: Optional[PlanDecompositionService] = None


def get_decomposition_service() -> PlanDecompositionService:
    """Get or create the plan decomposition service singleton.
    
    Returns:
        PlanDecompositionService instance
    """
    global _decomposition_service
    if _decomposition_service is None:
        _decomposition_service = PlanDecompositionService()
    return _decomposition_service

