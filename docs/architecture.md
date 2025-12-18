# Architecture Documentation

## System Overview

The Mamad Validation App is a FastAPI-based microservice that validates Israeli Home Front Command shelter (ממ"ד) architectural plans using Azure OpenAI GPT-5.1 (reasoning model with vision capabilities).

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   React Frontend (Vite)                      │
│  Multi-stage Workflow: Upload → Review → Preflight → Validate → Results │
│  - DecompositionUpload (drag & drop)                        │
│  - DecompositionReview (segment approval)                   │
│  - PreflightChecks (submission completeness gate)            │
│  - ValidationResults (violation display)                    │
└─────────────────────────┬───────────────────────────────────┘
                          │ HTTP/REST API
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Application                       │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  API Layer                                            │  │
│  │  - /health (Health check)                            │  │
│  │  - /api/v1/decomposition/analyze (Upload & decompose)│  │
│  │  - /api/v1/decomposition/{id} (Get decomposition)    │  │
│  │  - /api/v1/decomposition/{id}/segments/analyze (Analyze segments)│  │
│  │  - /api/v1/preflight (Submission completeness)        │  │
│  │  - /api/v1/segments/validate-segments (Validate segs)│  │
│  │  - /api/v1/segments/validate-segments-stream (NDJSON)│  │
│  │  - /api/v1/segments/validations (History list)       │  │
│  │  - /api/v1/segments/validation/{id} (History detail) │  │
│  │  - /api/v1/validate (Legacy: validate full plan)     │  │
│  │  - /api/v1/requirements (Requirements catalog)       │  │
│  │  - /api/v1/requirements/summary (Counts)             │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Business Logic Layer                                 │  │
│  │  - Requirements Parser (25+ rules)                   │  │
│  │  - Plan Decomposition Service (GPT-5.1)             │  │
│  │  - Submission Preflight (completeness rules)         │  │
│  │  - Plan Extraction Service (GPT-5.1)                 │  │
│  │  - Validation Engine                                  │  │
│  │  - Image Cropper (segment extraction)                │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Utilities                                            │  │
│  │  - File Converter (DWF/DWFX → PNG via Aspose.CAD)   │  │
│  │  - Image Cropper (PIL/Pillow)                        │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Azure Integration Layer                              │  │
│  │  - OpenAI Client (Entra ID auth)                     │  │
│  │  - Blob Storage Client (Entra ID auth)               │  │
│  │  - Cosmos DB Client (Entra ID auth)                  │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────┬───────────────────────────────────┘
                          │ Azure Entra ID (Managed Identity)
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                      Azure Services                          │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────┐  │
│  │Azure OpenAI  │  │ Blob Storage │  │   Cosmos DB     │  │
│  │   GPT-5.1    │  │  (Plans +    │  │(Decompositions  │  │
│  │  (Reasoning)  │  │  Segments)   │  │  + Results)     │  │
│  └──────────────┘  └──────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Component Details

### 1. API Layer (`src/api/`)

**Responsibilities:**
- Handle HTTP requests/responses
- Request validation (Pydantic models)
- Error handling and status codes
- OpenAPI documentation

**Key Files:**
- `main.py` - FastAPI application entry point, CORS, lifespan
- `routes/health.py` - Health check endpoints
- `routes/decomposition.py` - ✅ Plan decomposition endpoints (NEW)
- `routes/validation.py` - Validation API endpoints
- `routes/segment_validation.py` - ✅ Segment-based validation + history endpoints
- `routes/requirements.py` - ✅ Requirements catalog endpoints

### 2. Business Logic Layer (`src/services/`)

**Responsibilities:**
- Core validation logic
- Requirements parsing
- Plan decomposition and segmentation
- Plan data extraction orchestration

**Key Files:**
- `requirements_parser.py` - ✅ Parses `requirements-mamad.md` into structured rules (25+ rules)
- `plan_decomposition.py` - ✅ Orchestrates GPT-5.1 to identify and segment multi-sheet plans (NEW)
- `plan_extractor.py` - ✅ Orchestrates GPT-5.1 extraction with reasoning
- `validation_engine.py` - ✅ Applies rules to extracted data

### 3. Utilities Layer (`src/utils/`)

**Responsibilities:**
- File format conversion
- Image processing and cropping
- Helper functions

**Key Files:**
- `file_converter.py` - ✅ DWF/DWFX to PNG conversion using Aspose.CAD (NEW)
- `image_cropper.py` - ✅ Segment cropping, thumbnail generation using PIL/Pillow (NEW)

### 4. Azure Integration Layer (`src/azure/`)

**Responsibilities:**
- Manage Azure service connections
- Handle authentication with Entra ID
- Abstract Azure SDK complexity

**Key Files:**
- `openai_client.py` - Azure OpenAI GPT-5.1 wrapper
- `blob_client.py` - Azure Blob Storage wrapper
- `cosmos_client.py` - Azure Cosmos DB wrapper

**Authentication Pattern:**
```python
from azure.identity import DefaultAzureCredential

credential = DefaultAzureCredential()
# Automatically uses:
# 1. Managed Identity (production)
# 2. Azure CLI credentials (local dev)
# 3. Environment variables (fallback)
```

### 5. Data Models (`src/models/`)

**Responsibilities:**
- Define API request/response schemas
- Data validation with Pydantic
- Type safety across the application

**Key Models:**
- `DecompositionRequest` - ✅ Plan decomposition request (NEW)
- `DecompositionResponse` - ✅ Decomposition results with segments (NEW)
- `PlanSegment` - ✅ Individual segment metadata (NEW)
- `ValidationRequest` - Plan upload request
- `ValidationResult` - Complete validation output
- `ExtractedPlanData` - Structured plan measurements
- `ValidationViolation` - Single rule violation

### 6. Frontend Layer (`frontend/`)

**Responsibilities:**
- User interface for plan decomposition and validation
- Multi-stage workflow management
- File upload and drag & drop
- Segment review and approval

**Tech Stack:**
- **Framework**: React 18 with TypeScript
- **Build Tool**: Vite 7.2.7 with HMR
- **Styling**: TailwindCSS
- **HTTP Client**: Fetch API

**Key Components:**
- `App.tsx` - ✅ Main workflow orchestration (5 stages)
- `DecompositionUpload.tsx` - ✅ File upload with progress indicator
- `DecompositionReview.tsx` - ✅ Segment list, approval UI, confidence display
- `PreflightChecks.tsx` - ✅ Submission completeness checks UI gate
- `types.ts` - ✅ TypeScript interfaces matching backend models

## Data Flow

### Decomposition Flow (NEW)

```
1. User uploads DWF/DWFX/PNG/JPG file via frontend
   POST /api/v1/decomposition/analyze
   │
   ▼
2. Convert DWF/DWFX to PNG (if needed)
   - Use Aspose.CAD library
   - Full resolution preservation
   - Temporary file handling
   │
   ▼
3. Upload full plan to Azure Blob Storage
   - Container: 'architectural-plans'
   - Generate unique blob name
   - Get blob URL for GPT-5.1
   │
   ▼
4. Analyze plan with GPT-5.1 (Reasoning Model)
   - Send full plan image URL
   - Hebrew prompt for Israeli architectural standards
   - GPT identifies all frames/sheets
   - Extracts: titles, types, bounding boxes, metadata
   - Returns structured JSON with segments
   │
   ▼
5. Crop segments from full plan
   - Use PIL/Pillow for image processing
   - Create full-size crops + thumbnails
   - Upload each segment to Blob Storage
   │
   ▼
6. Store decomposition in Cosmos DB
   - Container: 'decompositions'
   - Document: PlanDecomposition with all segments
   - Status: 'pending_review'
   │
   ▼
7. Return to frontend for user review
   - Display all segments with confidence scores
   - User approves/rejects each segment
   - Metadata editing (optional)
   │
   ▼
8. User approves segments
   - Frontend sends approval list
   - Update Cosmos DB status to 'approved'
   - Proceed to validation with approved segments only

### Segment Validation + Coverage Flow (NEW)

```
1. Client sends decomposition_id + approved_segment_ids
   POST /api/v1/segments/validate-segments
   │
   ▼
2. Backend analyzes each segment (GPT-5.1)
   - classification.primary_category
   - classification.view_type (e.g., top_view vs side_section)
   - Hebrew description
   │
   ▼
3. Backend runs targeted validations (deterministic mapping by category)
   - Emits internal rule IDs (e.g., HEIGHT_002)
   - Also returns UX fields per segment:
     - checked_requirements: ["2.1", "2.2", ...]
     - decision_summary_he: short explanation in Hebrew
   │
   ▼
4. Backend computes coverage report
   - Maps internal rule_id → official requirement_id for correct attribution
   - May enrich extracted data with cross-segment inference (e.g., external vs internal walls)
   │
   ▼
5. Store segment_validation doc in Cosmos DB (type="segment_validation")

### Segment Analysis Endpoint (Preflight + Validation Assist)

The system can optionally analyze approved segments ahead of preflight/validation to extract OCR text and a lightweight summary.

- Endpoint: `POST /api/v1/decomposition/{id}/segments/analyze`
- Purpose: populate per-segment `analysis_data` to improve:
   - Preflight keyword detection (e.g., locating required submission tables/attachments)
   - Segment type inference when segments are initially `unknown`
- Performance: runs with bounded concurrency and per-segment timeout to prevent long “stuck” runs.

### Segment Validation (Streaming NDJSON)

The UI uses the streaming endpoint to display live progress.

- Internally, segment "prepare" work (analysis + focused extraction + cross-segment inference) can run concurrently (bounded).
- Streamed NDJSON events are emitted in a stable, original segment order to keep UX deterministic.
- Final validation remains sequential to preserve deterministic "skip already passed" semantics.
```
```

### Validation Flow

```
1. Client uploads plan (PDF/DWG/image)
   POST /api/v1/validate
   │
   ▼
2. Upload to Azure Blob Storage
   - Generate unique blob name
   - Store in 'architectural-plans' container
   - Get blob URL
   │
   ▼
3. Extract data with GPT-5.1
   - Send plan image to Azure OpenAI
   - Use reasoning capabilities for accurate measurement extraction
   - Parse response to ExtractedPlanData
   │
   ▼
4. Load validation rules
   - Parse requirements-mamad.md (cached)
   - Filter applicable rules
   │
   ▼
5. Run validation engine
   - Compare extracted data vs. rules
   - Generate violations list
   - Calculate overall status
   │
   ▼
6. Store results in Cosmos DB
   - Container: validation-results
   - Partition key: project_id
   - Document: ValidationResult
   │
   ▼
7. Return validation ID to client
   {"validation_id": "abc-123", "status": "completed"}
```

### Retrieval Flow

```
1. Client requests results
   GET /api/v1/results/{validation_id}
   │
   ▼
2. Query Cosmos DB
   - Read by id and partition key
   │
   ▼
3. Return ValidationResult
   - Extracted data
   - All violations
   - Pass/fail status
```

## Database Schema

### Cosmos DB Container: `decompositions` (NEW)

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "project_id": "project-123",  // Partition key
  "original_filename": "full-plan.dwf",
  "full_plan_blob_url": "https://storage.blob.core.windows.net/plans/full-plan.png",
  "status": "approved",
  "segments": [
    {
      "segment_id": "seg-001",
      "title": "קומת קרקע - תוכנית ממ\"ד",
      "type": "floor_plan",
      "bbox": {"x": 100, "y": 200, "width": 800, "height": 600},
      "confidence": 0.95,
      "metadata": {
        "floor": "קומת קרקע",
        "room_type": "ממ\"ד",
        "scale": "1:50"
      },
      "image_url": "https://storage.blob.core.windows.net/segments/seg-001.png",
      "thumbnail_url": "https://storage.blob.core.windows.net/segments/seg-001-thumb.png",
      "approved": true
    }
  ],
  "total_segments": 4,
  "approved_segments": 3,
  "created_at": "2025-12-11T10:30:00Z",
  "updated_at": "2025-12-11T10:35:00Z"
}
```

### Cosmos DB Container: `validation-results`

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "project_id": "project-123",  // Partition key
  "plan_name": "floor-plan-2024.pdf",
  "plan_blob_url": "https://storage.blob.core.windows.net/plans/...",
  "status": "fail",
  "extracted_data": {
    "external_wall_count": 2,
    "wall_thickness_cm": [50, 50, 60, 60],
    "room_height_m": 2.6,
    "room_volume_m3": 25.0,
    "door_spacing_internal_cm": 95,
    "door_spacing_external_cm": 80,
    "has_ventilation_note": true,
    "confidence_score": 0.92
  },
  "violations": [
    {
      "rule_id": "1.2_wall_thickness_2_walls",
      "category": "wall_thickness",
      "description": "2 קירות חיצוניים: עובי 52 ס\"מ",
      "severity": "critical",
      "expected_value": "52",
      "actual_value": "50",
      "section_reference": "1.2"
    }
  ],
  "total_checks": 25,
  "passed_checks": 24,
  "failed_checks": 1,
  "created_at": "2024-12-09T10:30:00Z"
}

### Cosmos DB Container: `validation-results` (segment validations)

Segment-based validations are stored with `type="segment_validation"` and include:
- `analyzed_segments[]` with `analysis_data.classification` and `validation.*`
- `coverage` report returned to UI

The history detail endpoint recomputes `coverage` on read so older stored results reflect updated mapping logic.
```

## Security

### Authentication & Authorization

- **No secrets in code or config** - All auth via Azure Entra ID
- **Managed Identity** in production (Azure Container Apps)
- **DefaultAzureCredential** for local development (Azure CLI)

### Required RBAC Roles

```yaml
Azure OpenAI:
  - Cognitive Services OpenAI User

Azure Blob Storage:
  - Storage Blob Data Contributor

Azure Cosmos DB:
  - Cosmos DB Account Contributor
```

### Data Security

- Plans stored in Azure Blob Storage (encrypted at rest)
- Results in Cosmos DB (encrypted at rest)
- HTTPS only for all API communication
- CORS configured for production origins

## Deployment

### Docker Container

```dockerfile
FROM python:3.11-slim
# Non-root user for security
USER appuser
# FastAPI on port 8000
EXPOSE 8000
```

### Azure Container Apps (Recommended)

```yaml
Container Apps Benefits:
  - Automatic HTTPS/TLS
  - Built-in Managed Identity
  - Auto-scaling
  - Easy CI/CD integration
  - Application Insights integration
```

## Monitoring & Observability

### Logging

- **Structured JSON logs** (pythonjsonlogger)
- **Log levels**: DEBUG, INFO, WARNING, ERROR
- **Context**: All logs include environment, service name, timestamps

### Health Checks

- `/health` endpoint checks all Azure services
- Used by Docker and orchestrators
- Returns degraded status if any service fails

### Metrics (Future)

- Application Insights integration
- Custom metrics: validation count, success rate, extraction confidence
- Performance: API response time, Azure service latency

## Scalability

### Current Design

- **Stateless API** - can run multiple instances
- **Singleton pattern** for Azure clients (connection pooling)
- **Cached requirements** - parse once, use many times

### Future Optimizations

- Add Redis for distributed caching
- Implement request queuing for long-running validations
- Add background workers for async processing
- Implement rate limiting per project
- Optimize GPT-5.1 reasoning token usage

## Error Handling

### Azure Service Failures

```python
try:
    result = await azure_client.operation()
except AzureError as e:
    logger.error("Azure operation failed", error=str(e))
    # Graceful degradation or retry logic
    raise HTTPException(status_code=503, detail="Service temporarily unavailable")
```

### Validation Failures

- Partial results returned when possible
- Low confidence extractions flagged for manual review
- Violations clearly categorized by severity

## Development Workflow

1. **Local Development**
   - Use Azure CLI for authentication
   - Docker Compose for local testing
   - Hot reload enabled for fast iteration

2. **Testing**
   - Unit tests for parsers and validators
   - Integration tests for Azure clients (mocked)
   - E2E tests for API endpoints

3. **CI/CD**
   - GitHub Actions (future)
   - Build Docker image
   - Push to Azure Container Registry
   - Deploy to staging → production

## Technology Stack

### Backend
- **Language**: Python 3.11
- **Framework**: FastAPI 0.109+
- **Azure SDKs**: azure-identity, azure-storage-blob, azure-cosmos, openai
- **Validation**: Pydantic 2.5+
- **Logging**: structlog, python-json-logger
- **Testing**: pytest, pytest-asyncio
- **Containerization**: Docker, Docker Compose
- **File Processing**: Aspose.CAD (DWF/DWFX), Pillow (image cropping)

### Frontend (NEW)
- **Framework**: React 18 with TypeScript 5.6+
- **Build Tool**: Vite 7.2.7
- **Styling**: TailwindCSS 3.4+
- **HTTP**: Fetch API
- **Dev Server**: Vite HMR (Hot Module Replacement)

### AI/ML
- **Model**: Azure OpenAI GPT-5.1 (o1-preview)
- **Capabilities**: Vision + Reasoning
- **Use Cases**: Plan decomposition, measurement extraction, Hebrew text understanding

## Future Enhancements

1. ~~**Frontend UI**~~ - ✅ **COMPLETED** - React/Vite with multi-stage workflow
2. ~~**Plan Decomposition**~~ - ✅ **COMPLETED** - GPT-5.1 intelligent segmentation
3. **Visual Annotations** - Highlight violations on plan images with bounding boxes
4. **PDF Report Generation** - Professional validation reports in Hebrew
5. **Multi-language Support** - Full English/Hebrew UI toggle
6. **Batch Processing** - Validate multiple plans at once
7. **ML Improvements** - Optimize GPT-5.1 prompts for reasoning and accuracy
8. **Regulation Versioning** - Track changes to requirements over time
9. **Reasoning Chain Analysis** - Expose GPT-5.1 reasoning steps for transparency
10. **Full Plan Viewer** - Interactive viewer with zoom/pan and bounding box overlays
11. **Violation-to-Segment Mapping** - Show which segment each violation came from
