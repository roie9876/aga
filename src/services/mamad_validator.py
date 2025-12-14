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
            "ROOM_LAYOUT": [self._validate_room_height],
            "DOOR_DETAILS": [self._validate_door_spacing],
            "WINDOW_DETAILS": [self._validate_window_spacing],
            "REBAR_DETAILS": [self._validate_rebar_specifications],
            "MATERIALS_SPECS": [self._validate_concrete_grade, self._validate_steel_type],
            "GENERAL_NOTES": [self._validate_ventilation_note],
            "SECTIONS": [self._validate_room_height],
        }
        # Which official requirement IDs each validator corresponds to.
        # IMPORTANT: We only count a requirement as "checked" if the validator actually
        # had enough evidence to evaluate it (or emitted a missing-info violation).
        validator_to_requirements = {
            self._validate_wall_thickness: ["1.2"],
            self._validate_room_height: ["2.1", "2.2"],
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
        
        def _classify_wall_exposure(location_text: str, wall_type_text: str) -> str:
            """Return 'external' | 'internal' | 'unknown' based on labels in the segment."""
            location_lower = (location_text or "").lower()
            wall_type_lower = (wall_type_text or "").lower()

            # Explicit external markers
            external_markers = [
                "קיר חיצוני",
                "חיצוני",
                "external",
                "outside",
                "exterior",
                "חזית",
                "מעטפת",
                "outer wall",
            ]
            # Explicit internal markers
            internal_markers = [
                "קיר פנימי",
                "פנימי",
                "internal",
                "inside",
                "אזור פנימי",
                "חלל פנימי",
            ]

            # If any internal marker appears, treat as internal even if 'outer wall' appears,
            # because some drawings use 'outer wall' loosely for wall thickness callouts.
            if any(m.lower() in location_lower for m in internal_markers):
                return "internal"
            if any(m.lower() in wall_type_lower for m in internal_markers):
                return "internal"

            if any(m.lower() in location_lower for m in external_markers):
                return "external"
            if any(m.lower() in wall_type_lower for m in external_markers):
                return "external"

            return "unknown"

        # Prefer an explicitly extracted external-wall count when present.
        external_wall_count_raw = data.get("external_wall_count")
        num_external_known: Optional[int] = None
        if isinstance(external_wall_count_raw, int) and 1 <= external_wall_count_raw <= 4:
            num_external_known = external_wall_count_raw

        # Check each wall thickness. We only apply requirement 1.2 to walls that are explicitly external.
        evidence: List[Dict[str, Any]] = []
        parsed_external_thicknesses: List[float] = []
        parsed_internal_thicknesses: List[float] = []
        parsed_unknown_thicknesses: List[float] = []
        external_walls_observed = 0
        for wall in walls:
            thickness_str = wall.get("thickness", "")
            
            # Extract numeric thickness (handle "25cm", "25 ס\"מ", etc.)
            thickness_cm = self._extract_dimension_value(thickness_str, "cm")
            
            if thickness_cm is None:
                continue

            wall_location = str(wall.get("location", "") or "")
            wall_type = str(wall.get("type", "") or "")
            exposure = _classify_wall_exposure(wall_location, wall_type)

            if exposure == "external":
                parsed_external_thicknesses.append(thickness_cm)
                external_walls_observed += 1
            elif exposure == "internal":
                parsed_internal_thicknesses.append(thickness_cm)
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

        if not (parsed_external_thicknesses or parsed_internal_thicknesses or parsed_unknown_thicknesses):
            self._add_requirement_evaluation(
                "1.2",
                "not_checked",
                reason_not_checked="no_parseable_wall_thickness",
                evidence=evidence,
                notes_he="זוהו קירות אך לא נמצאו ערכי עובי שניתנים לפענוח.",
            )
            return False

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
            self._add_requirement_evaluation(
                "1.2",
                "failed",
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
                    f"נמצא עובי קיר חיצוני {min_external_thickness:.0f} ס\"מ קטן מהמינימום 25 ס\"מ לפי סעיף 1.2."
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

        required_thickness = self._get_required_wall_thickness(num_external_known, has_window=False)
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

        text_items = data.get("text_items", [])
        annotations = data.get("annotations", [])
        all_text_lower = " ".join(
            [str(t.get("text", "")) for t in (text_items + annotations)]
        ).lower()

        height_markers_present = any(k in all_text_lower for k in ["h=", "גובה", "height"])
        segment_is_section_like = (primary_category == "SECTIONS") or height_markers_present
        
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
            # Fails both the standard and the exception minimum.
            self._add_requirement_evaluation(
                "2.1",
                "failed",
                evidence=height_evidence + [self._evidence_dimension(value=2.50, unit="m", element="required_min_height")],
                notes_he="גובה החדר נמוך מהמינימום הסטנדרטי 2.50 מ'.",
            )
            self._add_requirement_evaluation(
                "2.2",
                "failed",
                evidence=height_evidence + [self._evidence_dimension(value=2.20, unit="m", element="required_exception_min_height")],
                notes_he="גובה החדר נמוך גם מהמינימום לחריג 2.20 מ'.",
            )
            return True

        # 2.20 <= height < 2.50: standard fails; exception depends on basement/addition + volume.
        self._add_requirement_evaluation(
            "2.1",
            "failed",
            evidence=height_evidence + [self._evidence_dimension(value=2.50, unit="m", element="required_min_height")],
            notes_he="גובה החדר נמוך מ-2.50 מ' ולכן אינו עומד בדרישה הסטנדרטית.",
        )
        self._add_requirement_evaluation(
            "2.2",
            "not_checked",
            reason_not_checked="missing_exception_context_or_volume",
            evidence=height_evidence + [self._evidence_dimension(value=22.5, unit="m3", element="required_min_volume")],
            notes_he="כדי לאשר חריג 2.20 מ' נדרשות ראיות למרתף/תוספת בניה ונפח ≥ 22.5 מ\"ק.",
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
                self._add_requirement_evaluation(
                    "3.2",
                    "not_checked",
                    reason_not_checked="no_window_spacing_annotation",
                    evidence=window_evidence,
                    notes_he="לא נמצאו מידות ריווח חלון מפורשות בסגמנט (עם יחידות והקשר לחלון).",
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
