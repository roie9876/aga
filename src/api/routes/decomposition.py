"""API endpoints for plan decomposition."""
import uuid
import tempfile
import os
from pathlib import Path
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from typing import Optional

from src.models.decomposition import (
    PlanDecomposition,
    DecompositionResponse,
    DecompositionStatus,
    SegmentUpdateRequest,
    ApprovalRequest,
)
from src.services.plan_decomposition import get_decomposition_service
from src.azure import get_cosmos_client
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
        
        # Convert DWF/DWFX to PNG if needed
        from src.utils.file_converter import convert_dwf_to_image, is_dwf_file
        
        if is_dwf_file(file.filename):
            logger.info("Converting DWF/DWFX to PNG", filename=file.filename)
            try:
                plan_image_bytes, converted_filename = convert_dwf_to_image(
                    file_content, 
                    file.filename
                )
                logger.info("DWF conversion successful", 
                           original=file.filename,
                           converted=converted_filename)
            except Exception as conv_error:
                logger.error("DWF conversion failed", error=str(conv_error))
                raise HTTPException(
                    status_code=400,
                    detail=f"שגיאה בהמרת קובץ DWF: {str(conv_error)}. אנא וודא שהקובץ תקין."
                )
        else:
            plan_image_bytes = file_content
        
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
