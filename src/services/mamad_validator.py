"""
MAMAD (Bomb Shelter) Validation Service - Part 4

This service validates extracted architectural plan data against official
MAMAD requirements from requirements-mamad.md.

Validates:
- Wall thickness requirements (1-4 external walls)
- Room height and volume
- Door and window spacing
- Rebar specifications
- Concrete and steel materials
- Ventilation system requirements
"""

import structlog
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum
import re

logger = structlog.get_logger(__name__)


class ViolationSeverity(str, Enum):
    """Severity levels for violations"""
    CRITICAL = "critical"  # Must fix - prevents approval
    ERROR = "error"        # Should fix - safety issue
    WARNING = "warning"    # Nice to fix - best practice


@dataclass
class Violation:
    """Represents a validation rule violation"""
    rule_id: str
    severity: ViolationSeverity
    category: str
    description_he: str  # Hebrew description
    requirement: str     # What's required
    found: str          # What was found
    location: str = ""  # Where in the plan


class MamadValidator:
    """Validates MAMAD architectural plans against requirements"""
    
    def __init__(self):
        self.violations: List[Violation] = []
        
    def validate_segment(self, analysis_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate a single segment's analysis data against MAMAD requirements.
        
        Only runs validation rules that are RELEVANT to this segment based on its classification.
        
        Args:
            analysis_data: Extracted data from GPT analysis (includes classification)
            
        Returns:
            Validation result with violations and status
        """
        self.violations = []  # Reset violations
        
        # Get segment classification
        classification = analysis_data.get("classification", {})
        primary_category_raw = classification.get("primary_category", "OTHER")
        secondary_categories_raw = classification.get("secondary_categories", [])
        relevant_requirements = classification.get("relevant_requirements", [])

        # Normalize categories: support multi-label primary_category like "ROOM_LAYOUT|DOOR_DETAILS"
        # and include secondary_categories as additional signals.
        categories: List[str] = []
        if isinstance(primary_category_raw, str) and primary_category_raw.strip():
            parts = re.split(r"[|,]", primary_category_raw)
            categories.extend([p.strip().upper() for p in parts if p.strip()])
        elif isinstance(primary_category_raw, list):
            categories.extend([str(p).strip().upper() for p in primary_category_raw if str(p).strip()])

        if isinstance(secondary_categories_raw, list):
            categories.extend([str(c).strip().upper() for c in secondary_categories_raw if str(c).strip()])

        # Default
        if not categories:
            categories = ["OTHER"]

        primary_category = categories[0]
        
        logger.info("Starting MAMAD validation", 
                   category=primary_category,
                   relevant_requirements=relevant_requirements,
                   has_dimensions=bool(analysis_data.get("dimensions")),
                   has_elements=bool(analysis_data.get("structural_elements")))
        
        # Map categories to validation functions
        validation_map = {
            "WALL_SECTION": [self._validate_wall_thickness],
            "ROOM_LAYOUT": [self._validate_room_height],
            "DOOR_DETAILS": [self._validate_door_spacing],
            "WINDOW_DETAILS": [self._validate_window_spacing],
            "REBAR_DETAILS": [self._validate_rebar_specifications],
            "MATERIALS_SPECS": [self._validate_concrete_grade, self._validate_steel_type],
            "GENERAL_NOTES": [self._validate_ventilation_note],
            "SECTIONS": [self._validate_room_height],
        }

        # Which official requirement IDs this validator actually checks per category.
        # This is used for coverage reporting (and UI) and should match the rules implemented below.
        category_to_checked_requirements = {
            "WALL_SECTION": ["1.2"],
            "ROOM_LAYOUT": ["2.1", "2.2"],
            "DOOR_DETAILS": ["3.1"],
            "WINDOW_DETAILS": ["3.2"],
            "REBAR_DETAILS": ["6.3"],
            "MATERIALS_SPECS": ["6.1", "6.2"],
            "GENERAL_NOTES": ["4.2"],
            "SECTIONS": ["2.1", "2.2"],
        }
        
        # Run validations based on ALL classified categories (primary + secondary)
        validations_to_run = []
        checked_set = set()
        for cat in categories:
            for fn in validation_map.get(cat, []):
                if fn not in validations_to_run:
                    validations_to_run.append(fn)
            for req in category_to_checked_requirements.get(cat, []):
                checked_set.add(req)
        checked_requirements = sorted(checked_set)
        
        decision_summary_he = ""

        if not validations_to_run:
            # If category not recognized or OTHER, skip validation
            logger.info("No specific validations for this segment category",
                       category=primary_category)
            decision_summary_he = (
                f"לא הופעלו בדיקות כי הקטגוריה שסווגה היא '{primary_category}'. "
                "המערכת מפעילה בדיקות רק עבור קטגוריות מוגדרות (כמו ROOM_LAYOUT/SECTIONS/WALL_SECTION וכו')."
            )
        else:
            for validation_func in validations_to_run:
                validation_func(analysis_data)

            decision_summary_he = (
                f"הופעלו בדיקות לפי קטגוריות הסגמנט: {', '.join(categories)}. "
                f"דרישות שנבדקו בסגמנט זה: {', '.join(checked_requirements) if checked_requirements else 'אין'}. "
                "דרישות אחרות לא נבדקו כי הן ממופות לקטגוריות אחרות או דורשות סגמנטים מסוג אחר (למשל פרט/חתך)."
            )
        
        # Categorize violations
        critical = [v for v in self.violations if v.severity == ViolationSeverity.CRITICAL]
        errors = [v for v in self.violations if v.severity == ViolationSeverity.ERROR]
        warnings = [v for v in self.violations if v.severity == ViolationSeverity.WARNING]
        
        passed = len(critical) == 0 and len(errors) == 0
        
        logger.info("Validation complete",
                   passed=passed,
                   critical=len(critical),
                   errors=len(errors),
                   warnings=len(warnings))
        
        return {
            "status": "passed" if passed else "failed",
            "passed": passed,
            "total_violations": len(self.violations),
            "critical_count": len(critical),
            "error_count": len(errors),
            "warning_count": len(warnings),
            "violations": [self._violation_to_dict(v) for v in self.violations],
            "checked_requirements": checked_requirements,
            "decision_summary_he": decision_summary_he,
            "debug": {
                "categories_used": categories,
                "validators_run": [fn.__name__ for fn in validations_to_run],
                "primary_category": primary_category,
                "relevant_requirements": relevant_requirements,
            },
        }
    
    def _violation_to_dict(self, v: Violation) -> Dict[str, Any]:
        """Convert Violation to dictionary"""
        return {
            "rule_id": v.rule_id,
            "severity": v.severity.value,
            "category": v.category,
            "description": v.description_he,
            "requirement": v.requirement,
            "found": v.found,
            "location": v.location
        }
    
    # =========================================================================
    # Validation Rules (Requirements from requirements-mamad.md)
    # =========================================================================
    
    def _validate_wall_thickness(self, data: Dict[str, Any]):
        """
        Rule 1.2: Wall thickness requirements
        - 1 external wall: 25cm (with window: 30cm)
        - 2 external walls: 25cm (with window: 30cm)
        - 3 external walls: 30cm
        - 4 external walls: 40cm
        """
        elements = data.get("structural_elements", [])
        walls = [e for e in elements if e.get("type") in ["wall", "קיר", "קיר חיצוני"]]
        
        if not walls:
            self.violations.append(Violation(
                rule_id="WALL_001",
                severity=ViolationSeverity.WARNING,
                category="קירות",
                description_he="לא זוהו קירות בתוכנית",
                requirement="חובה לזהות קירות חיצוניים",
                found="0 קירות"
            ))
            return
        
        # Count external walls (simplified - would need more context)
        external_walls = walls  # TODO: Distinguish external vs internal
        num_external = len(external_walls)
        
        # Check each wall thickness
        for wall in walls:
            thickness_str = wall.get("thickness", "")
            
            # Extract numeric thickness (handle "25cm", "25 ס\"מ", etc.)
            thickness_cm = self._extract_dimension_value(thickness_str, "cm")
            
            if thickness_cm is None:
                self.violations.append(Violation(
                    rule_id="WALL_002",
                    severity=ViolationSeverity.WARNING,
                    category="קירות",
                    description_he=f"עובי קיר לא ברור: {wall.get('location', 'לא צוין')}",
                    requirement="עובי קיר חייב להיות מצוין בס\"מ",
                    found=thickness_str or "לא צוין",
                    location=wall.get("location", "")
                ))
                continue
            
            # Determine required thickness based on number of external walls
            required_thickness = self._get_required_wall_thickness(num_external, has_window=False)
            
            if thickness_cm < required_thickness:
                self.violations.append(Violation(
                    rule_id="WALL_003",
                    severity=ViolationSeverity.CRITICAL,
                    category="קירות",
                    description_he=f"קיר דק מדי - {wall.get('location', 'לא צוין')}",
                    requirement=f"עובי מינימלי: {required_thickness} ס\"מ ({num_external} קירות חיצוניים)",
                    found=f"{thickness_cm} ס\"מ",
                    location=wall.get("location", "")
                ))
    
    def _validate_room_height(self, data: Dict[str, Any]):
        """
        Rule 2.1-2.2: Room height requirements
        - Standard minimum: 2.50m
        - Exception: 2.20m if basement/addition AND volume ≥ 22.5 m³
        """
        dimensions = data.get("dimensions", [])
        
        # Find height dimension
        height_dims = [d for d in dimensions if "גובה" in d.get("element", "").lower() 
                      or "height" in d.get("element", "").lower()]
        
        if not height_dims:
            self.violations.append(Violation(
                rule_id="HEIGHT_001",
                severity=ViolationSeverity.ERROR,
                category="גובה",
                description_he="גובה החדר לא צוין בתוכנית",
                requirement="גובה מינימלי: 2.50 מ'",
                found="לא צוין"
            ))
            return
        
        # Get height value
        height_m = self._extract_dimension_value(height_dims[0].get("value", ""), "m")
        
        if height_m is None:
            return
        
        # Check minimum height
        if height_m < 2.20:
            self.violations.append(Violation(
                rule_id="HEIGHT_002",
                severity=ViolationSeverity.CRITICAL,
                category="גובה",
                description_he="גובה החדר נמוך מדי",
                requirement="גובה מינימלי: 2.20 מ' (במרתף/תוספת אם נפח ≥ 22.5 מ\"ק)",
                found=f"{height_m} מ'",
                location=height_dims[0].get("location", "")
            ))
        elif height_m < 2.50:
            self.violations.append(Violation(
                rule_id="HEIGHT_003",
                severity=ViolationSeverity.WARNING,
                category="גובה",
                description_he="גובה החדר נמוך מהסטנדרט",
                requirement="גובה מינימלי סטנדרטי: 2.50 מ'",
                found=f"{height_m} מ' (מותר רק במרתף/תוספת אם נפח ≥ 22.5 מ\"ק)",
                location=height_dims[0].get("location", "")
            ))
    
    def _validate_door_spacing(self, data: Dict[str, Any]):
        """
        Rule 3.1: Door spacing requirements
        - Distance from door frame to perpendicular wall inside: ≥ 90cm
        - Distance from door edge to perpendicular wall outside: ≥ 75cm
        """
        elements = data.get("structural_elements", [])
        doors = [e for e in elements if e.get("type") in ["door", "דלת", "דלת הדף"]]
        
        if not doors:
            # Not necessarily an error - segment might not show door
            return
        
        # Check door spacing (simplified - would need spatial analysis)
        for door in doors:
            dimensions_str = door.get("dimensions", "")
            
            # Look for spacing annotations in text_items
            text_items = data.get("text_items", [])
            spacing_texts = [t for t in text_items if "מרחק" in t.get("text", "") 
                           or "ס\"מ" in t.get("text", "")]
            
            # If no spacing info found, warn
            if not spacing_texts:
                self.violations.append(Violation(
                    rule_id="DOOR_001",
                    severity=ViolationSeverity.WARNING,
                    category="דלת",
                    description_he="מרחקי דלת לא מצוינים בתוכנית",
                    requirement="מרחק מדלת לקיר ניצב: ≥ 90 ס\"מ פנימי, ≥ 75 ס\"מ חיצוני",
                    found="לא צוין",
                    location=door.get("location", "")
                ))
    
    def _validate_window_spacing(self, data: Dict[str, Any]):
        """
        Rule 3.2: Window spacing requirements
        - Distance between sliding niches: ≥ 20cm
        - Distance between light openings: ≥ 100cm
        - Distance from window to perpendicular wall: ≥ 20cm
        """
        elements = data.get("structural_elements", [])
        windows = [e for e in elements if e.get("type") in ["window", "חלון", "חלון הדף"]]
        
        if not windows:
            return  # Not all segments have windows
        
        # Check spacing (simplified)
        for window in windows:
            # Look for spacing annotations
            text_items = data.get("text_items", [])
            spacing_found = any("20" in t.get("text", "") or "100" in t.get("text", "") 
                              for t in text_items)
            
            if not spacing_found:
                self.violations.append(Violation(
                    rule_id="WINDOW_001",
                    severity=ViolationSeverity.WARNING,
                    category="חלון",
                    description_he="מרחקי חלון לא מצוינים",
                    requirement="מרחק בין נישות: ≥ 20 ס\"מ, בין פתחי אור: ≥ 100 ס\"מ",
                    found="לא צוין",
                    location=window.get("location", "")
                ))
    
    def _validate_rebar_specifications(self, data: Dict[str, Any]):
        """
        Rule 6.3: Rebar specifications
        - External rebar: spacing ≤ 20cm
        - Internal rebar: spacing ≤ 10cm
        """
        rebar_details = data.get("rebar_details", [])
        
        if not rebar_details:
            self.violations.append(Violation(
                rule_id="REBAR_001",
                severity=ViolationSeverity.ERROR,
                category="זיון",
                description_he="פרטי זיון לא מצוינים בתוכנית",
                requirement="זיון חיצוני: פסיעה ≤ 20 ס\"מ, זיון פנימי: ≤ 10 ס\"מ",
                found="לא צוין"
            ))
            return
        
        for rebar in rebar_details:
            spacing_str = rebar.get("spacing", "")
            spacing_cm = self._extract_dimension_value(spacing_str, "cm")
            
            if spacing_cm is None:
                continue
            
            # Check external rebar spacing
            if "חיצוני" in rebar.get("location", "") or "external" in rebar.get("location", "").lower():
                if spacing_cm > 20:
                    self.violations.append(Violation(
                        rule_id="REBAR_002",
                        severity=ViolationSeverity.CRITICAL,
                        category="זיון",
                        description_he="פסיעת זיון חיצוני גדולה מדי",
                        requirement="פסיעה מקסימלית: 20 ס\"מ",
                        found=f"{spacing_cm} ס\"מ",
                        location=rebar.get("location", "")
                    ))
            
            # Check internal rebar spacing
            if "פנימי" in rebar.get("location", "") or "internal" in rebar.get("location", "").lower():
                if spacing_cm > 10:
                    self.violations.append(Violation(
                        rule_id="REBAR_003",
                        severity=ViolationSeverity.CRITICAL,
                        category="זיון",
                        description_he="פסיעת זיון פנימי גדולה מדי",
                        requirement="פסיעה מקסימלית: 10 ס\"מ",
                        found=f"{spacing_cm} ס\"מ",
                        location=rebar.get("location", "")
                    ))
    
    def _validate_concrete_grade(self, data: Dict[str, Any]):
        """
        Rule 6.1: Concrete grade must be B-30 or higher
        """
        materials = data.get("materials", [])
        concrete_materials = [m for m in materials if "בטון" in m.get("type", "").lower() 
                             or "concrete" in m.get("type", "").lower()]
        
        if not concrete_materials:
            self.violations.append(Violation(
                rule_id="CONCRETE_001",
                severity=ViolationSeverity.ERROR,
                category="בטון",
                description_he="סוג בטון לא מצוין בתוכנית",
                requirement="בטון ב-30 לפחות",
                found="לא צוין"
            ))
            return
        
        for concrete in concrete_materials:
            grade = concrete.get("grade", "")
            
            # Check if grade contains B-30 or higher
            if "ב-30" not in grade and "b-30" not in grade.lower() and "b30" not in grade.lower():
                # Try to extract numeric grade
                if "ב-" in grade or "b-" in grade.lower():
                    self.violations.append(Violation(
                        rule_id="CONCRETE_002",
                        severity=ViolationSeverity.WARNING,
                        category="בטון",
                        description_he="דרגת בטון לא ברורה",
                        requirement="בטון ב-30 לפחות",
                        found=grade,
                        location=concrete.get("notes", "")
                    ))
    
    def _validate_steel_type(self, data: Dict[str, Any]):
        """
        Rule 6.2: Steel must be hot-rolled or welded, NOT cold-drawn
        """
        materials = data.get("materials", [])
        steel_materials = [m for m in materials if "פלדה" in m.get("type", "").lower() 
                          or "steel" in m.get("type", "").lower()]
        
        if not steel_materials:
            return  # Not all segments specify steel type
        
        for steel in steel_materials:
            spec = steel.get("grade", "") + " " + steel.get("notes", "")
            
            # Check for forbidden cold-drawn steel
            if "משוכה בקור" in spec or "cold-drawn" in spec.lower():
                self.violations.append(Violation(
                    rule_id="STEEL_001",
                    severity=ViolationSeverity.CRITICAL,
                    category="פלדה",
                    description_he="שימוש אסור בפלדה משוכה בקור",
                    requirement="פלדה מעוגלת בחום או רתיך בלבד",
                    found=spec,
                    location=steel.get("notes", "")
                ))
    
    def _validate_ventilation_note(self, data: Dict[str, Any]):
        """
        Rule 4.2: Must include note about TI 4570 ventilation standard
        """
        text_items = data.get("text_items", [])
        annotations = data.get("annotations", [])
        
        all_text = " ".join([t.get("text", "") for t in text_items + annotations])
        
        # Check for TI 4570 reference
        if "4570" not in all_text and "ת\"י 4570" not in all_text:
            self.violations.append(Violation(
                rule_id="VENT_001",
                severity=ViolationSeverity.WARNING,
                category="אוורור",
                description_he="חסרה הערה על תקן אוורור וסינון",
                requirement='חובה לכתוב: "מערכות האוורור והסינון יותקנו בהתאם לת״י 4570"',
                found="לא נמצא"
            ))
    
    # =========================================================================
    # Helper Methods
    # =========================================================================
    
    def _extract_dimension_value(self, value_str: str, unit: str) -> Optional[float]:
        """
        Extract numeric value from dimension string.
        
        Examples:
            "25cm" -> 25.0
            "2.5 מ'" -> 2.5
            "20 ס\"מ" -> 20.0
        """
        if not value_str:
            return None
        
        # Convert to string if it's a number
        if isinstance(value_str, (int, float)):
            value_str = str(value_str)
        
        import re
        
        # Remove common units
        clean_str = value_str.replace("cm", "").replace("ס\"מ", "").replace("מ'", "")
        clean_str = clean_str.replace("m", "").replace("mm", "").strip()
        
        # Extract number
        match = re.search(r'\d+\.?\d*', clean_str)
        if not match:
            return None
        
        value = float(match.group())
        
        # Convert to requested unit
        if unit == "cm":
            # Assume values > 100 are mm, values < 10 are m
            if value > 100:
                value = value / 10  # mm to cm
            elif value < 10:
                value = value * 100  # m to cm
        elif unit == "m":
            # Assume values > 10 are cm
            if value > 10:
                value = value / 100  # cm to m
        
        return value
    
    def _get_required_wall_thickness(self, num_external_walls: int, has_window: bool = False) -> int:
        """
        Get required wall thickness based on number of external walls.
        
        Rule 1.2:
        - 1 external wall: 25cm (with window: 30cm)
        - 2 external walls: 25cm (with window: 30cm)
        - 3 external walls: 30cm
        - 4 external walls: 40cm
        """
        if num_external_walls <= 2:
            return 30 if has_window else 25
        elif num_external_walls == 3:
            return 30
        else:  # 4 walls
            return 40


# Singleton instance
_validator_instance = None


def get_mamad_validator() -> MamadValidator:
    """Get singleton validator instance"""
    global _validator_instance
    if _validator_instance is None:
        _validator_instance = MamadValidator()
    return _validator_instance
