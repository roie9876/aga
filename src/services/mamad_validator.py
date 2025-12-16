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
        self.requirement_evaluations: List[Dict[str, Any]] = []
        # Per-run skip list (e.g., requirements already passed in earlier segments)
        self._skip_requirements: set[str] = set()

    def _add_requirement_evaluation(
        self,
        requirement_id: str,
        status: str,
        *,
        reason_not_checked: Optional[str] = None,
        evidence: Optional[List[Dict[str, Any]]] = None,
        notes_he: Optional[str] = None,
    ) -> None:
        # If a requirement already passed elsewhere, do not re-evaluate it.
        # Force a consistent explicit not_checked evaluation so UI/coverage are stable.
        if requirement_id in self._skip_requirements:
            # Avoid duplicating the same skip evaluation.
            for existing in self.requirement_evaluations:
                if (
                    isinstance(existing, dict)
                    and existing.get("requirement_id") == requirement_id
                    and existing.get("status") == "not_checked"
                    and existing.get("reason_not_checked") == "already_passed_in_other_segment"
                ):
                    return
            status = "not_checked"
            reason_not_checked = "already_passed_in_other_segment"
            if not notes_he:
                notes_he = "דרישה זו כבר עברה בסגמנט קודם ולכן לא הורצה שוב בסגמנט זה."
            evidence = []

        ev: Dict[str, Any] = {
            "requirement_id": requirement_id,
            "status": status,
            "evidence": evidence or [],
        }
        if reason_not_checked:
            ev["reason_not_checked"] = reason_not_checked
        if notes_he:
            ev["notes_he"] = notes_he
        self.requirement_evaluations.append(ev)

    def _evidence_dimension(
        self,
        *,
        value: Optional[float],
        unit: Optional[str],
        element: Optional[str] = None,
        location: Optional[str] = None,
        text: Optional[str] = None,
        raw: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return {
            "evidence_type": "dimension",
            "value": value,
            "unit": unit,
            "element": element,
            "location": location,
            "text": text,
            "raw": raw,
        }

    def _evidence_text(
        self,
        *,
        text: str,
        element: Optional[str] = None,
        location: Optional[str] = None,
        raw: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return {
            "evidence_type": "text",
            "text": text,
            "element": element,
            "location": location,
            "raw": raw,
        }

    def _sync_violations_from_requirement_evaluations(self) -> None:
        """Create legacy Violation objects from evidence-first failed evaluations.

        The UI and some flows still rely on `violations` to display failures.
        We keep evidence-first as the source of truth, but mirror failed evaluations
        into violations so that a `failed` requirement cannot appear as a green segment.
        """

        severity_by_req: Dict[str, ViolationSeverity] = {
            "1.2": ViolationSeverity.CRITICAL,
            "2.1": ViolationSeverity.CRITICAL,
            "2.2": ViolationSeverity.WARNING,
            "3.1": ViolationSeverity.WARNING,
            "3.2": ViolationSeverity.WARNING,
            "4.2": ViolationSeverity.WARNING,
            "6.1": ViolationSeverity.WARNING,
            "6.2": ViolationSeverity.CRITICAL,
            "6.3": ViolationSeverity.CRITICAL,
        }

        category_by_req: Dict[str, str] = {
            "1.2": "קירות",
            "2.1": "גובה",
            "2.2": "גובה",
            "3.1": "דלת",
            "3.2": "חלון",
            "4.2": "אוורור",
            "6.1": "בטון",
            "6.2": "פלדה",
            "6.3": "זיון",
        }

        requirement_text_by_req: Dict[str, str] = {
            "1.2": "עובי קיר - 25-40 ס\"מ לפי מספר קירות חיצוניים",
            "2.1": "גובה מינימלי 2.50 מטר",
            "2.2": "גובה 2.20 מטר במרתף/תוספת בניה (עם נפח ≥22.5 מ\"ק)",
            "3.1": "ריווח דלת - ≥90cm מבפנים, ≥75cm מבחוץ",
            "3.2": "ריווח חלון - ≥20cm בין נישות, ≥100cm בין פתחי אור",
            "4.2": 'הערת אוורור וסינון בהתאם לת"י 4570',
            "6.1": "דרגת בטון ב-30 לפחות",
            "6.2": "פלדה מעוגלת בחום או רתיך בלבד (לא משוכה בקור)",
            "6.3": "פסיעת זיון: חיצוני ≤20 ס\"מ, פנימי ≤10 ס\"מ",
        }

        existing_rule_ids = {v.rule_id for v in self.violations}

        def _summarize_evidence(ev_items: Any) -> str:
            if not isinstance(ev_items, list) or not ev_items:
                return "לא צוין"
            parts: list[str] = []
            for item in ev_items:
                if not isinstance(item, dict):
                    continue
                if item.get("value") is not None:
                    try:
                        unit = item.get("unit") or ""
                        parts.append(f"{float(item.get('value')):.2f} {unit}".strip())
                    except Exception:
                        pass
                elif item.get("text"):
                    parts.append(str(item.get("text"))[:60])
                if len(parts) >= 3:
                    break
            return ", ".join(parts) if parts else "לא צוין"

        for ev in self.requirement_evaluations:
            if not isinstance(ev, dict):
                continue
            if ev.get("status") != "failed":
                continue
            req_id = ev.get("requirement_id")
            if not isinstance(req_id, str) or not req_id:
                continue
            rule_id = f"REQ_{req_id.replace('.', '_')}"
            if rule_id in existing_rule_ids:
                continue

            notes_he = str(ev.get("notes_he") or "")
            found = _summarize_evidence(ev.get("evidence"))
            location = ""
            if isinstance(ev.get("evidence"), list) and ev.get("evidence"):
                first = ev.get("evidence")[0]
                if isinstance(first, dict):
                    location = str(first.get("location") or "")

            self.violations.append(
                Violation(
                    rule_id=rule_id,
                    severity=severity_by_req.get(req_id, ViolationSeverity.WARNING),
                    category=category_by_req.get(req_id, "כללי"),
                    description_he=notes_he or f"כשל בדרישה {req_id}",
                    requirement=requirement_text_by_req.get(req_id, f"דרישה {req_id}"),
                    found=found,
                    location=location,
                )
            )
        
    def validate_segment(
        self,
        analysis_data: Dict[str, Any],
        *,
        demo_mode: bool = False,
        enabled_requirements: Optional[set[str]] = None,
        skip_requirements: Optional[set[str]] = None,
    ) -> Dict[str, Any]:
        """
        Validate a single segment's analysis data against MAMAD requirements.
        
        Only runs validation rules that are RELEVANT to this segment based on its classification.
        
        Args:
            analysis_data: Extracted data from GPT analysis (includes classification)
            demo_mode: If True, run a reduced subset of checks for demo purposes.
            
        Returns:
            Validation result with violations and status
        """
        self.violations = []  # Reset violations
        self.requirement_evaluations = []
        self._skip_requirements = set(skip_requirements or set())
        
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
                   has_elements=bool(analysis_data.get("structural_elements")),
                   demo_mode=demo_mode)
        # Map categories to validation functions
        validation_map = {
            "WALL_SECTION": [self._validate_wall_thickness],
            "ROOM_LAYOUT": [
                self._validate_room_height,
                self._validate_external_wall_count,
                self._validate_external_wall_classification,
                self._validate_tower_continuity,
            ],
            "DOOR_DETAILS": [self._validate_door_spacing],
            "WINDOW_DETAILS": [self._validate_window_spacing],
            "REBAR_DETAILS": [self._validate_rebar_specifications],
            "MATERIALS_SPECS": [self._validate_concrete_grade, self._validate_steel_type],
            "GENERAL_NOTES": [self._validate_ventilation_note],
            "SECTIONS": [self._validate_room_height, self._validate_high_wall],
        }

        def _has_wall_thickness_evidence(data: Dict[str, Any]) -> bool:
            dims = data.get("dimensions")
            if isinstance(dims, list):
                for d in dims:
                    if not isinstance(d, dict):
                        continue
                    element = str(d.get("element") or "").lower()
                    if "wall thickness" in element or "עובי" in element:
                        if d.get("value") is not None:
                            return True

            elements = data.get("structural_elements")
            if isinstance(elements, list):
                for el in elements:
                    if not isinstance(el, dict):
                        continue
                    if str(el.get("type") or "").lower() != "wall":
                        continue
                    if el.get("thickness") is not None:
                        return True
            return False
        # Which official requirement IDs each validator corresponds to.
        # IMPORTANT: We only count a requirement as "checked" if the validator actually
        # had enough evidence to evaluate it (or emitted a missing-info violation).
        validator_to_requirements = {
            self._validate_wall_thickness: ["1.2"],
            self._validate_room_height: ["2.1", "2.2"],
            self._validate_external_wall_count: ["1.1"],
            self._validate_external_wall_classification: ["1.3"],
            self._validate_high_wall: ["1.4"],
            self._validate_tower_continuity: ["1.5"],
            self._validate_door_spacing: ["3.1"],
            self._validate_window_spacing: ["3.2"],
            self._validate_rebar_specifications: ["6.3"],
            self._validate_concrete_grade: ["6.1"],
            self._validate_steel_type: ["6.2"],
            self._validate_ventilation_note: ["4.2"],
        }

        if demo_mode:
            # For demo: focus on groups 1-3 to reduce runtime and complexity.
            allowed_categories = {"WALL_SECTION", "ROOM_LAYOUT", "SECTIONS", "DOOR_DETAILS", "WINDOW_DETAILS"}
            categories = [c for c in categories if c in allowed_categories]
            if not categories:
                categories = ["OTHER"]
        
        # Run validations based on ALL classified categories (primary + secondary)
        validations_to_run = []
        planned_requirements: set[str] = set()
        skipped_due_to_already_passed: set[str] = set()
        for cat in categories:
            for fn in validation_map.get(cat, []):
                # If user selected a subset of requirements, only allow validators that map
                # to at least one enabled requirement.
                mapped_all = set(validator_to_requirements.get(fn, []))

                # Track requirements that would have been planned but are skipped due to
                # already passing in other segments.
                for req in mapped_all:
                    if req in self._skip_requirements and (enabled_requirements is None or req in enabled_requirements):
                        skipped_due_to_already_passed.add(req)

                mapped_effective = {r for r in mapped_all if r not in self._skip_requirements}

                if enabled_requirements is not None:
                    mapped_effective = {r for r in mapped_effective if r in enabled_requirements}
                    if mapped_all and not mapped_effective:
                        continue
                else:
                    # If all requirements for this validator are skipped, do not run it.
                    if mapped_all and not mapped_effective:
                        continue

                if fn not in validations_to_run:
                    validations_to_run.append(fn)
                for req in mapped_effective:
                    planned_requirements.add(req)

        # Heuristic: Some segments are classified as ROOM_LAYOUT but still contain
        # explicit wall thickness callouts (e.g., 20/25/30/40 along wall lines).
        # In those cases, we should still run Requirement 1.2 validator.
        wants_12 = isinstance(relevant_requirements, list) and "1.2" in relevant_requirements
        has_thickness = _has_wall_thickness_evidence(analysis_data)
        should_force_12 = wants_12 or has_thickness
        if should_force_12:
            if (enabled_requirements is None or "1.2" in enabled_requirements) and "1.2" not in self._skip_requirements:
                if self._validate_wall_thickness not in validations_to_run:
                    validations_to_run.append(self._validate_wall_thickness)
                planned_requirements.add("1.2")

        # Manual ROI / unknown classification handling:
        # If the user explicitly enabled requirement groups but the segment classification
        # did not map to any validators (e.g., category OTHER or empty classification),
        # run the validators that correspond to the enabled requirements anyway.
        # This allows us to return explicit `not_checked` evaluations with reasons instead
        # of claiming that no checks were performed.
        ran_by_enabled_requirements = False
        if enabled_requirements is not None and not validations_to_run:
            for fn, reqs in validator_to_requirements.items():
                mapped_all = set(reqs)
                for req in mapped_all:
                    if req in self._skip_requirements and req in enabled_requirements:
                        skipped_due_to_already_passed.add(req)

                mapped_effective = {r for r in mapped_all if r in enabled_requirements and r not in self._skip_requirements}
                if mapped_all and mapped_effective:
                    validations_to_run.append(fn)
                    ran_by_enabled_requirements = True
                    for req in mapped_effective:
                        planned_requirements.add(req)

        # If the user explicitly enabled requirements that have no validator implementation,
        # emit explicit not_checked evaluations so the UI doesn't show a silent "nothing happened".
        if enabled_requirements is not None:
            unsupported = set(enabled_requirements) - planned_requirements - skipped_due_to_already_passed
            for req in sorted(unsupported):
                self._add_requirement_evaluation(
                    req,
                    "not_checked",
                    reason_not_checked="validator_not_implemented",
                    notes_he="המערכת עדיין לא מממשת בדיקה דטרמיניסטית לדרישה זו בסגמנטים; לא בוצעה בדיקה.",
                )

        # Emit explicit not_checked evaluations for requirements skipped because they already
        # passed in earlier segments (keeps UI/coverage consistent).
        for req in sorted(skipped_due_to_already_passed):
            self._add_requirement_evaluation(req, "not_checked")

        checked_requirements: List[str] = []
        skipped_requirements: List[str] = []
        
        decision_summary_he = ""

        if not validations_to_run:
            # If category not recognized or OTHER, skip validation
            logger.info("No specific validations for this segment category",
                       category=primary_category)
            if demo_mode:
                decision_summary_he = (
                    f"לא הופעלו בדיקות כי בדמו המערכת מתמקדת בדרישות 1–3 בלבד, "
                    f"והקטגוריה שסווגה היא '{primary_category}'."
                )
            else:
                decision_summary_he = (
                    f"לא הופעלו בדיקות כי הקטגוריה שסווגה היא '{primary_category}'. "
                    "המערכת מפעילה בדיקות רק עבור קטגוריות מוגדרות (כמו ROOM_LAYOUT/SECTIONS/WALL_SECTION וכו')."
                )
        else:
            checked_set: set[str] = set()
            for validation_func in validations_to_run:
                did_check = validation_func(analysis_data)
                # Safety: if a validator didn't explicitly confirm it checked evidence,
                # we treat it as NOT checked (prevents false "passed" without evidence).
                if did_check is None:
                    did_check = False

            # Compute checked requirements from explicit evaluations (evidence-first).
            for ev in self.requirement_evaluations:
                if not isinstance(ev, dict):
                    continue
                req_id = ev.get("requirement_id")
                status = ev.get("status")
                if req_id and status in {"passed", "failed"}:
                    checked_set.add(req_id)

            checked_requirements = sorted(checked_set)
            skipped_requirements = sorted(planned_requirements - checked_set)

            if demo_mode:
                decision_summary_he = (
                    f"(דמו) הופעלו בדיקות לפי קטגוריות הסגמנט: {', '.join(categories)}. "
                    f"דרישות שנבדקו בדמו בסגמנט זה: {', '.join(checked_requirements) if checked_requirements else 'אין'}. "
                    "בדיקות נוספות קיימות במערכת אך לא הורצו בדמו כדי לקצר זמן ריצה."
                )
            else:
                decision_summary_he = (
                    f"הופעלו בדיקות לפי קטגוריות הסגמנט: {', '.join(categories)}. "
                    f"דרישות שנבדקו בסגמנט זה: {', '.join(checked_requirements) if checked_requirements else 'אין'}. "
                    "דרישות אחרות לא נבדקו כי הן ממופות לקטגוריות אחרות או דורשות סגמנטים מסוג אחר (למשל פרט/חתך)."
                )

            if ran_by_enabled_requirements and not checked_requirements:
                decision_summary_he = (
                    f"הופעלו בדיקות לפי בחירת המשתמש (check_groups) למרות שהסיווג לא היה חד-משמעי. "
                    f"לא נמצאו ראיות מספיקות כדי לאמת אף דרישה בסגמנט זה. "
                    f"דרישות שנוסו: {', '.join(sorted(planned_requirements)) if planned_requirements else 'אין'}."
                )

        # Mirror evidence-first failures into legacy violations for UI/back-compat.
        self._sync_violations_from_requirement_evaluations()
        
        # Categorize violations
        critical = [v for v in self.violations if v.severity == ViolationSeverity.CRITICAL]
        errors = [v for v in self.violations if v.severity == ViolationSeverity.ERROR]
        warnings = [v for v in self.violations if v.severity == ViolationSeverity.WARNING]

        # IMPORTANT:
        # A segment must never be marked as "passed" if we didn't actually check any requirements.
        # "No checks" is an explicit status (used heavily for manual ROI flows).
        checks_performed = bool(checked_requirements)
        # Non-breaking signal for UI/stream: validators may have run but still end in not_checked.
        checks_attempted = bool(validations_to_run) or bool(self.requirement_evaluations)
        has_failures = len(critical) > 0 or len(errors) > 0

        if has_failures:
            status = "failed"
            passed = False
        elif checks_performed:
            status = "passed"
            passed = True
        else:
            status = "not_checked"
            passed = False
        
        logger.info("Validation complete",
                   status=status,
                   passed=passed,
                   checks_performed=checks_performed,
                   critical=len(critical),
                   errors=len(errors),
                   warnings=len(warnings))
        
        return {
            "status": status,
            "passed": passed,
            "total_violations": len(self.violations),
            "critical_count": len(critical),
            "error_count": len(errors),
            "warning_count": len(warnings),
            "violations": [self._violation_to_dict(v) for v in self.violations],
            "checked_requirements": checked_requirements,
            "requirement_evaluations": self.requirement_evaluations,
            "decision_summary_he": decision_summary_he,
            "debug": {
                "categories_used": categories,
                "validators_run": [fn.__name__ for fn in validations_to_run],
                "primary_category": primary_category,
                "relevant_requirements": relevant_requirements,
                "demo_mode": demo_mode,
                "planned_requirements": sorted(planned_requirements),
                "skipped_requirements": skipped_requirements,
                "ran_by_enabled_requirements": ran_by_enabled_requirements,
            },
            "checks_performed": checks_performed,
            "checks_attempted": checks_attempted,
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
        if not elements:
            self._add_requirement_evaluation(
                "1.2",
                "not_checked",
                reason_not_checked="no_structural_elements",
                notes_he="לא נמצאו אלמנטים מבניים בסגמנט ולכן לא ניתן לבדוק עובי קירות.",
            )
            return False

        walls = [e for e in elements if e.get("type") in ["wall", "קיר", "קיר חיצוני"]]
        if not walls:
            # Not enough information to evaluate thickness.
            self._add_requirement_evaluation(
                "1.2",
                "not_checked",
                reason_not_checked="no_walls_detected",
                notes_he="לא זוהו קירות בסגמנט ולכן לא ניתן לבדוק עובי קיר.",
            )
            return False
        
        def _infer_sides_from_text(text: str) -> set[str]:
            t = (text or "").lower()
            sides: set[str] = set()
            # Hebrew
            if any(k in t for k in ["שמאל", "צד שמאל", "קיר שמאל", "שמאלה"]):
                sides.add("left")
            if any(k in t for k in ["ימין", "צד ימין", "קיר ימין", "ימינה"]):
                sides.add("right")
            if any(k in t for k in ["עליון", "למעלה", "צד עליון", "קיר עליון", "צפון"]):
                sides.add("top")
            if any(k in t for k in ["תחתון", "למטה", "צד תחתון", "קיר תחתון", "דרום"]):
                sides.add("bottom")
            # English
            if "left" in t:
                sides.add("left")
            if "right" in t:
                sides.add("right")
            # Be conservative: free-form OCR locations often include words like "top"/"bottom"
            # that describe drawing placement (not the room's wall side). Only accept these when
            # explicitly tied to a wall/side direction.
            if any(p in t for p in ["north wall", "wall north", "top wall", "wall top", "top side", "upper wall"]):
                sides.add("top")
            if any(p in t for p in ["south wall", "wall south", "bottom wall", "wall bottom", "bottom side", "lower wall"]):
                sides.add("bottom")
            if "east" in t:
                sides.add("right")
            if "west" in t:
                sides.add("left")
            return sides

        def _infer_sides_from_any(obj: Any) -> set[str]:
            """Extract side hints from nested dict/list evidence structures."""
            sides: set[str] = set()
            if obj is None:
                return sides
            if isinstance(obj, str):
                return _infer_sides_from_text(obj)
            if isinstance(obj, (int, float, bool)):
                return sides
            if isinstance(obj, list):
                for item in obj:
                    sides |= _infer_sides_from_any(item)
                return sides
            if isinstance(obj, dict):
                for v in obj.values():
                    sides |= _infer_sides_from_any(v)
                return sides
            # Fallback: string representation
            try:
                return _infer_sides_from_text(str(obj))
            except Exception:
                return sides

        # Rule-of-thumb inference: door => internal, window => external (when side can be inferred)
        door_sides: set[str] = set()
        window_sides: set[str] = set()
        has_any_window = False
        has_mamad_window_marker = False
        has_sliding_window_marker = False
        window_external_marker_present = False

        for el in elements:
            if not isinstance(el, dict):
                continue
            el_type = str(el.get("type") or "").lower()
            loc = str(el.get("location") or "")
            notes = str(el.get("notes") or "")
            combined = f"{loc} {notes}"
            if el_type == "door":
                # Stronger signal when it's explicitly a MAMAD door.
                if any(k in combined for k in ["ממ\"ד", "ממד", "ד.ה", "דלת הדף", "דלת ממ\"ד", "משוריינת", "ממ" ]):
                    door_sides |= _infer_sides_from_text(combined)
            elif el_type == "window":
                has_any_window = True
                window_sides |= _infer_sides_from_text(combined)
                combined_lower = combined.lower()

                # Blast-window markers (not necessarily sliding).
                if any(k in combined for k in ["חלון הדף", "הדף", "ת\"י 4422", "4422", "ממ\"ד", "ממד", "blast"]):
                    has_mamad_window_marker = True

                # Sliding-window markers: the 30cm window-case in 1.2 applies ONLY to sliding blast windows.
                # Be conservative: only treat as sliding when explicitly indicated.
                if any(
                    k in combined_lower
                    for k in [
                        "נגרר",
                        "נגררת",
                        "נגררים",
                        "נישת גרירה",
                        "גרירה",
                        "sliding",
                        "pocket",
                    ]
                ):
                    has_sliding_window_marker = True
                if any(k in combined.lower() for k in ["קיר חיצוני", "חיצוני", "external", "outside", "exterior", "חזית", "מעטפת", "perimeter", "outer"]):
                    window_external_marker_present = True

        def _classify_wall_exposure(location_text: str, wall_type_text: str, *, wall: Dict[str, Any]) -> str:
            """Return 'external' | 'internal' | 'unknown' based on labels and rule-of-thumb inference."""
            location_lower = (location_text or "").lower()
            wall_type_lower = (wall_type_text or "").lower()

            # Consider the full wall context (location/notes/evidence) when searching for explicit markers.
            wall_notes = str(wall.get("notes") or "")
            ev_items = wall.get("evidence")
            ev_text = ""
            if isinstance(ev_items, list):
                # Evidence may contain nested dicts; include them in text search.
                ev_text = " ".join([str(x) for x in ev_items])
            combined_lower = f"{location_text or ''} {wall_type_text or ''} {wall_notes} {ev_text}".lower()

            # Explicit external markers
            external_markers = [
                "קיר חיצוני",
                "חיצוני",
                "external",
                "outside",
                "exterior",
                "חזית",
                "מעטפת",
                "היקפי",
                "perimeter",
                "cyan perimeter",
                "outer band",
                "outer wall",
            ]
            # Explicit internal markers
            internal_markers = [
                "קיר פנימי",
                "פנימי",
                "internal",
                "inside",
                "partition",
                "adjacent",
                "אזור פנימי",
                "חלל פנימי",
            ]

            # If any internal marker appears, treat as internal even if 'outer wall' appears,
            # because some drawings use 'outer wall' loosely for wall thickness callouts.
            if any(m.lower() in combined_lower for m in internal_markers):
                return "internal"

            if any(m.lower() in combined_lower for m in external_markers):
                return "external"

            # Side-hint inference from wall context (location/notes/evidence)
            wall_side_hints: set[str] = set()
            wall_side_hints |= _infer_sides_from_text(location_text)
            wall_side_hints |= _infer_sides_from_text(str(wall.get("notes") or ""))
            if isinstance(ev_items, list):
                wall_side_hints |= _infer_sides_from_any(ev_items)

            # Door/window rule-of-thumb (when a side can be inferred)
            if wall_side_hints and (wall_side_hints & door_sides):
                return "internal"

            # A thickness callout referencing multiple sides is usually a perimeter (external) wall set.
            # Do NOT assume a single-side callout is external just because a window exists on that side.
            if len(wall_side_hints) >= 2 and not (wall_side_hints & door_sides):
                return "external"

            return "unknown"

        # Prefer an explicitly extracted external-wall count AFTER applying counting exceptions (1.1–1.3).
        # This supports the updated spec in requirements-mamad.md where 1.2 depends on the *final* count.
        external_wall_count_raw = None
        for key in [
            "external_wall_count_after_exceptions",
            "external_wall_count_final",
            "external_wall_count_post_exceptions",
            "external_wall_count",
        ]:
            if key in data:
                external_wall_count_raw = data.get(key)
                break
        num_external_known: Optional[int] = None
        if isinstance(external_wall_count_raw, int) and 1 <= external_wall_count_raw <= 4:
            num_external_known = external_wall_count_raw

        external_wall_count_source = str(data.get("external_wall_count_source") or "").strip()
        external_wall_count_confidence = data.get("external_wall_count_confidence")
        external_wall_count_evidence = data.get("external_wall_count_evidence")
        if not isinstance(external_wall_count_evidence, list):
            external_wall_count_evidence = []

        # Check each wall thickness. We only apply requirement 1.2 to walls that are explicitly external.
        evidence: List[Dict[str, Any]] = []
        parsed_external_thicknesses: List[float] = []
        parsed_internal_thicknesses: List[float] = []
        parsed_unknown_thicknesses: List[float] = []
        explicit_external_thicknesses: List[float] = []
        external_walls_observed = 0
        external_sides_inferred: set[str] = set()
        internal_sides_inferred: set[str] = set()

        def _has_any_marker(*, wall: Dict[str, Any], markers: List[str]) -> bool:
            wall_location = str(wall.get("location") or "")
            wall_type = str(wall.get("type") or "")
            wall_notes = str(wall.get("notes") or "")
            ev_items = wall.get("evidence")
            ev_text = ""
            if isinstance(ev_items, list):
                ev_text = " ".join([str(x) for x in ev_items])
            combined_lower = f"{wall_location} {wall_type} {wall_notes} {ev_text}".lower()
            return any(m.lower() in combined_lower for m in markers)
        for wall in walls:
            thickness_str = wall.get("thickness", "")
            
            # Extract numeric thickness (handle "25cm", "25 ס\"מ", etc.)
            thickness_cm = self._extract_dimension_value(thickness_str, "cm")
            
            if thickness_cm is None:
                continue

            wall_location = str(wall.get("location", "") or "")
            wall_type = str(wall.get("type", "") or "")

            # Collect side hints for optional external-wall-count inference.
            wall_side_hints: set[str] = set()
            wall_side_hints |= _infer_sides_from_text(wall_location)
            wall_side_hints |= _infer_sides_from_text(str(wall.get("notes") or ""))
            if isinstance(wall.get("evidence"), list):
                wall_side_hints |= _infer_sides_from_any(wall.get("evidence"))

            exposure = _classify_wall_exposure(wall_location, wall_type, wall=wall)

            if exposure == "external":
                parsed_external_thicknesses.append(thickness_cm)
                external_walls_observed += 1
                # Track explicit external marker separately for absolute-min failure.
                if _has_any_marker(
                    wall=wall,
                    markers=[
                        "קיר חיצוני",
                        "חיצוני",
                        "external",
                        "outside",
                        "exterior",
                        "חזית",
                        "מעטפת",
                        "היקפי",
                        "perimeter",
                        "outer wall",
                        "outer band",
                    ],
                ):
                    explicit_external_thicknesses.append(thickness_cm)
                # If this wall references multiple sides, treat them as external unless a MAMAD door marks a side internal.
                if wall_side_hints:
                    external_sides_inferred |= (wall_side_hints - door_sides)
            elif exposure == "internal":
                parsed_internal_thicknesses.append(thickness_cm)
                if wall_side_hints:
                    internal_sides_inferred |= wall_side_hints
            else:
                parsed_unknown_thicknesses.append(thickness_cm)

            evidence.append(
                self._evidence_dimension(
                    value=thickness_cm,
                    unit="cm",
                    element="wall_thickness",
                    location=wall_location,
                    text=thickness_str,
                    raw=wall,
                )
            )

        # If we have a known total external wall count (possibly inferred from a floor plan),
        # attach it as evidence so the UI can explain why a specific minimum thickness was chosen.
        if num_external_known is not None:
            evidence.append(
                self._evidence_dimension(
                    value=float(num_external_known),
                    unit="count",
                    element="external_wall_count",
                    location=external_wall_count_source or "external_wall_count",
                    raw={
                        "source": external_wall_count_source or None,
                        "confidence": external_wall_count_confidence,
                    },
                )
            )
            for ev_text in [x for x in external_wall_count_evidence if isinstance(x, str) and x.strip()][:3]:
                evidence.append(
                    self._evidence_text(
                        text=ev_text.strip(),
                        element="external_wall_count_evidence",
                        location=external_wall_count_source or "external_wall_count",
                    )
                )

        if not (parsed_external_thicknesses or parsed_internal_thicknesses or parsed_unknown_thicknesses):
            self._add_requirement_evaluation(
                "1.2",
                "not_checked",
                reason_not_checked="no_parseable_wall_thickness",
                evidence=evidence,
                notes_he="זוהו קירות אך לא נמצאו ערכי עובי שניתנים לפענוח.",
            )
            return False

        # If the LLM did not provide external_wall_count but we can infer it confidently from side hints,
        # use it to avoid unnecessary not_checked outcomes.
        if num_external_known is None:
            # Resolve conflicts: a side cannot be both internal and external.
            conflict = bool(external_sides_inferred & internal_sides_inferred)
            if not conflict and 1 <= len(external_sides_inferred) <= 4:
                # Only accept inference if we also have at least one strong internal/external signal.
                # (e.g., window/door sides present or explicit markers already classified walls).
                strong_signal = bool(window_sides or door_sides or parsed_external_thicknesses)
                if strong_signal:
                    num_external_known = len(external_sides_inferred)

        # If nothing was explicitly classified as external, but this is a WALL_SECTION-like segment and
        # all observed wall thicknesses are >=25cm, treat the unknown-thickness walls as *candidates*
        # for external walls. This avoids skipping 1.2 when drawings omit explicit external labels.
        classification_ctx = data.get("classification", {})
        primary_category_ctx = str(classification_ctx.get("primary_category") or "").upper()
        is_wall_section_like = "WALL_SECTION" in primary_category_ctx
        if not parsed_external_thicknesses and is_wall_section_like and parsed_unknown_thicknesses:
            if min(parsed_unknown_thicknesses) >= 25:
                parsed_external_thicknesses = list(parsed_unknown_thicknesses)
            # If there is a thickness <25cm, it might be an internal partition, so keep the conservative
            # not_checked path below.

        # If we only have internal/unknown thicknesses, do not fail: requirement 1.2 applies to *external* walls.
        if not parsed_external_thicknesses:
            self._add_requirement_evaluation(
                "1.2",
                "not_checked",
                reason_not_checked="no_external_wall_thickness_identified",
                evidence=evidence,
                notes_he=(
                    "נמצאו מידות עובי קיר, אך אין סימון ברור שמדובר בקיר חיצוני. "
                    "לכן לא בוצעה בדיקת עובי לפי סעיף 1.2 (קירות חיצוניים בלבד)."
                ),
            )
            return False

        # Absolute minimum: any external wall thinner than 25cm is always non-compliant (independent of wall count).
        min_external_thickness = min(parsed_external_thicknesses)
        if min_external_thickness < 25:
            # If we know the external wall count and have strong SLIDING window evidence, use the spec minimum
            # (e.g., 30cm for 1–2 external walls with a sliding blast window) for the error message/evidence.
            sliding_window_case_evidence_strong = bool(has_sliding_window_marker and (window_external_marker_present or window_sides))
            required_min_for_message: int = 25
            if num_external_known is not None and sliding_window_case_evidence_strong:
                required_min_for_message = self._get_required_wall_thickness(
                    num_external_known,
                    has_window=True,
                )

            # If the <25cm value came from heuristic classification (no explicit "external" markers),
            # be conservative: report not_checked instead of failing.
            min_explicit = min(explicit_external_thicknesses) if explicit_external_thicknesses else None
            if min_explicit is None or min_explicit >= 25:
                self._add_requirement_evaluation(
                    "1.2",
                    "not_checked",
                    reason_not_checked="ambiguous_thin_wall_candidate",
                    evidence=evidence
                    + [
                        self._evidence_dimension(
                            value=required_min_for_message,
                            unit="cm",
                            element="required_min_wall_thickness_absolute",
                            location="external_wall_minimum",
                        )
                    ],
                    notes_he=(
                        f"זוהתה מידה {min_external_thickness:.0f} ס\"מ שעשויה להתפרש כעובי קיר, אך ללא סימון חד-משמעי שמדובר בקיר חיצוני. "
                        "כדי למנוע כשל שווא, בדיקת 1.2 סומנה כ'לא נבדק' במקרה זה."
                    ),
                )
                return False

            self._add_requirement_evaluation(
                "1.2",
                "failed",
                evidence=evidence
                + [
                    self._evidence_dimension(
                        value=required_min_for_message,
                        unit="cm",
                        element="required_min_wall_thickness_absolute",
                        location="external_wall_minimum",
                    )
                ],
                notes_he=(
                    f"נמצא עובי קיר חיצוני {min_external_thickness:.0f} ס\"מ קטן מהמינימום {required_min_for_message} ס\"מ לפי סעיף 1.2."
                ),
            )
            return True

        # If we don't reliably know how many external walls the *room* has, we avoid a false PASS.
        # Exception: if thickness is >=40cm, it satisfies 1.2 for any 1-4 external walls.
        if num_external_known is None:
            if min_external_thickness >= 40:
                self._add_requirement_evaluation(
                    "1.2",
                    "passed",
                    evidence=evidence
                    + [
                        self._evidence_dimension(
                            value=40,
                            unit="cm",
                            element="required_min_wall_thickness_max_case",
                            location="external_wall_maximum_case",
                        )
                    ],
                    notes_he=(
                        "נמצא עובי קיר חיצוני ≥40 ס\"מ, ולכן הדרישה לעובי קירות חיצוניים לפי סעיף 1.2 מתקיימת "
                        "ללא תלות במספר הקירות החיצוניים (1-4)."
                    ),
                )
                return True

            # Heuristic: if we can infer at least one internal wall side (e.g., a MAMAD door side),
            # then the room cannot have 4 external walls. In that case, a minimum external thickness
            # of 30cm satisfies 1.2 for 1–3 external walls (and also covers the window-case for 1–2).
            if min_external_thickness >= 30 and door_sides:
                self._add_requirement_evaluation(
                    "1.2",
                    "passed",
                    evidence=evidence
                    + [
                        self._evidence_dimension(
                            value=30,
                            unit="cm",
                            element="required_min_wall_thickness_inferred_max3",
                            location="external_wall_count_inferred_max3",
                        )
                    ],
                    notes_he=(
                        "זוהה עובי קיר חיצוני מינימלי ≥30 ס\"מ וכן אינדיקציה לקיר פנימי (דלת ממ\"ד), "
                        "ולכן מספר הקירות החיצוניים הוא לכל היותר 3. במצב זה עובי ≥30 ס\"מ עומד בדרישה 1.2 "
                        "עבור 1–3 קירות חיצוניים (כולל מקרה חלון עבור 1–2)."
                    ),
                )
                return True

            self._add_requirement_evaluation(
                "1.2",
                "not_checked",
                reason_not_checked="external_wall_count_unknown",
                evidence=evidence
                + [
                    self._evidence_dimension(
                        value=25,
                        unit="cm",
                        element="required_min_wall_thickness_absolute",
                        location="external_wall_minimum",
                    )
                ],
                notes_he=(
                    "זוהה לפחות קיר חיצוני אחד עם עובי ≥25 ס\"מ, אך מספר הקירות החיצוניים הכולל לא זוהה בוודאות "
                    "ולכן לא ניתן לקבוע אם נדרש 30/40 ס\"מ."
                ),
            )
            return False

        # Window-case rule (1.2): for 1–2 external walls, ONLY a *sliding* blast window in the external wall requires 30cm.
        # Do NOT upgrade thickness on generic "window" or generic blast-window markers unless sliding is explicitly indicated.
        has_sliding_window_on_external = bool(
            has_any_window and has_sliding_window_marker and (window_external_marker_present or window_sides)
        )
        required_thickness = self._get_required_wall_thickness(
            num_external_known,
            has_window=has_sliding_window_on_external,
        )
        if min_external_thickness < required_thickness:
            self._add_requirement_evaluation(
                "1.2",
                "failed",
                evidence=evidence
                + [
                    self._evidence_dimension(
                        value=required_thickness,
                        unit="cm",
                        element="required_min_wall_thickness",
                        location=f"external_walls={num_external_known}",
                    )
                ],
                notes_he=(
                    f"נמצא עובי קיר חיצוני {min_external_thickness:.0f} ס\"מ קטן מהמינימום {required_thickness} ס\"מ "
                    f"(לפי {num_external_known} קירות חיצוניים)."
                ),
            )
            return True

        self._add_requirement_evaluation(
            "1.2",
            "passed",
            evidence=evidence
            + [
                self._evidence_dimension(
                    value=required_thickness,
                    unit="cm",
                    element="required_min_wall_thickness",
                    location=f"external_walls={num_external_known}",
                )
            ],
            notes_he=(
                f"עובי הקירות החיצוניים שפוענחו עומד בדרישה: מינימום {required_thickness} ס\"מ "
                f"(לפי {num_external_known} קירות חיצוניים)."
            ),
        )
        return True
    
    def _validate_room_height(self, data: Dict[str, Any]) -> bool:
        """
        Rule 2.1-2.2: Room height requirements
        - Standard minimum: 2.50m
        - Exception: 2.20m if basement/addition AND volume ≥ 22.5 m³
        """
        dimensions = data.get("dimensions", [])

        # Determine whether this segment is likely to contain a ROOM height (not an opening height).
        # IMPORTANT: use PRIMARY category only (secondary labels are often noisy on mixed crops).
        classification = data.get("classification", {})
        primary_category_raw = classification.get("primary_category", "")
        primary_category = ""
        if isinstance(primary_category_raw, str) and primary_category_raw.strip():
            primary_category = re.split(r"[|,]", primary_category_raw.strip())[0].strip().upper()
        elif isinstance(primary_category_raw, list) and primary_category_raw:
            primary_category = str(primary_category_raw[0]).strip().upper()

        # View type gating: height (2.1/2.2) should only be extracted from vertical sections.
        # Floor plans / top-view crops frequently contain H=/installation heights that are NOT room height.
        view_type_raw = None
        if isinstance(classification, dict):
            view_type_raw = classification.get("view_type")
        summary = data.get("summary", {})
        primary_function_raw = summary.get("primary_function") if isinstance(summary, dict) else None
        view_type_norm = str(view_type_raw or "").strip().lower()
        primary_function_norm = str(primary_function_raw or "").strip().lower()
        is_top_view = view_type_norm in {"top_view", "floor_plan", "plan"} or primary_function_norm == "floor_plan"
        is_side_section = view_type_norm in {"side_section", "section"} or primary_function_norm == "section"

        text_items = data.get("text_items", [])
        annotations = data.get("annotations", [])
        all_text_lower = " ".join(
            [str(t.get("text", "")) for t in (text_items + annotations)]
        ).lower()

        h_equals_present = "h=" in all_text_lower
        generic_height_word_present = "height" in all_text_lower
        hebrew_height_word_present = "גובה" in all_text_lower
        mamad_label_present = ("ממ\"ד" in all_text_lower) or ("ממד" in all_text_lower)

        # Stronger context markers that usually indicate ROOM/CEILING height (not an opening sill/jamb).
        # Note: we intentionally do NOT treat a bare "H=..." as sufficient in non-section segments.
        explicit_room_height_context_present = any(
            k in all_text_lower
            for k in [
                "גובה חדר",
                "גובה החלל",
                "גובה נקי",
                "גובה תקרה",
                "גובה תקר",
                "ceiling height",
                "room height",
                "clear height",
            ]
        )

        # IMPORTANT: Prefer view signals over category when available.
        # A crop can be misclassified (e.g., SECTIONS) while still being a clear floor-plan top view.
        if is_top_view:
            segment_is_section_like = False
        elif is_side_section:
            segment_is_section_like = True
        else:
            # Do not treat generic height markers (e.g., H=) as proof this is a section.
            segment_is_section_like = primary_category in {"SECTIONS", "WALL_SECTION"}
        
        def _is_opening_height_dimension(d: Dict[str, Any]) -> bool:
            element = str(d.get("element", "")).lower()
            location = str(d.get("location", "")).lower()
            # If it's explicitly tied to openings, it is NOT a room height.
            opening_markers = [
                "door", "window", "opening", "jamb",
                "דלת", "חלון", "פתח", "משקוף",
            ]
            if any(m in element for m in opening_markers):
                return True
            if any(m in location for m in opening_markers):
                return True
            return False

        # Find *room* height dimensions (avoid door/window heights like 80/200)
        raw_height_dims = [
            d for d in dimensions
            if ("גובה" in str(d.get("element", "")).lower())
            or ("height" in str(d.get("element", "")).lower())
        ]
        height_dims = [d for d in raw_height_dims if not _is_opening_height_dimension(d)]

        def _height_dim_score(d: Dict[str, Any]) -> int:
            element = str(d.get("element", "")).lower()
            location = str(d.get("location", "")).lower()
            score = 0
            if "חדר" in element or "room" in element:
                score += 5
            if "תקרה" in element or "ceiling" in element:
                score += 4
            if "גובה" in element or "height" in element:
                score += 1
            if "חתך" in location or "section" in location:
                score += 1
            return score

        if height_dims:
            height_dims.sort(key=_height_dim_score, reverse=True)
        
        if not height_dims:
            # If the segment is not primarily a section and does not explicitly include height markers,
            # don't penalize it for missing room height.
            if not segment_is_section_like:
                self._add_requirement_evaluation(
                    "2.1",
                    "not_checked",
                    reason_not_checked="segment_not_section_like",
                    notes_he="הסגמנט לא נראה כמו חתך/גובה חדר ולכן לא נבדקה דרישת גובה.",
                )
                self._add_requirement_evaluation(
                    "2.2",
                    "not_checked",
                    reason_not_checked="segment_not_section_like",
                    notes_he="הסגמנט לא נראה כמו חתך/גובה חדר ולכן לא נבדקה דרישת החריג (2.2).",
                )
                return False

            # Evidence-first: missing room height is not treated as a failure unless we have
            # strong evidence that this segment should contain it. Mark as not_checked.
            self._add_requirement_evaluation(
                "2.1",
                "not_checked",
                reason_not_checked="room_height_not_found",
                evidence=[self._evidence_text(text="לא נמצא מימד גובה חדר בסגמנט", element="room_height")],
                notes_he="לא נמצא מימד שמזוהה בבירור כגובה חדר.",
            )
            self._add_requirement_evaluation(
                "2.2",
                "not_checked",
                reason_not_checked="room_height_not_found",
                evidence=[self._evidence_text(text="לא נמצא מימד גובה חדר בסגמנט", element="room_height")],
                notes_he="לא נמצא מימד שמזוהה בבירור כגובה חדר.",
            )
            return False

        # Hard gate: if this is a top-view (floor plan), height is not applicable.
        # Even if a height-like value was injected into dimensions by a focused extractor, do not evaluate.
        if is_top_view:
            self._add_requirement_evaluation(
                "2.1",
                "not_checked",
                reason_not_checked="segment_top_view",
                evidence=[
                    self._evidence_text(
                        text="Segment classified as top view (floor plan); room height cannot be validated here.",
                        element="view_type",
                        raw={"view_type": view_type_raw, "primary_function": primary_function_raw, "primary_category": primary_category},
                    )
                ],
                notes_he="הסגמנט מזוהה כמבט-על/תכנית (ולא חתך), ולכן לא נבדקה דרישת גובה הממ\"ד (2.1).",
            )
            self._add_requirement_evaluation(
                "2.2",
                "not_checked",
                reason_not_checked="segment_top_view",
                evidence=[
                    self._evidence_text(
                        text="Segment classified as top view (floor plan); room height exception cannot be validated here.",
                        element="view_type",
                        raw={"view_type": view_type_raw, "primary_function": primary_function_raw, "primary_category": primary_category},
                    )
                ],
                notes_he="הסגמנט מזוהה כמבט-על/תכנית (ולא חתך), ולכן לא נבדק חריג 2.2.",
            )
            return False

        # Guardrail: A numeric height can be extracted from floor plans (e.g., multiple H= markers).
        # In non-section segments, only treat the extracted height as ROOM height if we have explicit
        # room/ceiling context + a Mamad label. Otherwise, mark as not_checked to avoid false failures.
        if primary_category not in {"SECTIONS", "WALL_SECTION"} and not (
            explicit_room_height_context_present and mamad_label_present
        ):
            # Provide evidence so the UI can show what was found but why we didn't use it.
            try:
                candidate_height_m = self._extract_dimension_value(height_dims[0].get("value", ""), "m")
            except Exception:
                candidate_height_m = None
            candidate_evidence = [
                self._evidence_dimension(
                    value=candidate_height_m,
                    unit="m" if candidate_height_m is not None else str(height_dims[0].get("unit") or ""),
                    element=str(height_dims[0].get("element") or "room_height_candidate"),
                    location=str(height_dims[0].get("location") or ""),
                    text=str(height_dims[0].get("value") or ""),
                    raw=height_dims[0],
                )
            ]
            self._add_requirement_evaluation(
                "2.1",
                "not_checked",
                reason_not_checked="non_section_weak_height_evidence",
                evidence=candidate_evidence,
                notes_he=(
                    "נמצא ערך גובה בסגמנט, אך הסגמנט אינו חתך ואין סימון מפורש שמדובר בגובה החדר/התקרה של הממ\"ד; "
                    "כדי להימנע מפסילה שגויה (למשל גובה אדן/משקוף/אלמנט), דרישת הגובה לא נבדקה בסגמנט זה."
                ),
            )
            self._add_requirement_evaluation(
                "2.2",
                "not_checked",
                reason_not_checked="non_section_weak_height_evidence",
                evidence=candidate_evidence,
                notes_he="חריג 2.2 לא נבדק מאותה סיבה (אין ראיה חזקה לגובה חדר בממ\"ד בסגמנט שאינו חתך).",
            )
            return False
        
        # Get height value
        height_m = self._extract_dimension_value(height_dims[0].get("value", ""), "m")
        
        if height_m is None:
            # We attempted to evaluate height but couldn't parse it reliably.
            self._add_requirement_evaluation(
                "2.1",
                "not_checked",
                reason_not_checked="unparseable_room_height",
                evidence=[
                    self._evidence_dimension(
                        value=None,
                        unit=str(height_dims[0].get("unit") or ""),
                        element=str(height_dims[0].get("element") or "room_height"),
                        location=str(height_dims[0].get("location") or ""),
                        text=str(height_dims[0].get("value") or ""),
                        raw=height_dims[0],
                    )
                ],
                notes_he="נמצא מימד גובה אך לא ניתן היה לפענח את הערך בצורה אמינה.",
            )
            self._add_requirement_evaluation(
                "2.2",
                "not_checked",
                reason_not_checked="unparseable_room_height",
                evidence=[
                    self._evidence_dimension(
                        value=None,
                        unit=str(height_dims[0].get("unit") or ""),
                        element=str(height_dims[0].get("element") or "room_height"),
                        location=str(height_dims[0].get("location") or ""),
                        text=str(height_dims[0].get("value") or ""),
                        raw=height_dims[0],
                    )
                ],
                notes_he="נמצא מימד גובה אך לא ניתן היה לפענח את הערך בצורה אמינה.",
            )
            return False

        # Confidence/plausibility guardrails:
        # - Prevent obvious misreads (e.g., wall thickness '30'cm parsed as 0.30m room height)
        # - Avoid failing height rules on low-confidence, weakly-signaled measurements
        dim_conf_raw = height_dims[0].get("confidence", None)
        try:
            dim_confidence = float(dim_conf_raw) if dim_conf_raw is not None else 1.0
        except Exception:
            dim_confidence = 1.0

        height_evidence = [
            self._evidence_dimension(
                value=height_m,
                unit="m",
                element=str(height_dims[0].get("element") or "room_height"),
                location=str(height_dims[0].get("location") or ""),
                text=str(height_dims[0].get("value") or ""),
                raw=height_dims[0],
            )
        ]

        # Global confidence guardrail: never fail height rules on a very low-confidence read.
        # This preserves evidence-first behavior where uncertain measurements should be reported
        # as not_checked rather than hard failures.
        if dim_confidence < 0.60:
            self._add_requirement_evaluation(
                "2.1",
                "not_checked",
                reason_not_checked="low_confidence_room_height",
                evidence=height_evidence,
                notes_he="זוהה מימד גובה אך ברמת ביטחון נמוכה; כדי להימנע מפסילה שגויה דרישת הגובה לא נבדקה.",
            )
            self._add_requirement_evaluation(
                "2.2",
                "not_checked",
                reason_not_checked="low_confidence_room_height",
                evidence=height_evidence,
                notes_he="זוהה מימד גובה אך ברמת ביטחון נמוכה; כדי להימנע מפסילה שגויה חריג 2.2 לא נבדק.",
            )
            return False

        # Room height in drawings is typically in the ~2.2–3.2m range. Anything below 1.5m is
        # almost certainly an unrelated dimension (opening / sill / thickness / detail).
        if height_m < 1.50 or height_m > 6.00:
            self._add_requirement_evaluation(
                "2.1",
                "not_checked",
                reason_not_checked="implausible_room_height",
                evidence=height_evidence,
                notes_he="נמצא ערך גובה אך הוא לא סביר כגובה חדר (ייתכן שמדובר במימד אחר), לכן לא בוצעה בדיקת גובה.",
            )
            self._add_requirement_evaluation(
                "2.2",
                "not_checked",
                reason_not_checked="implausible_room_height",
                evidence=height_evidence,
                notes_he="נמצא ערך גובה אך הוא לא סביר כגובה חדר (ייתכן שמדובר במימד אחר), לכן לא בוצעה בדיקת חריג 2.2.",
            )
            return False

        # If extraction confidence is low on a non-section segment, avoid failing height rules.
        # This prevents false failures from noisy crops where a nearby H= marker is misread.
        if primary_category != "SECTIONS" and dim_confidence < 0.75:
            self._add_requirement_evaluation(
                "2.1",
                "not_checked",
                reason_not_checked="low_confidence_room_height",
                evidence=height_evidence,
                notes_he="זוהה מימד גובה אך ברמת ביטחון נמוכה בסגמנט שאינו חתך; כדי להימנע מפסילה שגויה דרישת הגובה לא נבדקה.",
            )
            self._add_requirement_evaluation(
                "2.2",
                "not_checked",
                reason_not_checked="low_confidence_room_height",
                evidence=height_evidence,
                notes_he="זוהה מימד גובה אך ברמת ביטחון נמוכה בסגמנט שאינו חתך; כדי להימנע מפסילה שגויה חריג 2.2 לא נבדק.",
            )
            return False
        
        # Evidence-first evaluation for 2.1 and 2.2.
        if height_m >= 2.50:
            self._add_requirement_evaluation(
                "2.1",
                "passed",
                evidence=height_evidence + [self._evidence_dimension(value=2.50, unit="m", element="required_min_height")],
                notes_he="גובה החדר עומד בדרישה המינימלית (2.50 מ').",
            )
            self._add_requirement_evaluation(
                "2.2",
                "not_checked",
                reason_not_checked="not_applicable_height_meets_standard",
                evidence=height_evidence,
                notes_he="החריג (2.2) לא נדרש כי הגובה עומד ב-2.50 מ'.",
            )
            return True

        if height_m < 2.20:
            # Below the exception threshold: the plan cannot rely on the 2.20m exception.
            # We still fail the standard requirement (2.1) and mark 2.2 as not_checked to avoid
            # presenting it as an independent failure.
            self._add_requirement_evaluation(
                "2.1",
                "failed",
                evidence=height_evidence + [self._evidence_dimension(value=2.50, unit="m", element="required_min_height")],
                notes_he="גובה החדר נמוך מהמינימום הסטנדרטי 2.50 מ'.",
            )
            self._add_requirement_evaluation(
                "2.2",
                "not_checked",
                reason_not_checked="height_below_exception_min",
                evidence=height_evidence + [self._evidence_dimension(value=2.20, unit="m", element="required_exception_min_height")],
                notes_he="הגובה נמוך מ-2.20 מ' ולכן החריג (2.2) אינו יכול לחול; הכשל מדווח במסגרת 2.1.",
            )
            return True

        # 2.20 <= height < 2.50: standard fails; exception depends on basement/addition + volume.
        # Evaluate exception conditions (AND logic): basement/addition AND volume >= 22.5m^3.
        # If conditions are not met, the standard height requirement applies and fails.
        exc_markers = [
            "מרתף",
            "במרתף",
            "תוספת",
            "תוספת בניה",
            "בניין קיים",
            "existing building",
            "basement",
            "addition",
        ]
        has_exception_context = any(m in all_text_lower for m in [x.lower() for x in exc_markers])

        # Parse explicit volume evidence if present.
        def _extract_volume_m3() -> Optional[float]:
            dims = data.get("dimensions")
            if isinstance(dims, list):
                for d in dims:
                    if not isinstance(d, dict):
                        continue
                    unit = str(d.get("unit") or "").strip().lower()
                    element = str(d.get("element") or "").lower()
                    loc = str(d.get("location") or "").lower()
                    if unit in {"m3", "m^3", "m³", "מ\"ק"} or ("מ\"ק" in element) or ("נפח" in element) or ("volume" in element):
                        v = self._extract_dimension_value(d.get("value"), "m3")
                        if v is not None:
                            return v
                        # Some producers store the numeric value directly.
                        try:
                            raw = d.get("value")
                            if isinstance(raw, (int, float)):
                                return float(raw)
                            if isinstance(raw, str) and raw.strip():
                                return float(raw.strip())
                        except Exception:
                            pass
                    # Heuristic: free-text location/element contains "נפח" and a number.
                    s = f"{element} {loc}"
                    if "נפח" in s or "volume" in s:
                        m = re.search(r"(?<!\d)(\d{1,3}(?:\.\d+)?)\s*(?:m3|m\^3|m³|מ\"ק)\b", s, flags=re.IGNORECASE)
                        if m:
                            try:
                                return float(m.group(1))
                            except Exception:
                                pass

            # Look in text items/annotations.
            m = re.search(r"(?i)(?:נפח|volume|v\s*=)\s*[:=]?\s*(\d{1,3}(?:\.\d+)?)\s*(?:m3|m\^3|m³|מ\"ק)", all_text_lower)
            if m:
                try:
                    return float(m.group(1))
                except Exception:
                    return None
            return None

        volume_m3 = _extract_volume_m3()

        # If we have evidence that the exception context applies, validate the volume condition.
        if has_exception_context:
            if volume_m3 is None:
                self._add_requirement_evaluation(
                    "2.1",
                    "failed",
                    evidence=height_evidence
                    + [self._evidence_dimension(value=2.50, unit="m", element="required_min_height")],
                    notes_he="גובה החדר נמוך מ-2.50 מ' ולכן אינו עומד בדרישה הסטנדרטית (וחריג 2.2 לא אומת עקב חסר בנפח).",
                )
                self._add_requirement_evaluation(
                    "2.2",
                    "not_checked",
                    reason_not_checked="missing_exception_volume",
                    evidence=height_evidence + [self._evidence_dimension(value=22.5, unit="m3", element="required_min_volume")],
                    notes_he="זוהו סימנים למרתף/תוספת בניה אך לא נמצא נפח חדר מפורש (נדרש ≥22.5 מ\"ק) כדי לאשר חריג 2.2.",
                )
                return True

            volume_evidence = [
                self._evidence_dimension(value=volume_m3, unit="m3", element="room_volume", location=""),
                self._evidence_dimension(value=22.5, unit="m3", element="required_min_volume"),
            ]

            if volume_m3 >= 22.5:
                # Exception satisfied: treat as compliant for height.
                self._add_requirement_evaluation(
                    "2.2",
                    "passed",
                    evidence=height_evidence + volume_evidence,
                    notes_he="החריג (2.2) חל: הסגמנט מצביע על מרתף/תוספת בניה ונפח ≥22.5 מ\"ק, ולכן גובה 2.20–2.50 מ' מותר.",
                )
                self._add_requirement_evaluation(
                    "2.1",
                    "passed",
                    evidence=height_evidence + [self._evidence_dimension(value=2.50, unit="m", element="required_min_height")],
                    notes_he="גובה החדר נמוך מ-2.50 מ' אך החריג 2.2 חל, ולכן דרישת הגובה מתקיימת.",
                )
                return True

            # Exception context exists and volume is explicitly too small -> explicit exception failure.
            self._add_requirement_evaluation(
                "2.1",
                "failed",
                evidence=height_evidence
                + [self._evidence_dimension(value=2.50, unit="m", element="required_min_height")],
                notes_he="גובה החדר נמוך מ-2.50 מ' ולכן אינו עומד בדרישה הסטנדרטית.",
            )
            self._add_requirement_evaluation(
                "2.2",
                "failed",
                evidence=height_evidence + volume_evidence,
                notes_he="החריג (2.2) אינו חל: זוהה מרתף/תוספת בניה אך נפח החדר קטן מ-22.5 מ\"ק, ולכן גובה מתחת 2.50 מ' אינו מותר.",
            )
            return True

        # No evidence that exception context exists -> exception is not applicable.
        self._add_requirement_evaluation(
            "2.1",
            "failed",
            evidence=height_evidence + [self._evidence_dimension(value=2.50, unit="m", element="required_min_height")],
            notes_he="גובה החדר נמוך מ-2.50 מ' ולכן אינו עומד בדרישה הסטנדרטית.",
        )
        self._add_requirement_evaluation(
            "2.2",
            "not_checked",
            reason_not_checked="not_applicable_no_exception_context",
            evidence=height_evidence,
            notes_he="לא נמצאו ראיות לכך שהממ\"ד במרתף/תוספת בניה; לכן החריג (2.2) אינו רלוונטי והגובה חייב לעמוד ב-2.50 מ'.",
        )
        return True


    def _validate_external_wall_count(self, data: Dict[str, Any]) -> bool:
        """Rule 1.1: External wall count must be between 1 and 4.

        This is a pre-calculation dependency for wall thickness (1.2).
        In the segment-based flow, we only validate this when the extractor explicitly
        provides `external_wall_count` with sufficient context.
        """
        raw = data.get("external_wall_count")
        if not isinstance(raw, int):
            self._add_requirement_evaluation(
                "1.1",
                "not_checked",
                reason_not_checked="external_wall_count_not_provided",
                notes_he="לא סופק מספר קירות חיצוניים (1–4) מהחילוץ ולכן לא ניתן היה לבדוק דרישה 1.1 בסגמנט.",
            )
            return False

        if 1 <= raw <= 4:
            self._add_requirement_evaluation(
                "1.1",
                "passed",
                evidence=[self._evidence_dimension(value=float(raw), unit="count", element="external_wall_count")],
                notes_he=f"מספר הקירות החיצוניים שזוהה הוא {raw} (בתחום 1–4).",
            )
            return True

        self._add_requirement_evaluation(
            "1.1",
            "failed",
            evidence=[self._evidence_dimension(value=float(raw), unit="count", element="external_wall_count")],
            notes_he=f"מספר הקירות החיצוניים שזוהה ({raw}) אינו בתחום 1–4.",
        )
        return True


    def _validate_external_wall_classification(self, data: Dict[str, Any]) -> bool:
        """Rule 1.3: Conditional external wall classification near exterior line.

        Condition:
        - There is evidence a wall is <2m from the building exterior line.

        Validation (only if the plan is attempting to classify it as NOT external):
        - A protective reinforced concrete wall (>=20cm) must exist.
        """
        text_items = data.get("text_items") or []
        annotations = data.get("annotations") or []
        all_text = " ".join([str(t.get("text", "")) for t in (text_items + annotations) if isinstance(t, dict)]).lower()

        near_exterior = bool(
            ("קו" in all_text and ("חיצונ" in all_text or "בנין" in all_text))
            and re.search(r"(?<!\d)2\s*(?:m|מ')\b", all_text)
        )
        if not near_exterior:
            self._add_requirement_evaluation(
                "1.3",
                "not_checked",
                reason_not_checked="not_applicable_no_near_exterior_condition",
                notes_he="לא נמצאו ראיות לכך שקיר נמצא במרחק קטן מ-2 מ' מהקו החיצוני של הבניין; חריג 1.3 אינו רלוונטי בסגמנט.",
            )
            return False

        # Detect whether the plan is explicitly claiming the wall is NOT external.
        claims_not_external = any(
            p in all_text
            for p in [
                "לא נחשב קיר חיצוני",
                "לא נחשב חיצוני",
                "not external",
                "is not external",
            ]
        )

        protective_wall = ("קיר מגן" in all_text or "protective wall" in all_text) and bool(
            re.search(r"(?<!\d)20\s*(?:cm|ס\"מ)\b", all_text)
        )

        evidence = []
        evidence.append(self._evidence_text(text="זוהתה אינדיקציה לקיר במרחק <2 מ' מהקו החיצוני", element="near_exterior_line"))
        if protective_wall:
            evidence.append(self._evidence_text(text="זוהתה אינדיקציה לקיר מגן מבטון בעובי 20 ס\"מ", element="protective_wall"))

        if not claims_not_external:
            # We have the condition, but not enough to assert what classification the plan uses.
            self._add_requirement_evaluation(
                "1.3",
                "not_checked",
                reason_not_checked="classification_condition_detected",
                evidence=evidence,
                notes_he="זוהתה אינדיקציה לחריג 1.3 (קיר <2 מ' מהקו החיצוני), אך אין בסגמנט הצהרה/הקשר מספיק לגבי סיווג הקיר כחיצוני/לא חיצוני כדי לאמת את הכלל.",
            )
            return False

        # The plan is attempting to treat it as not external -> protective wall becomes mandatory.
        if protective_wall:
            self._add_requirement_evaluation(
                "1.3",
                "passed",
                evidence=evidence + [self._evidence_dimension(value=20.0, unit="cm", element="required_protective_wall_thickness")],
                notes_he="החריג 1.3 נתמך: קיימת אינדיקציה לקיר <2 מ' מהקו החיצוני ובמקביל קיים קיר מגן מבטון בעובי ≥20 ס\"מ.",
            )
            return True

        self._add_requirement_evaluation(
            "1.3",
            "failed",
            evidence=evidence + [self._evidence_dimension(value=20.0, unit="cm", element="required_protective_wall_thickness")],
            notes_he="החריג 1.3 אינו מתקיים: קיימת אינדיקציה לקיר <2 מ' מהקו החיצוני וכן ניסיון להתייחס אליו כלא-חיצוני, אך לא נמצאה ראיה לקיר מגן מבטון בעובי ≥20 ס\"מ.",
        )
        return True


    def _validate_high_wall(self, data: Dict[str, Any]) -> bool:
        """Rule 1.4: High wall definition and conditional extra checks.

        Condition:
        - A wall is "high" only if the clear concrete-to-concrete opening exceeds 2.8m.

        In the segment-based deterministic flow we can often detect the condition,
        but the reinforcement/engineering approval checks require additional structural context.
        """
        dims = data.get("dimensions")
        if not isinstance(dims, list) or not dims:
            self._add_requirement_evaluation(
                "1.4",
                "not_checked",
                reason_not_checked="no_dimensions",
                notes_he="לא נמצאו מידות בסגמנט ולכן לא ניתן לקבוע אם מדובר בקיר גבוה (1.4).",
            )
            return False

        # Detect a candidate clear opening / wall height dimension.
        best: Optional[Dict[str, Any]] = None
        best_value: Optional[float] = None
        for d in dims:
            if not isinstance(d, dict):
                continue
            unit = str(d.get("unit") or "").lower().strip()
            if unit not in {"m", "meter", "meters"}:
                continue
            v = self._extract_dimension_value(d.get("value"), "m")
            if v is None:
                continue
            element = str(d.get("element") or "").lower()
            loc = str(d.get("location") or "").lower()
            # Prefer explicit wall-height / concrete-to-concrete wording.
            if any(k in element or k in loc for k in ["בטון", "beton", "concrete", "קיר", "wall", "בטון-לבטון", "clear", "מפתח"]):
                if best_value is None or v > best_value:
                    best_value = v
                    best = d

        if best_value is None:
            self._add_requirement_evaluation(
                "1.4",
                "not_checked",
                reason_not_checked="no_high_wall_candidate",
                notes_he="לא נמצאה מידה שניתן לקשור בבירור למפתח קיר (בטון-לבטון/גובה קיר) כדי לבדוק אם מדובר בקיר גבוה.",
            )
            return False

        if best_value <= 2.80:
            self._add_requirement_evaluation(
                "1.4",
                "not_checked",
                reason_not_checked="not_applicable_not_high_wall",
                evidence=[
                    self._evidence_dimension(
                        value=best_value,
                        unit="m",
                        element=str(best.get("element") or "high_wall_candidate"),
                        location=str(best.get("location") or ""),
                        raw=best,
                    )
                ],
                notes_he="המפתח/גובה הקיר שנמצא אינו עולה על 2.8 מ' ולכן כללי 'קיר גבוה' (1.4) אינם חלים.",
            )
            return False

        # Condition met: additional checks apply, but require structural/engineering context.
        self._add_requirement_evaluation(
            "1.4",
            "not_checked",
            reason_not_checked="high_wall_requires_structural_context",
            evidence=[
                self._evidence_dimension(
                    value=best_value,
                    unit="m",
                    element=str(best.get("element") or "high_wall_candidate"),
                    location=str(best.get("location") or ""),
                    raw=best,
                ),
                self._evidence_dimension(value=2.8, unit="m", element="high_wall_threshold"),
            ],
            notes_he="זוהה מפתח בטון-לבטון >2.8 מ' ולכן מדובר בקיר גבוה. בדיקות חיזוק/זיון/אישור מהנדס נדרשות אך אינן ניתנות לאימות דטרמיניסטי מסגמנט זה.",
        )
        return False


    def _validate_tower_continuity(self, data: Dict[str, Any]) -> bool:
        """Rule 1.5: 70% continuity in a MAMAD tower.

        Condition:
        - Applies only if a MAMAD tower (stack of MAMADs across floors) exists.

        Validation:
        - Continuity must be >=70%. If <70%, it indicates a required alternative design path.
        """
        text_items = data.get("text_items") or []
        annotations = data.get("annotations") or []
        all_text = " ".join([str(t.get("text", "")) for t in (text_items + annotations) if isinstance(t, dict)]).lower()

        tower_markers = [
            "מגדל ממ\"דים",
            "מגדל ממדים",
            "ערימת ממ\"דים",
            "tower",
            "stack",
        ]
        has_tower_context = any(m in all_text for m in [x.lower() for x in tower_markers])
        if not has_tower_context:
            self._add_requirement_evaluation(
                "1.5",
                "not_checked",
                reason_not_checked="not_applicable_no_tower_context",
                notes_he="לא נמצאו ראיות שמדובר במגדל ממ""דים (ערימה בין קומות); כלל 70% (1.5) אינו רלוונטי בסגמנט.",
            )
            return False

        # Parse continuity percentage if explicitly provided.
        m = re.search(r"(?i)(?:רציפות|continuity)\s*[:=]?\s*(\d{1,3}(?:\.\d+)?)\s*%", all_text)
        if not m:
            # Fallback: explicit mention of 70% near continuity.
            m = re.search(r"(?i)(?:רציפות|continuity)[^\n%]{0,40}(\d{1,3}(?:\.\d+)?)\s*%", all_text)

        if not m:
            self._add_requirement_evaluation(
                "1.5",
                "not_checked",
                reason_not_checked="missing_continuity_percentage",
                evidence=[self._evidence_text(text="זוהתה אינדיקציה למגדל ממ""דים אך לא נמצא אחוז רציפות", element="tower_continuity")],
                notes_he="זוהתה אינדיקציה למגדל ממ""דים אך לא נמצא אחוז רציפות מפורש (נדרש ≥70%) כדי לאמת את דרישה 1.5.",
            )
            return False

        try:
            pct = float(m.group(1))
        except Exception:
            pct = None

        if pct is None:
            self._add_requirement_evaluation(
                "1.5",
                "not_checked",
                reason_not_checked="unparseable_continuity_percentage",
                notes_he="נמצא טקסט לגבי רציפות במגדל ממ""דים אך לא ניתן היה לפענח את האחוז.",
            )
            return False

        evidence = [
            self._evidence_dimension(value=pct, unit="%", element="tower_continuity_percent"),
            self._evidence_dimension(value=70.0, unit="%", element="required_min_tower_continuity"),
        ]

        if pct >= 70.0:
            self._add_requirement_evaluation(
                "1.5",
                "passed",
                evidence=evidence,
                notes_he="הרציפות במגדל ממ""דים עומדת בדרישה (≥70%).",
            )
            return True

        self._add_requirement_evaluation(
            "1.5",
            "failed",
            evidence=evidence,
            notes_he="הרציפות במגדל ממ""דים נמוכה מ-70%. לפי האוגדן זה אינו רק כשל נקודתי אלא מעבר למסלול תכנון חלופי/חיזוקים מיוחדים.",
        )
        return True
    
    def _validate_door_spacing(self, data: Dict[str, Any]) -> bool:
        """
        Rule 3.1: Door spacing requirements
        - Distance from door frame to perpendicular wall inside: ≥ 90cm
        - Distance from door edge to perpendicular wall outside: ≥ 75cm
        """
        elements = data.get("structural_elements", [])
        doors = [e for e in elements if e.get("type") in ["door", "דלת", "דלת הדף"]]
        
        if not doors:
            # Not necessarily an error - segment might not show door
            self._add_requirement_evaluation(
                "3.1",
                "not_checked",
                reason_not_checked="no_doors_detected",
                notes_he="לא זוהו דלתות בסגמנט ולכן לא נבדקה דרישת ריווח דלת.",
            )
            return False

        checked_any = False
        evidence: List[Dict[str, Any]] = []
        
        # Check door spacing (simplified - would need spatial analysis)
        for door in doors:
            dimensions_str = door.get("dimensions", "")

            classification = data.get("classification", {})
            primary_category_raw = classification.get("primary_category", "")
            primary_category = ""
            if isinstance(primary_category_raw, str) and primary_category_raw.strip():
                primary_category = re.split(r"[|,]", primary_category_raw.strip())[0].strip().upper()
            elif isinstance(primary_category_raw, list) and primary_category_raw:
                primary_category = str(primary_category_raw[0]).strip().upper()
            
            # Look for spacing annotations in text_items
            text_items = data.get("text_items", [])
            door_markers = [
                "door", "jamb", "frame", 
                "דלת", "משקוף",
            ]

            def _mentions_door(s: str) -> bool:
                s = (s or "").lower()
                return any(m in s for m in door_markers)

            spacing_texts = [
                t for t in text_items
                if (
                    ("מרחק" in (t.get("text", "") or ""))
                    or ("ס\"מ" in (t.get("text", "") or ""))
                    or ("cm" in (t.get("text", "") or "").lower())
                )
                and _mentions_door(str(t.get("text", "")))
            ]

            # Also look for spacing in extracted dimensions/door fields (more reliable than raw text)
            extracted_dims = data.get("dimensions", [])
            spacing_dims = []
            for d in extracted_dims:
                element = str(d.get("element", ""))
                location = str(d.get("location", ""))
                joined = f"{element} {location}"

                # Accept generic "distance/מרחק" only if the dimension is explicitly tied to a door/frame/opening.
                if not _mentions_door(joined):
                    continue

                el_lower = element.lower()
                if any(k in el_lower for k in ["door", "jamb", "spacing", "clearance", "distance", "מרחק"]):
                    spacing_dims.append(d)

            door_internal = door.get("spacing_internal_cm") or door.get("door_spacing_internal_cm")
            door_external = door.get("spacing_external_cm") or door.get("door_spacing_external_cm")
            door_confidence = door.get("spacing_confidence") or door.get("door_spacing_confidence")

            def _as_number(v: Any) -> Optional[float]:
                try:
                    if v is None:
                        return None
                    return float(v)
                except Exception:
                    return None

            internal_cm = _as_number(door_internal)
            external_cm = _as_number(door_external)
            confidence = _as_number(door_confidence)

            def _as_cm(value: Any, unit: Any) -> Optional[float]:
                num = _as_number(value)
                if num is None:
                    return None
                u = (str(unit or "").strip().lower() or "cm")
                if u in {"m", "meter", "meters", "מ", "מטר"}:
                    return num * 100.0
                if u in {"mm", "millimeter", "millimeters", "מ\"מ", "ממ"}:
                    return num / 10.0
                # Default to cm if unit is missing/unknown
                return num

            # If the model provided explicit internal/external values, evaluate them.
            if internal_cm is not None or external_cm is not None:
                # If the focused extractor provided a low confidence, prefer not_checked over
                # a potentially false pass/fail.
                if confidence is not None and confidence < 0.60:
                    self._add_requirement_evaluation(
                        "3.1",
                        "not_checked",
                        reason_not_checked="low_confidence_door_spacing_extraction",
                        evidence=[
                            self._evidence_dimension(
                                value=internal_cm,
                                unit="cm",
                                element="door_spacing_internal",
                                location=str(door.get("location") or ""),
                                raw=door,
                            ),
                            self._evidence_dimension(
                                value=external_cm,
                                unit="cm",
                                element="door_spacing_external",
                                location=str(door.get("location") or ""),
                                raw=door,
                            ),
                        ],
                        notes_he="זוהו ערכי ריווח דלת אך רמת הוודאות נמוכה; לא בוצעה הכרעה כדי למנוע טעות.",
                    )
                    continue

                checked_any = True
                if internal_cm is not None:
                    evidence.append(self._evidence_dimension(value=internal_cm, unit="cm", element="door_spacing_internal", location=door.get("location", ""), raw=door))
                if external_cm is not None:
                    evidence.append(self._evidence_dimension(value=external_cm, unit="cm", element="door_spacing_external", location=door.get("location", ""), raw=door))

                # For a reliable PASS we require BOTH internal and external clearances.
                if internal_cm is None or external_cm is None:
                    self._add_requirement_evaluation(
                        "3.1",
                        "not_checked",
                        reason_not_checked="missing_internal_or_external_clearance",
                        evidence=evidence,
                        notes_he="נמצאה מידה חלקית לריווח דלת אך חסר פנימי/חיצוני; לא ניתן לקבוע עמידה מלאה בדרישה.",
                    )
                    continue

                ok_internal = internal_cm >= 90.0
                ok_external = external_cm >= 75.0

                if ok_internal and ok_external:
                    self._add_requirement_evaluation(
                        "3.1",
                        "passed",
                        evidence=evidence + [
                            self._evidence_dimension(value=90.0, unit="cm", element="required_internal_min"),
                            self._evidence_dimension(value=75.0, unit="cm", element="required_external_min"),
                        ],
                        notes_he="ריווחי הדלת עומדים בדרישות (≥90 ס\"מ פנימי, ≥75 ס\"מ חיצוני).",
                    )
                else:
                    self._add_requirement_evaluation(
                        "3.1",
                        "failed",
                        evidence=evidence + [
                            self._evidence_dimension(value=90.0, unit="cm", element="required_internal_min"),
                            self._evidence_dimension(value=75.0, unit="cm", element="required_external_min"),
                        ],
                        notes_he="נמצאו ריווחי דלת שאינם עומדים בדרישות.",
                    )
                continue

            # If we found spacing-like dimensions near the door, use them as evidence.
            # For demo/real-world plans, we prefer to avoid false negatives when the drawing
            # provides dimensions but doesn't label them as "internal/external" explicitly.
            if spacing_dims: 
                spacing_values_cm: list[float] = []
                found_preview: list[str] = []
                for d in spacing_dims:
                    v_cm = _as_cm(d.get("value"), d.get("unit"))
                    if v_cm is not None:
                        # Filter out very small "offset" values (e.g., 20/25/40/45) that are commonly
                        # wall thicknesses or local offsets near the door, not the required clearances.
                        # We only evaluate plausible clearance candidates.
                        if v_cm >= 60.0:
                            spacing_values_cm.append(v_cm)

                    if v_cm is not None:
                        evidence.append(
                            self._evidence_dimension(
                                value=v_cm,
                                unit="cm",
                                element=str(d.get("element") or "door_spacing"),
                                location=str(d.get("location") or door.get("location", "")),
                                text=str(d.get("value") or ""),
                                raw=d,
                            )
                        )

                    # Build a short preview for logs only
                    if len(found_preview) < 4:
                        elem = d.get("element") or "door"
                        try:
                            if v_cm is not None:
                                found_preview.append(f"{elem}: {v_cm:.0f} cm")
                            else:
                                found_preview.append(f"{elem}: {d.get('value')} {d.get('unit') or ''}")
                        except Exception:
                            pass

                if spacing_values_cm:
                    max_cm = max(spacing_values_cm)
                    min_cm = min(spacing_values_cm)

                    # Heuristic:
                    # - If all observed door-adjacent spacings are >= 75cm and at least one is >= 90cm,
                    #   treat as compliant (likely covers external>=75 and internal>=90).
                    if min_cm >= 75.0 and max_cm >= 90.0: 
                        checked_any = True
                        self._add_requirement_evaluation(
                            "3.1",
                            "passed",
                            evidence=evidence + [
                                self._evidence_dimension(value=90.0, unit="cm", element="required_internal_min"),
                                self._evidence_dimension(value=75.0, unit="cm", element="required_external_min"),
                            ],
                            notes_he="נמצאו מידות סמוכות לדלת שמספיקות כדי לעמוד בספי 75/90 ס\"מ.",
                        )
                        continue

                    # Otherwise: evidence exists but mapping is ambiguous. Don't mark as checked
                    # (prevents false green "passed" when we can't truly validate).
                    logger.info(
                        "Door spacing evidence found but ambiguous; not emitting violation",
                        found_preview=found_preview,
                        location=door.get("location", "")
                    )
                    self._add_requirement_evaluation(
                        "3.1",
                        "not_checked",
                        reason_not_checked="ambiguous_spacing_evidence",
                        evidence=evidence,
                        notes_he="נמצאו מידות סמוכות לדלת אך לא ניתן למפות בבירור ל'פנימי/חיצוני' ולכן לא בוצעה בדיקה.",
                    )
                    continue

                # spacing_dims exist but without numeric values; not enough to validate.
                logger.info(
                    "Door spacing evidence found (non-numeric); not emitting violation",
                    location=door.get("location", "")
                )
                self._add_requirement_evaluation(
                    "3.1",
                    "not_checked",
                    reason_not_checked="non_numeric_spacing_evidence",
                    evidence=evidence,
                    notes_he="נמצאו סימני ריווח ליד הדלת אך ללא ערך מספרי שניתן לפענוח.",
                )
                continue
            
            # If no spacing info found, warn
            if not spacing_texts:
                # If this is not primarily a door-detail segment, don't penalize for missing
                # door spacing values (they are often absent from general room layout crops).
                if primary_category and primary_category != "DOOR_DETAILS":
                    logger.info(
                        "Skipping DOOR_001 missing-spacing warning for non-door-detail segment",
                        primary_category=primary_category,
                        location=door.get("location", "")
                    )
                    # Still emit an explicit not_checked evaluation for transparency.
                    self._add_requirement_evaluation(
                        "3.1",
                        "not_checked",
                        reason_not_checked="missing_clearance_dimensions",
                        evidence=[
                            self._evidence_text(
                                text="לא נמצאו מידות ריווח דלת לקיר ניצב (פנימי/חיצוני) שנדרשות ל-3.1",
                                element="door_spacing",
                                location=str(door.get("location") or ""),
                                raw=door,
                            )
                        ],
                        notes_he="כדי לבדוק 3.1 נדרשות מידות ריווח מהמשקוף/מסגרת הדלת אל הקיר הניצב (פנימי וחיצוני). בסגמנט זה זוהתה דלת, אך לא נמצאו מידות ריווח כאלה באופן חד-משמעי.",
                    )
                    continue

                # Evidence-first: absence of spacing annotations is not treated as a failure.
                self._add_requirement_evaluation(
                    "3.1",
                    "not_checked",
                    reason_not_checked="no_spacing_evidence",
                    evidence=[self._evidence_text(text="לא נמצאו מידות ריווח דלת (90/75 ס\"מ)", element="door_spacing")],
                    notes_he="לא נמצאו ראיות מספקות לריווח דלת בסגמנט.",
                )
                checked_any = False

        return checked_any
    
    def _validate_window_spacing(self, data: Dict[str, Any]) -> bool:
        """
        Rule 3.2: Window spacing requirements
        - Distance between sliding niches: ≥ 20cm
        - Distance between light openings: ≥ 100cm
        - Distance from window to perpendicular wall: ≥ 20cm
        """
        elements = data.get("structural_elements", [])
        windows = [e for e in elements if e.get("type") in ["window", "חלון", "חלון הדף"]]
        
        if not windows:
            self._add_requirement_evaluation(
                "3.2",
                "not_checked",
                reason_not_checked="no_windows_detected",
                notes_he="לא זוהו חלונות בסגמנט ולכן לא נבדקה דרישת ריווח חלון.",
            )
            return False  # Not all segments have windows
        
        checked_any = False

        # Prefer structured focused extraction when available.
        focus = data.get("window_spacing_focus")
        focus_windows = focus.get("windows") if isinstance(focus, dict) else None
        focus_unavailable = False
        if isinstance(focus, dict):
            notes = str(focus.get("notes") or "").strip().lower()
            if notes.startswith("focus_unavailable"):
                focus_unavailable = True

        focus_inconclusive_evidence: List[Dict[str, Any]] = []
        if isinstance(focus_windows, list) and focus_windows:
            any_failed = False
            any_checked = False
            any_inconclusive = False
            evidence: List[Dict[str, Any]] = []

            def _as_number(v: Any) -> Optional[float]:
                try:
                    if v is None:
                        return None
                    return float(v)
                except Exception:
                    return None

            for w in focus.get("windows", [])[:6]:
                if not isinstance(w, dict):
                    continue

                conf = _as_number(w.get("confidence"))
                location = str(w.get("location") or "")
                ev_list = w.get("evidence")
                if isinstance(ev_list, list):
                    for ev in ev_list[:8]:
                        if isinstance(ev, str) and ev.strip():
                            evidence.append(
                                self._evidence_text(
                                    text=ev.strip(),
                                    element="window_spacing_focus",
                                    location=location,
                                    raw=w,
                                )
                            )

                # If confidence is low, do not make a pass/fail decision.
                if conf is not None and conf < 0.60:
                    continue

                niche_cm = _as_number(w.get("niche_to_niche_cm"))
                openings_cm = _as_number(w.get("light_openings_spacing_cm"))
                to_wall_cm = _as_number(w.get("to_perpendicular_wall_cm"))
                sep_cm = _as_number(w.get("same_wall_door_separation_cm"))
                door_h_cm = _as_number(w.get("door_height_cm"))
                has_concrete_between = w.get("has_concrete_wall_between_openings")
                conc_th_cm = _as_number(w.get("concrete_wall_thickness_cm"))

                # Subchecks 1-3: only evaluate when value is present.
                sub_checked = 0
                if niche_cm is not None:
                    sub_checked += 1
                    evidence.append(self._evidence_dimension(value=niche_cm, unit="cm", element="niche_to_niche", location=location, raw=w))
                    if niche_cm < 20.0:
                        any_failed = True
                if openings_cm is not None:
                    sub_checked += 1
                    evidence.append(self._evidence_dimension(value=openings_cm, unit="cm", element="light_openings_spacing", location=location, raw=w))
                    if openings_cm < 100.0:
                        any_failed = True
                if to_wall_cm is not None:
                    sub_checked += 1
                    evidence.append(self._evidence_dimension(value=to_wall_cm, unit="cm", element="window_to_perpendicular_wall", location=location, raw=w))
                    if to_wall_cm < 20.0:
                        any_failed = True

                # Subcheck 4: window+door same wall rule.
                # Evaluate only if we have separation evidence, or explicit concrete-between evidence.
                if has_concrete_between is True:
                    evidence.append(self._evidence_text(text="קיים קיר בטון בין דלת לחלון", element="window_door_separator", location=location, raw=w))
                    if conc_th_cm is not None:
                        any_checked = True
                        evidence.append(self._evidence_dimension(value=conc_th_cm, unit="cm", element="concrete_wall_thickness", location=location, raw=w))
                        if conc_th_cm < 20.0:
                            any_failed = True
                    else:
                        # Condition suggests this sub-rule applies, but we can't validate thickness.
                        any_inconclusive = True
                elif sep_cm is not None:
                    evidence.append(self._evidence_dimension(value=sep_cm, unit="cm", element="window_door_separation", location=location, raw=w))
                    if door_h_cm is not None:
                        any_checked = True
                        evidence.append(self._evidence_dimension(value=door_h_cm, unit="cm", element="door_height", location=location, raw=w))
                        if sep_cm < door_h_cm:
                            any_failed = True
                    else:
                        # Condition suggests this sub-rule applies, but we can't validate without door height.
                        any_inconclusive = True

                if sub_checked > 0:
                    any_checked = True

            if any_checked:
                checked_any = True
                if any_failed:
                    self._add_requirement_evaluation(
                        "3.2",
                        "failed",
                        evidence=evidence
                        + [
                            self._evidence_dimension(value=20.0, unit="cm", element="required_min_niche_or_wall"),
                            self._evidence_dimension(value=100.0, unit="cm", element="required_min_light_openings"),
                            self._evidence_dimension(value=20.0, unit="cm", element="required_min_window_to_wall"),
                        ],
                        notes_he="נמצאו מרחקים/נישות לחלון הדף שאינם עומדים בדרישות סעיף 3.2.",
                    )
                    return True

                # If any sub-rule seems applicable but is inconclusive (e.g., window+door rule without door height),
                # stay evidence-first and do not force pass/fail.
                if any_inconclusive:
                    self._add_requirement_evaluation(
                        "3.2",
                        "not_checked",
                        reason_not_checked="window_spacing_inconclusive",
                        evidence=evidence,
                        notes_he="נמצאו ראיות המעידות שייתכן שחלק מדרישות 3.2 חלות (למשל חלון+דלת באותו קיר), אך חסרים נתונים כדי להכריע באופן חד-משמעי.",
                    )
                else:
                    # Conditional logic per the guide: only evaluate rules that are applicable.
                    # If the applicable rules we could evaluate all pass, mark as PASSED.
                    self._add_requirement_evaluation(
                        "3.2",
                        "passed",
                        evidence=evidence
                        + [
                            self._evidence_dimension(value=20.0, unit="cm", element="required_min_niche_or_wall"),
                            self._evidence_dimension(value=100.0, unit="cm", element="required_min_light_openings"),
                            self._evidence_dimension(value=20.0, unit="cm", element="required_min_window_to_wall"),
                        ],
                        notes_he="כל תתי-הבדיקות הרלוונטיות של 3.2 שניתן היה לאמת בסגמנט זה עומדות בדרישות (כלל מותנה לפי מצב תכנוני).",
                    )
                return True

            # Structured focus exists but didn't yield any confident numeric checks.
            # Keep the evidence and continue to the legacy text-based fallback.
            focus_inconclusive_evidence = evidence

        # Check spacing (simplified)
        for window in windows:
            window_evidence: List[Dict[str, Any]] = [
                self._evidence_text(
                    text="חלון זוהה בסגמנט",
                    element="window",
                    location=str(window.get("location") or ""),
                    raw=window,
                )
            ]

            if focus_inconclusive_evidence:
                # Include a small subset of focus evidence to explain why the
                # structured path couldn't be used (e.g., low confidence / capacity).
                window_evidence.extend(focus_inconclusive_evidence[:10])
            # Look for spacing annotations
            text_items = data.get("text_items", [])
            spacing_found = False
            for t in text_items:
                txt = str(t.get("text", "") or "")
                if not txt:
                    continue
                txt_lower = txt.lower()
                # Require explicit mention of window/opening context
                if ("חלון" not in txt) and ("window" not in txt_lower):
                    continue
                # Require explicit unit to avoid matching substrings like "200" -> "20"
                if re.search(r"(?<!\d)20(?:\.0)?\s*(?:cm|ס\"מ)\b", txt, flags=re.IGNORECASE):
                    spacing_found = True
                    window_evidence.append(self._evidence_text(text=txt, element="window_spacing", raw=t))
                    break
                if re.search(r"(?<!\d)100(?:\.0)?\s*(?:cm|ס\"מ)\b", txt, flags=re.IGNORECASE):
                    spacing_found = True
                    window_evidence.append(self._evidence_text(text=txt, element="window_spacing", raw=t))
                    break
            
            if spacing_found:
                checked_any = True
                self._add_requirement_evaluation(
                    "3.2",
                    "passed",
                    evidence=window_evidence,
                    notes_he="נמצאה ראיית ריווח חלון עם יחידות מפורשות (ס\"מ/CM).",
                )
            else:
                # Evidence-first: do not fail on absence; mark not_checked.
                reason = "no_window_spacing_annotation"
                notes_he = "לא נמצאו מידות ריווח חלון מפורשות בסגמנט (עם יחידות והקשר לחלון)."
                if focus_unavailable:
                    reason = "window_spacing_focus_unavailable"
                    notes_he = "לא ניתן היה לבצע חילוץ ממוקד לריווח חלון (לרוב עקב עומס/קיבולת זמנית במודל), וגם לא נמצאו מידות ריווח מפורשות בסגמנט."
                elif focus_inconclusive_evidence:
                    reason = "low_confidence_or_no_numeric_window_spacing"
                    notes_he = "החילוץ הממוקד לריווח חלון לא סיפק ערכים מספריים ברמת ביטחון מספקת, וגם לא נמצאו מידות ריווח מפורשות בסגמנט."
                self._add_requirement_evaluation(
                    "3.2",
                    "not_checked",
                    reason_not_checked=reason,
                    evidence=window_evidence,
                    notes_he=notes_he,
                )

        return checked_any
    
    def _validate_rebar_specifications(self, data: Dict[str, Any]) -> bool:
        """
        Rule 6.3: Rebar specifications
        - External rebar: spacing ≤ 20cm
        - Internal rebar: spacing ≤ 10cm
        """
        rebar_details = data.get("rebar_details", [])
        if not rebar_details:
            self._add_requirement_evaluation(
                "6.3",
                "not_checked",
                reason_not_checked="no_rebar_details",
                notes_he="לא נמצאו פרטי זיון בסגמנט ולכן לא ניתן לבדוק פסיעת זיון.",
            )
            return False

        evidence: List[Dict[str, Any]] = []
        has_any_numeric = False
        has_external = False
        has_internal = False
        external_ok = True
        internal_ok = True
        external_values: List[float] = []
        internal_values: List[float] = []

        for rebar in rebar_details:
            if not isinstance(rebar, dict):
                continue
            spacing_str = rebar.get("spacing", "")
            spacing_cm = self._extract_dimension_value(str(spacing_str or ""), "cm")
            location = str(rebar.get("location", "") or "")
            location_lower = location.lower()

            if spacing_cm is None:
                continue

            has_any_numeric = True
            evidence.append(
                self._evidence_dimension(
                    value=spacing_cm,
                    unit="cm",
                    element="rebar_spacing",
                    location=location,
                    text=str(spacing_str or ""),
                    raw=rebar,
                )
            )

            is_external = ("חיצוני" in location) or ("external" in location_lower)
            is_internal = ("פנימי" in location) or ("internal" in location_lower)

            if is_external:
                has_external = True
                external_values.append(spacing_cm)
                if spacing_cm > 20.0:
                    external_ok = False
            if is_internal:
                has_internal = True
                internal_values.append(spacing_cm)
                if spacing_cm > 10.0:
                    internal_ok = False

        if not has_any_numeric:
            self._add_requirement_evaluation(
                "6.3",
                "not_checked",
                reason_not_checked="no_parseable_rebar_spacing",
                evidence=evidence,
                notes_he="נמצאו פרטי זיון אך ללא פסיעות שניתנות לפענוח.",
            )
            return False

        # Fail fast if any parsed evidence violates.
        if (has_external and not external_ok) or (has_internal and not internal_ok):
            self._add_requirement_evaluation(
                "6.3",
                "failed",
                evidence=evidence
                + [
                    self._evidence_dimension(value=20.0, unit="cm", element="required_external_max"),
                    self._evidence_dimension(value=10.0, unit="cm", element="required_internal_max"),
                ],
                notes_he="נמצאה פסיעת זיון שעולה על הערכים המותרים (חיצוני≤20, פנימי≤10 ס\"מ).",
            )
            return True

        # For a reliable PASS we prefer to have evidence for both external+internal.
        if has_external and has_internal and external_ok and internal_ok:
            self._add_requirement_evaluation(
                "6.3",
                "passed",
                evidence=evidence
                + [
                    self._evidence_dimension(value=20.0, unit="cm", element="required_external_max"),
                    self._evidence_dimension(value=10.0, unit="cm", element="required_internal_max"),
                ],
                notes_he="פסיעות הזיון שנמצאו עומדות בדרישות (חיצוני≤20, פנימי≤10 ס\"מ).",
            )
            return True

        self._add_requirement_evaluation(
            "6.3",
            "not_checked",
            reason_not_checked="partial_rebar_context",
            evidence=evidence
            + [
                self._evidence_dimension(value=20.0, unit="cm", element="required_external_max"),
                self._evidence_dimension(value=10.0, unit="cm", element="required_internal_max"),
            ],
            notes_he="נמצאו פסיעות זיון אך חסר הקשר ברור האם מדובר גם בזיון פנימי וגם בזיון חיצוני; לא בוצעה הכרעה מלאה.",
        )
        return False
    
    def _validate_concrete_grade(self, data: Dict[str, Any]) -> bool:
        """
        Rule 6.1: Concrete grade must be B-30 or higher
        """
        materials = data.get("materials", [])
        if not materials:
            self._add_requirement_evaluation(
                "6.1",
                "not_checked",
                reason_not_checked="no_materials",
                notes_he="לא נמצאו מפרטי חומרים בסגמנט ולכן לא ניתן לבדוק דרגת בטון.",
            )
            return False

        concrete_materials = [
            m
            for m in materials
            if isinstance(m, dict)
            and (
                "בטון" in str(m.get("type", "")).lower()
                or "concrete" in str(m.get("type", "")).lower()
            )
        ]
        if not concrete_materials:
            self._add_requirement_evaluation(
                "6.1",
                "not_checked",
                reason_not_checked="no_concrete_materials",
                notes_he="לא נמצאה התייחסות לבטון/דרגת בטון בסגמנט.",
            )
            return False

        evidence: List[Dict[str, Any]] = []
        parsed_grades: List[int] = []
        for concrete in concrete_materials:
            grade_raw = str(concrete.get("grade", "") or "")
            notes = str(concrete.get("notes", "") or "")
            combined = f"{grade_raw} {notes}".strip()
            evidence.append(self._evidence_text(text=combined or "בטון", element="concrete_grade", raw=concrete))

            m = re.search(r"(?:b|ב)\s*[-]?\s*(\d+)", combined, flags=re.IGNORECASE)
            if m:
                try:
                    parsed_grades.append(int(m.group(1)))
                except Exception:
                    pass

        if not parsed_grades:
            self._add_requirement_evaluation(
                "6.1",
                "not_checked",
                reason_not_checked="concrete_grade_not_parseable",
                evidence=evidence,
                notes_he="נמצא בטון אך דרגת הבטון לא ניתנת לפענוח בבירור.",
            )
            return False

        min_grade = min(parsed_grades)
        if min_grade < 30:
            self._add_requirement_evaluation(
                "6.1",
                "failed",
                evidence=evidence + [self._evidence_text(text="נדרש B-30 לפחות", element="required_concrete_grade")],
                notes_he=f"נמצאה דרגת בטון B-{min_grade} נמוכה מהמינימום B-30.",
            )
            return True

        self._add_requirement_evaluation(
            "6.1",
            "passed",
            evidence=evidence + [self._evidence_text(text="נדרש B-30 לפחות", element="required_concrete_grade")],
            notes_he=f"דרגת הבטון שפוענחה (מינימום B-{min_grade}) עומדת בדרישה B-30 לפחות.",
        )
        return True
    
    def _validate_steel_type(self, data: Dict[str, Any]) -> bool:
        """
        Rule 6.2: Steel must be hot-rolled or welded, NOT cold-drawn
        """
        materials = data.get("materials", [])
        if not materials:
            self._add_requirement_evaluation(
                "6.2",
                "not_checked",
                reason_not_checked="no_materials",
                notes_he="לא נמצאו מפרטי חומרים בסגמנט ולכן לא ניתן לבדוק סוג פלדה.",
            )
            return False

        steel_materials = [
            m
            for m in materials
            if isinstance(m, dict)
            and (
                "פלדה" in str(m.get("type", "")).lower()
                or "steel" in str(m.get("type", "")).lower()
            )
        ]

        if not steel_materials:
            self._add_requirement_evaluation(
                "6.2",
                "not_checked",
                reason_not_checked="no_steel_materials",
                notes_he="לא נמצאה התייחסות לפלדה/סוג פלדה בסגמנט.",
            )
            return False

        evidence: List[Dict[str, Any]] = []
        found_cold_drawn = False
        found_allowed = False

        for steel in steel_materials:
            grade = str(steel.get("grade", "") or "")
            notes = str(steel.get("notes", "") or "")
            spec = f"{grade} {notes}".strip()
            evidence.append(self._evidence_text(text=spec or "פלדה", element="steel_spec", raw=steel))

            spec_lower = spec.lower()
            if ("משוכה בקור" in spec) or ("cold-drawn" in spec_lower) or ("cold drawn" in spec_lower):
                found_cold_drawn = True
            if ("מעוגלת בחום" in spec) or ("רתיך" in spec) or ("hot-rolled" in spec_lower) or ("hot rolled" in spec_lower) or ("welded" in spec_lower):
                found_allowed = True

        if found_cold_drawn:
            self._add_requirement_evaluation(
                "6.2",
                "failed",
                evidence=evidence,
                notes_he="נמצאה אינדיקציה לפלדה משוכה בקור (אסור לפי דרישה 6.2).",
            )
            return True

        if found_allowed:
            self._add_requirement_evaluation(
                "6.2",
                "passed",
                evidence=evidence,
                notes_he="נמצאה אינדיקציה לפלדה מותרת (מעוגלת בחום/רתיך) ללא אזכור משוכה בקור.",
            )
            return True

        self._add_requirement_evaluation(
            "6.2",
            "not_checked",
            reason_not_checked="steel_type_ambiguous",
            evidence=evidence,
            notes_he="נמצאה התייחסות לפלדה אך ללא אינדיקציה ברורה האם היא מעוגלת בחום/רתיך או משוכה בקור.",
        )
        return False
    
    def _validate_ventilation_note(self, data: Dict[str, Any]) -> bool:
        """
        Rule 4.2: Must include note about TI 4570 ventilation standard
        """
        text_items = data.get("text_items", [])
        annotations = data.get("annotations", [])
        all_text = " ".join([str(t.get("text", "") or "") for t in (text_items + annotations) if isinstance(t, dict)])

        if not all_text.strip():
            self._add_requirement_evaluation(
                "4.2",
                "not_checked",
                reason_not_checked="no_text",
                notes_he="לא נמצאה טקסט/הערות בסגמנט ולכן לא ניתן לבדוק הערת אוורור (ת\"י 4570).",
            )
            return False

        # Check for TI 4570 reference
        if ("4570" in all_text) or ("ת\"י 4570" in all_text) or ("ת״י 4570" in all_text):
            self._add_requirement_evaluation(
                "4.2",
                "passed",
                evidence=[self._evidence_text(text="נמצא אזכור לת\"י 4570", element="ti_4570")],
                notes_he="נמצאה התייחסות לת\"י 4570 בהערות הסגמנט.",
            )
            return True

        self._add_requirement_evaluation(
            "4.2",
            "failed",
            evidence=[self._evidence_text(text="לא נמצא אזכור לת\"י 4570", element="ti_4570")],
            notes_he='חסרה הערה על תקן אוורור וסינון בהתאם לת\"י 4570.',
        )
        return True
    
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
