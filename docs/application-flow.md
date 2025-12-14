# Application Flow (Upload → Review → Validation → Final Report)

This document describes the end-to-end UX and backend execution flow for the Mamad Validation App.

- Frontend: React/Vite
- Backend: FastAPI
- Storage: Azure Blob Storage + Azure Cosmos DB
- AI: Azure OpenAI (vision)

## End-to-end flow (Mermaid)

```mermaid
flowchart TB

  %% =====================
  %% Frontend (Browser)
  %% =====================
  subgraph FE["Frontend (Browser) - React"]
    FE1["1) Upload step\nfrontend/src/components/DecompositionUpload.tsx\n- handleFileUpload() -> POST /api/v1/decomposition/analyze\n- handleSegmentsUpload() -> POST /api/v1/decomposition/upload-segments"]
    FE2["2) Review step\nfrontend/src/components/DecompositionReview.tsx\n- loadDecomposition() -> GET /api/v1/decomposition/{id}\n- toggle approvals / ROI edits\n- onApprove(...)"]
    FE3["3) Validation step (NDJSON stream)\nfrontend/src/App.tsx\n- handleApprovalComplete(...)\n- fetch('/api/v1/segments/validate-segments-stream')\n- reader.read() loop -> handleEvent(evt)"]
    FE4["4) Results + Export\nfrontend/src/App.tsx\n- openPrintableReport() -> window.print()\n- downloadJsonReport() -> Blob(JSON) + download"]
  end

  %% =====================
  %% API Layer (FastAPI)
  %% =====================
  subgraph API["Backend API - FastAPI"]
    API1["POST /api/v1/decomposition/analyze\nsrc/api/routes/decomposition.py\n- decompose_plan(...)"]
    API1b["POST /api/v1/decomposition/upload-segments\nsrc/api/routes/decomposition.py\n- create_decomposition_from_uploaded_segments(...)"]

    API2["GET /api/v1/decomposition/{id}\nsrc/api/routes/decomposition.py\n- get_decomposition(...)"]

    API3["PATCH /api/v1/decomposition/{id}/segments/{segId}/bbox\nsrc/api/routes/decomposition.py\n- update_segment_bbox(...)"]

    API4["POST /api/v1/decomposition/{id}/approve\nsrc/api/routes/decomposition.py\n- approve_decomposition(...)"]

    API5["POST /api/v1/segments/validate-segments-stream (NDJSON)\nsrc/api/routes/segment_validation.py\n- validate_segments_stream(...)"]

    API6["GET images for UI & report\nsrc/api/routes/decomposition.py\n- get_full_plan_image(...)\n- get_segment_image(...)"]
  end

  %% =====================
  %% Core Services
  %% =====================
  subgraph SVC["Core Services"]
    S1["Plan conversion\nsrc/utils/file_converter.py\n- convert_to_image_if_needed(...)\n- convert_pdf_to_image(...)"]

    S2["Decomposition service\nsrc/services/plan_decomposition.py\n- get_decomposition_service()\n- crop_and_upload_segments(...)"]

    S3["Image crop + thumbnails\nsrc/utils/image_cropper.py\n- ImageCropper.crop_and_create_thumbnail(...)"]

    S4["Segment analysis (vision)\nsrc/services/segment_analyzer.py\n- SegmentAnalyzer.analyze_segment(...)\n- SegmentAnalyzer._download_segment_image(...)\n- SegmentAnalyzer._analyze_with_gpt(...)"]

    S5["Validation rules\nsrc/services/mamad_validator.py\n- MamadValidator.validate_segment(...)"]

    S6["Coverage tracking\nsrc/services/requirements_coverage.py\n- RequirementsCoverageTracker.calculate_coverage(...)"]
  end

  %% =====================
  %% Azure Clients
  %% =====================
  subgraph AZ["Azure Clients"]
    AZ1["Azure Blob Storage\nsrc/azure/blob_client.py\n- upload_blob(...)\n- download_blob(...)"]
    AZ2["Azure Cosmos DB\nsrc/azure/cosmos_client.py\n- create_item(...)\n- upsert_item(...)\n- query_items(...)"]
    AZ3["Azure OpenAI\nsrc/azure/openai_client.py\n- chat_completions_create(...)"]
  end

  %% =====================
  %% Flow connections
  %% =====================

  %% Upload paths
  FE1 -->|"Upload plan (single file)"| API1
  FE1 -->|"Upload folder (segments: images+PDF)"| API1b

  %% /decomposition/analyze
  API1 --> S1
  API1 --> S2
  S2 --> S3
  S2 --> AZ1
  API1 --> AZ2

  %% /decomposition/upload-segments
  API1b --> S1
  API1b --> S3
  API1b --> AZ1
  API1b --> AZ2

  %% Review
  FE2 --> API2
  FE2 -->|"manual ROI edit"| API3
  FE2 --> API4

  %% Images for review/report
  FE2 -->|"segment thumbnails / images"| API6
  FE4 -->|"embed same-origin images"| API6
  API6 --> AZ1

  %% Validation stream
  API4 --> FE3
  FE3 --> API5
  API5 --> S4
  S4 --> AZ1
  S4 --> AZ3
  API5 --> S5
  API5 --> S6
  API5 --> AZ2

  %% Results
  API5 --> FE4

```

## Code executed per step (real imports + entrypoints)

### 1) Upload

**Frontend (React)**

Source: `frontend/src/components/DecompositionUpload.tsx`

Calls one of:
- `POST /api/v1/decomposition/analyze`
- `POST /api/v1/decomposition/upload-segments`

**Backend (FastAPI)**

Source: `src/api/routes/decomposition.py`

Key imports (top of file):

```python
from src.services.segment_analyzer import SegmentAnalyzer
from src.services.plan_decomposition import get_decomposition_service
from src.azure import get_cosmos_client
from src.azure.blob_client import get_blob_client
from src.utils.image_cropper import get_image_cropper
```

Folder upload (PDF + images) uses local imports inside `create_decomposition_from_uploaded_segments(...)`:

```python
from src.utils.file_converter import convert_to_image_if_needed
from PIL import Image
```

### 2) Review

**Frontend (React)**

Source: `frontend/src/components/DecompositionReview.tsx`

Loads decomposition + images via:
- `GET /api/v1/decomposition/{id}`
- `GET /api/v1/decomposition/{id}/images/...`

Approves segments via:
- `POST /api/v1/decomposition/{id}/approve`

### 3) Validation (streaming)

**Frontend (React)**

Source: `frontend/src/App.tsx`

The streaming reader is implemented using a `fetch()` + `ReadableStream` loop:

```ts
// frontend/src/App.tsx
// - handleApprovalComplete(...)
// - fetch('/api/v1/segments/validate-segments-stream')
// - reader.read() loop parses NDJSON events
```

**Backend (FastAPI)**

Source: `src/api/routes/segment_validation.py`

Key imports used by the streaming endpoint:

```python
from fastapi.responses import StreamingResponse

from src.azure import get_cosmos_client, get_openai_client
from src.services.segment_analyzer import get_segment_analyzer
from src.services.mamad_validator import get_mamad_validator
from src.services.requirements_coverage import get_coverage_tracker
```

### 4) Per-segment AI analysis + rule validation

**AI extraction (vision)**

Source: `src/services/segment_analyzer.py`

```python
from PIL import Image

from src.azure import get_openai_client, get_blob_client

class SegmentAnalyzer:
  async def analyze_segment(...):
    image_bytes = await self._download_segment_image(segment_blob_url)
    extracted_data = await self._analyze_with_gpt(image_bytes=image_bytes, ...)
```

**Rules validation**

Source: `src/services/mamad_validator.py`

Entry point:
- `MamadValidator.validate_segment(...)`

### 5) Final report (client-side)

Source: `frontend/src/App.tsx`

- `openPrintableReport()` builds an HTML report and calls `window.print()`.
- `downloadJsonReport()` serializes the final results to JSON and triggers a download.


## Notes

- Folder upload currently supports **images + PDF**. Autodesk formats (DWF/DWFX/DWG) are intentionally not supported in this flow.
- The “Final Report” is generated client-side by `openPrintableReport()` (HTML + `window.print()`), and it embeds images via same-origin backend endpoints.
