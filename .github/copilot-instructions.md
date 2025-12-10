# GitHub Copilot Instructions

## Project Context

This is a FastAPI application for validating Israeli Home Front Command shelter (ממ"ד) architectural plans using Azure OpenAI GPT-5.1 (reasoning model with vision). The app uses GPT-5.1's advanced reasoning capabilities to extract measurements from uploaded plans and validates them against official regulations defined in `requirements-mamad.md`.

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
- `src/services/` - Business logic (validation engine, plan extraction)
- `src/azure/` - Azure client wrappers (Blob, Cosmos DB, OpenAI)
- `src/models/` - Pydantic models and data schemas
- `src/utils/` - Helper functions and utilities

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
- Test Hebrew text encoding/decoding explicitly

## Performance Considerations
- Cache parsed requirements in memory (singleton pattern)
- Use async blob upload/download for large files
- Batch Cosmos DB operations when possible
- Set reasonable timeouts for OpenAI API calls (90s+ for GPT-5.1 reasoning)
- Stream large file uploads using FastAPI's `UploadFile`
- GPT-5.1 reasoning may take longer but provides more accurate results

## Security
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