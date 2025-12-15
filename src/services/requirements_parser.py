"""Requirements parser service - converts requirements-mamad.md to structured validation rules."""
import re
from typing import List, Dict, Optional, Any
from pathlib import Path

from src.models import ValidationSeverity
from src.utils.logging import get_logger

logger = get_logger(__name__)


class ValidationRule:
    """A single validation rule parsed from requirements."""
    
    def __init__(
        self,
        rule_id: str,
        section: str,
        category: str,
        description: str,
        severity: ValidationSeverity,
        field: Optional[str] = None,
        operator: Optional[str] = None,
        expected_value: Optional[Any] = None,
    ):
        self.rule_id = rule_id
        self.section = section
        self.category = category
        self.description = description
        self.severity = severity
        self.field = field
        self.operator = operator
        self.expected_value = expected_value
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert rule to dictionary."""
        return {
            "rule_id": self.rule_id,
            "section": self.section,
            "category": self.category,
            "description": self.description,
            "severity": self.severity.value,
            "field": self.field,
            "operator": self.operator,
            "expected_value": self.expected_value,
        }


class RequirementsParser:
    """Parser for requirements-mamad.md file."""
    
    def __init__(self, requirements_path: str = "requirements-mamad.md"):
        """Initialize parser with path to requirements file.
        
        Args:
            requirements_path: Path to requirements-mamad.md
        """
        self.requirements_path = Path(requirements_path)
        self._rules: Optional[List[ValidationRule]] = None
    
    def parse(self) -> List[ValidationRule]:
        """Parse requirements file into structured validation rules.
        
        Returns:
            List of ValidationRule objects
        """
        if self._rules is not None:
            return self._rules
        
        logger.info("Parsing requirements file", path=str(self.requirements_path))
        
        if not self.requirements_path.exists():
            raise FileNotFoundError(f"Requirements file not found: {self.requirements_path}")
        
        content = self.requirements_path.read_text(encoding="utf-8")
        self._rules = self._parse_content(content)
        
        logger.info("Requirements parsed successfully", rule_count=len(self._rules))
        return self._rules
    
    def _parse_content(self, content: str) -> List[ValidationRule]:
        """Parse markdown content into rules.
        
        Args:
            content: Markdown file content
            
        Returns:
            List of ValidationRule objects
        """
        rules = []
        
        # Section 1: Wall requirements
        rules.extend(self._parse_section_1(content))
        
        # Section 2: Height and volume
        rules.extend(self._parse_section_2(content))
        
        # Section 3: Door and window spacing
        rules.extend(self._parse_section_3(content))
        
        # Section 4: Ventilation system
        rules.extend(self._parse_section_4(content))
        
        # Section 5: Infrastructure
        rules.extend(self._parse_section_5(content))
        
        # Section 6: Concrete, steel, reinforcement
        rules.extend(self._parse_section_6(content))
        
        # Section 7: Opening specifications
        rules.extend(self._parse_section_7(content))
        
        # Section 8: Usage restrictions
        rules.extend(self._parse_section_8(content))
        
        return rules
    
    def _parse_section_1(self, content: str) -> List[ValidationRule]:
        """Parse Section 1: Wall requirements."""
        rules = []
        
        # Rule 1.1: External wall count (1-4)
        rules.append(ValidationRule(
            rule_id="1.1_wall_count",
            section="1.1",
            category="external_walls",
            description="לממד חייב להיות בין 1 ל-4 קירות חיצוניים",
            severity=ValidationSeverity.CRITICAL,
            field="external_wall_count",
            operator="between",
            expected_value={"min": 1, "max": 4}
        ))
        
        # Rule 1.2: Wall thickness based on external wall count
        # 1 external wall - 25cm (30cm with sliding blast window)
        rules.append(ValidationRule(
            rule_id="1.2_wall_thickness_1_wall",
            section="1.2",
            category="wall_thickness",
            description="1 קיר חיצוני: עובי 25 ס\"מ (קיר עם חלון הדף נגרר: 30 ס\"מ)",
            severity=ValidationSeverity.CRITICAL,
            field="wall_thickness_cm",
            operator=">=",
            expected_value=25  # 30 if sliding blast window present
        ))
        
        # 2 external walls - 25cm (30cm with sliding blast window)
        rules.append(ValidationRule(
            rule_id="1.2_wall_thickness_2_walls",
            section="1.2",
            category="wall_thickness",
            description="2 קירות חיצוניים: עובי 25 ס\"מ (קיר עם חלון הדף נגרר: 30 ס\"מ)",
            severity=ValidationSeverity.CRITICAL,
            field="wall_thickness_cm",
            operator=">=",
            expected_value=25
        ))
        
        # 3 external walls - 30cm
        rules.append(ValidationRule(
            rule_id="1.2_wall_thickness_3_walls",
            section="1.2",
            category="wall_thickness",
            description="3 קירות חיצוניים: עובי 30 ס\"מ",
            severity=ValidationSeverity.CRITICAL,
            field="wall_thickness_cm",
            operator=">=",
            expected_value=30
        ))
        
        # 4 external walls - 40cm
        rules.append(ValidationRule(
            rule_id="1.2_wall_thickness_4_walls",
            section="1.2",
            category="wall_thickness",
            description="4 קירות חיצוניים: עובי 40 ס\"מ",
            severity=ValidationSeverity.CRITICAL,
            field="wall_thickness_cm",
            operator=">=",
            expected_value=40
        ))
        
        # Rule 1.3: Wall distance from building edge
        rules.append(ValidationRule(
            rule_id="1.3_wall_distance_from_edge",
            section="1.3",
            category="wall_position",
            description="קיר במרחק קטן מ־2 מ' מהקו החיצוני של הבניין לא נחשב קיר חיצוני",
            severity=ValidationSeverity.MAJOR,
            field="wall_distance_from_edge_m",
            operator=">=",
            expected_value=2.0
        ))
        
        return rules
    
    def _parse_section_2(self, content: str) -> List[ValidationRule]:
        """Parse Section 2: Height and volume requirements."""
        rules = []
        
        # Rule 2.1: Minimum height
        rules.append(ValidationRule(
            rule_id="2.1_min_height",
            section="2.1",
            category="room_dimensions",
            description="גובה מינימלי: 2.50 מ'",
            severity=ValidationSeverity.CRITICAL,
            field="room_height_m",
            operator=">=",
            expected_value=2.5
        ))
        
        # Rule 2.2: Exception for 2.20m height
        rules.append(ValidationRule(
            rule_id="2.2_exception_height",
            section="2.2",
            category="room_dimensions",
            description="גובה של 2.20 מ' מותר רק כאשר הממ\"ד הוא במרתף או תוספת לבניין קיים ונפח החדר ≥ 22.5 מ\"ק",
            severity=ValidationSeverity.MAJOR,
            field="room_volume_m3",
            operator=">=",
            expected_value=22.5
        ))
        
        return rules
    
    def _parse_section_3(self, content: str) -> List[ValidationRule]:
        """Parse Section 3: Door and window spacing."""
        rules = []
        
        # Rule 3.1: Door spacing internal
        rules.append(ValidationRule(
            rule_id="3.1_door_spacing_internal",
            section="3.1",
            category="door_spacing",
            description="מרחק מקצה משקוף הדלת לקיר ניצב בתוך הממ\"ד: ≥ 90 ס\"מ",
            severity=ValidationSeverity.CRITICAL,
            field="door_spacing_internal_cm",
            operator=">=",
            expected_value=90
        ))
        
        # Rule 3.1: Door spacing external
        rules.append(ValidationRule(
            rule_id="3.1_door_spacing_external",
            section="3.1",
            category="door_spacing",
            description="מרחק מקצה הדלת לקיר ניצב מחוץ לממ\"ד: ≥ 75 ס\"מ",
            severity=ValidationSeverity.CRITICAL,
            field="door_spacing_external_cm",
            operator=">=",
            expected_value=75
        ))
        
        # Rule 3.2: Window spacing
        rules.append(ValidationRule(
            rule_id="3.2_window_spacing",
            section="3.2",
            category="window_spacing",
            description="מרחק חלון הדף מקיר ניצב: לפחות 20 ס\"מ",
            severity=ValidationSeverity.MAJOR,
            field="window_spacing_cm",
            operator=">=",
            expected_value=20
        ))

        # Rule 3.2: Sliding niches spacing
        rules.append(ValidationRule(
            rule_id="3.2_sliding_niches_spacing",
            section="3.2",
            category="window_spacing",
            description="מרחק בין נישות גרירה: 20 ס\"מ לפחות",
            severity=ValidationSeverity.MAJOR,
            field="window_niche_spacing_cm",
            operator=">=",
            expected_value=20,
        ))

        # Rule 3.2: Light openings spacing
        rules.append(ValidationRule(
            rule_id="3.2_light_openings_spacing",
            section="3.2",
            category="window_spacing",
            description="מרחק בין פתחי אור: 100 ס\"מ לפחות",
            severity=ValidationSeverity.MAJOR,
            field="window_light_openings_spacing_cm",
            operator=">=",
            expected_value=100,
        ))
        
        # Rule 3.2: Window to door spacing
        rules.append(ValidationRule(
            rule_id="3.2_window_door_spacing",
            section="3.2",
            category="window_spacing",
            description="חלון ודלת באותו קיר: מרחק הפרדה ≥ גובה הדלת או קיר מבטון בעובי 20 ס\"מ בין הפתחים",
            severity=ValidationSeverity.MAJOR,
            field="window_to_door_spacing_cm",
            operator=">=",
            expected_value=200  # Assuming 2m door height
        ))
        
        return rules
    
    def _parse_section_4(self, content: str) -> List[ValidationRule]:
        """Parse Section 4: Ventilation system requirements."""
        rules = []
        
        # Rule 4.2: ת״י 4570 note requirement
        rules.append(ValidationRule(
            rule_id="4.2_ventilation_note",
            section="4.2",
            category="ventilation",
            description="חובה לכתוב בתוכנית: \"מערכות האוורור והסינון יותקנו בהתאם לת״י 4570\"",
            severity=ValidationSeverity.MAJOR,
            field="has_ventilation_note",
            operator="==",
            expected_value=True
        ))
        
        return rules
    
    def _parse_section_5(self, content: str) -> List[ValidationRule]:
        """Parse Section 5: Infrastructure requirements."""
        rules = []
        
        # Rule 5.1: Air inlet pipe
        rules.append(ValidationRule(
            rule_id="5.1_air_inlet_pipe",
            section="5.1",
            category="infrastructure",
            description="צינור כניסת אוויר: קוטר 4\"",
            severity=ValidationSeverity.CRITICAL,
            field="has_air_inlet_pipe",
            operator="==",
            expected_value=True
        ))
        
        # Rule 5.1: Air outlet pipe
        rules.append(ValidationRule(
            rule_id="5.1_air_outlet_pipe",
            section="5.1",
            category="infrastructure",
            description="צינור פליטת אוויר: קוטר 4\"",
            severity=ValidationSeverity.CRITICAL,
            field="has_air_outlet_pipe",
            operator="==",
            expected_value=True
        ))
        
        return rules
    
    def _parse_section_6(self, content: str) -> List[ValidationRule]:
        """Parse Section 6: Concrete, steel, reinforcement."""
        rules = []
        
        # Rule 6.1: Concrete grade
        rules.append(ValidationRule(
            rule_id="6.1_concrete_grade",
            section="6.1",
            category="materials",
            description="סוג בטון: ב-30 לפחות",
            severity=ValidationSeverity.CRITICAL,
            field="concrete_grade",
            operator=">=",
            expected_value="B-30"
        ))
        
        return rules
    
    def _parse_section_7(self, content: str) -> List[ValidationRule]:
        """Parse Section 7: Opening specifications."""
        rules = []
        
        # Rule 7: Opening standards
        rules.append(ValidationRule(
            rule_id="7_opening_standards",
            section="7",
            category="openings",
            description="כל האלמנטים (דלת, חלון, פתח מילוט) חייבים להיות מאושרים לפי ת\"י 4422",
            severity=ValidationSeverity.CRITICAL,
            field="openings_certified",
            operator="==",
            expected_value=True
        ))
        
        return rules
    
    def _parse_section_8(self, content: str) -> List[ValidationRule]:
        """Parse Section 8: Usage restrictions."""
        rules = []
        
        # Rule 8.1: Not a passageway
        rules.append(ValidationRule(
            rule_id="8.1_not_passageway",
            section="8.1",
            category="usage",
            description="אסור שהממ\"ד ישמש כמעבר בין חדרים",
            severity=ValidationSeverity.MAJOR,
            field="is_passageway",
            operator="==",
            expected_value=False
        ))
        
        # Rule 8.1: No fixed furniture
        rules.append(ValidationRule(
            rule_id="8.1_no_fixed_furniture",
            section="8.1",
            category="usage",
            description="אסור להצמיד ארונות קבועים או אלמנטים בנויים לקירות הממ\"ד",
            severity=ValidationSeverity.MAJOR,
            field="has_fixed_furniture",
            operator="==",
            expected_value=False
        ))
        
        # Rule 8.2: Accessibility
        rules.append(ValidationRule(
            rule_id="8.2_accessibility",
            section="8.2",
            category="usage",
            description="חייב להיות נגיש ולא מעבר דרך חדרי רחצה/מטבח",
            severity=ValidationSeverity.MAJOR,
            field="accessible_without_bathroom",
            operator="==",
            expected_value=True
        ))
        
        return rules
    
    def get_rules_by_category(self, category: str) -> List[ValidationRule]:
        """Get all rules for a specific category.
        
        Args:
            category: Rule category to filter by
            
        Returns:
            List of rules in the category
        """
        if self._rules is None:
            self.parse()
        
        return [rule for rule in self._rules if rule.category == category]
    
    def get_rule_by_id(self, rule_id: str) -> Optional[ValidationRule]:
        """Get a specific rule by ID.
        
        Args:
            rule_id: Rule identifier
            
        Returns:
            ValidationRule or None if not found
        """
        if self._rules is None:
            self.parse()
        
        for rule in self._rules:
            if rule.rule_id == rule_id:
                return rule
        return None


# Global singleton instance
_parser: Optional[RequirementsParser] = None


def get_requirements_parser() -> RequirementsParser:
    """Get the global requirements parser instance.
    
    Returns:
        RequirementsParser singleton
    """
    global _parser
    if _parser is None:
        _parser = RequirementsParser()
        _parser.parse()  # Pre-load rules
    return _parser
