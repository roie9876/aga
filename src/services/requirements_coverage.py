"""Service for tracking requirements coverage across validation runs."""
from typing import Dict, List, Any
from src.utils.logging import get_logger

logger = get_logger(__name__)


class RequirementsCoverageTracker:
    """Tracks which MAMAD requirements have been validated and their status."""
    
    # Define all MAMAD requirements from requirements-mamad.md
    ALL_REQUIREMENTS = {
        "1.1": {"category": "קירות", "description": "מיקום ממ\"ד - מרחק מקיר חיצוני", "severity": "critical"},
        "1.2": {"category": "קירות", "description": "עובי קיר - 25-40 ס\"מ לפי מספר קירות חיצוניים", "severity": "critical"},
        "2.1": {"category": "גובה החדר", "description": "גובה מינימלי 2.50 מטר", "severity": "critical"},
        "2.2": {"category": "גובה החדר", "description": "גובה 2.20 מטר במרתף/תוספת בניה (עם נפח ≥22.5 מ\"ק)", "severity": "warning"},
        "3.1": {"category": "פתחים", "description": "ריווח דלת - ≥90cm מבפנים, ≥75cm מבחוץ", "severity": "warning"},
        "3.2": {"category": "פתחים", "description": "ריווח חלון - ≥20cm בין נישות, ≥100cm בין פתחי אור", "severity": "warning"},
        "4.1": {"category": "אוורור", "description": "מערכת אוורור וסינון בהתאם לת\"י 4570", "severity": "critical"},
        "4.2": {"category": "אוורור", "description": "הערה בתכנית: 'מערכות האוורור והסינון יותקנו בהתאם לת\"י 4570'", "severity": "warning"},
        "5.1": {"category": "תשתיות", "description": "צנרת במרחק ≥2.5cm מפני בטון", "severity": "error"},
        "5.2": {"category": "תשתיות", "description": "צנרת חשמל/מים בקירות - מקסימום ברזל 2.5%", "severity": "error"},
        "6.1": {"category": "חומרים", "description": "בטון - מינימום B-30", "severity": "critical"},
        "6.2": {"category": "חומרים", "description": "פלדה - רק מגולגלת בחום או מרותכת (לא משוכה בקור)", "severity": "critical"},
        "6.3": {"category": "חומרים", "description": "זיון - ריווח ≤20cm חיצוני, ≤10cm פנימי", "severity": "critical"},
        "7.1": {"category": "ביצוע פתחים", "description": "ביצוע לפי ת\"י 4422", "severity": "error"},
        "8.1": {"category": "מגבלות שימוש", "description": "אין מעבר בין חדרים דרך הממ\"ד", "severity": "warning"},
        "8.2": {"category": "מגבלות שימוש", "description": "אין ריהוט קבוע", "severity": "warning"},
    }
    
    def __init__(self):
        """Initialize the coverage tracker."""
        logger.info("RequirementsCoverageTracker initialized")
    
    def calculate_coverage(self, validation_result: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate requirements coverage for a validation run.
        
        Args:
            validation_result: Full validation result with analyzed_segments
            
        Returns:
            Coverage report with status per requirement
        """
        coverage = {}
        
        # Initialize all requirements as "not_checked"
        for req_id, req_info in self.ALL_REQUIREMENTS.items():
            coverage[req_id] = {
                "requirement_id": req_id,
                "category": req_info["category"],
                "description": req_info["description"],
                "severity": req_info["severity"],
                "status": "not_checked",  # not_checked, passed, failed, skipped
                "segments_checked": [],
                "violations": []
            }
        
        # Process each analyzed segment
        for segment in validation_result.get("analyzed_segments", []):
            classification = segment.get("analysis_data", {}).get("classification", {})
            relevant_reqs = classification.get("relevant_requirements", [])
            validation = segment.get("validation", {})
            
            # Mark relevant requirements as checked
            for req_id in relevant_reqs:
                if req_id not in coverage:
                    continue
                
                coverage[req_id]["segments_checked"].append(segment.get("segment_id"))
                
                # Check if there are violations for this requirement
                segment_violations = [
                    v for v in validation.get("violations", [])
                    if v.get("rule_id", "").startswith(req_id.replace(".", "_"))
                ]
                
                if segment_violations:
                    coverage[req_id]["status"] = "failed"
                    coverage[req_id]["violations"].extend(segment_violations)
                elif coverage[req_id]["status"] == "not_checked":
                    coverage[req_id]["status"] = "passed"
        
        # Calculate statistics
        total = len(coverage)
        checked = sum(1 for c in coverage.values() if c["status"] != "not_checked")
        passed = sum(1 for c in coverage.values() if c["status"] == "passed")
        failed = sum(1 for c in coverage.values() if c["status"] == "failed")
        not_checked = sum(1 for c in coverage.values() if c["status"] == "not_checked")
        
        coverage_percentage = (checked / total * 100) if total > 0 else 0
        pass_percentage = (passed / total * 100) if total > 0 else 0
        
        # Group by category
        by_category = {}
        for req_id, req_data in coverage.items():
            category = req_data["category"]
            if category not in by_category:
                by_category[category] = []
            by_category[category].append(req_data)
        
        logger.info("Coverage calculated",
                   total=total,
                   checked=checked,
                   passed=passed,
                   failed=failed,
                   not_checked=not_checked,
                   coverage_percentage=coverage_percentage)
        
        return {
            "statistics": {
                "total_requirements": total,
                "checked": checked,
                "passed": passed,
                "failed": failed,
                "not_checked": not_checked,
                "coverage_percentage": round(coverage_percentage, 1),
                "pass_percentage": round(pass_percentage, 1)
            },
            "requirements": coverage,
            "by_category": by_category,
            "missing_segments_needed": self._get_missing_segments(coverage)
        }
    
    def _get_missing_segments(self, coverage: Dict[str, Any]) -> List[Dict[str, str]]:
        """Get list of segment types needed to complete coverage.
        
        Args:
            coverage: Coverage data per requirement
            
        Returns:
            List of missing segment descriptions
        """
        not_checked = [
            {
                "requirement_id": req_id,
                "description": req_data["description"],
                "category": req_data["category"],
                "severity": req_data["severity"],
                "needed_segment_type": self._map_requirement_to_segment_type(req_id)
            }
            for req_id, req_data in coverage.items()
            if req_data["status"] == "not_checked"
        ]
        
        return not_checked
    
    def _map_requirement_to_segment_type(self, req_id: str) -> str:
        """Map requirement ID to needed segment type.
        
        Args:
            req_id: Requirement ID (e.g., "1.2", "6.3")
            
        Returns:
            Hebrew description of needed segment type
        """
        mapping = {
            "1.1": "תכנית קומה - מיקום ממ\"ד ביחס לקירות חיצוניים",
            "1.2": "חתך קיר - עובי ומספר קירות חיצוניים",
            "2.1": "חתך אנכי - גובה החדר",
            "2.2": "חתך אנכי - גובה בתוספת בניה/מרתף + נפח החדר",
            "3.1": "פרט דלת - ריווח מקיר ניצב",
            "3.2": "פרט חלון - ריווח בין פתחים",
            "4.1": "מערכת אוורור - פרט התקנה",
            "4.2": "הערות כלליות - אזכור ת\"י 4570",
            "5.1": "פרט צנרת - מרחק מבטון",
            "5.2": "חתך קיר עם צנרת - אחוז ברזל",
            "6.1": "הערות כלליות/פרט - ציון סוג בטון B-30",
            "6.2": "הערות כלליות/פרט - ציון סוג פלדה",
            "6.3": "פרט זיון - ריווח מוטות",
            "7.1": "פרט פתחים - התייחסות לת\"י 4422",
            "8.1": "תכנית קומה - בדיקת מעבר בין חדרים",
            "8.2": "תכנית קומה - אין ריהוט קבוע",
        }
        
        return mapping.get(req_id, f"סגמנט רלוונטי לדרישה {req_id}")


def get_coverage_tracker() -> RequirementsCoverageTracker:
    """Get singleton instance of coverage tracker."""
    return RequirementsCoverageTracker()
