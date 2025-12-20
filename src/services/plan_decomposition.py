"""Plan decomposition service using GPT-5.1 for intelligent segmentation."""
import json
import time
import uuid
import os
import tempfile
import anyio
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
        self.openai_client = get_openai_client()
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

            # Optional: keep only "top-level" frames (drop nested/internal detail boxes)
            # This is often closer to how a human perceives separate drawings on a sheet.
            if settings.decomposition_filter_nested_frames_enabled and len(segments_data) > 1:
                before_count = len(segments_data)
                gpt_width_for_filter = float(metadata_data.get("image_width", actual_width) or actual_width)
                gpt_height_for_filter = float(metadata_data.get("image_height", actual_height) or actual_height)
                segments_data = self._filter_nested_segments(
                    segments_data=segments_data,
                    image_width=gpt_width_for_filter,
                    image_height=gpt_height_for_filter,
                )
                logger.info(
                    "Filtered nested frames",
                    before=before_count,
                    after=len(segments_data),
                    containment_threshold=settings.decomposition_nested_containment_threshold,
                    min_area_ratio=settings.decomposition_min_box_area_ratio,
                )

            # Optional: merge nearby detected frames into larger "macro" regions
            # This creates crops closer to the manual red-box grouping (clusters/columns)
            if settings.decomposition_merge_enabled and segments_data:
                before_count = len(segments_data)
                gpt_width_for_merge = metadata_data.get("image_width", actual_width)
                gpt_height_for_merge = metadata_data.get("image_height", actual_height)
                segments_data = self._merge_nearby_segments(
                    segments_data=segments_data,
                    image_width=float(gpt_width_for_merge),
                    image_height=float(gpt_height_for_merge),
                )
                logger.info(
                    "Merged nearby segments",
                    before=before_count,
                    after=len(segments_data),
                    merge_enabled=True,
                    margin_ratio=settings.decomposition_merge_margin_ratio,
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

            # Note: we no longer apply a fixed % padding here.
            # Fixed global padding can cause small details to expand into neighboring drawings,
            # making some crops look wrong. Instead, we keep scaled boxes tight and let
            # OpenCV use a dynamic search margin based on the box size during cropping.
            
            for idx, seg_data in enumerate(segments_data, 1):
                # Scale bounding box coordinates to original image size
                bbox = seg_data.get("bounding_box", {})
                
                # First, scale to original resolution
                scaled_x = bbox.get("x", 0) * scale_x
                scaled_y = bbox.get("y", 0) * scale_y
                scaled_width = bbox.get("width", 0) * scale_x
                scaled_height = bbox.get("height", 0) * scale_y

                # Clamp to image bounds
                clamped_x = max(0.0, min(float(actual_width), float(scaled_x)))
                clamped_y = max(0.0, min(float(actual_height), float(scaled_y)))
                clamped_w = max(0.0, min(float(actual_width) - clamped_x, float(scaled_width)))
                clamped_h = max(0.0, min(float(actual_height) - clamped_y, float(scaled_height)))

                scaled_bbox = {
                    "x": clamped_x,
                    "y": clamped_y,
                    "width": clamped_w,
                    "height": clamped_h,
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

    def _merge_nearby_segments(
        self,
        segments_data: List[Dict[str, Any]],
        image_width: float,
        image_height: float,
    ) -> List[Dict[str, Any]]:
        """Merge detected frame boxes that are close/adjacent into larger regions.

        We intentionally keep GPT detecting "fine" rectangles (individual frames),
        then merge them into macro regions (like a column of details) to match
        the desired UX while avoiding reliance on a drawn outer border.
        """
        if len(segments_data) < 2:
            return segments_data

        margin_ratio = float(settings.decomposition_merge_margin_ratio)
        margin_ratio = max(0.0, min(0.10, margin_ratio))
        margin_x = image_width * margin_ratio
        margin_y = image_height * margin_ratio

        # Heuristics tuned to avoid "chaining" that collapses everything into one cluster.
        min_axis_overlap_ratio = 0.25  # require meaningful alignment to merge
        max_cluster_area_ratio = 0.70  # safety cap against mega-cluster

        def _bbox_xyxy(seg: Dict[str, Any]) -> Tuple[float, float, float, float]:
            b = seg.get("bounding_box", {}) or {}
            x1 = float(b.get("x", 0))
            y1 = float(b.get("y", 0))
            w = float(b.get("width", 0))
            h = float(b.get("height", 0))
            x2 = x1 + max(0.0, w)
            y2 = y1 + max(0.0, h)
            return x1, y1, x2, y2

        def _overlap(a1: float, a2: float, b1: float, b2: float) -> float:
            return max(0.0, min(a2, b2) - max(a1, b1))

        def _gap(a1: float, a2: float, b1: float, b2: float) -> float:
            # distance between two intervals (0 if overlapping)
            return max(0.0, max(a1, b1) - min(a2, b2))

        def _mergeable(box_a: Tuple[float, float, float, float], box_b: Tuple[float, float, float, float]) -> bool:
            ax1, ay1, ax2, ay2 = box_a
            bx1, by1, bx2, by2 = box_b

            aw = max(1.0, ax2 - ax1)
            ah = max(1.0, ay2 - ay1)
            bw = max(1.0, bx2 - bx1)
            bh = max(1.0, by2 - by1)

            ox = _overlap(ax1, ax2, bx1, bx2)
            oy = _overlap(ay1, ay2, by1, by2)
            overlap_x_ratio = ox / min(aw, bw)
            overlap_y_ratio = oy / min(ah, bh)

            gx = _gap(ax1, ax2, bx1, bx2)
            gy = _gap(ay1, ay2, by1, by2)

            # Merge vertical stacks: strong X alignment + small vertical gap
            if overlap_x_ratio >= min_axis_overlap_ratio and gy <= margin_y:
                return True
            # Merge horizontal neighbors: strong Y alignment + small horizontal gap
            if overlap_y_ratio >= min_axis_overlap_ratio and gx <= margin_x:
                return True
            return False

        def _union(a: Tuple[float, float, float, float], b: Tuple[float, float, float, float]) -> Tuple[float, float, float, float]:
            ax1, ay1, ax2, ay2 = a
            bx1, by1, bx2, by2 = b
            return (min(ax1, bx1), min(ay1, by1), max(ax2, bx2), max(ay2, by2))

        def _area(box: Tuple[float, float, float, float]) -> float:
            x1, y1, x2, y2 = box
            return max(0.0, x2 - x1) * max(0.0, y2 - y1)

        image_area = max(1.0, image_width * image_height)

        # Sort boxes top-to-bottom, left-to-right for stable greedy clustering
        boxes = [_bbox_xyxy(seg) for seg in segments_data]
        order = sorted(range(len(segments_data)), key=lambda i: (boxes[i][1], boxes[i][0]))

        clusters: List[Dict[str, Any]] = []
        # each cluster: {"indices": [...], "bbox": (x1,y1,x2,y2)}

        for idx in order:
            box = boxes[idx]
            best_cluster = None
            best_increase = None

            for c in clusters:
                cb = c["bbox"]
                if not _mergeable(cb, box):
                    continue

                ub = _union(cb, box)
                if _area(ub) / image_area > max_cluster_area_ratio:
                    continue

                increase = _area(ub) - _area(cb)
                if best_increase is None or increase < best_increase:
                    best_increase = increase
                    best_cluster = c

            if best_cluster is None:
                clusters.append({"indices": [idx], "bbox": box})
            else:
                best_cluster["indices"].append(idx)
                best_cluster["bbox"] = _union(best_cluster["bbox"], box)

        # Prefer stable ordering
        clusters.sort(key=lambda c: (c["bbox"][1], c["bbox"][0]))

        cluster_indices_list: List[List[int]] = [sorted(c["indices"]) for c in clusters]

        def _pick_type(indices: List[int]) -> str:
            types = {str(segments_data[i].get("type", "unknown")) for i in indices}
            priority = [
                "floor_plan",
                "section",
                "elevation",
                "detail",
                "table",
                "legend",
                "unknown",
            ]
            for t in priority:
                if t in types:
                    return t
            return "unknown"

        def _title_for_type(type_str: str, count: int) -> str:
            if count <= 1:
                return "ללא כותרת"
            if type_str == "floor_plan":
                return f"אזור תוכניות ({count})"
            if type_str == "section":
                return f"אזור חתכים ({count})"
            if type_str == "elevation":
                return f"אזור חזיתות ({count})"
            if type_str == "detail":
                return f"מקבץ פרטים ({count})"
            if type_str == "table":
                return f"אזור טבלאות ({count})"
            if type_str == "legend":
                return f"אזור מקרא ({count})"
            return f"אזור שרטוטים ({count})"

        merged: List[Dict[str, Any]] = []

        for indices in cluster_indices_list:
            if len(indices) == 1:
                merged.append(segments_data[indices[0]])
                continue

            # Union bbox
            x1 = float("inf")
            y1 = float("inf")
            x2 = 0.0
            y2 = 0.0
            descriptions: List[str] = []
            confidences: List[float] = []
            region_ids: List[str] = []

            for idx in indices:
                seg = segments_data[idx]
                bx1, by1, bx2, by2 = _bbox_xyxy(seg)
                x1 = min(x1, bx1)
                y1 = min(y1, by1)
                x2 = max(x2, bx2)
                y2 = max(y2, by2)
                d = str(seg.get("description", "")).strip()
                if d:
                    descriptions.append(d)
                try:
                    confidences.append(float(seg.get("confidence", 1.0)))
                except Exception:
                    pass
                rid = str(seg.get("region_id", "")).strip()
                if rid:
                    region_ids.append(rid)

            cluster_type = _pick_type(indices)
            title = _title_for_type(cluster_type, len(indices))

            # Keep description short and human readable
            short_desc = "; ".join(descriptions[:3])
            if len(descriptions) > 3:
                short_desc = short_desc + "..."

            merged.append(
                {
                    "title": title,
                    "type": cluster_type,
                    "description": short_desc or "אזור מקובץ של מספר שרטוטים",
                    "bounding_box": {
                        "x": max(0.0, x1),
                        "y": max(0.0, y1),
                        "width": max(0.0, x2 - x1),
                        "height": max(0.0, y2 - y1),
                    },
                    "confidence": sum(confidences) / len(confidences) if confidences else 1.0,
                    # Marker used later to skip OpenCV border snapping
                    "reasoning": f"MERGED_CLUSTER:{len(indices)} ids={','.join(region_ids[:12])}",
                }
            )

        return merged

    def _filter_nested_segments(
        self,
        segments_data: List[Dict[str, Any]],
        image_width: float,
        image_height: float,
    ) -> List[Dict[str, Any]]:
        if len(segments_data) < 2:
            return segments_data

        image_area = max(1.0, float(image_width) * float(image_height))
        min_area = max(1.0, float(settings.decomposition_min_box_area_ratio))
        min_area = max(0.0, min(0.20, min_area))
        min_area_px = image_area * min_area

        containment = float(settings.decomposition_nested_containment_threshold)
        containment = max(0.50, min(0.99, containment))

        def _bbox_xyxy(seg: Dict[str, Any]) -> Tuple[float, float, float, float]:
            b = seg.get("bounding_box", {}) or {}
            x1 = float(b.get("x", 0))
            y1 = float(b.get("y", 0))
            w = float(b.get("width", 0))
            h = float(b.get("height", 0))
            x2 = x1 + max(0.0, w)
            y2 = y1 + max(0.0, h)
            return x1, y1, x2, y2

        def _area(box: Tuple[float, float, float, float]) -> float:
            x1, y1, x2, y2 = box
            return max(0.0, x2 - x1) * max(0.0, y2 - y1)

        def _intersection(a: Tuple[float, float, float, float], b: Tuple[float, float, float, float]) -> float:
            ax1, ay1, ax2, ay2 = a
            bx1, by1, bx2, by2 = b
            ix1 = max(ax1, bx1)
            iy1 = max(ay1, by1)
            ix2 = min(ax2, bx2)
            iy2 = min(ay2, by2)
            return _area((ix1, iy1, ix2, iy2))

        boxes = [_bbox_xyxy(seg) for seg in segments_data]
        areas = [_area(b) for b in boxes]

        # Drop tiny boxes first
        candidates = [i for i, a in enumerate(areas) if a >= min_area_px]
        if len(candidates) < 2:
            return [segments_data[i] for i in candidates] if candidates else segments_data

        # Keep larger boxes first, and drop boxes that are mostly contained inside a kept larger box
        order = sorted(candidates, key=lambda i: areas[i], reverse=True)
        kept: List[int] = []

        for i in order:
            bi = boxes[i]
            ai = areas[i]
            is_nested = False

            for j in kept:
                bj = boxes[j]
                aj = areas[j]
                if aj <= ai:
                    continue
                inter = _intersection(bi, bj)
                if ai > 0 and (inter / ai) >= containment:
                    is_nested = True
                    break

            if not is_nested:
                kept.append(i)

        # Stable ordering top-to-bottom, left-to-right
        kept.sort(key=lambda i: (boxes[i][1], boxes[i][0]))
        return [segments_data[i] for i in kept]
    
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
   - description: תיאור קצר בעברית של המסגרת הספציפית הזו (לא קבוצה)

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
```json
{
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
      "description": "תוכנית קומה עם חדרים וקירות"
    },
    {
      "id": "D2",
      "x": 900,
      "y": 100,
      "width": 400,
      "height": 600,
      "type": "section",
      "description": "פרט חתך אנכי"
    }
  ]
}
```

**חשוב: כל התיאורים (description) חייבים להיות בעברית!**

**NOW ANALYZE THE IMAGE AND RETURN ONLY THE JSON - NO OTHER TEXT:**"""

        # Call GPT-5.1
        try:
            response = self.openai_client.chat_completions_create(
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
            # Load image size once for clamping
            try:
                with Image.open(plan_image_path) as img:
                    img_w, img_h = img.size
            except Exception:
                img_w = int(decomposition.full_plan_width or 0)
                img_h = int(decomposition.full_plan_height or 0)

            crop_image_path = plan_image_path
            scale_x = 1.0
            scale_y = 1.0

            # If source is PDF, render a high-res copy for cropping to preserve detail.
            if (
                getattr(decomposition, "source_file_type", None) == "pdf"
                and getattr(decomposition, "source_file_url", None)
                and int(getattr(settings, "pdf_crop_render_dpi", 0)) > 0
            ):
                try:
                    import requests
                    from pdf2image import convert_from_bytes
                    import math

                    def _get() -> bytes:
                        r = requests.get(decomposition.source_file_url, timeout=60)
                        r.raise_for_status()
                        return r.content

                    pdf_bytes = await anyio.to_thread.run_sync(_get)
                    requested_dpi = int(getattr(settings, "pdf_crop_render_dpi", 600))
                    min_dpi = 100
                    max_pixels = int(getattr(settings, "pdf_crop_max_pixels", 120_000_000))

                    def _render(dpi: int):
                        return convert_from_bytes(pdf_bytes, dpi=dpi, fmt="png", use_pdftocairo=True)

                    images = None
                    effective_dpi = requested_dpi
                    try:
                        images = _render(requested_dpi)
                    except Exception as e:
                        msg = str(e).lower()
                        if "decompression bomb" in msg:
                            for dpi in [800, 600, 450, 300, 200, 150]:
                                if dpi > requested_dpi:
                                    continue
                                if dpi < min_dpi:
                                    break
                                try:
                                    images = _render(dpi)
                                    effective_dpi = dpi
                                    break
                                except Exception as e2:
                                    if "decompression bomb" in str(e2).lower():
                                        continue
                                    raise
                        else:
                            raise

                    if images:
                        image = images[0]
                        pixel_count = int(image.width * image.height)
                        if pixel_count > max_pixels:
                            scale = math.sqrt(max_pixels / float(pixel_count))
                            new_w = max(1, int(image.width * scale))
                            new_h = max(1, int(image.height * scale))
                            image = image.resize((new_w, new_h), resample=Image.Resampling.LANCZOS)

                        hr_path = os.path.join(tempfile.mkdtemp(), "full_plan_hr.png")
                        image.save(hr_path, format="PNG", optimize=True)
                        crop_image_path = hr_path
                        scale_x = float(image.width) / float(img_w or image.width)
                        scale_y = float(image.height) / float(img_h or image.height)

                        logger.info(
                            "Using high-res PDF render for cropping",
                            dpi=effective_dpi,
                            original_dimensions=f"{img_w}x{img_h}",
                            rendered_dimensions=f"{image.width}x{image.height}",
                            scale_x=scale_x,
                            scale_y=scale_y,
                        )
                except Exception as e:
                    logger.warning("Failed to render high-res PDF for cropping", error=str(e))

            def _clamp_bbox(b: Dict[str, Any]) -> Dict[str, Any]:
                if img_w <= 0 or img_h <= 0:
                    return b
                x = float(b.get("x", 0))
                y = float(b.get("y", 0))
                w = float(b.get("width", 0))
                h = float(b.get("height", 0))
                x = max(0.0, min(float(img_w), x))
                y = max(0.0, min(float(img_h), y))
                w = max(0.0, min(float(img_w) - x, w))
                h = max(0.0, min(float(img_h) - y, h))
                return {"x": x, "y": y, "width": w, "height": h}

            def _expand_bbox(b: Dict[str, Any], pad: float) -> Dict[str, Any]:
                x = float(b.get("x", 0))
                y = float(b.get("y", 0))
                w = float(b.get("width", 0))
                h = float(b.get("height", 0))
                x2 = x + w
                y2 = y + h
                x = x - pad
                y = y - pad
                x2 = x2 + pad
                y2 = y2 + pad
                return _clamp_bbox({"x": x, "y": y, "width": x2 - x, "height": y2 - y})

            def _scale_bbox(b: Dict[str, Any]) -> Dict[str, Any]:
                if scale_x == 1.0 and scale_y == 1.0:
                    return b
                return {
                    "x": float(b.get("x", 0)) * scale_x,
                    "y": float(b.get("y", 0)) * scale_y,
                    "width": float(b.get("width", 0)) * scale_x,
                    "height": float(b.get("height", 0)) * scale_y,
                }

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
                    original_bbox = _clamp_bbox(segment.bounding_box.model_dump())

                    # STEP 1: Optionally refine using OpenCV border detection
                    # For merged macro-clusters (no guaranteed outer border), skip snapping.
                    refined_bbox = original_bbox
                    is_merged_cluster = bool(
                        segment.llm_reasoning
                        and isinstance(segment.llm_reasoning, str)
                        and segment.llm_reasoning.startswith("MERGED_CLUSTER:")
                    )

                    if not is_merged_cluster:
                        logger.info(
                            "Refining bounding box with OpenCV",
                            segment_id=segment.segment_id,
                            gpt_bbox=original_bbox,
                        )

                        # Dynamic search margin: scale with bbox size (helps small/large drawings)
                        ow = float(original_bbox.get("width", 0))
                        oh = float(original_bbox.get("height", 0))
                        base = max(1.0, min(ow, oh))
                        search_margin = int(max(25.0, min(220.0, base * 0.18)))

                        refined_bbox = self.border_detector.refine_bounding_box(
                            image_path=plan_image_path,
                            bbox=original_bbox,
                            search_margin=search_margin,
                        )

                        refined_bbox = _clamp_bbox(refined_bbox)

                        # Update segment with refined coordinates
                        segment.bounding_box = BoundingBox(**refined_bbox)

                        logger.info(
                            "Bounding box refined",
                            segment_id=segment.segment_id,
                            original=original_bbox,
                            refined=refined_bbox,
                            search_margin=search_margin,
                        )

                        if refined_bbox == original_bbox:
                            logger.info(
                                "OpenCV border refinement made no change",
                                segment_id=segment.segment_id,
                            )
                    else:
                        logger.info(
                            "Skipping OpenCV border refinement for merged cluster",
                            segment_id=segment.segment_id,
                            bbox=original_bbox,
                        )
                    
                    # STEP 2: Crop segment using refined bounding box
                    # Add a small safety padding to avoid cutting off border lines.
                    pad = float(max(4.0, min(40.0, min(float(refined_bbox.get("width", 0)), float(refined_bbox.get("height", 0))) * 0.02)))
                    crop_bbox = _expand_bbox(refined_bbox, pad) if (img_w > 0 and img_h > 0) else refined_bbox

                    crop_bbox_scaled = _scale_bbox(crop_bbox)
                    cropped_buffer, thumb_buffer = self.image_cropper.crop_and_create_thumbnail(
                        image_path=crop_image_path,
                        bounding_box=crop_bbox_scaled
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
