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
from src.utils.border_detector import get_border_detector
from src.utils.logging import get_logger

logger = get_logger(__name__)


class PlanDecompositionService:
    """Service for decomposing architectural plans into segments using GPT-5.1."""
    
    def __init__(self):
        """Initialize the decomposition service."""
        self.openai_client = get_openai_client().client  # Get the actual AzureOpenAI client
        self.blob_client = get_blob_client()
        self.image_cropper = get_image_cropper()
        self.border_detector = get_border_detector()
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
            # Step 1: Get ACTUAL image dimensions (original resolution)
            image = Image.open(BytesIO(plan_image_bytes))
            actual_width, actual_height = image.size
            logger.info("Plan image loaded (ORIGINAL)", 
                       width=actual_width, 
                       height=actual_height)
            
            # Step 2: Analyze plan with GPT-5.1
            analysis_start = time.time()
            segments_data, metadata_data, tokens_used = self._analyze_plan_with_gpt(
                plan_image_bytes=plan_image_bytes
            )
            analysis_time = time.time() - analysis_start
            logger.info("GPT analysis complete", 
                       segments_found=len(segments_data),
                       analysis_time=analysis_time)
            
            # Step 3: Get GPT's analyzed image dimensions (may be downscaled)
            gpt_width = metadata_data.get("image_width", actual_width)
            gpt_height = metadata_data.get("image_height", actual_height)
            
            # Calculate scaling factors
            scale_x = actual_width / gpt_width if gpt_width > 0 else 1.0
            scale_y = actual_height / gpt_height if gpt_height > 0 else 1.0
            
            logger.info("Coordinate scaling",
                       actual_size=f"{actual_width}x{actual_height}",
                       gpt_analyzed_size=f"{gpt_width}x{gpt_height}",
                       scale_x=scale_x,
                       scale_y=scale_y)
            
            # Step 4: Create segment objects with SCALED coordinates + MODERATE PADDING
            segments = []
            
            # Add moderate padding to give OpenCV room to search for actual borders
            # Padding is ~5% of image dimensions - OpenCV will refine to exact borders
            # This provides a search area for border detection while avoiding excessive overlap
            padding_x = int(actual_width * 0.05)  # 5% horizontal padding (~175px for 3500px image)
            padding_y = int(actual_height * 0.05)  # 5% vertical padding (~125px for 2500px image)
            
            logger.info("Applying moderate padding (OpenCV will refine to exact borders)",
                       padding_x=padding_x,
                       padding_y=padding_y,
                       reason="Provide search area for OpenCV border detection")
            
            for idx, seg_data in enumerate(segments_data, 1):
                # Scale bounding box coordinates to original image size
                bbox = seg_data.get("bounding_box", {})
                
                # First, scale to original resolution
                scaled_x = bbox.get("x", 0) * scale_x
                scaled_y = bbox.get("y", 0) * scale_y
                scaled_width = bbox.get("width", 0) * scale_x
                scaled_height = bbox.get("height", 0) * scale_y
                
                # Then, add padding while ensuring we stay within image bounds
                padded_x = max(0, scaled_x - padding_x)
                padded_y = max(0, scaled_y - padding_y)
                padded_width = min(actual_width - padded_x, scaled_width + (2 * padding_x))
                padded_height = min(actual_height - padded_y, scaled_height + (2 * padding_y))
                
                scaled_bbox = {
                    "x": padded_x,
                    "y": padded_y,
                    "width": padded_width,
                    "height": padded_height
                }
                
                # Update segment data with scaled + padded coordinates
                seg_data_scaled = {**seg_data, "bounding_box": scaled_bbox}
                
                segment = self._create_segment(
                    segment_id=f"seg_{idx:03d}",
                    segment_data=seg_data_scaled,
                    decomp_id=decomp_id,
                    validation_id=validation_id
                )
                segments.append(segment)
                
                logger.info("Segment coordinates scaled + padded",
                           segment_id=f"seg_{idx:03d}",
                           original_bbox=bbox,
                           scaled_bbox_before_padding={
                               "x": bbox.get("x", 0) * scale_x,
                               "y": bbox.get("y", 0) * scale_y,
                               "width": bbox.get("width", 0) * scale_x,
                               "height": bbox.get("height", 0) * scale_y
                           },
                           final_bbox_with_padding=scaled_bbox)
            
            # Step 5: Create metadata object
            metadata = ProjectMetadata(**metadata_data) if metadata_data else ProjectMetadata()
            
            # Step 6: Create decomposition object (use ACTUAL dimensions)
            total_time = time.time() - start_time
            
            decomposition = PlanDecomposition(
                id=decomp_id,
                validation_id=validation_id,
                project_id=project_id,
                status=DecompositionStatus.COMPLETE,
                full_plan_url=f"https://placeholder.blob.core.windows.net/{validation_id}/full_plan.png",
                full_plan_width=actual_width,  # Original image width
                full_plan_height=actual_height,  # Original image height
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
        
        # System prompt for layout detection ONLY
        system_prompt = """You are an expert at detecting INDIVIDUAL RECTANGULAR FRAMES in architectural drawings.

**YOUR ONLY TASK:** Find EVERY SINGLE rectangular frame separately - do NOT group them.

**CRITICAL - FIND EACH FRAME INDIVIDUALLY:**
- If you see 5 separate rectangular boxes → return 5 separate regions
- If you see 10 separate rectangular boxes → return 10 separate regions
- Do NOT group multiple frames into one region
- Do NOT describe "cluster of frames" - describe EACH frame separately

**What is a frame?**
- A COMPLETE RECTANGLE with 4 visible border lines (top, bottom, left, right)
- Usually contains: floor plan, section, detail, elevation, or table
- Often has a title block or label (include it in the bounding box)

**STEP-BY-STEP:**

1. **Scan the ENTIRE image from left to right, top to bottom**
2. **Find EVERY rectangular border** (look for dark lines forming boxes)
3. **For EACH rectangle you find:**
   - Measure its position and size separately
   - Do NOT combine it with nearby rectangles
   - Each frame gets its own bounding box

**Example:**
- If you see 4 floor plans arranged in a 2×2 grid → return 4 separate regions
- If you see 3 sections side-by-side → return 3 separate regions
- Even if frames are touching or aligned → measure each one individually

**What to IGNORE:**
- Watermarks, UI elements, page borders
- Content without a clear rectangular frame
- Annotations outside of framed areas"""

        user_prompt = """Find ALL rectangular frames (boxes with borders) in this architectural drawing.

**CRITICAL: Find EACH frame SEPARATELY - do NOT group them!**

**PROCESS:**

**Step 1: Scan for INDIVIDUAL frames**
- Look at the ENTIRE image carefully
- Find EVERY rectangular box with visible border lines
- Count them: How many separate rectangular frames do you see?
- **IMPORTANT**: If you see 6 frames → return 6 regions (NOT 1 region describing "group of 6")

**Step 2: For EACH individual frame:**

a) **Measure the 4 border lines:**
   - Find the TOP border line → Y coordinate
   - Find the LEFT border line → X coordinate  
   - Find the RIGHT border line → calculate WIDTH
   - Find the BOTTOM border line → calculate HEIGHT
   - Include any title block at bottom/top of frame

b) **Identify what's inside:**
   - type: "floor_plan", "section", "detail", "elevation", "legend", "table", or "unknown"
   - description: Brief description of THIS SPECIFIC frame (not a group)

**Step 3: Return EACH frame as a separate region**
- Do NOT write: "Cluster of 4 plans" → Instead: return 4 separate regions
- Do NOT write: "Group of sections" → Instead: return each section separately
- Each frame gets its own entry in the "regions" array

**Example - if you see this layout:**
```
[Floor Plan 1] [Floor Plan 2]
[Section A]    [Section B]
```
**You should return 4 regions:**
1. Floor Plan 1 (top-left frame)
2. Floor Plan 2 (top-right frame)
3. Section A (bottom-left frame)
4. Section B (bottom-right frame)

**NOT:** "Group of 2 floor plans and 2 sections"

**OUTPUT FORMAT (JSON ONLY):**
  "image_width": 3508,
  "image_height": 2480,
  "regions": [
    {
      "id": "D1",
      "x": 50,
      "y": 100,
      "width": 800,
      "height": 1200,
      "type": "floor_plan",
      "description": "Main floor plan with rooms and walls"
    },
    {
      "id": "D2",
      "x": 900,
      "y": 100,
      "width": 400,
      "height": 600,
      "type": "section",
      "description": "Vertical section detail"
    }
  ]
}
```

**NOW ANALYZE THE IMAGE AND RETURN ONLY THE JSON - NO OTHER TEXT:**"""

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
            
            logger.info("Raw GPT response", 
                       content_length=len(content),
                       content_preview=content[:500])
            
            # Extract JSON from response
            try:
                # Try to find JSON in the response
                start_idx = content.find('{')
                end_idx = content.rfind('}') + 1
                
                logger.info("JSON extraction attempt",
                           start_idx=start_idx,
                           end_idx=end_idx)
                
                if start_idx != -1 and end_idx > start_idx:
                    json_str = content[start_idx:end_idx]
                    logger.info("Extracted JSON string", json_preview=json_str[:300])
                    result = json.loads(json_str)
                else:
                    logger.warning("No JSON markers found, trying to parse entire content")
                    result = json.loads(content)
                
                logger.info("JSON parsed successfully", keys=list(result.keys()))
                
                # New format: regions instead of segments
                image_width = result.get("image_width", 0)
                image_height = result.get("image_height", 0)
                regions = result.get("regions", [])
                
                logger.info("Extracted regions data",
                           image_width=image_width,
                           image_height=image_height,
                           regions_count=len(regions))
                
                # Convert regions to old segment format for compatibility
                segments_data = []
                for region in regions:
                    segment = {
                        "title": region.get("description", f"Region {region.get('id', 'Unknown')}"),
                        "type": region.get("type", "unknown"),
                        "description": region.get("description", ""),
                        "bounding_box": {
                            "x": region.get("x", 0),
                            "y": region.get("y", 0),
                            "width": region.get("width", 0),
                            "height": region.get("height", 0)
                        },
                        "confidence": 1.0,  # Default confidence
                        "reasoning": f"Detected as {region.get('type', 'unknown')}",
                        "region_id": region.get("id", ""),
                        "pixel_coords": True  # Flag indicating pixel coordinates
                    }
                    segments_data.append(segment)
                    logger.info("Converted region to segment",
                               region_id=region.get("id"),
                               type=region.get("type"))
                
                # Empty metadata for now (focus on layout detection only)
                metadata_data = {
                    "image_width": image_width,
                    "image_height": image_height
                }
                
                logger.info("GPT response parsed successfully",
                           regions_found=len(segments_data),
                           image_size=f"{image_width}x{image_height}",
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
                    # STEP 1: Refine bounding box using OpenCV border detection
                    # This snaps GPT's estimate to actual rectangular borders in the image
                    original_bbox = segment.bounding_box.model_dump()
                    
                    logger.info("Refining bounding box with OpenCV",
                               segment_id=segment.segment_id,
                               gpt_bbox=original_bbox)
                    
                    refined_bbox = self.border_detector.refine_bounding_box(
                        image_path=plan_image_path,
                        bbox=original_bbox,
                        search_margin=100  # Search 100px beyond GPT's estimate for borders
                    )
                    
                    # Update segment with refined coordinates
                    segment.bounding_box = BoundingBox(**refined_bbox)
                    
                    logger.info("Bounding box refined",
                               segment_id=segment.segment_id,
                               original=original_bbox,
                               refined=refined_bbox)
                    
                    # STEP 2: Crop segment using refined bounding box
                    cropped_buffer, thumb_buffer = self.image_cropper.crop_and_create_thumbnail(
                        image_path=plan_image_path,
                        bounding_box=refined_bbox
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

