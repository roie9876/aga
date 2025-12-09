"""Validation engine - matches extracted plan data against requirements."""
from typing import List, Dict, Any, Optional
from datetime import datetime

from src.models import (
    ExtractedPlanData,
    ValidationViolation,
    ValidationResult,
    ValidationStatus,
    ValidationSeverity,
)
from src.services.requirements_parser import get_requirements_parser, ValidationRule
from src.utils.logging import get_logger

logger = get_logger(__name__)


class ValidationEngine:
    """Core validation engine that applies rules to extracted plan data."""
    
    def __init__(self):
        """Initialize validation engine with requirements parser."""
        self.parser = get_requirements_parser()
        self.rules = self.parser.parse()
        logger.info("Validation engine initialized", rule_count=len(self.rules))
    
    def validate(
        self,
        validation_id: str,
        project_id: str,
        plan_name: str,
        plan_blob_url: str,
        extracted_data: ExtractedPlanData,
    ) -> ValidationResult:
        """Run full validation against all requirements.
        
        Args:
            validation_id: Unique validation ID
            project_id: Project identifier
            plan_name: Name of the architectural plan
            plan_blob_url: Azure Blob Storage URL
            extracted_data: Data extracted from the plan
            
        Returns:
            Complete ValidationResult with all violations
        """
        logger.info("Starting validation", 
                   validation_id=validation_id,
                   project_id=project_id)
        
        violations: List[ValidationViolation] = []
        
        # Section 1: Wall thickness validation
        violations.extend(self._validate_walls(extracted_data))
        
        # Section 2: Room dimensions validation
        violations.extend(self._validate_room_dimensions(extracted_data))
        
        # Section 3: Door and window spacing
        violations.extend(self._validate_openings(extracted_data))
        
        # Section 4: Ventilation system
        violations.extend(self._validate_ventilation(extracted_data))
        
        # Section 5: Infrastructure
        violations.extend(self._validate_infrastructure(extracted_data))
        
        # Section 6: Materials (if data available)
        violations.extend(self._validate_materials(extracted_data))
        
        # Section 7: Opening standards
        violations.extend(self._validate_opening_standards(extracted_data))
        
        # Section 8: Usage restrictions
        violations.extend(self._validate_usage(extracted_data))
        
        # Calculate statistics
        total_checks = len(self.rules)
        failed_checks = len(violations)
        passed_checks = total_checks - failed_checks
        
        # Determine overall status
        has_critical = any(v.severity == ValidationSeverity.CRITICAL for v in violations)
        status = ValidationStatus.FAIL if has_critical else (
            ValidationStatus.NEEDS_REVIEW if violations else ValidationStatus.PASS
        )
        
        logger.info("Validation completed",
                   status=status.value,
                   total_checks=total_checks,
                   failed_checks=failed_checks)
        
        return ValidationResult(
            id=validation_id,
            project_id=project_id,
            plan_name=plan_name,
            plan_blob_url=plan_blob_url,
            status=status,
            extracted_data=extracted_data,
            violations=violations,
            total_checks=total_checks,
            passed_checks=passed_checks,
            failed_checks=failed_checks,
            created_at=datetime.utcnow(),
        )
    
    def _validate_walls(self, data: ExtractedPlanData) -> List[ValidationViolation]:
        """Validate wall requirements (Section 1)."""
        violations = []
        
        # Rule 1.1: External wall count (1-4)
        if data.external_wall_count is not None:
            if not (1 <= data.external_wall_count <= 4):
                rule = self.parser.get_rule_by_id("1.1_wall_count")
                if rule:
                    violations.append(ValidationViolation(
                        rule_id=rule.rule_id,
                        category=rule.category,
                        description=rule.description,
                        severity=rule.severity,
                        expected_value="1-4",
                        actual_value=str(data.external_wall_count),
                        section_reference=rule.section,
                    ))
        
        # Rule 1.2: Wall thickness based on external wall count
        if data.external_wall_count is not None and data.wall_thickness_cm:
            required_thickness = self._get_required_wall_thickness(
                data.external_wall_count,
                data.wall_with_window or False
            )
            
            min_thickness = min(data.wall_thickness_cm)
            if min_thickness < required_thickness:
                rule_id = f"1.2_wall_thickness_{data.external_wall_count}_wall{'s' if data.external_wall_count > 1 else ''}"
                rule = self.parser.get_rule_by_id(rule_id)
                if rule:
                    violations.append(ValidationViolation(
                        rule_id=rule.rule_id,
                        category=rule.category,
                        description=rule.description,
                        severity=rule.severity,
                        expected_value=f"{required_thickness} ס\"מ",
                        actual_value=f"{min_thickness} ס\"מ",
                        section_reference=rule.section,
                    ))
        
        return violations
    
    def _get_required_wall_thickness(self, wall_count: int, has_window: bool) -> float:
        """Determine required wall thickness based on wall count and window presence.
        
        Args:
            wall_count: Number of external walls (1-4)
            has_window: Whether any wall has a window
            
        Returns:
            Required thickness in cm
        """
        if wall_count in [1, 2]:
            return 62 if has_window else 52
        elif wall_count in [3, 4]:
            return 62
        return 62  # Default to strictest requirement
    
    def _validate_room_dimensions(self, data: ExtractedPlanData) -> List[ValidationViolation]:
        """Validate room height and volume (Section 2)."""
        violations = []
        
        # Rule 2.1: Minimum height 2.50m
        if data.room_height_m is not None:
            if data.room_height_m < 2.5:
                # Check if exception applies (2.20m with volume >= 22.5)
                if data.room_height_m < 2.2 or (data.room_volume_m3 is None or data.room_volume_m3 < 22.5):
                    rule = self.parser.get_rule_by_id("2.1_min_height")
                    if rule:
                        violations.append(ValidationViolation(
                            rule_id=rule.rule_id,
                            category=rule.category,
                            description=rule.description,
                            severity=rule.severity,
                            expected_value="2.50 מ'",
                            actual_value=f"{data.room_height_m} מ'",
                            section_reference=rule.section,
                        ))
        
        # Rule 2.2: Exception validation (if height is between 2.20 and 2.50)
        if data.room_height_m is not None and 2.2 <= data.room_height_m < 2.5:
            if data.room_volume_m3 is None or data.room_volume_m3 < 22.5:
                rule = self.parser.get_rule_by_id("2.2_exception_height")
                if rule:
                    violations.append(ValidationViolation(
                        rule_id=rule.rule_id,
                        category=rule.category,
                        description=rule.description,
                        severity=rule.severity,
                        expected_value="22.5 מ\"ק",
                        actual_value=f"{data.room_volume_m3 or 'לא זוהה'} מ\"ק",
                        section_reference=rule.section,
                    ))
        
        return violations
    
    def _validate_openings(self, data: ExtractedPlanData) -> List[ValidationViolation]:
        """Validate door and window spacing (Section 3)."""
        violations = []
        
        # Rule 3.1: Door spacing internal
        if data.door_spacing_internal_cm is not None:
            if data.door_spacing_internal_cm < 90:
                rule = self.parser.get_rule_by_id("3.1_door_spacing_internal")
                if rule:
                    violations.append(ValidationViolation(
                        rule_id=rule.rule_id,
                        category=rule.category,
                        description=rule.description,
                        severity=rule.severity,
                        expected_value="≥ 90 ס\"מ",
                        actual_value=f"{data.door_spacing_internal_cm} ס\"מ",
                        section_reference=rule.section,
                    ))
        
        # Rule 3.1: Door spacing external
        if data.door_spacing_external_cm is not None:
            if data.door_spacing_external_cm < 75:
                rule = self.parser.get_rule_by_id("3.1_door_spacing_external")
                if rule:
                    violations.append(ValidationViolation(
                        rule_id=rule.rule_id,
                        category=rule.category,
                        description=rule.description,
                        severity=rule.severity,
                        expected_value="≥ 75 ס\"מ",
                        actual_value=f"{data.door_spacing_external_cm} ס\"מ",
                        section_reference=rule.section,
                    ))
        
        # Rule 3.2: Window spacing
        if data.window_spacing_cm is not None:
            if data.window_spacing_cm < 20:
                rule = self.parser.get_rule_by_id("3.2_window_spacing")
                if rule:
                    violations.append(ValidationViolation(
                        rule_id=rule.rule_id,
                        category=rule.category,
                        description=rule.description,
                        severity=rule.severity,
                        expected_value="≥ 20 ס\"מ",
                        actual_value=f"{data.window_spacing_cm} ס\"מ",
                        section_reference=rule.section,
                    ))
        
        # Rule 3.2: Window to door spacing
        if data.window_to_door_spacing_cm is not None:
            if data.window_to_door_spacing_cm < 200:  # Assuming 2m door height
                rule = self.parser.get_rule_by_id("3.2_window_door_spacing")
                if rule:
                    violations.append(ValidationViolation(
                        rule_id=rule.rule_id,
                        category=rule.category,
                        description=rule.description,
                        severity=rule.severity,
                        expected_value="≥ גובה הדלת (200 ס\"מ)",
                        actual_value=f"{data.window_to_door_spacing_cm} ס\"מ",
                        section_reference=rule.section,
                    ))
        
        return violations
    
    def _validate_ventilation(self, data: ExtractedPlanData) -> List[ValidationViolation]:
        """Validate ventilation system requirements (Section 4)."""
        violations = []
        
        # Rule 4.2: ת״י 4570 note requirement
        if data.has_ventilation_note is False:
            rule = self.parser.get_rule_by_id("4.2_ventilation_note")
            if rule:
                violations.append(ValidationViolation(
                    rule_id=rule.rule_id,
                    category=rule.category,
                    description=rule.description,
                    severity=rule.severity,
                    expected_value='הערה: "מערכות האוורור והסינון יותקנו בהתאם לת״י 4570"',
                    actual_value="הערה לא נמצאה",
                    section_reference=rule.section,
                ))
        
        return violations
    
    def _validate_infrastructure(self, data: ExtractedPlanData) -> List[ValidationViolation]:
        """Validate infrastructure requirements (Section 5)."""
        violations = []
        
        # Rule 5.1: Air inlet pipe
        if data.has_air_inlet_pipe is False:
            rule = self.parser.get_rule_by_id("5.1_air_inlet_pipe")
            if rule:
                violations.append(ValidationViolation(
                    rule_id=rule.rule_id,
                    category=rule.category,
                    description=rule.description,
                    severity=rule.severity,
                    expected_value='צינור כניסת אוויר: קוטר 4"',
                    actual_value="לא זוהה בתוכנית",
                    section_reference=rule.section,
                ))
        
        # Rule 5.1: Air outlet pipe
        if data.has_air_outlet_pipe is False:
            rule = self.parser.get_rule_by_id("5.1_air_outlet_pipe")
            if rule:
                violations.append(ValidationViolation(
                    rule_id=rule.rule_id,
                    category=rule.category,
                    description=rule.description,
                    severity=rule.severity,
                    expected_value='צינור פליטת אוויר: קוטר 4"',
                    actual_value="לא זוהה בתוכנית",
                    section_reference=rule.section,
                ))
        
        return violations
    
    def _validate_materials(self, data: ExtractedPlanData) -> List[ValidationViolation]:
        """Validate concrete and steel requirements (Section 6)."""
        violations = []
        
        # Rule 6.1: Concrete grade (if extractable from annotations)
        concrete_grade = data.annotations.get("concrete_grade") if data.annotations else None
        if concrete_grade:
            # Check if it meets B-30 minimum
            # This is simplified - real implementation would parse grade strings
            if "B-" in str(concrete_grade):
                try:
                    grade_num = int(str(concrete_grade).split("-")[1])
                    if grade_num < 30:
                        rule = self.parser.get_rule_by_id("6.1_concrete_grade")
                        if rule:
                            violations.append(ValidationViolation(
                                rule_id=rule.rule_id,
                                category=rule.category,
                                description=rule.description,
                                severity=rule.severity,
                                expected_value="ב-30 לפחות",
                                actual_value=str(concrete_grade),
                                section_reference=rule.section,
                            ))
                except (ValueError, IndexError):
                    pass
        
        return violations
    
    def _validate_opening_standards(self, data: ExtractedPlanData) -> List[ValidationViolation]:
        """Validate opening certification requirements (Section 7)."""
        violations = []
        
        # Rule 7: Opening standards (if extractable from annotations)
        openings_certified = data.annotations.get("openings_certified") if data.annotations else None
        if openings_certified is False:
            rule = self.parser.get_rule_by_id("7_opening_standards")
            if rule:
                violations.append(ValidationViolation(
                    rule_id=rule.rule_id,
                    category=rule.category,
                    description=rule.description,
                    severity=rule.severity,
                    expected_value="אישור לפי ת\"י 4422",
                    actual_value="אישור לא צוין",
                    section_reference=rule.section,
                ))
        
        return violations
    
    def _validate_usage(self, data: ExtractedPlanData) -> List[ValidationViolation]:
        """Validate usage restrictions (Section 8)."""
        violations = []
        
        # Rule 8.1: Not a passageway
        is_passageway = data.annotations.get("is_passageway") if data.annotations else None
        if is_passageway is True:
            rule = self.parser.get_rule_by_id("8.1_not_passageway")
            if rule:
                violations.append(ValidationViolation(
                    rule_id=rule.rule_id,
                    category=rule.category,
                    description=rule.description,
                    severity=rule.severity,
                    expected_value="לא משמש כמעבר",
                    actual_value="משמש כמעבר בין חדרים",
                    section_reference=rule.section,
                ))
        
        # Rule 8.1: No fixed furniture
        has_fixed_furniture = data.annotations.get("has_fixed_furniture") if data.annotations else None
        if has_fixed_furniture is True:
            rule = self.parser.get_rule_by_id("8.1_no_fixed_furniture")
            if rule:
                violations.append(ValidationViolation(
                    rule_id=rule.rule_id,
                    category=rule.category,
                    description=rule.description,
                    severity=rule.severity,
                    expected_value="ללא ארונות קבועים",
                    actual_value="ארונות קבועים צמודים לקיר",
                    section_reference=rule.section,
                ))
        
        # Rule 8.2: Accessibility
        accessible = data.annotations.get("accessible_without_bathroom") if data.annotations else None
        if accessible is False:
            rule = self.parser.get_rule_by_id("8.2_accessibility")
            if rule:
                violations.append(ValidationViolation(
                    rule_id=rule.rule_id,
                    category=rule.category,
                    description=rule.description,
                    severity=rule.severity,
                    expected_value="נגיש ללא מעבר דרך חדרי רחצה/מטבח",
                    actual_value="מעבר דרך חדרי שירות",
                    section_reference=rule.section,
                ))
        
        return violations


# Global singleton instance
_validation_engine: Optional[ValidationEngine] = None


def get_validation_engine() -> ValidationEngine:
    """Get the global validation engine instance.
    
    Returns:
        ValidationEngine singleton
    """
    global _validation_engine
    if _validation_engine is None:
        _validation_engine = ValidationEngine()
    return _validation_engine
