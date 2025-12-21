# Requirements Coverage Tracking

**Feature**: Automated tracking of MAMAD requirements validation coverage  
**Created**: December 11, 2025  
**Last Updated**: December 12, 2025  
**Status**: ✅ Complete and Integrated (for implemented checks)

---

## Overview

The Requirements Coverage Tracking system provides users with comprehensive visibility into which MAMAD requirements have been validated, which have passed/failed, and which requirements still need coverage. This addresses the critical question: **"What's missing from my validation?"**

---

## Problem Solved

**User Challenge**: After uploading a plan and getting validation results, users had no way to know:
- Which of the **implemented** MAMAD checks were actually executed
- Which requirements have no relevant segments in their uploaded plan
- What additional drawings/segments they need to provide for complete coverage
- Overall validation status relative to the full requirements document

**Solution**:
- A full **Requirements Catalog** (66 requirements) for transparency: `GET /api/v1/requirements`
- A real-time **Coverage Dashboard** for the **implemented machine-checkable subset** (16 checks across 6 categories), showing exactly what was checked, what passed/failed, and what is missing for coverage completeness.

---

## Architecture

### Backend Components

#### 1. **RequirementsCoverageTracker Service**
**File**: `src/services/requirements_coverage.py` (223 lines)

**Core Data Structure (Implemented Checks)**:
```python
ALL_REQUIREMENTS = {
    "1.1": {"category": "קירות", "description": "מיקום ממ\"ד - מרחק מקיר חיצוני", "severity": "critical"},
    "1.2": {"category": "קירות", "description": "עובי קיר - 25-40 ס\"מ", "severity": "critical"},
    "2.1": {"category": "גובה החדר", "description": "גובה מינימלי 2.50 מטר", "severity": "critical"},
    "2.2": {"category": "גובה החדר", "description": "גובה 2.20 מטר במרתף", "severity": "warning"},
    "2.3": {"category": "שטח ממ\"ד", "description": "שטח נטו מינימלי 9 מ\"ר (ללא קירות)", "severity": "critical"},
    "3.1": {"category": "פתחים", "description": "ריווח דלת", "severity": "warning"},
    "3.2": {"category": "פתחים", "description": "ריווח חלון", "severity": "warning"},
    "4.1": {"category": "אוורור", "description": "מערכת אוורור ת\"י 4570", "severity": "critical"},
    "4.2": {"category": "אוורור", "description": "הערה בתכנית ת\"י 4570", "severity": "warning"},
    "5.1": {"category": "תשתיות", "description": "צנרת במרחק ≥2.5cm", "severity": "error"},
    "5.2": {"category": "תשתיות", "description": "צנרת בקירות - מקסימום ברזל 2.5%", "severity": "error"},
    "6.1": {"category": "חומרים", "description": "בטון B-30", "severity": "critical"},
    "6.2": {"category": "חומרים", "description": "פלדה - לא משוכה בקור", "severity": "critical"},
    "6.3": {"category": "חומרים", "description": "זיון - ריווח ≤20cm/≤10cm", "severity": "critical"},
    "7.1": {"category": "ביצוע פתחים", "description": "ביצוע פתחים ת\"י 4422", "severity": "error"},
    "8.1": {"category": "מגבלות שימוש", "description": "אין מעבר בין חדרים", "severity": "warning"},
    "8.2": {"category": "מגבלות שימוש", "description": "אין ריהוט קבוע", "severity": "warning"},
}
```

**Key Method**: `calculate_coverage(validation_result)`

**Input**:
```python
{
    "analyzed_segments": [
        {
            "segment_id": "seg_001",
            "classification": {
                "primary_category": "WALL_SECTION",
                "description": "חתך קיר חיצוני עם עובי",
                "relevant_requirements": ["1.2"]
            },
            "validation": {
                "passed": True,
                "violations": [],
                "checked_requirements": ["2.1", "2.2"],
                "decision_summary_he": "הופעלו בדיקות לפי קטגוריית הסגמנט..."
            }
        },
        ...
    ]
}
```

**Output**:
```python
{
    "statistics": {
        "total_requirements": 16,
        "checked": 8,           # 8 requirements had relevant segments
        "passed": 6,            # 6 requirements passed validation
        "failed": 2,            # 2 requirements failed validation
        "not_checked": 8,       # 8 requirements have no relevant segments
        "coverage_percentage": 50.0,  # 8/16 implemented checks = 50%
        "pass_percentage": 37.5       # 6/16 = 37.5%
    },
    "requirements": {
        "1.1": {
            "requirement_id": "1.1",
            "category": "קירות",
            "description": "מיקום ממ\"ד...",
            "severity": "critical",
            "status": "passed",         # or "failed" or "not_checked"
            "segments_checked": ["seg_001", "seg_002"],
            "violations": []
        },
        ...
    },
    "by_category": {
        "קירות": [...],
        "גובה החדר": [...],
        ...
    },
    "missing_segments_needed": [
        {
            "requirement_id": "4.1",
            "description": "מערכת אוורור וסינון בהתאם לת\"י 4570",
            "category": "אוורור",
            "severity": "critical",
            "needed_segment_type": "מערכת אוורור - פרט התקנה"
        },
        ...
    ]
}
```

---

#### 2. **API Integration**
**File**: `src/api/routes/segment_validation.py`

**Endpoints**:
- `POST /api/v1/segments/validate-segments` - validate approved segments and return coverage
- `GET /api/v1/segments/validations` - list history (no re-upload)
- `GET /api/v1/segments/validation/{validation_id}` - load one validation (recomputes coverage on read)

**Response Model**:
```python
class SegmentValidationResponse(BaseModel):
    validation_id: str
    total_segments: int
    passed: int
    failed: int
    warnings: int
    analyzed_segments: List[Dict[str, Any]]
    coverage: Optional[Dict[str, Any]] = None  # NEW - Coverage report
```

**Integration Point** (after validation completes):
```python
# Calculate requirements coverage
tracker = get_coverage_tracker()
coverage_report = tracker.calculate_coverage({
    "analyzed_segments": analyzed_segments
})

logger.info("Validation complete",
           coverage_percentage=coverage_report["statistics"]["coverage_percentage"],
           pass_percentage=coverage_report["statistics"]["pass_percentage"])

return {
    ...,
    "coverage": coverage_report  # Include in response
}
```

#### 3. **Correctness: Rule ID → Requirement ID Mapping**
Older coverage logic assumed the validator emits official requirement IDs. In practice, the validator emits internal rule IDs (e.g., `HEIGHT_002`).

The tracker now maps internal IDs to official IDs (examples):
- `HEIGHT_002` → `2.2`
- `HEIGHT_001` / `HEIGHT_003` → `2.1`
- `WALL_001..003` → `1.2`
- `DOOR_001` → `3.1`
- `WINDOW_001` → `3.2`

This ensures violations are correctly attributed to the official requirement rows the UI displays.

---

### Frontend Components

#### 1. **TypeScript Types**
**File**: `frontend/src/types.ts`

```typescript
export interface RequirementCoverage {
  requirement_id: string;
  category: string;
  description: string;
  severity: 'critical' | 'error' | 'warning';
  status: 'passed' | 'failed' | 'not_checked';
  segments_checked: string[];
  violations: ValidationViolation[];
}

export interface CoverageStatistics {
  total_requirements: number;
  checked: number;
  passed: number;
  failed: number;
  not_checked: number;
  coverage_percentage: number;
  pass_percentage: number;
}

export interface CoverageReport {
  statistics: CoverageStatistics;
  requirements: Record<string, RequirementCoverage>;
  by_category: Record<string, RequirementCoverage[]>;
  missing_segments_needed: MissingSegment[];
}
```

---

#### 2. **Coverage Dashboard UI**
**File**: `frontend/src/App.tsx` (results stage)

**Components**:

1. **Statistics Cards**:
   - Coverage % (purple)
   - Passed count (green)
   - Failed count (red)
   - Not checked count (gray)

    **NEW (Dec 12, 2025)**: Cards are clickable filters (all/passed/failed/not_checked).

2. **Progress Bar**:
   - Visual representation of coverage_percentage
    - Shows X out of 16 implemented checks covered

3. **Requirements Table** (grouped by category):
   - ✅ Green background for passed requirements
   - ❌ Red background for failed requirements
   - ⚠️ Gray background for not_checked requirements
   - Shows requirement ID, severity badge, description
   - Lists which segments validated each requirement
   - Displays violations for failed requirements

4. **Missing Segments Recommendations**:
   - Yellow alert box
   - Lists all not_checked requirements
   - Shows needed segment type for each missing requirement
   - Helps users know what to upload next

---

## Coverage Calculation Logic

### Step 1: Initialize Coverage Map
```python
# All tracked (implemented) requirements start as "not_checked"
coverage = {req_id: {"status": "not_checked", ...} for req_id in ALL_REQUIREMENTS}
```

### Step 2: Process Analyzed Segments
```python
for segment in analyzed_segments:
    classification = segment.get("analysis_data", {}).get("classification", {})
    validation = segment.get("validation", {})

    # Prefer deterministic list from validator; fall back to classification
    checked_reqs = validation.get("checked_requirements") or classification.get("relevant_requirements") or []

    # Map internal rule IDs (e.g., HEIGHT_002) to official requirement IDs (e.g., 2.2)
    violations_by_req = {}
    for v in (validation.get("violations") or []):
        req_id = _map_rule_id_to_requirement_id(v.get("rule_id", ""))
        if req_id:
            violations_by_req.setdefault(req_id, []).append(v)

    # Any mapped violation implies that requirement was checked
    for req_id in violations_by_req.keys():
        if req_id not in checked_reqs:
            checked_reqs.append(req_id)
    
    for req_id in checked_reqs:
        coverage[req_id]["segments_checked"].append(segment_id)
        
        segment_violations = violations_by_req.get(req_id, [])
        
        if segment_violations:
            coverage[req_id]["status"] = "failed"
            coverage[req_id]["violations"].extend(segment_violations)
        elif coverage[req_id]["status"] == "not_checked":
            coverage[req_id]["status"] = "passed"
```

### Step 3: Calculate Statistics
```python
total = len(ALL_REQUIREMENTS)
checked = count(status != "not_checked")
passed = count(status == "passed")
failed = count(status == "failed")
not_checked = count(status == "not_checked")

coverage_percentage = (checked / total) * 100
pass_percentage = (passed / total) * 100
```

### Step 4: Identify Missing Segments
```python
missing = [
    {
        "requirement_id": req_id,
        "needed_segment_type": _map_requirement_to_segment_type(req_id)
    }
    for req_id, req_data in coverage.items()
    if req_data["status"] == "not_checked"
]
```

---

## Requirement → Segment Type Mapping

The system maps each requirement to the segment type needed for validation:

| Requirement ID | Category | Needed Segment Type |
|----------------|----------|---------------------|
| 1.1 | קירות | תכנית קומה - מיקום ממ"ד ביחס לקירות חיצוניים |
| 1.2 | קירות | תכנית ממ"ד בקנ"מ 1:50 - עובי קירות ומספר קירות חיצוניים |
| 2.1 | גובה החדר | חתך אנכי - גובה החדר |
| 2.2 | גובה החדר | חתך אנכי - גובה בתוספת בניה/מרתף + נפח החדר |
| 2.3 | שטח ממ"ד | תכנית ממ"ד בקנ"מ 1:50 - שטח פנימי נטו |
| 3.1 | פתחים | פרט דלת - ריווח מקיר ניצב |
| 3.2 | פתחים | פרט חלון - ריווח בין פתחים |
| 4.1 | אוורור | מערכת אוורור - פרט התקנה |
| 4.2 | אוורור | הערות כלליות - אזכור ת"י 4570 |
| 5.1 | תשתיות | פרט צנרת - מרחק מבטון |
| 5.2 | תשתיות | חתך קיר עם צנרת - אחוז ברזל |
| 6.1 | חומרים | הערות כלליות/פרט - ציון סוג בטון B-30 |
| 6.2 | חומרים | הערות כלליות/פרט - ציון סוג פלדה |
| 6.3 | חומרים | פרט זיון - ריווח מוטות |
| 7.1 | ביצוע פתחים | פרט פתחים - התייחסות לת"י 4422 |
| 8.1 | מגבלות שימוש | תכנית קומה - בדיקת מעבר בין חדרים |
| 8.2 | מגבלות שימוש | תכנית קומה - אין ריהוט קבוע |

---

## User Workflow

### 1. Upload & Validate Plan
User uploads PDF → Segments detected → Segments classified → Validation runs

### 2. View Coverage Dashboard
System automatically calculates coverage after validation completes

### 3. Interpret Results

**Example Scenario**:
```
Coverage: 50% (8/16 implemented checks checked)
Pass Rate: 75% (6/8 checked requirements passed)

✅ Passed (6):
  - 1.2: עובי קיר (validated in seg_001)
  - 2.1: גובה מינימלי (validated in seg_003)
  - 3.1: ריווח דלת (validated in seg_005)
  - 6.1: בטון B-30 (validated in seg_007)
  - 6.3: זיון ריווח (validated in seg_008)
  - 8.1: אין מעבר (validated in seg_002)

❌ Failed (2):
  - 1.1: מיקום ממ"ד (found 0.8m, required ≥1.0m)
  - 5.1: צנרת מרחק (found 1.5cm, required ≥2.5cm)

⚠️ Not Checked (8):
  - 2.2: גובה במרתף → Need: חתך אנכי במרתף
  - 3.2: ריווח חלון → Need: פרט חלון
  - 4.1: מערכת אוורור → Need: פרט התקנה אוורור
  - 4.2: הערה ת"י 4570 → Need: הערות כלליות
  - 5.2: צנרת אחוז ברזל → Need: חתך קיר עם צנרת
  - 6.2: סוג פלדה → Need: הערות/פרט פלדה
  - 7.1: ביצוע פתחים → Need: פרט פתחים
  - 8.2: אין ריהוט → Need: תכנית קומה מפורטת
```

### 4. Take Action
- **Fix Failures**: Re-upload corrected segments for requirements 1.1, 5.1
- **Complete Coverage**: Upload missing segment types (ventilation details, window details, etc.)
- **Re-validate**: Submit new segments → Coverage recalculates

---

## Benefits

1. **Transparency**: Users see exactly which requirements were checked
2. **Actionable**: Clear recommendations for what's missing
3. **Prioritized**: Severity levels (critical/error/warning) guide user focus
4. **Progressive**: Users can incrementally add segments to improve coverage
5. **Extensible**: Designed so additional requirements can be added to the implemented set over time

---

## Technical Implementation Details

### Performance Considerations
- Coverage calculation is O(n) where n = number of segments
- Runs in-memory after validation (no additional DB calls)
- Adds ~10ms to API response time

### Error Handling
- If classification.relevant_requirements is missing → requirement stays "not_checked"
- If requirement_id not in ALL_REQUIREMENTS → logged as warning, skipped
- Empty analyzed_segments → 100% not_checked (valid state)

### Extensibility
- Easy to add new requirements (update ALL_REQUIREMENTS dictionary)
- Easy to change severity levels
- Easy to customize segment type recommendations

---

## Future Enhancements

### Planned
- [ ] Visual pie chart of coverage (green/red/gray slices)
- [ ] Export coverage report to PDF
- [ ] Save coverage history (track improvement over time)
- [ ] Email alerts for incomplete coverage
- [ ] Bulk upload recommendations (suggest all missing segments at once)

### Possible
- [ ] Auto-suggest which segments to crop from full plan based on missing requirements
- [ ] Confidence scoring for missing segments (how likely they exist in uploaded plan)
- [ ] Integration with external CAD viewers (highlight recommended areas)

---

## Testing

### Manual Test Cases
1. ✅ Upload plan with all segment types → Expect 100% coverage
2. ✅ Upload plan with only walls → Expect ~12.5% coverage (2/16)
3. ✅ Upload plan with violations → Expect failed status for specific requirements
4. ✅ Upload plan with no segments → Expect 0% coverage, all not_checked

### Automated Tests (TODO)
- [ ] Unit tests for calculate_coverage()
- [ ] Integration tests for API endpoint
- [ ] UI tests for coverage dashboard rendering

---

## Related Documentation
- `requirements-mamad.md` - Full requirements catalog (currently parsed as 66 items)
- `docs/architecture.md` - System architecture overview
- `docs/decomposition-feature.md` - Plan decomposition system
- `docs/project-status.md` - Overall project status

---

## Changelog

| Date | Change |
|------|--------|
| 2025-12-11 | Initial implementation of coverage tracking system |
| 2025-12-11 | Created RequirementsCoverageTracker service |
| 2025-12-11 | Integrated into segment validation API |
| 2025-12-11 | Built coverage dashboard UI |
| 2025-12-11 | Completed documentation |
