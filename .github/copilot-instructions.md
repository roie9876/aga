# GitHub Copilot Instructions

## Project Context

This is a FastAPI application for validating Israeli Home Front Command shelter (ממ"ד) architectural plans using Azure OpenAI GPT-5.1 (reasoning model with vision). The app uses GPT-5.1's advanced reasoning capabilities to extract measurements from uploaded plans and validates them against official regulations defined in `requirements-mamad.md`.

**Current Project Status:** As of December 11, 2025
- ✅ **Backend**: FastAPI fully operational with decomposition + validation APIs
- ✅ **Frontend**: React/Vite UI with multi-stage workflow (Upload → Review → Validate → Results)
- ✅ **Plan Decomposition**: GPT-5.1 intelligent segmentation system complete
- ✅ **File Support**: DWF, DWFX, PNG, JPG, PDF via Aspose.CAD + Pillow
- 🔄 **Testing Phase**: Ready for end-to-end validation with real files

**🚨 IMPORTANT - Project Status Tracking:**
- **Always read** `docs/project-status.md` FIRST before making architectural changes
- **Update** `docs/project-status.md` when completing features/phases
- **Update** `docs/architecture.md` when adding new components or data flows
- **Create** feature-specific docs (like `docs/decomposition-feature.md`) for major new capabilities
- **Update** this section's "Current Project Status" when project phase changes

## Architecture Principles

### Azure Authentication
- **CRITICAL**: All Azure services use **Azure Entra ID authentication only**
- Use `DefaultAzureCredential` from `azure.identity` for all Azure clients
- **NEVER** use connection strings, access keys, or any secrets
- Assume Managed Identity in production, local development uses Azure CLI credentials

### Code Style
- Follow PEP 8 for Python code
- Use type hints for all function signatures
- Prefer async/await for I/O operations
- Use Pydantic models for data validation
- Write docstrings for all public functions (Google style)

### Project Structure
- `src/api/` - FastAPI route handlers
  - ✅ `routes/health.py` - Health checks
  - ✅ `routes/decomposition.py` - Plan decomposition endpoints
  - ✅ `routes/validation.py` - Validation endpoints
- `src/services/` - Business logic
  - ✅ `requirements_parser.py` - Parse 25+ rules from requirements-mamad.md
  - ✅ `plan_decomposition.py` - GPT-5.1 multi-sheet segmentation
  - ✅ `plan_extractor.py` - GPT-5.1 measurement extraction
  - ✅ `validation_engine.py` - Rule application engine
- `src/azure/` - Azure client wrappers (Entra ID auth only)
  - ✅ `openai_client.py`, `blob_client.py`, `cosmos_client.py`
- `src/models/` - Pydantic models
  - ✅ `decomposition.py` - DecompositionRequest/Response, PlanSegment
  - ✅ `validation.py` - ValidationRequest/Result, ExtractedPlanData
- `src/utils/` - Utilities
  - ✅ `file_converter.py` - DWF/DWFX → PNG (Aspose.CAD)
  - ✅ `image_cropper.py` - Segment cropping + thumbnails (Pillow)
- `frontend/` - React + Vite frontend
  - ✅ `src/App.tsx` - Multi-stage workflow orchestration
  - ✅ `src/components/DecompositionUpload.tsx` - Drag & drop upload
  - ✅ `src/components/DecompositionReview.tsx` - Segment approval UI
  - ✅ `src/types.ts` - TypeScript interfaces (matches backend models)

### Azure Integration Patterns

#### Azure OpenAI Client
```python
from azure.identity import DefaultAzureCredential
from openai import AzureOpenAI

credential = DefaultAzureCredential()
token = credential.get_token("https://cognitiveservices.azure.com/.default")

client = AzureOpenAI(
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    azure_ad_token=token.token,
    api_version=os.getenv("AZURE_OPENAI_API_VERSION")
)
```

#### Azure Blob Storage
```python
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient

credential = DefaultAzureCredential()
account_url = f"https://{os.getenv('AZURE_STORAGE_ACCOUNT_NAME')}.blob.core.windows.net"
blob_service_client = BlobServiceClient(account_url, credential=credential)
```

#### Azure Cosmos DB
```python
from azure.identity import DefaultAzureCredential
from azure.cosmos import CosmosClient

credential = DefaultAzureCredential()
client = CosmosClient(
    url=os.getenv("AZURE_COSMOSDB_ENDPOINT"),
    credential=credential
)
```

## Domain-Specific Guidelines

### Hebrew Text Handling
- All requirement descriptions are in Hebrew (RTL text)
- Use UTF-8 encoding everywhere
- Preserve Hebrew text exactly when parsing `requirements-mamad.md`
- API responses may contain Hebrew fields (e.g., violation descriptions)

### Validation Rules
- Each requirement in `requirements-mamad.md` maps to a validation rule
- Rules are deterministic (no ML interpretation needed)
- Extract structured data from Markdown sections (1.1, 1.2, 2.1, etc.)
- Store rules with: category, severity, field, operator, expected_value

### Plan Extraction
- Use GPT-5.1 to analyze uploaded architectural plans with reasoning
- Extract: wall_thickness, wall_count, room_dimensions, door_spacing, window_spacing, annotations
- Leverage reasoning capabilities for accurate measurement interpretation
- Return structured JSON with confidence scores
- Handle multiple file formats: PDF, DWG, PNG, JPG
- Note: GPT-5.1 does NOT support temperature, top_p, presence_penalty, frequency_penalty, logprobs, top_logprobs, logit_bias, or max_tokens parameters

### Error Handling
- Use FastAPI's HTTPException for API errors
- Log all Azure client errors with context
- Graceful degradation if Azure services unavailable
- Return partial results if some validations fail

## Common Tasks

### Adding a New Validation Rule
1. Add rule definition to `requirements-mamad.md` if not exists
2. Update `src/services/requirements_parser.py` to extract the rule
3. Implement validation logic in `src/services/validation_engine.py`
4. Add test case in `tests/test_validation.py`

### Adding a New API Endpoint
1. Define Pydantic request/response models in `src/models/`
2. Create route handler in `src/api/routes/`
3. Register router in `src/api/main.py`
4. Add OpenAPI documentation (summary, description, tags)
5. Write integration test in `tests/test_api.py`

### Working with Cosmos DB
- Container structure: `{id, project_id, plan_data, validation_results, created_at}`
- Use partition key: `project_id`
- Query by id for single results, query by project_id for all validations
- Enable indexing on `created_at` for time-based queries

## Testing Guidelines
- Write unit tests for all service functions
- Mock Azure clients using `unittest.mock`
- Use `pytest` for test framework
- Add integration tests for API endpoints using `TestClient`
## Documentation Strategy

**Primary Documentation Files:**
1. **`docs/project-status.md`** - Single source of truth for project progress
   - **When to update**: Completing phases, features, major milestones
   - **What to track**: Completion status, metrics, blockers, next steps, change log
   - **Format**: Structured with phases, checklists, dates, metrics

2. **`docs/architecture.md`** - Technical architecture reference
   - **When to update**: Adding components, new data flows, tech stack changes
   - **What to track**: System diagrams, component details, integration patterns
   - **Format**: Diagrams + detailed component descriptions

3. **`docs/{feature-name}.md`** - Feature-specific deep dives
  - **When to create**: Major new features (e.g., decomposition-feature.md, pdf-support.md)
   - **What to include**: Feature overview, architecture, API details, examples
   - **Format**: Tutorial-style with code samples

4. **`.github/copilot-instructions.md`** - THIS FILE
   - **When to update**: Coding patterns change, new best practices, project phase shifts
   - **What to include**: How to code (NOT what's done), quick status summary at top
   - **Format**: Guidelines, code snippets, common tasks

**Documentation Workflow:**
```
Feature Complete → Update docs/project-status.md (mark ✅)
                 → Update docs/architecture.md (if architecture changed)
                 → Create docs/feature-name.md (if major feature)
                 → Update .github/copilot-instructions.md (if coding patterns changed)
                 → Update change log in docs/project-status.md
```

**Status Tracking Rules:**
- ✅ Use `docs/project-status.md` as THE source of truth for "what's done"
- 📍 Use `.github/copilot-instructions.md` for "how to code it"
- 🏗️ Use `docs/architecture.md` for "how it's structured"
- 📚 Use `docs/{feature}.md` for "how it works in detail"

## When in Doubt
- **Before coding**: Read `docs/project-status.md` to see what's already done
- **During coding**: Follow patterns in this file (copilot-instructions.md)
- **For validation logic**: Refer to `requirements-mamad.md`
- **For architecture**: Check `docs/architecture.md`
- **After coding**: Update `docs/project-status.md` completion status
- Validate all user inputs using Pydantic
- Sanitize file uploads (check file type, size limits)
- Use CORS middleware for web clients
- Rate limit API endpoints
- Never log sensitive data (plan contents, personal info)

## Documentation
- Update `docs/project-status.md` when completing major features
- Add architecture diagrams to `docs/architecture.md` for complex flows
- Keep README.md up to date with setup instructions
- Use docstrings for all public APIs

## When in Doubt
- Refer to `requirements-mamad.md` for validation logic
- Check Azure SDK documentation for authentication patterns
- Follow FastAPI best practices from official docs
- Ask for clarification before implementing ambiguous requirements

you can answer me in english, only if the user ask to answer in hebrew you can answer in hebrew.