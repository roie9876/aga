"""API endpoints for plan decomposition."""
import asyncio
import uuid
import tempfile
import os
import json
from datetime import datetime
from pathlib import Path
from io import BytesIO
import anyio
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import Response, StreamingResponse
from typing import Optional
from PIL import Image
from pydantic import BaseModel, Field

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
from src.config import settings
from src.services.plan_decomposition import get_decomposition_service
from src.azure import get_cosmos_client
from src.azure.blob_client import get_blob_client
from src.utils.image_cropper import get_image_cropper
from src.utils.logging import get_logger
from src.segmentation.auto_segmenter import (
    SegmenterConfig,
    segment_image,
    DependencyError,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/decomposition", tags=["decomposition"])


class AutoSegmentationRequest(BaseModel):
    """Request payload for automatic segmentation."""

    mode: str = Field("cv", description="Segmentation mode: cv | llm")
    auto_tune: bool = Field(False, description="Try multiple CV settings and auto-pick best")
    target_segments: int = Field(12, description="Target segment count for auto-tune scoring")
    verify_with_llm: bool = Field(False, description="Use GPT-5.1 to drop empty/blank regions")
    replace_existing: bool = Field(True, description="Replace existing segments if present")
    ocr_enabled: bool = Field(True, description="Enable OCR on candidate crops")
    max_dim: int = Field(4200, description="Max image dimension for detection")
    min_area_ratio: float = Field(0.005, description="Minimum area ratio for proposals")
    max_area_ratio: float = Field(0.55, description="Maximum area ratio for proposals")
    merge_iou_threshold: float = Field(0.20, description="IoU threshold for merging boxes")
    deskew: bool = Field(False, description="Enable deskew before segmentation")
    adaptive_block_size: Optional[int] = Field(None, description="Adaptive threshold block size")
    adaptive_c: Optional[int] = Field(None, description="Adaptive threshold C")
    close_kernel: Optional[int] = Field(None, description="Morph close kernel size")
    close_iterations: Optional[int] = Field(None, description="Morph close iterations")
    projection_density_threshold: Optional[float] = Field(None, description="Projection density threshold")
    projection_min_gap: Optional[int] = Field(None, description="Projection minimum gap")
    split_large_area_ratio: Optional[float] = Field(None, description="Split large area ratio")
    split_large_min_boxes: Optional[int] = Field(None, description="Split large min boxes")
    line_kernel_scale: Optional[int] = Field(None, description="Line kernel scale")
    line_merge_iterations: Optional[int] = Field(None, description="Line merge iterations")
    separator_line_density: Optional[float] = Field(None, description="Separator line density")
    separator_min_line_width: Optional[int] = Field(None, description="Separator minimum line width")
    separator_min_gap: Optional[int] = Field(None, description="Separator minimum gap")
    separator_min_height_ratio: Optional[float] = Field(None, description="Separator minimum height ratio")
    separator_max_width: Optional[int] = Field(None, description="Separator maximum width")
    hough_threshold: Optional[int] = Field(None, description="Hough threshold")
    hough_min_line_length_ratio: Optional[float] = Field(None, description="Hough min line length ratio")
    hough_max_line_gap: Optional[int] = Field(None, description="Hough max line gap")
    hough_cluster_px: Optional[int] = Field(None, description="Hough cluster px")
    min_ink_ratio: Optional[float] = Field(None, description="Min ink ratio")
    min_ink_pixels: Optional[int] = Field(None, description="Min ink pixels")
    min_segment_width_ratio: Optional[float] = Field(None, description="Min segment width ratio")
    content_crop_enabled: Optional[bool] = Field(None, description="Enable content crop")
    content_crop_pad: Optional[int] = Field(None, description="Content crop pad")
    content_density_threshold: Optional[float] = Field(None, description="Content density threshold")
    content_min_span_ratio: Optional[float] = Field(None, description="Content minimum span ratio")
    edge_refine_enabled: Optional[bool] = Field(None, description="Enable edge refine")
    edge_refine_pad: Optional[int] = Field(None, description="Edge refine pad")
    refine_by_content: Optional[bool] = Field(None, description="Refine by content")
    refine_pad: Optional[int] = Field(None, description="Refine pad")


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
    file: UploadFile = File(..., description="Architectural plan file (PNG, JPG, PDF, DWF, DWFX)"),
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
        from src.utils.file_converter import convert_to_image_if_needed, get_file_type
        source_file_type = get_file_type(file.filename)
        source_file_url = None
        source_file_name = file.filename
        
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

        # Store original source file (PDF/DWF) for high-res cropping if available.
        try:
            if source_file_type in {"pdf", "dwf"}:
                blob_client = get_blob_client()
                source_blob = f"{validation_id}/source/{file.filename}"
                source_file_url = await blob_client.upload_blob(
                    blob_name=source_blob,
                    data=BytesIO(file_content),
                )
                logger.info(
                    "Source file uploaded",
                    source_type=source_file_type,
                    source_url=source_file_url[:100] + "...",
                )
        except Exception as src_error:
            logger.warning("Failed to upload source file", error=str(src_error))
        
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
            source_file_url=source_file_url,
            source_file_type=source_file_type,
            source_file_name=source_file_name,
            metadata=ProjectMetadata(),
            segments=[],
            processing_stats=ProcessingStats(
                total_segments=0,
                processing_time_seconds=0.0,
                llm_tokens_used=0,
            ),
        )
        
        # Optionally persist a local copy for troubleshooting
        try:
            export_dir = settings.full_plan_local_export_dir or str(Path.cwd() / "tmp" / "full_plan_exports")
            os.makedirs(export_dir, exist_ok=True)
            local_export_path = os.path.join(export_dir, f"{decomp_id}.png")
            with open(local_export_path, "wb") as f:
                f.write(plan_image_bytes)
            logger.info(
                "Saved local full plan copy",
                decomposition_id=decomp_id,
                local_path=local_export_path,
            )

            # Optional: tile the full-plan image into smaller PNGs for zoomed inspection.
            if bool(settings.dwf_tiling_enabled):
                tile_size = int(settings.dwf_tile_size)
                overlap = int(settings.dwf_tile_overlap)
                step = max(1, tile_size - overlap)
                tiles_dir = os.path.join(export_dir, f"{decomp_id}_tiles")
                os.makedirs(tiles_dir, exist_ok=True)

                with Image.open(BytesIO(plan_image_bytes)) as img:
                    crop_img = img
                    if bool(settings.dwf_tile_crop_enabled):
                        try:
                            gray = img.convert("L")
                            threshold = int(settings.dwf_tile_crop_threshold)
                            mask = gray.point(lambda p: 255 if p < threshold else 0)
                            bbox = mask.getbbox()
                            if bbox:
                                crop_img = img.crop(bbox)
                                crop_path = os.path.join(export_dir, f"{decomp_id}_cropped.png")
                                crop_img.save(crop_path, format="PNG", optimize=True)
                                logger.info(
                                    "Saved cropped full plan copy",
                                    decomposition_id=decomp_id,
                                    local_path=crop_path,
                                    bbox=bbox,
                                )
                        except Exception as crop_error:
                            logger.warning(
                                "Failed to crop full plan image",
                                decomposition_id=decomp_id,
                                error=str(crop_error),
                            )

                    img = crop_img
                    width, height = img.size
                    row = 0
                    for y in range(0, height, step):
                        col = 0
                        for x in range(0, width, step):
                            box = (x, y, min(x + tile_size, width), min(y + tile_size, height))
                            tile = img.crop(box)
                            tile_path = os.path.join(tiles_dir, f"tile_r{row:03d}_c{col:03d}.png")
                            tile.save(tile_path, format="PNG", optimize=True)
                            col += 1
                        row += 1

                logger.info(
                    "Saved tiled full plan copies",
                    decomposition_id=decomp_id,
                    tiles_dir=tiles_dir,
                    tile_size=tile_size,
                    overlap=overlap,
                )
            else:
                logger.info(
                    "Tiling disabled; only full plan saved",
                    decomposition_id=decomp_id,
                )
        except Exception as export_error:
            logger.warning(
                "Failed to save local full plan copy",
                decomposition_id=decomp_id,
                error=str(export_error),
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

        # This endpoint can be called with many segments (e.g., when uploading a folder of
        # already-cropped images). Running GPT analysis strictly sequentially can take a
        # very long time, so we parallelize with a small concurrency limit.
        analysis_concurrency = max(1, int(getattr(settings, "segment_analysis_concurrency", 4)))
        analysis_timeout_seconds = max(30, int(getattr(settings, "segment_analysis_timeout_seconds", 300)))
        limiter = anyio.CapacityLimiter(analysis_concurrency)
        update_lock = anyio.Lock()
        updated = 0

        async def _analyze_one(seg_doc: dict) -> None:
            nonlocal updated
            seg_id = seg_doc.get("segment_id")
            if not seg_id:
                return

            async with limiter:
                try:
                    with anyio.fail_after(analysis_timeout_seconds):
                        result = await analyzer.analyze_segment(
                            segment_id=seg_id,
                            segment_blob_url=seg_doc.get("blob_url", ""),
                            segment_type=str(seg_doc.get("type", "unknown")),
                            segment_description=seg_doc.get("description", ""),
                        )
                except TimeoutError:
                    result = {"status": "error", "error": f"Analysis timeout אחרי {analysis_timeout_seconds} שניות"}
                except asyncio.CancelledError:
                    # Preserve cancellation semantics
                    raise
                except Exception as e:
                    result = {"status": "error", "error": str(e)}

            if result.get("status") == "analyzed" and result.get("analysis_data"):
                seg_doc["analysis_data"] = result.get("analysis_data")

                # Best-effort: if the analyzer inferred a primary drawing function,
                # persist it into the segment `type` so preflight/validation can use it.
                try:
                    ad = seg_doc.get("analysis_data")
                    summary = ad.get("summary") if isinstance(ad, dict) else None
                    primary_fn = summary.get("primary_function") if isinstance(summary, dict) else None
                    if isinstance(primary_fn, str):
                        primary_fn_norm = primary_fn.strip().lower()
                        if primary_fn_norm in {
                            SegmentType.FLOOR_PLAN.value,
                            SegmentType.SECTION.value,
                            SegmentType.DETAIL.value,
                            SegmentType.ELEVATION.value,
                        }:
                            current = str(seg_doc.get("type") or "unknown").strip().lower()
                            if current == SegmentType.UNKNOWN.value:
                                seg_doc["type"] = primary_fn_norm
                except Exception:
                    # Best-effort only: do not fail analysis if type mapping fails.
                    pass

                async with update_lock:
                    updated += 1
            else:
                seg_doc["analysis_data"] = {
                    "status": "error",
                    "error": result.get("error") or "Analysis failed",
                }

        async with anyio.create_task_group() as tg:
            for seg_doc in decomp_data.get("segments", []):
                seg_id = seg_doc.get("segment_id")
                if not seg_id or seg_id not in segment_ids:
                    continue
                tg.start_soon(_analyze_one, seg_doc)

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


@router.post("/{decomposition_id}/segments/analyze-stream")
async def analyze_decomposition_segments_stream(
    decomposition_id: str,
    request: AnalyzeSegmentsRequest,
):
    """Stream segment analysis progress as NDJSON.

    This endpoint is designed for realtime UX feedback (e.g., preflight stage),
    showing which segments are currently being analyzed and when they complete.

    Events are NDJSON lines with a `type` field.
    """

    logger.info(
        "Analyzing decomposition segments (stream)",
        decomposition_id=decomposition_id,
        segment_count=len(request.segment_ids),
    )

    async def _ndjson_streamer():
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
            # Stream a terminal error event instead of raising (better UX).
            yield json.dumps({"type": "error", "message": "פירוק לא נמצא"}, ensure_ascii=False) + "\n"
            return

        decomp_data = items[0]
        analyzer = SegmentAnalyzer()
        segment_ids = set(request.segment_ids or [])

        targets: list[dict] = []
        for seg_doc in decomp_data.get("segments", []):
            seg_id = seg_doc.get("segment_id")
            if not seg_id or (segment_ids and seg_id not in segment_ids):
                continue
            targets.append(seg_doc)

        total = len(targets)
        yield json.dumps({"type": "begin", "total": total}, ensure_ascii=False) + "\n"

        analysis_concurrency = max(1, int(os.getenv("SEGMENT_ANALYSIS_CONCURRENCY", "3")))
        analysis_timeout_seconds = max(30, int(os.getenv("SEGMENT_ANALYSIS_TIMEOUT_SECONDS", "300")))
        limiter = anyio.CapacityLimiter(analysis_concurrency)
        update_lock = anyio.Lock()

        send_stream, receive_stream = anyio.create_memory_object_stream(1000)

        updated = 0
        errors = 0

        async def _analyze_one(seg_doc: dict) -> None:
            nonlocal updated, errors
            seg_id = seg_doc.get("segment_id")
            if not seg_id:
                return

            async with limiter:
                await send_stream.send({"type": "segment_start", "segment_id": seg_id})
                try:
                    with anyio.fail_after(analysis_timeout_seconds):
                        result = await analyzer.analyze_segment(
                            segment_id=seg_id,
                            segment_blob_url=seg_doc.get("blob_url", ""),
                            segment_type=str(seg_doc.get("type", "unknown")),
                            segment_description=seg_doc.get("description", ""),
                        )
                except TimeoutError:
                    result = {"status": "error", "error": f"Analysis timeout אחרי {analysis_timeout_seconds} שניות"}
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    result = {"status": "error", "error": str(e)}

            inferred_type: Optional[str] = None
            if result.get("status") == "analyzed" and result.get("analysis_data"):
                seg_doc["analysis_data"] = result.get("analysis_data")

                # Best-effort: persist inferred primary function into segment type.
                try:
                    ad = seg_doc.get("analysis_data")
                    summary = ad.get("summary") if isinstance(ad, dict) else None
                    primary_fn = summary.get("primary_function") if isinstance(summary, dict) else None
                    if isinstance(primary_fn, str):
                        primary_fn_norm = primary_fn.strip().lower()
                        if primary_fn_norm in {
                            SegmentType.FLOOR_PLAN.value,
                            SegmentType.SECTION.value,
                            SegmentType.DETAIL.value,
                            SegmentType.ELEVATION.value,
                        }:
                            current = str(seg_doc.get("type") or "unknown").strip().lower()
                            if current == SegmentType.UNKNOWN.value:
                                seg_doc["type"] = primary_fn_norm
                                inferred_type = primary_fn_norm
                except Exception:
                    pass

                async with update_lock:
                    updated += 1
            else:
                seg_doc["analysis_data"] = {
                    "status": "error",
                    "error": result.get("error") or "Analysis failed",
                }
                async with update_lock:
                    errors += 1

            await send_stream.send(
                {
                    "type": "segment_done",
                    "segment_id": seg_id,
                    "status": "ok" if result.get("status") == "analyzed" else "error",
                    "error": result.get("error") if result.get("status") != "analyzed" else None,
                    "inferred_type": inferred_type,
                }
            )

        async def _producer() -> None:
            try:
                async with anyio.create_task_group() as tg:
                    for seg_doc in targets:
                        tg.start_soon(_analyze_one, seg_doc)
            finally:
                await send_stream.aclose()

        async with anyio.create_task_group() as tg:
            tg.start_soon(_producer)
            async with receive_stream:
                async for evt in receive_stream:
                    yield json.dumps(evt, ensure_ascii=False) + "\n"

        # Persist after streaming per-segment completions.
        decomp_data["updated_at"] = datetime.utcnow().isoformat()
        if updated > 0:
            decomp_data["status"] = DecompositionStatus.REVIEW_NEEDED.value
        await cosmos_client.upsert_item(decomp_data)

        yield json.dumps(
            {"type": "complete", "total": total, "updated_segments": updated, "errors": errors},
            ensure_ascii=False,
        ) + "\n"

    return StreamingResponse(
        _ndjson_streamer(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-store, max-age=0",
            "X-Accel-Buffering": "no",
        },
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
            crop_image_path = temp_image_path
            scale_x = 1.0
            scale_y = 1.0

            # If source is PDF, render a high-res copy for cropping to preserve detail.
            if (
                getattr(decomposition, "source_file_type", None) == "pdf"
                and getattr(decomposition, "source_file_url", None)
                and int(getattr(settings, "pdf_crop_render_dpi", 0)) > 0
            ):
                try:
                    import math
                    import requests
                    from pdf2image import convert_from_bytes

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
                        scale_x = float(image.width) / float(decomposition.full_plan_width or image.width)
                        scale_y = float(image.height) / float(decomposition.full_plan_height or image.height)

                        logger.info(
                            "Using high-res PDF render for manual cropping",
                            dpi=effective_dpi,
                            original_dimensions=f"{decomposition.full_plan_width}x{decomposition.full_plan_height}",
                            rendered_dimensions=f"{image.width}x{image.height}",
                            scale_x=scale_x,
                            scale_y=scale_y,
                        )
                except Exception as e:
                    logger.warning("Failed to render high-res PDF for manual cropping", error=str(e))

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

                crop_bbox_scaled = {
                    "x": crop_bbox["x"] * scale_x,
                    "y": crop_bbox["y"] * scale_y,
                    "width": crop_bbox["width"] * scale_x,
                    "height": crop_bbox["height"] * scale_y,
                }
                cropped_buffer, thumb_buffer = cropper.crop_and_create_thumbnail(
                    image_path=crop_image_path,
                    bounding_box=crop_bbox_scaled,
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


@router.post("/{decomposition_id}/auto-segments", response_model=PlanDecomposition)
async def auto_segment_decomposition(
    decomposition_id: str,
    request: AutoSegmentationRequest,
):
    """Automatically propose segments for a decomposition and attach crops."""
    logger.info(
        "Starting auto-segmentation",
        decomposition_id=decomposition_id,
        mode=request.mode,
        auto_tune=request.auto_tune,
        target_segments=request.target_segments,
        verify_with_llm=request.verify_with_llm,
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

        decomposition = PlanDecomposition(**items[0])
        if not decomposition.validation_id:
            raise HTTPException(status_code=400, detail="validation_id חסר בפירוק")

        blob_client = get_blob_client()
        blob_name = f"{decomposition.validation_id}/full_plan.png"

        try:
            with anyio.fail_after(120):
                img_bytes = await blob_client.download_blob(blob_name)
        except Exception as e:
            logger.error("Failed to download full plan", decomposition_id=decomposition_id, error=str(e))
            raise HTTPException(status_code=500, detail="שגיאה בטעינת התוכנית המלאה")

        with Image.open(BytesIO(img_bytes)) as img:
            low_image = img.convert("RGB")

        seg_image = low_image
        scale_x = 1.0
        scale_y = 1.0

        # If we have the original PDF, render a higher-res image for segmentation only.
        if (
            decomposition.source_file_type == "pdf"
            and decomposition.source_file_url
            and int(getattr(settings, "pdf_crop_render_dpi", 0)) > 0
        ):
            try:
                import httpx
                from pdf2image import convert_from_bytes
                import math

                async def _fetch_pdf() -> bytes:
                    async with httpx.AsyncClient(timeout=60.0) as client:
                        resp = await client.get(decomposition.source_file_url)
                        resp.raise_for_status()
                        return resp.content

                pdf_bytes = await _fetch_pdf()
                requested_dpi = int(getattr(settings, "pdf_crop_render_dpi", 600))
                min_dpi = 100
                max_pixels = int(getattr(settings, "pdf_crop_max_pixels", 120_000_000))

                def _render(dpi: int):
                    return convert_from_bytes(pdf_bytes, dpi=dpi, fmt="png", use_pdftocairo=True)

                images = None
                effective_dpi = requested_dpi
                try:
                    images = await anyio.to_thread.run_sync(lambda: _render(requested_dpi))
                except Exception as e:
                    msg = str(e).lower()
                    if "decompression bomb" in msg:
                        for dpi in [800, 600, 450, 300, 200, 150]:
                            if dpi > requested_dpi:
                                continue
                            if dpi < min_dpi:
                                break
                            try:
                                images = await anyio.to_thread.run_sync(lambda d=dpi: _render(d))
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

                    seg_image = image.convert("RGB")
                    scale_x = float(low_image.width) / float(seg_image.width or low_image.width)
                    scale_y = float(low_image.height) / float(seg_image.height or low_image.height)

                    logger.info(
                        "Using high-res PDF render for segmentation",
                        dpi=effective_dpi,
                        low_dimensions=f"{low_image.width}x{low_image.height}",
                        seg_dimensions=f"{seg_image.width}x{seg_image.height}",
                        scale_x=scale_x,
                        scale_y=scale_y,
                    )
            except Exception as e:
                logger.warning("Failed to render high-res PDF for segmentation", error=str(e))

        mode = str(request.mode or "cv").strip().lower()
        result: dict = {}
        regions: list = []
        region_scale_x = 1.0
        region_scale_y = 1.0

        def _score_regions(regions_list: list, img_w: int, target: int) -> float:
            valid = [r for r in regions_list if float(r.get("width", 0)) > 1 and float(r.get("height", 0)) > 1]
            count = len(valid)
            if count == 0:
                return -1e9
            widths = [max(1.0, float(r.get("width", 0))) for r in valid]
            narrow = sum(1 for w in widths if w < (img_w * 0.04))
            wide = sum(1 for w in widths if w > (img_w * 0.60))
            score = 100.0
            score -= abs(count - target) * 8.0
            score -= narrow * 3.5
            score -= wide * 4.0
            return score

        def _build_cfg(
            separator_density: float,
            separator_gap: int,
            min_width_ratio: float,
            projection_gap: int,
            separator_height_ratio: float,
        ) -> SegmenterConfig:
            cfg = SegmenterConfig(
                mode="cv",
                max_dim=int(request.max_dim),
                min_area_ratio=float(request.min_area_ratio),
                max_area_ratio=float(request.max_area_ratio),
                merge_iou_threshold=float(request.merge_iou_threshold),
                ocr_enabled=bool(request.ocr_enabled),
                deskew=bool(request.deskew),
                projection_density_threshold=0.008,
                projection_min_gap=projection_gap,
                split_large_area_ratio=0.16,
                split_large_min_boxes=2,
                line_kernel_scale=28,
                line_merge_iterations=1,
                separator_line_density=separator_density,
                separator_min_line_width=3,
                separator_min_gap=separator_gap,
                separator_min_height_ratio=separator_height_ratio,
                separator_max_width=12,
                hough_threshold=40,
                hough_min_line_length_ratio=0.60,
                hough_max_line_gap=24,
                hough_cluster_px=12,
                min_ink_ratio=0.0015,
                min_ink_pixels=250,
                min_segment_width_ratio=min_width_ratio,
                content_crop_enabled=True,
                content_crop_pad=12,
            )
            _apply_cfg_overrides(cfg, request)
            return cfg

        def _apply_cfg_overrides(cfg: SegmenterConfig, req: AutoSegmentationRequest) -> None:
            overrides = {
                "adaptive_block_size": req.adaptive_block_size,
                "adaptive_c": req.adaptive_c,
                "close_kernel": req.close_kernel,
                "close_iterations": req.close_iterations,
                "projection_density_threshold": req.projection_density_threshold,
                "projection_min_gap": req.projection_min_gap,
                "split_large_area_ratio": req.split_large_area_ratio,
                "split_large_min_boxes": req.split_large_min_boxes,
                "line_kernel_scale": req.line_kernel_scale,
                "line_merge_iterations": req.line_merge_iterations,
                "separator_line_density": req.separator_line_density,
                "separator_min_line_width": req.separator_min_line_width,
                "separator_min_gap": req.separator_min_gap,
                "separator_min_height_ratio": req.separator_min_height_ratio,
                "separator_max_width": req.separator_max_width,
                "hough_threshold": req.hough_threshold,
                "hough_min_line_length_ratio": req.hough_min_line_length_ratio,
                "hough_max_line_gap": req.hough_max_line_gap,
                "hough_cluster_px": req.hough_cluster_px,
                "min_ink_ratio": req.min_ink_ratio,
                "min_ink_pixels": req.min_ink_pixels,
                "min_segment_width_ratio": req.min_segment_width_ratio,
                "content_crop_enabled": req.content_crop_enabled,
                "content_crop_pad": req.content_crop_pad,
                "content_density_threshold": req.content_density_threshold,
                "content_min_span_ratio": req.content_min_span_ratio,
                "edge_refine_enabled": req.edge_refine_enabled,
                "edge_refine_pad": req.edge_refine_pad,
                "refine_by_content": req.refine_by_content,
                "refine_pad": req.refine_pad,
            }
            for name, value in overrides.items():
                if value is not None:
                    setattr(cfg, name, value)

        def _merge_regions_to_target(regions_list: list, target: int) -> list:
            if target <= 0 or len(regions_list) <= target:
                return regions_list
            regions_sorted = sorted(regions_list, key=lambda r: float(r.get("x", 0)))
            while len(regions_sorted) > target:
                # Find the narrowest region and merge it with the closest neighbor.
                widths = [max(1.0, float(r.get("width", 0))) for r in regions_sorted]
                idx = int(min(range(len(widths)), key=lambda i: widths[i]))
                if len(regions_sorted) == 1:
                    break
                left_idx = idx - 1 if idx > 0 else None
                right_idx = idx + 1 if idx + 1 < len(regions_sorted) else None
                if left_idx is None:
                    merge_idx = right_idx
                elif right_idx is None:
                    merge_idx = left_idx
                else:
                    left = regions_sorted[left_idx]
                    right = regions_sorted[right_idx]
                    x = float(regions_sorted[idx].get("x", 0))
                    left_gap = x - float(left.get("x", 0)) - float(left.get("width", 0))
                    right_gap = float(right.get("x", 0)) - x - float(regions_sorted[idx].get("width", 0))
                    merge_idx = left_idx if left_gap <= right_gap else right_idx

                a = regions_sorted[idx]
                b = regions_sorted[merge_idx]
                ax1 = float(a.get("x", 0))
                ay1 = float(a.get("y", 0))
                ax2 = ax1 + float(a.get("width", 0))
                ay2 = ay1 + float(a.get("height", 0))
                bx1 = float(b.get("x", 0))
                by1 = float(b.get("y", 0))
                bx2 = bx1 + float(b.get("width", 0))
                by2 = by1 + float(b.get("height", 0))

                nx1 = min(ax1, bx1)
                ny1 = min(ay1, by1)
                nx2 = max(ax2, bx2)
                ny2 = max(ay2, by2)

                merged = {
                    **a,
                    "x": nx1,
                    "y": ny1,
                    "width": max(1.0, nx2 - nx1),
                    "height": max(1.0, ny2 - ny1),
                }

                keep_idx = min(idx, merge_idx)
                drop_idx = max(idx, merge_idx)
                regions_sorted[keep_idx] = merged
                regions_sorted.pop(drop_idx)

            return sorted(regions_sorted, key=lambda r: float(r.get("x", 0)))

        if mode == "llm":
            try:
                llm_image = low_image
                max_dim = int(request.max_dim or 0)
                if max_dim > 0:
                    max_side = max(llm_image.width, llm_image.height)
                    if max_side > max_dim:
                        scale = float(max_dim) / float(max_side)
                        new_w = max(1, int(llm_image.width * scale))
                        new_h = max(1, int(llm_image.height * scale))
                        llm_image = llm_image.resize((new_w, new_h), resample=Image.Resampling.LANCZOS)

                buffer = BytesIO()
                llm_image.save(buffer, format="PNG", optimize=True)
                plan_bytes = buffer.getvalue()

                decomposition_service = get_decomposition_service()
                segments_data, metadata_data, tokens_used = decomposition_service._analyze_plan_with_gpt(
                    plan_image_bytes=plan_bytes
                )

                gpt_w = float(metadata_data.get("image_width", llm_image.width) or llm_image.width)
                gpt_h = float(metadata_data.get("image_height", llm_image.height) or llm_image.height)
                scale_x_gpt = float(low_image.width) / gpt_w if gpt_w > 0 else 1.0
                scale_y_gpt = float(low_image.height) / gpt_h if gpt_h > 0 else 1.0

                regions = []
                for seg in segments_data:
                    bbox = seg.get("bounding_box", {}) or {}
                    regions.append(
                        {
                            "x": float(bbox.get("x", 0)) * scale_x_gpt,
                            "y": float(bbox.get("y", 0)) * scale_y_gpt,
                            "width": float(bbox.get("width", 0)) * scale_x_gpt,
                            "height": float(bbox.get("height", 0)) * scale_y_gpt,
                            "type": seg.get("type", "unknown"),
                            "label_text": seg.get("description", ""),
                            "confidence": float(seg.get("confidence", 0.7)),
                        }
                    )

                result = {
                    "regions": regions,
                    "meta": {
                        "mode": "llm",
                        "tokens_used": tokens_used,
                    },
                }
                logger.info(
                    "Auto-segmentation stats (llm)",
                    decomposition_id=decomposition_id,
                    regions=len(regions),
                    tokens_used=tokens_used,
                )
            except Exception as e:
                logger.error("LLM segmentation failed; falling back to CV", error=str(e))
                mode = "cv"

        if mode != "llm":
            try:
                if bool(request.auto_tune):
                    candidates = [
                        _build_cfg(0.90, 180, 0.06, 24, 0.72),
                        _build_cfg(0.85, 160, 0.055, 20, 0.70),
                        _build_cfg(0.80, 140, 0.05, 18, 0.68),
                        _build_cfg(0.75, 120, 0.045, 16, 0.65),
                        _build_cfg(0.70, 100, 0.04, 14, 0.62),
                    ]
                    best_score = -1e9
                    best_result = None
                    best_regions = []
                    for idx, cfg in enumerate(candidates, start=1):
                        candidate = segment_image(seg_image, cfg)
                        candidate_regions = list(candidate.get("regions", []) or [])
                        score = _score_regions(candidate_regions, int(seg_image.width), int(request.target_segments))
                        logger.info(
                            "Auto-segmentation auto-tune candidate",
                            decomposition_id=decomposition_id,
                            candidate=idx,
                            regions=len(candidate_regions),
                            score=score,
                            debug=candidate.get("meta", {}).get("debug"),
                        )
                        if score > best_score:
                            best_score = score
                            best_result = candidate
                            best_regions = candidate_regions
                    if best_result is None:
                        best_result = segment_image(seg_image, _build_cfg(0.85, 160, 0.05, 18, 0.70))
                        best_regions = list(best_result.get("regions", []) or [])
                    result = best_result
                    regions = best_regions
                    region_scale_x = scale_x
                    region_scale_y = scale_y
                else:
                    cfg = _build_cfg(0.85, 160, 0.045, 18, 0.70)
                    result = segment_image(seg_image, cfg)
                    regions = list(result.get("regions", []) or [])
                    region_scale_x = scale_x
                    region_scale_y = scale_y
                    logger.info(
                        "Auto-segmentation stats (primary)",
                        decomposition_id=decomposition_id,
                        regions=len(regions),
                        debug=result.get("meta", {}).get("debug"),
                    )
                    if len(regions) <= 1:
                        fallback = SegmenterConfig(
                            mode="cv",
                            max_dim=int(request.max_dim),
                            min_area_ratio=max(0.0025, float(request.min_area_ratio) * 0.7),
                            max_area_ratio=min(0.45, float(request.max_area_ratio)),
                            merge_iou_threshold=max(0.12, float(request.merge_iou_threshold) * 0.7),
                            ocr_enabled=bool(request.ocr_enabled),
                            deskew=bool(request.deskew),
                            close_kernel=3,
                            close_iterations=1,
                            adaptive_block_size=19,
                            adaptive_c=6,
                            projection_density_threshold=0.008,
                            projection_min_gap=12,
                            split_large_area_ratio=0.12,
                            split_large_min_boxes=2,
                            line_kernel_scale=24,
                            line_merge_iterations=1,
                            separator_line_density=0.80,
                            separator_min_line_width=3,
                            separator_min_gap=90,
                            separator_min_height_ratio=0.65,
                            separator_max_width=12,
                            hough_threshold=35,
                            hough_min_line_length_ratio=0.55,
                            hough_max_line_gap=28,
                            hough_cluster_px=12,
                            min_ink_ratio=0.0012,
                            min_ink_pixels=180,
                            min_segment_width_ratio=0.04,
                            content_crop_enabled=True,
                            content_crop_pad=12,
                        )
                        _apply_cfg_overrides(fallback, request)
                        fallback_result = segment_image(seg_image, fallback)
                        fallback_regions = list(fallback_result.get("regions", []) or [])
                        logger.info(
                            "Auto-segmentation stats (fallback)",
                            decomposition_id=decomposition_id,
                            regions=len(fallback_regions),
                            debug=fallback_result.get("meta", {}).get("debug"),
                        )
                        if len(fallback_regions) > len(regions):
                            result = fallback_result
                            regions = fallback_regions
                            region_scale_x = scale_x
                            region_scale_y = scale_y
            except DependencyError as e:
                raise HTTPException(status_code=500, detail=f"Missing dependency: {str(e)}")

        min_w = max(20.0, float(low_image.width) * 0.02)
        min_h = max(30.0, float(low_image.height) * 0.08)
        filtered_regions = []
        for region in regions:
            if float(region.get("width", 0)) < min_w:
                continue
            if float(region.get("height", 0)) < min_h:
                continue
            filtered_regions.append(region)
        if len(filtered_regions) != len(regions):
            logger.info(
                "Auto-segmentation filtered tiny regions",
                decomposition_id=decomposition_id,
                before=len(regions),
                after=len(filtered_regions),
                min_w=min_w,
                min_h=min_h,
            )
        regions = filtered_regions

        async def _llm_keep_region(region: dict) -> bool:
            try:
                rx = float(region.get("x", 0))
                ry = float(region.get("y", 0))
                rw = float(region.get("width", 0))
                rh = float(region.get("height", 0))
                if rw <= 1 or rh <= 1:
                    return False
                crop = seg_image.crop((int(rx), int(ry), int(rx + rw), int(ry + rh)))
                max_side = 1024
                if max(crop.width, crop.height) > max_side:
                    scale = float(max_side) / float(max(crop.width, crop.height))
                    crop = crop.resize(
                        (max(1, int(crop.width * scale)), max(1, int(crop.height * scale))),
                        resample=Image.Resampling.LANCZOS,
                    )
                buf = BytesIO()
                crop.save(buf, format="PNG", optimize=True)
                image_base64 = base64.b64encode(buf.getvalue()).decode("utf-8")
                system_prompt = (
                    "You are a QA assistant for architectural plan crops. "
                    "Decide if the image contains meaningful drawing content (lines, symbols, tables, text) "
                    "or if it is mostly empty/blank."
                )
                user_prompt = (
                    "Return JSON only: {\"keep\": true/false, \"confidence\": 0-1}. "
                    "Keep=true if the crop contains meaningful plan content."
                )

                def _call() -> str:
                    response = get_openai_client().chat_completions_create(
                        model=settings.azure_openai_deployment_name,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": user_prompt},
                                    {
                                        "type": "image_url",
                                        "image_url": {"url": f"data:image/png;base64,{image_base64}"},
                                    },
                                ],
                            },
                        ],
                    )
                    return response.choices[0].message.content or ""

                content = await anyio.to_thread.run_sync(_call)
                start = content.find("{")
                end = content.rfind("}") + 1
                payload = {}
                if start != -1 and end > start:
                    payload = json.loads(content[start:end])
                else:
                    payload = json.loads(content)
                keep = bool(payload.get("keep"))
                return keep
            except Exception:
                # Best-effort: if LLM fails, keep the region.
                return True

        if bool(request.verify_with_llm) and regions:
            keep_regions: list = []
            removed = 0
            limiter = anyio.CapacityLimiter(4)

            async def _check_one(region: dict) -> None:
                nonlocal removed
                async with limiter:
                    keep = await _llm_keep_region(region)
                if keep:
                    keep_regions.append(region)
                else:
                    removed += 1

            async with anyio.create_task_group() as tg:
                for region in regions:
                    tg.start_soon(_check_one, region)

            if keep_regions:
                regions = keep_regions
            logger.info(
                "Auto-segmentation LLM verify",
                decomposition_id=decomposition_id,
                kept=len(regions),
                removed=removed,
            )

        if bool(request.auto_tune) and request.target_segments > 0 and len(regions) > request.target_segments:
            before = len(regions)
            regions = _merge_regions_to_target(regions, int(request.target_segments))
            logger.info(
                "Auto-segmentation merged to target",
                decomposition_id=decomposition_id,
                before=before,
                after=len(regions),
                target=request.target_segments,
            )

        segments: list[PlanSegment] = []

        def _map_type(raw: str) -> SegmentType:
            value = str(raw or "").strip().lower()
            if value in {
                SegmentType.FLOOR_PLAN.value,
                SegmentType.SECTION.value,
                SegmentType.DETAIL.value,
                SegmentType.ELEVATION.value,
                SegmentType.LEGEND.value,
                SegmentType.TABLE.value,
            }:
                return SegmentType(value)
            return SegmentType.UNKNOWN

        for idx, region in enumerate(result.get("regions", []), start=1):
            raw_x = float(region.get("x", 0)) * region_scale_x
            raw_y = float(region.get("y", 0)) * region_scale_y
            raw_w = float(region.get("width", 0)) * region_scale_x
            raw_h = float(region.get("height", 0)) * region_scale_y
            bbox = BoundingBox(
                x=max(0.0, raw_x),
                y=max(0.0, raw_y),
                width=max(1.0, min(float(low_image.width) - max(0.0, raw_x), raw_w)),
                height=max(1.0, min(float(low_image.height) - max(0.0, raw_y), raw_h)),
            )
            label_text = str(region.get("label_text") or "").strip()
            title = label_text or f"סגמנט אוטומטי {idx}"
            description = label_text or "אזור שהוצע אוטומטית"
            confidence = float(region.get("confidence", 0.5))

            segments.append(
                PlanSegment(
                    segment_id=f"seg_{idx:03d}",
                    type=_map_type(region.get("type")),
                    title=title,
                    description=description,
                    bounding_box=bbox,
                    blob_url="",
                    thumbnail_url="",
                    confidence=max(0.05, min(1.0, confidence)),
                    llm_reasoning="AUTO_SEGMENT_CV",
                    approved_by_user=False,
                    used_in_checks=[],
                )
            )

        if request.replace_existing or not decomposition.segments:
            decomposition.segments = segments
        else:
            decomposition.segments.extend(segments)

        decomposition.status = DecompositionStatus.REVIEW_NEEDED
        decomposition.processing_stats.total_segments = len(decomposition.segments)
        decomposition.updated_at = datetime.utcnow()

        # Write plan image to temp file for cropping
        temp_dir = tempfile.mkdtemp()
        temp_image_path = os.path.join(temp_dir, "full_plan.png")
        with open(temp_image_path, "wb") as f:
            f.write(img_bytes)

        decomposition_service = get_decomposition_service()
        decomposition = await decomposition_service.crop_and_upload_segments(
            decomposition=decomposition,
            plan_image_path=temp_image_path,
        )

        try:
            os.remove(temp_image_path)
            os.rmdir(temp_dir)
        except Exception:
            pass

        decomp_dict = decomposition.model_dump(mode="json")
        decomp_dict["type"] = "decomposition"
        decomp_dict["project_id"] = decomposition.project_id
        await cosmos_client.upsert_item(decomp_dict)

        logger.info(
            "Auto-segmentation complete",
            decomposition_id=decomposition_id,
            segments=len(decomposition.segments),
        )

        return decomposition

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Auto-segmentation failed", decomposition_id=decomposition_id, error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"שגיאה בסגמנטציה אוטומטית: {str(e)}",
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
