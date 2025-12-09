"""Architecture Documentation

## System Overview

The Mamad Validation App is a FastAPI-based microservice that validates Israeli Home Front Command shelter (ממ"ד) architectural plans using Azure OpenAI GPT-4 Vision.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Client Applications                     │
│            (Web UI, Mobile App, API Consumers)              │
└─────────────────────────┬───────────────────────────────────┘
                          │ HTTPS
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Application                       │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  API Layer                                            │  │
│  │  - /health (Health check)                            │  │
│  │  - /api/v1/validate (Upload & validate)             │  │
│  │  - /api/v1/results/{id} (Get results)               │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Business Logic Layer                                 │  │
│  │  - Requirements Parser                                │  │
│  │  - Plan Extraction Service (GPT-4 Vision)            │  │
│  │  - Validation Engine                                  │  │
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
│  │ GPT-4 Vision │  │  (Plans)     │  │  (Results)      │  │
│  └──────────────┘  └──────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────────────────┘
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
- `routes/validation.py` - Validation API endpoints

### 2. Business Logic Layer (`src/services/`)

**Responsibilities:**
- Core validation logic
- Requirements parsing
- Plan data extraction orchestration

**Key Files:**
- `requirements_parser.py` - Parses `requirements-mamad.md` into structured rules
- `plan_extractor.py` - (TODO) Orchestrates GPT-4 Vision extraction
- `validation_engine.py` - (TODO) Applies rules to extracted data

### 3. Azure Integration Layer (`src/azure/`)

**Responsibilities:**
- Manage Azure service connections
- Handle authentication with Entra ID
- Abstract Azure SDK complexity

**Key Files:**
- `openai_client.py` - Azure OpenAI GPT-4 Vision wrapper
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

### 4. Data Models (`src/models/`)

**Responsibilities:**
- Define API request/response schemas
- Data validation with Pydantic
- Type safety across the application

**Key Models:**
- `ValidationRequest` - Plan upload request
- `ValidationResult` - Complete validation output
- `ExtractedPlanData` - Structured plan measurements
- `ValidationViolation` - Single rule violation

## Data Flow

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
3. Extract data with GPT-4 Vision
   - Send plan image to Azure OpenAI
   - Prompt engineering for measurement extraction
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

- **Language**: Python 3.11
- **Framework**: FastAPI 0.109+
- **Azure SDKs**: azure-identity, azure-storage-blob, azure-cosmos, openai
- **Validation**: Pydantic 2.5+
- **Logging**: structlog, python-json-logger
- **Testing**: pytest, pytest-asyncio
- **Containerization**: Docker, Docker Compose

## Future Enhancements

1. **Frontend UI** - React/Next.js for architects
2. **Visual Annotations** - Highlight violations on plan images
3. **PDF Report Generation** - Professional validation reports
4. **Multi-language Support** - English/Hebrew UI
5. **Batch Processing** - Validate multiple plans at once
6. **ML Improvements** - Fine-tune GPT-4 Vision for better extraction
7. **Regulation Versioning** - Track changes to requirements over time
