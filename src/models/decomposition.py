"""Data models for plan decomposition."""
from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field


class SegmentType(str, Enum):
    """Type of architectural drawing segment."""
    FLOOR_PLAN = "floor_plan"
    SECTION = "section"
    DETAIL = "detail"
    ELEVATION = "elevation"
    LEGEND = "legend"
    TABLE = "table"
    UNKNOWN = "unknown"


class BoundingBox(BaseModel):
    """Bounding box coordinates (pixels or percentage)."""
    x: float = Field(..., ge=0, le=50000, description="X coordinate (pixels or %)")
    y: float = Field(..., ge=0, le=50000, description="Y coordinate (pixels or %)")
    width: float = Field(..., ge=0, le=50000, description="Width (pixels or %)")
    height: float = Field(..., ge=0, le=50000, description="Height (pixels or %)")


class ProjectMetadata(BaseModel):
    """Metadata extracted from plan legend."""
    project_name: Optional[str] = Field(None, description="שם הפרויקט")
    architect: Optional[str] = Field(None, description="שם אדריכל")
    date: Optional[str] = Field(None, description="תאריך התוכנית")
    plan_number: Optional[str] = Field(None, description="מספר תוכנית")
    scale: Optional[str] = Field(None, description="קנה מידה")
    floor: Optional[str] = Field(None, description="קומה")
    apartment: Optional[str] = Field(None, description="מספר דירה")
    additional_info: Optional[Dict[str, Any]] = Field(default_factory=dict, description="מידע נוסף")


class PlanSegment(BaseModel):
    """A segment extracted from the full architectural plan."""
    segment_id: str = Field(..., description="Unique segment ID (e.g., seg_001)")
    type: SegmentType = Field(..., description="Type of segment")
    title: str = Field(..., description="Title/heading of the segment")
    description: str = Field(..., description="Detailed description of what's visible")
    bounding_box: BoundingBox = Field(..., description="Location in full plan")
    blob_url: str = Field(..., description="Azure Blob URL for cropped image")
    thumbnail_url: str = Field(..., description="Azure Blob URL for thumbnail")
    confidence: float = Field(..., ge=0, le=1, description="GPT confidence score")
    llm_reasoning: Optional[str] = Field(None, description="GPT's reasoning for classification")
    approved_by_user: bool = Field(False, description="User approved this segment")
    used_in_checks: List[str] = Field(default_factory=list, description="Validation checks that used this segment")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ProcessingStats(BaseModel):
    """Statistics about the decomposition process."""
    total_segments: int = Field(..., description="Total segments identified")
    processing_time_seconds: float = Field(..., description="Total processing time")
    llm_tokens_used: int = Field(..., description="Total GPT tokens consumed")
    conversion_time_seconds: Optional[float] = Field(None, description="DWF→PNG conversion time")
    analysis_time_seconds: Optional[float] = Field(None, description="GPT analysis time")
    cropping_time_seconds: Optional[float] = Field(None, description="Image cropping time")


class DecompositionStatus(str, Enum):
    """Status of decomposition process."""
    PROCESSING = "processing"
    ANALYZING = "analyzing"
    CROPPING = "cropping"
    COMPLETE = "complete"
    FAILED = "failed"
    REVIEW_NEEDED = "review_needed"


class PlanDecomposition(BaseModel):
    """Complete decomposition of an architectural plan."""
    id: str = Field(..., description="Decomposition ID")
    validation_id: str = Field(..., description="Parent validation ID")
    project_id: str = Field(..., description="Project ID for partitioning")
    status: DecompositionStatus = Field(..., description="Current status")
    
    # Full plan info
    full_plan_url: str = Field(..., description="Azure Blob URL for full plan PNG")
    full_plan_width: int = Field(..., description="Full plan width in pixels")
    full_plan_height: int = Field(..., description="Full plan height in pixels")
    file_size_mb: float = Field(..., description="File size in MB")
    
    # Metadata
    metadata: ProjectMetadata = Field(..., description="Extracted project metadata")
    
    # Segments
    segments: List[PlanSegment] = Field(default_factory=list, description="Identified segments")
    
    # Statistics
    processing_stats: ProcessingStats = Field(..., description="Processing statistics")
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = Field(None, description="When processing completed")
    
    # Error handling
    error_message: Optional[str] = Field(None, description="Error message if failed")
    
    class Config:
        """Pydantic config."""
        json_schema_extra = {
            "example": {
                "id": "decomp-123",
                "validation_id": "val-123",
                "project_id": "proj-456",
                "status": "complete",
                "full_plan_url": "https://storage.blob.core.windows.net/plans/val-123/full_plan.png",
                "full_plan_width": 7680,
                "full_plan_height": 4320,
                "file_size_mb": 12.5,
                "metadata": {
                    "project_name": "בניין 60",
                    "architect": "משה כהן אדריכלים",
                    "date": "25/10/2023",
                    "plan_number": "T3-A"
                },
                "segments": [
                    {
                        "segment_id": "seg_001",
                        "type": "floor_plan",
                        "title": "תוכנית קומה טיפוסית",
                        "description": "תוכנית הקומה מציגה דירת 3 חדרים עם ממ״ד",
                        "bounding_box": {"x": 10, "y": 15, "width": 40, "height": 30},
                        "blob_url": "https://.../seg_001.png",
                        "thumbnail_url": "https://.../seg_001_thumb.png",
                        "confidence": 0.95,
                        "approved_by_user": True
                    }
                ],
                "processing_stats": {
                    "total_segments": 11,
                    "processing_time_seconds": 52.3,
                    "llm_tokens_used": 15420
                }
            }
        }


class DecompositionRequest(BaseModel):
    """Request to decompose a plan."""
    validation_id: str = Field(..., description="Parent validation ID")
    project_id: str = Field(..., description="Project ID")
    plan_blob_url: str = Field(..., description="URL of full plan image")


class DecompositionResponse(BaseModel):
    """Response after initiating decomposition."""
    decomposition_id: str = Field(..., description="Unique decomposition ID")
    status: DecompositionStatus = Field(..., description="Current status")
    estimated_time_seconds: int = Field(..., description="Estimated completion time")
    message: str = Field(..., description="Status message in Hebrew")


class SegmentUpdateRequest(BaseModel):
    """Request to update a segment."""
    title: Optional[str] = Field(None, description="Updated title")
    description: Optional[str] = Field(None, description="Updated description")
    type: Optional[SegmentType] = Field(None, description="Updated type")
    approved: Optional[bool] = Field(None, description="Approval status")


class ApprovalRequest(BaseModel):
    """Request to approve decomposition and start validation."""
    approved_segments: List[str] = Field(..., description="List of segment IDs to use")
    rejected_segments: List[str] = Field(default_factory=list, description="List of segment IDs to ignore")
    custom_metadata: Optional[ProjectMetadata] = Field(None, description="User-corrected metadata")


class ManualRoi(BaseModel):
    """A manually selected region-of-interest on the full plan (relative coordinates)."""

    x: float = Field(..., ge=0.0, le=1.0, description="Left (0..1) relative to full plan")
    y: float = Field(..., ge=0.0, le=1.0, description="Top (0..1) relative to full plan")
    width: float = Field(..., gt=0.0, le=1.0, description="Width (0..1) relative to full plan")
    height: float = Field(..., gt=0.0, le=1.0, description="Height (0..1) relative to full plan")


class AddManualSegmentsRequest(BaseModel):
    """Request to append manual ROI segments to an existing decomposition."""

    rois: List[ManualRoi] = Field(..., min_length=1, description="List of ROIs to append")
