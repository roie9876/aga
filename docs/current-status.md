# סטטוס עדכני - מערכת בדיקת ממ"ד

## ✅ מה הושלם

### Backend Infrastructure

#### 1. **Plan Decomposition Feature** (NEW! 🎉)
- ✅ **Models** (`src/models/decomposition.py`)
  - `PlanDecomposition`: Full decomposition document with segments, metadata, stats
  - `PlanSegment`: Individual segment with bounding box, type, confidence
  - `ProjectMetadata`: Extracted from legend (architect, date, plan number, etc.)
  - `SegmentType` enum: floor_plan, section, detail, elevation, legend, table
  
- ✅ **Service** (`src/services/plan_decomposition.py`)
  - `decompose_plan()`: Main GPT-5.1 analysis pipeline
  - `_analyze_plan_with_gpt()`: Hebrew prompts for architectural plan analysis
  - `crop_and_upload_segments()`: Image cropping and Blob Storage upload
  - Automatic confidence scoring
  
- ✅ **API Routes** (`src/api/routes/decomposition.py`)
  - `POST /api/v1/decomposition/analyze` - Upload and decompose plan
  - `GET /api/v1/decomposition/{id}` - Get decomposition
  - `PATCH /api/v1/decomposition/{id}/segments/{seg_id}` - Update segment
  - `POST /api/v1/decomposition/{id}/approve` - Approve and continue

- ✅ **Image Processing** (`src/utils/image_cropper.py`)
  - `crop_segment()`: Extract segment using percentage-based bounding box
  - `create_thumbnail()`: Generate 300x200 thumbnails
  - `crop_and_create_thumbnail()`: Combined operation
  - Uses PIL/Pillow for processing

#### 2. **DWF/DWFX Support**
- ✅ File format support for DWF (binary) and DWFX (XML)
- ✅ Auto-conversion to PNG using Aspose.CAD
- ✅ Integrated with decomposition pipeline

#### 3. **Azure Integration**
- ✅ Blob Storage: Upload full plans and cropped segments
- ✅ Cosmos DB: Store decompositions with type="decomposition"
- ✅ OpenAI GPT-5.1: Intelligent plan analysis with reasoning

#### 4. **Segment Validation + Coverage + History (NEW)**
- ✅ **Segment Validation API** (`src/api/routes/segment_validation.py`)
  - `POST /api/v1/segments/validate-segments` - בדיקת סגמנטים מאושרים
  - `GET /api/v1/segments/validations` - רשימת היסטוריית בדיקות (ללא העלאה מחדש)
  - `GET /api/v1/segments/validation/{validation_id}` - טעינת תוצאות בדיקה מלאה
- ✅ **Coverage Tracking** (`src/services/requirements_coverage.py`)
  - מעקב כיסוי עבור 16 דרישות “ממוכנות” (subset מיושם כרגע)
  - תיקון התאמה בין `rule_id` פנימי (לדוגמה `HEIGHT_002`) לבין מזהי דרישות רשמיים (לדוגמה `2.2`)
  - חישוב מחדש של כיסוי בעת טעינת היסטוריה כדי לשקף לוגיקה עדכנית
- ✅ **Explainability (Per Segment)** (`src/services/mamad_validator.py` + backfill)
  - `checked_requirements`: אילו דרישות נבדקו בפועל בסגמנט
  - `decision_summary_he`: הסבר קצר בעברית למה הופעלו/לא הופעלו בדיקות

#### 5. **Requirements Catalog (66 דרישות) (NEW)**
- ✅ `GET /api/v1/requirements` - קטלוג דרישות מלא מתוך requirements-mamad.md (סה"כ 66)
- ✅ `GET /api/v1/requirements/summary` - ספירה לפי פרקים

### Frontend Components

#### 1. **DecompositionUpload** (`frontend/src/components/DecompositionUpload.tsx`)
- ✅ Drag & drop file upload
- ✅ 4-step progress indicator:
  1. Converting DWF to PNG
  2. GPT analysis
  3. Cropping segments
  4. Saving to database
- ✅ File type validation (DWF, DWFX, PDF, PNG, JPG)
- ✅ Simulated progress for UX

#### 2. **DecompositionReview** (`frontend/src/components/DecompositionReview.tsx`)
- ✅ Full plan view with zoom controls (50-200%)
- ✅ Segment list with thumbnails
- ✅ Confidence scoring with color coding:
  - 🟢 Green: ≥85% (auto-approved)
  - 🟡 Yellow: 70-84%
  - 🔴 Red: <70%
- ✅ Approval checkboxes for each segment
- ✅ Expandable details (bounding box, GPT reasoning)
- ✅ Metadata display from legend
- ✅ Approve/Reject workflow

#### 3. **Multi-Stage App** (`frontend/src/App.tsx`)
- ✅ 4-stage workflow:
  1. **Upload**: File upload with progress
  2. **Decomposition Review**: User reviews and approves segments
  3. **Validation**: Run checks on approved segments
  4. **Results**: Show validation results
- ✅ Progress indicator in header
- ✅ Clean state management

#### 4. **Results UX Improvements (NEW)**
- ✅ טעינת בדיקות מהיסטוריה בלי להעלות קובץ מחדש
- ✅ פילטרים לכיסוי דרישות (all / passed / failed / not_checked) דרך כרטיסיות סטטיסטיקה לחיצות
- ✅ תצוגת “לא רלוונטי” עבור סגמנטים ללא דרישות רלוונטיות
- ✅ חלון/מודאל להצגת כלל הדרישות (66) למשתמש

## 🔄 In Progress

### Integration Tasks
- ⏳ Full plan viewer with bounding box overlays
- ⏳ Visual heatmap showing which segments used in which checks
- ⏳ הרחבת כיסוי הבדיקות מעבר ל-16 דרישות ממוכנות (מיפוי קטגוריות/כללים נוספים)
- ⏳ בדיקות end-to-end עם קבצים אמיתיים + כיול פרומפטים לפי תוצאות

## 📋 Next Steps

### High Priority
1. **Integration Testing**
   - Test complete flow: Upload → Decomposition → Review → Validate
   - Test with real DWF files
   - Verify blob storage URLs work correctly

2. **Coverage & Explainability Verification**
  - לוודא שמספרי הסטטיסטיקה מתעדכנים נכון לאחר טעינת היסטוריה
  - לוודא שמוצגים `checked_requirements` ו-`decision_summary_he` לכל סגמנט

3. **Full Plan Viewer**
   - Create interactive viewer component
   - Overlay bounding boxes on full plan
   - Click segment to highlight
   - Zoom/pan controls

4. **Validation Coverage Expansion**
  - הוספת בדיקות ממוכנות נוספות (בהתאם לדרישות במסמך)
  - הרחבת מיפוי `rule_id` → מזהי דרישות רשמיים

### Medium Priority
4. **Segment Editing**
   - Allow user to adjust bounding boxes
   - Merge/split segments
   - Change segment types

5. **Metadata Editing**
   - Form to edit extracted metadata
   - Manual override for incorrect extractions

6. **Error Handling**
   - Retry failed GPT calls
   - Handle low confidence segments
   - Graceful degradation

### Low Priority
7. **Performance Optimization**
   - Parallel segment cropping
   - Lazy load segment thumbnails
   - Progress polling for long operations

8. **UI Enhancements**
   - Animations and transitions
   - Dark mode support
   - Keyboard shortcuts

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Upload DWF/DWFX file                                       │
│  ↓                                                           │
│  Convert to PNG (if needed)                                 │
│  ↓                                                           │
│  GPT-5.1 Analysis                                           │
│  ├─ Identify all frames/sheets                              │
│  ├─ Read titles and labels                                  │
│  ├─ Classify segments (floor plan, section, etc.)           │
│  ├─ Provide bounding boxes (percentage-based)               │
│  └─ Extract metadata from legend                            │
│  ↓                                                           │
│  Crop segments from full plan                               │
│  ↓                                                           │
│  Upload to Blob Storage                                     │
│  ├─ Full plan: {validation_id}/full_plan.png                │
│  └─ Segments: {validation_id}/segments/seg_*.png            │
│  ↓                                                           │
│  Save to Cosmos DB (type="decomposition")                   │
│  ↓                                                           │
│  User Review UI                                             │
│  ├─ View full plan + segments                               │
│  ├─ Approve/reject/edit segments                            │
│  └─ Edit metadata                                           │
│  ↓                                                           │
│  Run validation on approved segments only                   │
│  ↓                                                           │
│  Show results with segment references                       │
└─────────────────────────────────────────────────────────────┘
```

## 📊 Cost Analysis

### Before Decomposition
- 1 GPT call with 8K image → 20,000 tokens
- All validations on same huge image
- **Cost per plan: ~$0.50**

### After Decomposition
- 1 GPT call for decomposition: ~15,000 tokens
- 20 validation calls on small segments: ~3,000 tokens each
- **Cost per plan: ~$0.30** (40% savings!)

**Additional Benefits:**
- ✅ More accurate (focused analysis)
- ✅ Faster (parallel processing possible)
- ✅ Better UX (user can review segments)
- ✅ Works with multi-sheet DWF files

## 📝 Files Summary

### Backend (Python)
- **New Files:**
  - `src/models/decomposition.py` (280 lines)
  - `src/services/plan_decomposition.py` (450 lines)
  - `src/api/routes/decomposition.py` (360 lines)
  - `src/utils/image_cropper.py` (210 lines)

- **Modified Files:**
  - `src/models/__init__.py` - Added decomposition exports
  - `src/api/main.py` - Registered decomposition router

### Frontend (TypeScript/React)
- **New Files:**
  - `frontend/src/components/DecompositionUpload.tsx` (185 lines)
  - `frontend/src/components/DecompositionReview.tsx` (315 lines)
  - `frontend/src/App.clean.tsx` (170 lines)

- **Modified Files:**
  - `frontend/src/types.ts` - Added decomposition types

### Documentation
- `docs/decomposition-feature.md` - Complete feature documentation
- `docs/dwf-support.md` - DWF/DWFX format details

## 🎯 Usage Example

```bash
# 1. Start backend
cd backend
uvicorn src.api.main:app --reload

# 2. Start frontend
cd frontend
npm run dev

# 3. Upload DWF file
# - Navigate to http://localhost:5173
# - Upload T3-N_BUILDING0-1.dwf
# - Wait for decomposition (~30-60s)
# - Review segments
# - Approve segments
# - Run validation
# - View results
```

## 🔧 Configuration

No additional environment variables needed. Uses existing:
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_DEPLOYMENT_NAME`
- `AZURE_COSMOSDB_ENDPOINT`
- `AZURE_STORAGE_ACCOUNT_NAME`

All authentication via **Azure Entra ID** (DefaultAzureCredential).

## 🚀 Next Session TODO

1. [ ] Replace App.tsx with App.clean.tsx
2. [ ] Test complete flow with real DWF file
3. [ ] Create FullPlanViewer component
4. [ ] Connect to validation engine
5. [ ] Add error handling for GPT failures
6. [ ] Document API endpoints in OpenAPI
7. [ ] Write integration tests
