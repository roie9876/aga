"""Pydantic models for API requests and responses."""
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict

# Configure JSON serialization for datetime
def datetime_serializer(dt: datetime) -> str:
    """Serialize datetime to ISO format string."""
    return dt.isoformat()


class ValidationSeverity(str, Enum):
    """Severity levels for validation violations."""
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    WARNING = "warning"


class ValidationStatus(str, Enum):
    """Status of a validation result."""
    PASS = "pass"
    FAIL = "fail"
    NEEDS_REVIEW = "needs_review"


class BoundingBox(BaseModel):
    """Bounding box coordinates (percentage-based, 0-100)."""
    model_config = ConfigDict(populate_by_name=True)
    
    x: float = Field(..., ge=0, le=100, description="Left edge as percentage from left (0-100)")
    y: float = Field(..., ge=0, le=100, description="Top edge as percentage from top (0-100)")
    width: float = Field(..., ge=0, le=100, description="Width as percentage (0-100)")
    height: float = Field(..., ge=0, le=100, description="Height as percentage (0-100)")


class ValidationViolation(BaseModel):
    """A single validation rule violation."""
    model_config = ConfigDict(populate_by_name=True)
    
    rule_id: str = Field(..., description="Unique identifier for the violated rule")
    category: str = Field(..., description="Category of the requirement (e.g., 'wall_thickness')")
    description: str = Field(..., description="Description of the violation in Hebrew")
    severity: ValidationSeverity = Field(..., description="Severity level")
    expected_value: Optional[str] = Field(None, description="Expected value per regulation")
    actual_value: Optional[str] = Field(None, description="Actual value found in plan")
    section_reference: str = Field(..., description="Section in requirements-mamad.md (e.g., '1.2')")
    location_description: Optional[str] = Field(None, description="Textual description of location in plan")
    bounding_box: Optional[BoundingBox] = Field(None, description="Visual location as bounding box")


class CheckStatus(str, Enum):
    """Status of an individual check."""
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"


class IndividualCheck(BaseModel):
    """A single validation check with its own image and result."""
    model_config = ConfigDict(populate_by_name=True)
    
    check_id: str = Field(..., description="Unique check identifier (e.g., '0_sanity', '1_wall_thickness')")
    check_name: str = Field(..., description="Hebrew name of the check")
    description: str = Field(..., description="What this check validates (Hebrew)")
    status: CheckStatus = Field(..., description="Pass/Fail/Skip status")
    
    # Image for this specific check with bounding box overlay
    plan_image_url: str = Field(..., description="URL to the original plan image")
    bounding_box: Optional[BoundingBox] = Field(None, description="Area highlighted for this check")
    
    # Violation details (if failed)
    violation: Optional[ValidationViolation] = Field(None, description="Violation details if check failed")
    
    # Additional context
    reasoning: Optional[str] = Field(None, description="Why this check passed/failed")


class ExtractedPlanData(BaseModel):
    """Structured data extracted from architectural plan."""
    model_config = ConfigDict(populate_by_name=True)
    
    # Wall measurements
    external_wall_count: Optional[int] = Field(None, description="Number of external walls")
    wall_thickness_cm: Optional[List[float]] = Field(None, description="Wall thickness measurements in cm")
    wall_with_window: Optional[bool] = Field(None, description="Whether any wall has a window")
    
    # Room dimensions
    room_height_m: Optional[float] = Field(None, description="Room height in meters")
    room_volume_m3: Optional[float] = Field(None, description="Room volume in cubic meters")
    
    # Door specifications
    door_spacing_internal_cm: Optional[float] = Field(None, description="Door to perpendicular wall spacing inside")
    door_spacing_external_cm: Optional[float] = Field(None, description="Door to perpendicular wall spacing outside")
    
    # Window specifications
    window_spacing_cm: Optional[float] = Field(None, description="Window spacing from perpendicular wall")
    window_to_door_spacing_cm: Optional[float] = Field(None, description="Spacing between window and door")
    
    # Infrastructure
    has_ventilation_note: Optional[bool] = Field(None, description="ת״י 4570 note present")
    has_air_inlet_pipe: Optional[bool] = Field(None, description="4\" air inlet pipe marked")
    has_air_outlet_pipe: Optional[bool] = Field(None, description="4\" air outlet pipe marked")
    
    # Additional annotations
    annotations: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional extracted data")
    confidence_score: float = Field(0.0, ge=0.0, le=1.0, description="Overall extraction confidence")


class ValidationRequest(BaseModel):
    """Request model for plan validation."""
    model_config = ConfigDict(populate_by_name=True)
    
    project_id: str = Field(..., description="Project identifier")
    plan_name: str = Field(..., description="Name of the architectural plan")


class ValidationResult(BaseModel):
    """Complete validation result."""
    model_config = ConfigDict(populate_by_name=True)
    
    id: str = Field(..., description="Unique validation result ID")
    project_id: str = Field(..., description="Project identifier")
    plan_name: str = Field(..., description="Name of the validated plan")
    plan_blob_url: str = Field(..., description="Azure Blob Storage URL for the plan")
    
    status: ValidationStatus = Field(..., description="Overall validation status")
    extracted_data: ExtractedPlanData = Field(..., description="Data extracted from the plan")
    
    # New: Individual checks instead of violations list
    checks: List[IndividualCheck] = Field(default_factory=list, description="List of individual validation checks")
    
    # Deprecated but kept for backward compatibility
    violations: List[ValidationViolation] = Field(default_factory=list, description="(Deprecated) Use checks instead")
    
    total_checks: int = Field(..., description="Total number of validation checks performed")
    passed_checks: int = Field(..., description="Number of checks that passed")
    failed_checks: int = Field(..., description="Number of checks that failed")
    
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Validation timestamp")


class ValidationResponse(BaseModel):
    """API response for validation request."""
    model_config = ConfigDict(populate_by_name=True)
    
    success: bool = Field(..., description="Whether validation completed successfully")
    validation_id: str = Field(..., description="ID to retrieve full results")
    message: str = Field(..., description="Human-readable message")


class HealthResponse(BaseModel):
    """Health check response."""
    model_config = ConfigDict(
        populate_by_name=True,
        json_encoders={datetime: lambda v: v.isoformat()}
    )
    
    status: str = Field(..., description="Overall health status")
    services: Dict[str, bool] = Field(..., description="Status of individual services")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
