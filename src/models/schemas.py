"""Pydantic models for API requests and responses."""
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict


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
    violations: List[ValidationViolation] = Field(default_factory=list, description="List of violations")
    
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
    model_config = ConfigDict(populate_by_name=True)
    
    status: str = Field(..., description="Overall health status")
    services: Dict[str, bool] = Field(..., description="Status of individual services")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
