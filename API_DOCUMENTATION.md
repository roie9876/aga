# API Documentation - MAMAD Validation System

## Overview

RESTful API for validating Israeli Home Front Command shelter (MAMAD) architectural plans using Azure OpenAI GPT-5.1.

**Base URL**: `http://localhost:8000`  
**API Version**: v1  
**API Documentation**: http://localhost:8000/docs (Swagger UI)

## Authentication

All Azure services use **Azure Entra ID (Managed Identity)**:
- No API keys or secrets required
- Uses `DefaultAzureCredential` from `azure-identity`
- Automatically works in both local development (Azure CLI) and production (Managed Identity)

## Endpoints

### 1. Health Check

Check the health status of all Azure services.

```http
GET /health
```

**Response 200 OK**:
```json
{
  "status": "healthy",
  "timestamp": "2025-12-10T07:00:00.000000Z",
  "services": {
    "openai": true,
    "blob_storage": true,
    "cosmos_db": true
  }
}
```

### 2. Validate Plan

Upload and validate an architectural plan.

```http
POST /api/v1/validate
Content-Type: multipart/form-data

project_id: string (required)
file: binary (required)
```

**cURL Example**:
```bash
curl -X POST http://localhost:8000/api/v1/validate \
  -F "project_id=demo-project-001" \
  -F "file=@/path/to/plan.png"
```

**Request Parameters**:
- `project_id` (string, required): Project identifier (e.g., "demo-project-001")
- `file` (binary, required): Architectural plan file (PNG, JPG, PDF)

**Response 200 OK**:
```json
{
  "validation_id": "96af2f4b-2972-4c83-894e-ce91ed07ecd9",
  "project_id": "demo-project-001",
  "plan_name": "demo_plan_perfect.png",
  "status": "pass",
  "total_checks": 20,
  "passed_checks": 20,
  "failed_checks": 0,
  "message": "Validation completed successfully"
}
```

**Flow**:
1. Upload file to Azure Blob Storage
2. Extract data with GPT-5.1 (30-90 seconds)
3. Validate against 20 requirements
4. Store results in Cosmos DB
5. Return validation ID

### 3. Get Validation Results

Retrieve full validation results by ID.

```http
GET /api/v1/results/{validation_id}
```

**cURL Example**:
```bash
curl http://localhost:8000/api/v1/results/96af2f4b-2972-4c83-894e-ce91ed07ecd9
```

**Response 200 OK**:
```json
{
  "validation_id": "96af2f4b-2972-4c83-894e-ce91ed07ecd9",
  "project_id": "demo-project-001",
  "plan_name": "demo_plan_perfect.png",
  "plan_blob_url": "https://agablob.blob.core.windows.net/architectural-plans/...",
  "status": "pass",
  "extracted_data": {
    "external_wall_count": 3,
    "wall_thickness_cm": [62, 62, 62],
    "room_height_m": 2.7,
    "room_volume_m3": 73.71,
    "door_spacing_cm": 120,
    "window_spacing_cm": 80,
    "ventilation_notes": "מערכות אוורור וסינון לפי ת\"י 4570",
    "confidence_score": 0.85
  },
  "violations": [],
  "total_checks": 20,
  "passed_checks": 20,
  "failed_checks": 0,
  "created_at": "2025-12-10T07:00:00.000000Z"
}
```

**Response 404 Not Found**:
```json
{
  "detail": "Validation result not found"
}
```

### 4. Delete Validation Results

Delete a validation result by ID.

```http
DELETE /api/v1/results/{validation_id}
```

**Response 200 OK**:
```json
{
  "message": "Validation deleted successfully"
}
```

**Response 404 Not Found**:
```json
{
  "detail": "Validation result not found"
}
```

### 5. List Project Validations

Get all validations for a specific project.

```http
GET /api/v1/projects/{project_id}/validations
```

**Response 200 OK**:
```json
{
  "project_id": "demo-project-001",
  "validations": [
    {
      "validation_id": "96af2f4b-2972-4c83-894e-ce91ed07ecd9",
      "plan_name": "demo_plan_perfect.png",
      "status": "pass",
      "total_checks": 20,
      "passed_checks": 20,
      "failed_checks": 0,
      "created_at": "2025-12-10T07:00:00.000000Z"
    },
    {
      "validation_id": "697e7afb-14e8-45bb-ac8d-2118d7e2578c",
      "plan_name": "demo_plan_thin_walls.png",
      "status": "fail",
      "total_checks": 20,
      "passed_checks": 17,
      "failed_checks": 3,
      "created_at": "2025-12-10T06:50:00.000000Z"
    }
  ],
  "total_count": 2
}
```

## Data Models

### ValidationStatus

```typescript
type ValidationStatus = 'pass' | 'fail' | 'needs_review';
```

### ValidationSeverity

```typescript
type ValidationSeverity = 'critical' | 'major' | 'minor';
```

### ExtractedData

Data extracted from the architectural plan by GPT-5.1.

```typescript
interface ExtractedData {
  external_wall_count: number | null;      // 1-4 walls
  wall_thickness_cm: number[] | null;      // Array of wall thicknesses
  room_height_m: number | null;            // Room height in meters
  room_volume_m3: number | null;           // Room volume in cubic meters
  door_spacing_cm: number | null;          // Door spacing from wall
  window_spacing_cm: number | null;        // Window spacing from wall
  ventilation_notes: string | null;        // Ventilation system notes
  confidence_score: number;                // 0.0 - 1.0
}
```

### ValidationViolation

A single validation rule violation.

```typescript
interface ValidationViolation {
  rule_id: string;                         // e.g., "1.1_wall_count"
  category: string;                        // e.g., "walls"
  description: string;                     // Hebrew description
  severity: ValidationSeverity;
  expected_value: any | null;              // Expected value
  actual_value: any | null;                // Actual value found
  message: string | null;                  // Additional details
}
```

### ValidationResult

Complete validation result.

```typescript
interface ValidationResult {
  validation_id: string;                   // UUID
  project_id: string;
  plan_name: string;
  plan_blob_url: string;
  status: ValidationStatus;
  extracted_data: ExtractedData;
  violations: ValidationViolation[];
  total_checks: number;                    // Always 20
  passed_checks: number;
  failed_checks: number;
  created_at: string;                      // ISO 8601 datetime
}
```

## 20 Validation Checks

### Category 1: External Walls (קירות חיצוניים)
- **1.1** `wall_count`: External wall count between 1-4
- **1.2** `wall_thickness`: Thickness matches wall count (52-62cm)

### Category 2: Height and Volume (גובה ונפח)
- **2.1** `min_height`: Minimum height 2.50m
- **2.2** `height_exception`: 2.20m allowed only in basement with volume ≥22.5m³

### Category 3: Openings - Door & Window (פתחים)
- **3.1** `door_internal_spacing`: Door to internal wall ≥90cm
- **3.2** `door_external_spacing`: Door to external wall ≥75cm
- **3.3** `window_niche_spacing`: Window niche spacing ≥20cm
- **3.4** `window_light_spacing`: Light opening spacing ≥100cm
- **3.5** `window_wall_spacing`: Window to perpendicular wall ≥20cm

### Category 4: Ventilation System (מערכת אוורור)
- **4.1** `ventilation_clearance`: Opening capability ≥20°
- **4.2** `ventilation_standard`: Note "per standard TI 4570" in plan

### Category 5: Infrastructure (תשתיות)
- **5.1** `air_intake_pipe`: Air intake pipe diameter 4"
- **5.2** `air_exhaust_pipe`: Air exhaust pipe diameter 4"
- **5.3** `ac_passage`: AC modular passage or two pipes
- **5.4** `electrical_passage`: Approved modular passage for electrical

### Category 6: Materials (חומרים)
- **6.1** `concrete_grade`: Concrete grade B-30 minimum
- **6.2** `steel_type`: Hot-rolled or welded steel only
- **6.3** `rebar_spacing`: External 20cm, internal 10cm

### Category 7: Standards (תקנים)
- **7.1** `opening_approval`: All openings per standard TI 4422

### Category 8: Usage Restrictions (מגבלות שימוש)
- **8.1** `no_passage`: MAMAD not used as passage between rooms
- **8.2** `no_fixed_furniture`: No fixed cabinets attached to walls

## Error Responses

### 400 Bad Request
Invalid request parameters.

```json
{
  "detail": "Invalid file format. Supported: PNG, JPG, PDF"
}
```

### 404 Not Found
Resource not found.

```json
{
  "detail": "Validation result not found"
}
```

### 500 Internal Server Error
Server-side error.

```json
{
  "detail": "GPT-5.1 extraction failed",
  "error": "Connection timeout"
}
```

### 503 Service Unavailable
Azure service unavailable.

```json
{
  "detail": "Azure OpenAI service unavailable",
  "services": {
    "openai": false,
    "blob_storage": true,
    "cosmos_db": true
  }
}
```

## Rate Limits

No rate limits in development. Production limits:
- 10 validations per minute per project
- 100 validations per hour per project

## GPT-5.1 Reasoning Model

### Model Details
- **Endpoint**: https://foundry-aga.openai.azure.com/
- **Deployment**: gpt-5.1
- **API Version**: 2024-05-01-preview
- **Capabilities**: Advanced reasoning with vision

### Unsupported Parameters
GPT-5.1 reasoning model does NOT support:
- `temperature`
- `top_p`
- `presence_penalty`
- `frequency_penalty`
- `logprobs`
- `top_logprobs`
- `logit_bias`
- `max_tokens`

### Extraction Process
1. **System Prompt** (Hebrew): Instructs model to act as architectural plan analyzer
2. **User Prompt** (Hebrew): Detailed extraction instructions with examples
3. **Image Input**: Base64-encoded architectural plan
4. **Response**: JSON with extracted measurements and confidence score
5. **Processing Time**: 30-90 seconds (reasoning takes longer than standard models)

### Confidence Score Interpretation
- **0.0 - 0.3**: Low quality plan, missing details
- **0.3 - 0.6**: Partial information, some fields unclear
- **0.6 - 0.8**: Good quality, most fields detected
- **0.8 - 1.0**: High quality plan with clear annotations

## Azure Services Configuration

### Blob Storage
- **Account**: agablob
- **Container**: architectural-plans
- **Path Structure**: `{project_id}/{validation_id}/{filename}`
- **Retention**: 90 days

### Cosmos DB
- **Account**: aga.documents.azure.com
- **Database**: mamad-validation
- **Container**: validation-results
- **Partition Key**: /project_id
- **Indexing**: created_at, status, project_id

### OpenAI
- **Endpoint**: https://foundry-aga.openai.azure.com/
- **Deployment**: gpt-5.1
- **Model**: o1-preview (reasoning with vision)
- **Region**: East US

## Development

### Running Locally

```bash
# Backend
cd /Users/robenhai/aga
source .venv/bin/activate
python -m uvicorn src.api.main:app --reload

# Frontend
cd frontend
npm run dev
```

### Environment Variables

No `.env` file needed! All authentication via Azure Entra ID.

Configuration in `src/config.py`:
```python
AZURE_OPENAI_ENDPOINT = "https://foundry-aga.openai.azure.com/"
AZURE_OPENAI_DEPLOYMENT_NAME = "gpt-5.1"
AZURE_OPENAI_API_VERSION = "2024-05-01-preview"
AZURE_STORAGE_ACCOUNT_NAME = "agablob"
AZURE_COSMOSDB_ENDPOINT = "https://aga.documents.azure.com:443/"
```

### Testing with cURL

```bash
# Health check
curl http://localhost:8000/health

# Validate plan
curl -X POST http://localhost:8000/api/v1/validate \
  -F "project_id=test-001" \
  -F "file=@test_data/demo_plan_perfect.png"

# Get results (replace with actual validation_id)
curl http://localhost:8000/api/v1/results/96af2f4b-2972-4c83-894e-ce91ed07ecd9

# List project validations
curl http://localhost:8000/api/v1/projects/test-001/validations
```

## Changelog

### v1.0.0 (2025-12-10)
- Initial release
- GPT-5.1 integration with reasoning
- 20 validation checks
- Azure Entra ID authentication
- Hebrew UI with detailed explanations
- Demo plans for presentations

---

**Built with ❤️ using FastAPI, React, and Azure OpenAI GPT-5.1**
