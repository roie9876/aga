"""API endpoints for plan decomposition."""
import uuid
import tempfile
import os
from datetime import datetime
from pathlib import Path
from io import BytesIO
import anyio
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import Response
from typing import Optional

from src.models.decomposition import (
    PlanDecomposition,
    DecompositionResponse,
    DecompositionStatus,
    ProcessingStats,
    ProjectMetadata,
    SegmentUpdateRequest,
    ApprovalRequest,
    AddManualSegmentsRequest,
    AnalyzeSegmentsRequest,
    PlanSegment,
    SegmentType,
    BoundingBox,
    ManualRoi,
)
from src.services.segment_analyzer import SegmentAnalyzer
from src.services.plan_decomposition import get_decomposition_service
from src.azure import get_cosmos_client
from src.azure.blob_client import get_blob_client
from src.utils.image_cropper import get_image_cropper
from src.utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/decomposition", tags=["decomposition"])


@router.post("/upload-segments", response_model=DecompositionResponse)
async def create_decomposition_from_uploaded_segments(
    project_id: str = Form(..., description="Project identifier"),
    files: list[UploadFile] = File(..., description="Segment image files (PNG, JPG)"),
    validation_id: Optional[str] = Form(None, description="Optional validation ID"),
):
    """Create a decomposition from already-cropped segment images.

    This is useful when the user already has a folder of segment images.
    We upload each segment + thumbnail to Blob Storage and persist a decomposition
    document for the regular review/approval workflow.
    """

    if not files:
        raise HTTPException(status_code=400, detail="לא נבחרו קבצים")

    if len(files) > 200:
        raise HTTPException(status_code=400, detail="יותר מדי קבצים (מקסימום 200)")

    try:
        if not validation_id:
            validation_id = f"val-{uuid.uuid4()}"

        decomp_id = f"decomp-{uuid.uuid4()}"
        cropper = get_image_cropper()
        blob_client = get_blob_client()

        segments: list[PlanSegment] = []
        total_bytes = 0

        from src.utils.file_converter import convert_to_image_if_needed
        from PIL import Image

        for idx, upload in enumerate(files, start=1):
            filename = upload.filename or f"segment_{idx:03d}"
            data = await upload.read()
            if not data:
                continue

            total_bytes += len(data)

            # Support: images + PDF (convert PDF->PNG if needed)
            try:
                processed_bytes, processed_filename, _was_converted = convert_to_image_if_needed(
                    data,
                    filename,
                )
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))

            # Normalize to PNG regardless of input (JPG/PNG/PDF)
            try:
                with Image.open(BytesIO(processed_bytes)) as img:
                    if img.mode in ("P", "LA", "RGBA"):
                        normalized = img.convert("RGBA")
                    elif img.mode != "RGB":
                        normalized = img.convert("RGB")
                    else:
                        normalized = img

                    png_buffer = BytesIO()
                    normalized.save(png_buffer, format="PNG")
                    png_buffer.seek(0)
            except Exception:
                raise HTTPException(status_code=400, detail=f"קובץ לא תקין: {processed_filename}")

            thumb_buffer = cropper.create_thumbnail(png_buffer)
            png_buffer.seek(0)

            seg_id = f"seg_{idx:03d}"
            segment_blob = f"{validation_id}/segments/{seg_id}.png"
            with anyio.fail_after(60):
                segment_url = await blob_client.upload_blob(
                    blob_name=segment_blob,
                    data=png_buffer,
                    overwrite=True,
                )

            thumb_blob = f"{validation_id}/segments/{seg_id}_thumb.png"
            with anyio.fail_after(60):
                thumb_url = await blob_client.upload_blob(
                    blob_name=thumb_blob,
                    data=thumb_buffer,
                    overwrite=True,
                )

            title = Path(filename).stem or f"סגמנט {idx}"

            segments.append(
                PlanSegment(
                    segment_id=seg_id,
                    type=SegmentType.UNKNOWN,
                    title=title,
                    description="סגמנט שהועלה כתמונה חתוכה",
                    bounding_box=BoundingBox(x=0.0, y=0.0, width=1.0, height=1.0),
                    blob_url=segment_url,
                    thumbnail_url=thumb_url,
                    confidence=1.0,
                    llm_reasoning=None,
                    approved_by_user=True,
                    used_in_checks=[],
                )
            )

        file_size_mb = total_bytes / (1024 * 1024)

        decomposition = PlanDecomposition(
            id=decomp_id,
            validation_id=validation_id,
            project_id=project_id,
            status=DecompositionStatus.REVIEW_NEEDED,
            full_plan_url="",
            full_plan_width=0,
            full_plan_height=0,
            file_size_mb=file_size_mb,
            metadata=ProjectMetadata(),
            segments=segments,
            processing_stats=ProcessingStats(
                total_segments=len(segments),
                processing_time_seconds=0.0,
                llm_tokens_used=0,
            ),
        )

        cosmos_client = get_cosmos_client()
        decomp_dict = decomposition.model_dump(mode="json")
        decomp_dict["type"] = "decomposition"
        await cosmos_client.create_item(decomp_dict)

        return DecompositionResponse(
            decomposition_id=decomposition.id,
            status=decomposition.status,
            estimated_time_seconds=10,
            message="הסגמנטים נטענו בהצלחה. סמן/בטל סגמנטים והמשך לשלב הבא.",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to create decomposition from uploaded segments",
            project_id=project_id,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=f"שגיאה ביצירת פירוק מסגמנטים: {str(e)}")


@router.get("/{decomposition_id}/images/full-plan")
async def get_full_plan_image(decomposition_id: str):
    """Fetch the stored full plan image for a decomposition.

    This provides a same-origin URL that can be embedded in printable reports
    (avoids cross-origin/CORS issues when printing to PDF).
    """

    cosmos_client = get_cosmos_client()
    query = """
        SELECT * FROM c
        WHERE c.id = @decomposition_id
        AND c.type = 'decomposition'
    """

    items = await cosmos_client.query_items(
        query=query,
        parameters=[
            {"name": "@decomposition_id", "value": decomposition_id},
        ],
    )

    if not items:
        raise HTTPException(status_code=404, detail="פירוק לא נמצא")

    decomposition = PlanDecomposition(**items[0])
    if not decomposition.validation_id:
        raise HTTPException(status_code=400, detail="validation_id חסר בפירוק")

    blob_client = get_blob_client()
    blob_name = f"{decomposition.validation_id}/full_plan.png"
    try:
        with anyio.fail_after(60):
            img_bytes = await blob_client.download_blob(blob_name)
    except Exception as e:
        logger.error(
            "Failed to download full plan image",
            decomposition_id=decomposition_id,
            blob_name=blob_name,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail="שגיאה בטעינת תמונת התוכנית המלאה")

    return Response(
        content=img_bytes,
        media_type="image/png",
        headers={
            # Prevent browsers/print-to-PDF flows from reusing stale cached images
            # after manual ROI updates or re-runs.
            "Cache-Control": "no-store, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@router.get("/{decomposition_id}/images/segments/{segment_id}")
async def get_segment_image(
    decomposition_id: str,
    segment_id: str,
    thumbnail: bool = False,
):
    """Fetch the stored segment crop (or thumbnail) for a decomposition."""

    cosmos_client = get_cosmos_client()
    query = """
        SELECT * FROM c
        WHERE c.id = @decomposition_id
        AND c.type = 'decomposition'
    """

    items = await cosmos_client.query_items(
        query=query,
        parameters=[
            {"name": "@decomposition_id", "value": decomposition_id},
        ],
    )

    if not items:
        raise HTTPException(status_code=404, detail="פירוק לא נמצא")

    decomposition = PlanDecomposition(**items[0])
    if not decomposition.validation_id:
        raise HTTPException(status_code=400, detail="validation_id חסר בפירוק")

    blob_client = get_blob_client()
    suffix = "_thumb.png" if thumbnail else ".png"
    blob_name = f"{decomposition.validation_id}/segments/{segment_id}{suffix}"

    try:
        with anyio.fail_after(60):
            img_bytes = await blob_client.download_blob(blob_name)
    except Exception as e:
        logger.error(
            "Failed to download segment image",
            decomposition_id=decomposition_id,
            segment_id=segment_id,
            blob_name=blob_name,
            thumbnail=thumbnail,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail="שגיאה בטעינת תמונת הסגמנט")

    return Response(
        content=img_bytes,
        media_type="image/png",
        headers={
            # Prevent browsers/print-to-PDF flows from reusing stale cached images
            # after manual ROI updates or re-runs.
            "Cache-Control": "no-store, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@router.post("/analyze", response_model=DecompositionResponse)
async def decompose_plan(
    file: UploadFile = File(..., description="Architectural plan file (PNG, JPG, PDF)"),
    project_id: str = Form(..., description="Project identifier"),
    validation_id: Optional[str] = Form(None, description="Optional validation ID"),
):
    """Decompose architectural plan into segments using GPT-5.1.
    
    This endpoint:
    1. Converts DWF/DWFX to PNG if needed
    2. Analyzes the full plan with GPT-5.1
    3. Identifies all segments/sheets in the plan
    4. Extracts metadata from legend
    5. Returns decomposition for user review
    
    Args:
        file: Uploaded architectural plan
        project_id: Project identifier
        validation_id: Optional validation ID (auto-generated if not provided)
        
    Returns:
        DecompositionResponse with decomposition ID and status
        
    Raises:
        HTTPException: If decomposition fails
    """
    logger.info("Received decomposition request",
               project_id=project_id,
               filename=file.filename)
    
    try:
        # Generate validation ID if not provided
        if not validation_id:
            validation_id = f"val-{uuid.uuid4()}"
        
        # Read file content
        file_content = await file.read()
        file_size_mb = len(file_content) / (1024 * 1024)
        
        logger.info("Processing file",
                   filename=file.filename,
                   size_mb=f"{file_size_mb:.2f}")
        
        # Convert file to PNG if needed (DWF, PDF, etc.)
        from src.utils.file_converter import convert_to_image_if_needed
        
        try:
            plan_image_bytes, processed_filename, was_converted = convert_to_image_if_needed(
                file_content,
                file.filename
            )
            
            if was_converted:
                logger.info("File converted successfully",
                           original=file.filename,
                           converted=processed_filename)
        except ValueError as conv_error:
            logger.error("File conversion failed", error=str(conv_error))
            raise HTTPException(
                status_code=400,
                detail=str(conv_error)
            )
        except Exception as conv_error:
            logger.error("File conversion failed unexpectedly", error=str(conv_error))
            raise HTTPException(
                status_code=500,
                detail=f"שגיאה בלתי צפויה בהמרת קובץ: {str(conv_error)}"
            )
        
        # Save to temp file for processing
        temp_dir = tempfile.mkdtemp()
        temp_image_path = os.path.join(temp_dir, "full_plan.png")
        
        with open(temp_image_path, 'wb') as f:
            f.write(plan_image_bytes)
        
        logger.info("Temp file created", path=temp_image_path)
        
        # Manual-only mode: do NOT run automatic segmentation.
        # We only upload the full plan and let the user define ROIs manually.
        from PIL import Image

        with Image.open(BytesIO(plan_image_bytes)) as img:
            actual_width, actual_height = img.size

        decomp_id = f"decomp-{uuid.uuid4()}"
        decomposition = PlanDecomposition(
            id=decomp_id,
            validation_id=validation_id,
            project_id=project_id,
            status=DecompositionStatus.REVIEW_NEEDED,
            full_plan_url=f"https://placeholder.blob.core.windows.net/{validation_id}/full_plan.png",
            full_plan_width=actual_width,
            full_plan_height=actual_height,
            file_size_mb=file_size_mb,
            metadata=ProjectMetadata(),
            segments=[],
            processing_stats=ProcessingStats(
                total_segments=0,
                processing_time_seconds=0.0,
                llm_tokens_used=0,
            ),
        )
        
        # Upload full plan (no segments to crop)
        decomposition_service = get_decomposition_service()
        logger.info(
            "Uploading full plan (manual ROI mode)",
            decomposition_id=decomposition.id,
        )
        decomposition = await decomposition_service.crop_and_upload_segments(
            decomposition=decomposition,
            plan_image_path=temp_image_path,
        )
        
        # Cleanup temp file
        try:
            os.remove(temp_image_path)
            os.rmdir(temp_dir)
        except Exception as cleanup_error:
            logger.warning("Failed to cleanup temp files", error=str(cleanup_error))
        
        # Save to Cosmos DB
        logger.info("Saving decomposition to Cosmos DB",
                   decomposition_id=decomposition.id)
        cosmos_client = get_cosmos_client()
        
        # Add project_id for partitioning
        decomp_dict = decomposition.model_dump(mode='json')
        decomp_dict["project_id"] = project_id
        decomp_dict["type"] = "decomposition"  # Document type
        
        await cosmos_client.create_item(decomp_dict)
        
        logger.info(
            "Decomposition saved successfully (manual ROI mode)",
            decomposition_id=decomposition.id,
            segments_count=len(decomposition.segments),
        )
        
        return DecompositionResponse(
            decomposition_id=decomposition.id,
            status=decomposition.status,
            estimated_time_seconds=60,
            message="התוכנית נטענה בהצלחה. בחר אזורים ידנית על גבי התוכנית כדי ליצור סגמנטים לבדיקה."
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Decomposition failed",
                    error=str(e),
                    filename=file.filename)
        raise HTTPException(
            status_code=500,
            detail=f"שגיאה בפירוק התוכנית: {str(e)}"
        )


@router.get("/{decomposition_id}", response_model=PlanDecomposition)
async def get_decomposition(decomposition_id: str):
    """Get decomposition by ID.
    
    Args:
        decomposition_id: Decomposition ID
        
    Returns:
        PlanDecomposition object
        
    Raises:
        HTTPException: If not found
    """
    logger.info("Fetching decomposition", decomposition_id=decomposition_id)
    
    try:
        cosmos_client = get_cosmos_client()
        
        # Query Cosmos DB
        query = """
            SELECT * FROM c 
            WHERE c.id = @decomposition_id 
            AND c.type = 'decomposition'
        """
        
        items = await cosmos_client.query_items(
            query=query,
            parameters=[
                {"name": "@decomposition_id", "value": decomposition_id}
            ]
        )
        
        if not items:
            raise HTTPException(
                status_code=404,
                detail=f"פירוק לא נמצא: {decomposition_id}"
            )
        
        # Convert to PlanDecomposition
        decomp_data = items[0]
        decomposition = PlanDecomposition(**decomp_data)
        
        logger.info("Decomposition found",
                   decomposition_id=decomposition_id,
                   segments=len(decomposition.segments))
        
        return decomposition
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to fetch decomposition",
                    decomposition_id=decomposition_id,
                    error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"שגיאה בטעינת הפירוק: {str(e)}"
        )


@router.post("/{decomposition_id}/segments/analyze", response_model=PlanDecomposition)
async def analyze_decomposition_segments(
    decomposition_id: str,
    request: AnalyzeSegmentsRequest,
):
    """Analyze/classify selected segments right after decomposition.

    This runs GPT analysis per segment (classification + extraction) and stores the
    resulting payload on each segment under `analysis_data` for UI transparency.

    Note: This does NOT run compliance validation.
    """

    logger.info(
        "Analyzing decomposition segments",
        decomposition_id=decomposition_id,
        segment_count=len(request.segment_ids),
    )

    try:
        cosmos_client = get_cosmos_client()

        query = """
            SELECT * FROM c
            WHERE c.id = @decomposition_id
            AND c.type = 'decomposition'
        """

        items = await cosmos_client.query_items(
            query=query,
            parameters=[{"name": "@decomposition_id", "value": decomposition_id}],
        )

        if not items:
            raise HTTPException(status_code=404, detail="פירוק לא נמצא")

        decomp_data = items[0]
        analyzer = SegmentAnalyzer()
        segment_ids = set(request.segment_ids)

        updated = 0
        for seg_doc in decomp_data.get("segments", []):
            seg_id = seg_doc.get("segment_id")
            if not seg_id or seg_id not in segment_ids:
                continue

            result = await analyzer.analyze_segment(
                segment_id=seg_id,
                segment_blob_url=seg_doc.get("blob_url", ""),
                segment_type=str(seg_doc.get("type", "unknown")),
                segment_description=seg_doc.get("description", ""),
            )

            if result.get("status") == "analyzed" and result.get("analysis_data"):
                seg_doc["analysis_data"] = result.get("analysis_data")
                updated += 1
            else:
                seg_doc["analysis_data"] = {
                    "status": "error",
                    "error": result.get("error") or "Analysis failed",
                }

        decomp_data["updated_at"] = datetime.utcnow().isoformat()
        if updated > 0:
            decomp_data["status"] = DecompositionStatus.REVIEW_NEEDED.value

        await cosmos_client.upsert_item(decomp_data)

        logger.info(
            "Segment analysis stored",
            decomposition_id=decomposition_id,
            updated_segments=updated,
        )

        return decomp_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to analyze decomposition segments",
            decomposition_id=decomposition_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail=f"שגיאה בניתוח סגמנטים: {str(e)}",
        )


@router.patch("/{decomposition_id}/segments/{segment_id}")
async def update_segment(
    decomposition_id: str,
    segment_id: str,
    update: SegmentUpdateRequest
):
    """Update a segment's properties.
    
    Args:
        decomposition_id: Decomposition ID
        segment_id: Segment ID
        update: Update data
        
    Returns:
        Updated decomposition
        
    Raises:
        HTTPException: If not found or update fails
    """
    logger.info("Updating segment",
               decomposition_id=decomposition_id,
               segment_id=segment_id)
    
    try:
        cosmos_client = get_cosmos_client()
        
        # Get current decomposition
        query = """
            SELECT * FROM c 
            WHERE c.id = @decomposition_id 
            AND c.type = 'decomposition'
        """
        
        items = await cosmos_client.query_items(
            query=query,
            parameters=[
                {"name": "@decomposition_id", "value": decomposition_id}
            ]
        )
        
        if not items:
            raise HTTPException(status_code=404, detail="פירוק לא נמצא")
        
        decomp_data = items[0]
        
        # Find and update segment
        segment_found = False
        for segment in decomp_data.get("segments", []):
            if segment.get("segment_id") == segment_id:
                segment_found = True
                
                # Update fields
                if update.title is not None:
                    segment["title"] = update.title
                if update.description is not None:
                    segment["description"] = update.description
                if update.type is not None:
                    segment["type"] = update.type.value
                if update.approved is not None:
                    segment["approved_by_user"] = update.approved
                
                break
        
        if not segment_found:
            raise HTTPException(status_code=404, detail="סגמנט לא נמצא")
        
        # Update status
        decomp_data["status"] = DecompositionStatus.REVIEW_NEEDED.value
        
        # Save back to Cosmos DB
        await cosmos_client.upsert_item(decomp_data)
        
        logger.info("Segment updated successfully",
                   segment_id=segment_id)
        
        return decomp_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update segment",
                    error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"שגיאה בעדכון הסגמנט: {str(e)}"
        )


@router.post("/{decomposition_id}/manual-segments")
async def add_manual_segments(
    decomposition_id: str,
    request: AddManualSegmentsRequest,
):
    """Append manual ROI segments to an existing decomposition (additive).

    The client sends ROIs in relative coordinates (0..1). The server converts them
    to pixel bounding boxes using the stored full plan dimensions, crops them from
    the stored full plan image, uploads the crops/thumbnails, and appends them as
    additional segments.
    """

    logger.info(
        "Adding manual segments",
        decomposition_id=decomposition_id,
        rois_count=len(request.rois),
    )

    try:
        cosmos_client = get_cosmos_client()

        query = """
            SELECT * FROM c
            WHERE c.id = @decomposition_id
            AND c.type = 'decomposition'
        """

        items = await cosmos_client.query_items(
            query=query,
            parameters=[
                {"name": "@decomposition_id", "value": decomposition_id},
            ],
        )

        if not items:
            raise HTTPException(status_code=404, detail="פירוק לא נמצא")

        decomp_data = items[0]
        decomposition = PlanDecomposition(**decomp_data)

        if decomposition.full_plan_width <= 0 or decomposition.full_plan_height <= 0:
            raise HTTPException(status_code=400, detail="ממדי התוכנית אינם זמינים")

        validation_id = decomposition.validation_id
        if not validation_id:
            raise HTTPException(status_code=400, detail="validation_id חסר בפירוק")

        existing_ids = {s.get("segment_id") for s in decomp_data.get("segments", [])}
        next_index = 1
        while f"manual_{next_index:03d}" in existing_ids:
            next_index += 1

        new_segments: list[PlanSegment] = []
        for roi in request.rois:
            seg_id = f"manual_{next_index:03d}"
            next_index += 1

            # Convert relative ROI (0..1) to pixel bbox
            x = float(roi.x) * float(decomposition.full_plan_width)
            y = float(roi.y) * float(decomposition.full_plan_height)
            w = float(roi.width) * float(decomposition.full_plan_width)
            h = float(roi.height) * float(decomposition.full_plan_height)

            # Clamp to image bounds
            x = max(0.0, min(float(decomposition.full_plan_width), x))
            y = max(0.0, min(float(decomposition.full_plan_height), y))
            w = max(1.0, min(float(decomposition.full_plan_width) - x, w))
            h = max(1.0, min(float(decomposition.full_plan_height) - y, h))

            bbox = BoundingBox(x=x, y=y, width=w, height=h)

            new_segments.append(
                PlanSegment(
                    segment_id=seg_id,
                    type=SegmentType.UNKNOWN,
                    title=f"אזור ידני {len(new_segments) + 1}",
                    description="אזור נבחר ידנית לבחינה",
                    bounding_box=bbox,
                    blob_url=f"https://placeholder.blob.core.windows.net/{validation_id}/segments/{seg_id}.png",
                    thumbnail_url=f"https://placeholder.blob.core.windows.net/{validation_id}/segments/{seg_id}_thumb.png",
                    confidence=1.0,
                    llm_reasoning="MANUAL_ROI",
                    approved_by_user=True,
                    used_in_checks=[],
                )
            )

        # Download the stored full plan image and crop only the new segments
        blob_client = get_blob_client()
        full_plan_blob_name = f"{validation_id}/full_plan.png"
        try:
            with anyio.fail_after(60):
                full_plan_bytes = await blob_client.download_blob(full_plan_blob_name)
        except Exception as e:
            logger.error(
                "Failed to download full plan for manual cropping",
                decomposition_id=decomposition_id,
                blob_name=full_plan_blob_name,
                error=str(e),
            )
            raise HTTPException(status_code=500, detail="שגיאה בטעינת התוכנית המלאה לחיתוך")

        temp_dir = tempfile.mkdtemp()
        temp_image_path = os.path.join(temp_dir, "full_plan.png")
        with open(temp_image_path, "wb") as f:
            f.write(full_plan_bytes)

        try:
            # Lightweight crop/upload for manual ROIs: no OpenCV refinement and no full-plan re-upload.
            cropper = get_image_cropper()

            for seg in new_segments:
                bbox = seg.bounding_box
                w = float(bbox.width)
                h = float(bbox.height)

                pad = float(max(4.0, min(40.0, min(w, h) * 0.02)))
                crop_bbox = {
                    "x": max(0.0, float(bbox.x) - pad),
                    "y": max(0.0, float(bbox.y) - pad),
                    "width": min(float(decomposition.full_plan_width) - max(0.0, float(bbox.x) - pad), w + 2 * pad),
                    "height": min(float(decomposition.full_plan_height) - max(0.0, float(bbox.y) - pad), h + 2 * pad),
                }

                cropped_buffer, thumb_buffer = cropper.crop_and_create_thumbnail(
                    image_path=temp_image_path,
                    bounding_box=crop_bbox,
                )

                segment_blob = f"{validation_id}/segments/{seg.segment_id}.png"
                with anyio.fail_after(60):
                    segment_url = await blob_client.upload_blob(
                        blob_name=segment_blob,
                        data=cropped_buffer,
                        overwrite=True,
                    )

                thumb_blob = f"{validation_id}/segments/{seg.segment_id}_thumb.png"
                with anyio.fail_after(60):
                    thumb_url = await blob_client.upload_blob(
                        blob_name=thumb_blob,
                        data=thumb_buffer,
                        overwrite=True,
                    )

                seg.blob_url = segment_url
                seg.thumbnail_url = thumb_url
        finally:
            try:
                os.remove(temp_image_path)
                os.rmdir(temp_dir)
            except Exception:
                pass

        # Append new segments to existing decomposition document

        appended = 0
        for seg in new_segments:
            decomp_data.setdefault("segments", []).append(seg.model_dump(mode="json"))
            appended += 1

        decomp_data["status"] = DecompositionStatus.REVIEW_NEEDED.value
        decomp_data["updated_at"] = datetime.utcnow().isoformat()

        # Keep stats in sync
        if isinstance(decomp_data.get("processing_stats"), dict):
            decomp_data["processing_stats"]["total_segments"] = len(decomp_data.get("segments", []))

        await cosmos_client.upsert_item(decomp_data)

        logger.info(
            "Manual segments appended",
            decomposition_id=decomposition_id,
            appended=appended,
            total_segments=len(decomp_data.get("segments", [])),
        )

        return decomp_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to add manual segments",
            decomposition_id=decomposition_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail=f"שגיאה בהוספת סגמנטים ידניים: {str(e)}",
        )


@router.patch("/{decomposition_id}/segments/{segment_id}/bbox")
async def update_segment_bbox(
    decomposition_id: str,
    segment_id: str,
    roi: ManualRoi,
):
    """Update a segment bounding box (used for manual ROI resizing).

    Accepts ROI in relative coords (0..1), converts to pixel bbox, re-crops from the
    stored full plan image, overwrites the segment blob + thumbnail, and updates the
    decomposition document.
    """

    logger.info(
        "Updating segment bbox",
        decomposition_id=decomposition_id,
        segment_id=segment_id,
    )

    try:
        cosmos_client = get_cosmos_client()

        query = """
            SELECT * FROM c
            WHERE c.id = @decomposition_id
            AND c.type = 'decomposition'
        """

        items = await cosmos_client.query_items(
            query=query,
            parameters=[
                {"name": "@decomposition_id", "value": decomposition_id},
            ],
        )

        if not items:
            raise HTTPException(status_code=404, detail="פירוק לא נמצא")

        decomp_data = items[0]
        decomposition = PlanDecomposition(**decomp_data)

        if decomposition.full_plan_width <= 0 or decomposition.full_plan_height <= 0:
            raise HTTPException(status_code=400, detail="ממדי התוכנית אינם זמינים")

        validation_id = decomposition.validation_id
        if not validation_id:
            raise HTTPException(status_code=400, detail="validation_id חסר בפירוק")

        # Find segment
        segment_idx: Optional[int] = None
        segments_list = decomp_data.get("segments", [])
        for idx, seg in enumerate(segments_list):
            if seg.get("segment_id") == segment_id:
                segment_idx = idx
                break

        if segment_idx is None:
            raise HTTPException(status_code=404, detail="סגמנט לא נמצא")

        # Convert relative ROI (0..1) to pixel bbox
        x = float(roi.x) * float(decomposition.full_plan_width)
        y = float(roi.y) * float(decomposition.full_plan_height)
        w = float(roi.width) * float(decomposition.full_plan_width)
        h = float(roi.height) * float(decomposition.full_plan_height)

        # Clamp
        x = max(0.0, min(float(decomposition.full_plan_width), x))
        y = max(0.0, min(float(decomposition.full_plan_height), y))
        w = max(1.0, min(float(decomposition.full_plan_width) - x, w))
        h = max(1.0, min(float(decomposition.full_plan_height) - y, h))

        pixel_bbox = {"x": x, "y": y, "width": w, "height": h}

        # Download full plan
        blob_client = get_blob_client()
        full_plan_blob_name = f"{validation_id}/full_plan.png"
        try:
            with anyio.fail_after(60):
                full_plan_bytes = await blob_client.download_blob(full_plan_blob_name)
        except Exception as e:
            logger.error(
                "Failed to download full plan for bbox update",
                decomposition_id=decomposition_id,
                blob_name=full_plan_blob_name,
                error=str(e),
            )
            raise HTTPException(status_code=500, detail="שגיאה בטעינת התוכנית המלאה לחיתוך")

        temp_dir = tempfile.mkdtemp()
        temp_image_path = os.path.join(temp_dir, "full_plan.png")
        with open(temp_image_path, "wb") as f:
            f.write(full_plan_bytes)

        try:
            # Crop + thumbnail
            cropper = get_image_cropper()

            pad = float(max(4.0, min(40.0, min(w, h) * 0.02)))
            crop_bbox = {
                "x": max(0.0, x - pad),
                "y": max(0.0, y - pad),
                "width": min(float(decomposition.full_plan_width) - max(0.0, x - pad), w + 2 * pad),
                "height": min(float(decomposition.full_plan_height) - max(0.0, y - pad), h + 2 * pad),
            }

            cropped_buffer, thumb_buffer = cropper.crop_and_create_thumbnail(
                image_path=temp_image_path,
                bounding_box=crop_bbox,
            )

            # Overwrite blob + thumb
            segment_blob = f"{validation_id}/segments/{segment_id}.png"
            with anyio.fail_after(60):
                segment_url = await blob_client.upload_blob(
                    blob_name=segment_blob,
                    data=cropped_buffer,
                    overwrite=True,
                )

            thumb_blob = f"{validation_id}/segments/{segment_id}_thumb.png"
            with anyio.fail_after(60):
                thumb_url = await blob_client.upload_blob(
                    blob_name=thumb_blob,
                    data=thumb_buffer,
                    overwrite=True,
                )
        finally:
            try:
                os.remove(temp_image_path)
                os.rmdir(temp_dir)
            except Exception:
                pass

        # Update document segment fields
        seg_doc = segments_list[segment_idx]
        seg_doc["bounding_box"] = BoundingBox(**pixel_bbox).model_dump()
        seg_doc["blob_url"] = segment_url
        seg_doc["thumbnail_url"] = thumb_url
        seg_doc["approved_by_user"] = True
        seg_doc["llm_reasoning"] = seg_doc.get("llm_reasoning") or "MANUAL_ROI"

        decomp_data["segments"] = segments_list
        decomp_data["status"] = DecompositionStatus.REVIEW_NEEDED.value
        decomp_data["updated_at"] = datetime.utcnow().isoformat()

        await cosmos_client.upsert_item(decomp_data)

        logger.info(
            "Segment bbox updated",
            decomposition_id=decomposition_id,
            segment_id=segment_id,
        )

        return decomp_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to update segment bbox",
            decomposition_id=decomposition_id,
            segment_id=segment_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail=f"שגיאה בעדכון אזור הסגמנט: {str(e)}",
        )


@router.post("/{decomposition_id}/approve")
async def approve_decomposition(
    decomposition_id: str,
    approval: ApprovalRequest
):
    """Approve decomposition and start validation process.
    
    Args:
        decomposition_id: Decomposition ID
        approval: Approval data with selected segments
        
    Returns:
        Success message
        
    Raises:
        HTTPException: If approval fails
    """
    logger.info("Approving decomposition",
               decomposition_id=decomposition_id,
               approved_count=len(approval.approved_segments))
    
    try:
        cosmos_client = get_cosmos_client()
        
        # Get decomposition
        query = """
            SELECT * FROM c 
            WHERE c.id = @decomposition_id 
            AND c.type = 'decomposition'
        """
        
        items = await cosmos_client.query_items(
            query=query,
            parameters=[
                {"name": "@decomposition_id", "value": decomposition_id}
            ]
        )
        
        if not items:
            raise HTTPException(status_code=404, detail="פירוק לא נמצא")
        
        decomp_data = items[0]
        
        # Update segment approval status
        for segment in decomp_data.get("segments", []):
            seg_id = segment.get("segment_id")
            if seg_id in approval.approved_segments:
                segment["approved_by_user"] = True
            elif seg_id in approval.rejected_segments:
                segment["approved_by_user"] = False
        
        # Update metadata if provided
        if approval.custom_metadata:
            decomp_data["metadata"] = approval.custom_metadata.model_dump()
        
        # Update status
        decomp_data["status"] = "approved"
        
        # Save
        await cosmos_client.upsert_item(decomp_data)
        
        logger.info("Decomposition approved",
                   decomposition_id=decomposition_id)
        
        return {
            "success": True,
            "message": f"הפירוק אושר בהצלחה. {len(approval.approved_segments)} סגמנטים נבחרו.",
            "validation_id": decomp_data.get("validation_id")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to approve decomposition",
                    error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"שגיאה באישור הפירוק: {str(e)}"
        )
