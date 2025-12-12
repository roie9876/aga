"""API endpoints for plan decomposition."""
import uuid
import tempfile
import os
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from typing import Optional

from src.models.decomposition import (
    PlanDecomposition,
    DecompositionResponse,
    DecompositionStatus,
    SegmentUpdateRequest,
    ApprovalRequest,
    AddManualSegmentsRequest,
    PlanSegment,
    SegmentType,
    BoundingBox,
    ManualRoi,
)
from src.services.plan_decomposition import get_decomposition_service
from src.azure import get_cosmos_client
from src.azure.blob_client import get_blob_client
from src.utils.image_cropper import get_image_cropper
from src.utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/decomposition", tags=["decomposition"])


@router.post("/analyze", response_model=DecompositionResponse)
async def decompose_plan(
    file: UploadFile = File(..., description="Architectural plan file (DWF, DWFX, PNG, JPG, PDF)"),
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
        
        # Decompose plan
        decomposition_service = get_decomposition_service()
        decomposition = decomposition_service.decompose_plan(
            validation_id=validation_id,
            project_id=project_id,
            plan_image_bytes=plan_image_bytes,
            file_size_mb=file_size_mb
        )

        # If the service returned a FAILED decomposition, surface it as an HTTP error
        if decomposition.error_message or decomposition.status == DecompositionStatus.FAILED:
            raise HTTPException(
                status_code=500,
                detail=f"שגיאה בפירוק התוכנית: {decomposition.error_message or 'Unknown error'}",
            )
        
        # Crop and upload segments
        logger.info("Cropping and uploading segments",
                   decomposition_id=decomposition.id)
        decomposition = await decomposition_service.crop_and_upload_segments(
            decomposition=decomposition,
            plan_image_path=temp_image_path
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
        
        logger.info("Decomposition saved successfully",
                   decomposition_id=decomposition.id,
                   segments_count=len(decomposition.segments))
        
        return DecompositionResponse(
            decomposition_id=decomposition.id,
            status=decomposition.status,
            estimated_time_seconds=60,
            message=f"פירוק התוכנית הושלם בהצלחה. זוהו {len(decomposition.segments)} סגמנטים."
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
            decomposition_service = get_decomposition_service()

            manual_decomposition = PlanDecomposition(
                id=decomposition.id,
                validation_id=decomposition.validation_id,
                project_id=decomposition.project_id,
                status=decomposition.status,
                full_plan_url=decomposition.full_plan_url,
                full_plan_width=decomposition.full_plan_width,
                full_plan_height=decomposition.full_plan_height,
                file_size_mb=decomposition.file_size_mb,
                metadata=decomposition.metadata,
                segments=new_segments,
                processing_stats=decomposition.processing_stats,
            )

            manual_decomposition = await decomposition_service.crop_and_upload_segments(
                decomposition=manual_decomposition,
                plan_image_path=temp_image_path,
            )
        finally:
            try:
                os.remove(temp_image_path)
                os.rmdir(temp_dir)
            except Exception:
                pass

        # Append new segments to existing decomposition document
        decomp_data["full_plan_url"] = manual_decomposition.full_plan_url

        appended = 0
        for seg in manual_decomposition.segments:
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
            segment_url = await blob_client.upload_blob(
                blob_name=segment_blob,
                data=cropped_buffer,
                overwrite=True,
            )

            thumb_blob = f"{validation_id}/segments/{segment_id}_thumb.png"
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
