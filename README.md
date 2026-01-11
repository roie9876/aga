# 🏠 מערכת בדיקת תוכניות ממ״ד - MAMAD Validation System

FastAPI + React application for validating Israeli Home Front Command shelter (ממ"ד) architectural plans using **Azure OpenAI GPT-5.1** reasoning model with vision capabilities.

[![Python](https://img.shields.io/badge/Python-3.12-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115.0-green.svg)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18-blue.svg)](https://react.dev)
[![Azure](https://img.shields.io/badge/Azure-OpenAI%20|%20Cosmos%20|%20Blob-blue.svg)](https://azure.microsoft.com)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.6-blue.svg)](https://www.typescriptlang.org)

## 📖 Overview

Automated validation system for protected space (מרחב מוגן דירתי - ממ"ד) architectural plans. The system uses GPT-5.1's advanced reasoning capabilities to:

1. **Extract measurements** from uploaded architectural plans
2. **Validate compliance** with 20 Israeli Home Front Command requirements
3. **Provide detailed reasoning** for each validation check
4. **Generate comprehensive reports** in Hebrew with visual indicators

## ✨ Key Features

- 🤖 **GPT-5.1 Reasoning Model** - Advanced AI with vision and reasoning capabilities
- 📋 **20 Validation Checks** - Complete coverage of all MAMAD requirements
- 🔍 **Detailed Explanations** - Shows exactly what the model understood and why
- 🌐 **Hebrew UI** - Full RTL support with beautiful, intuitive interface
- 🔒 **Zero Secrets** - Azure Entra ID authentication only (Managed Identity)
- ☁️ **Azure Native** - OpenAI, Cosmos DB, Blob Storage integration
- 📊 **Demo Plans Included** - 4 example plans for presentations

## 📚 Documentation

- **[📖 Demo Guide (Hebrew)](./DEMO_GUIDE_HE.md)** - מדריך שימוש והצגה בעברית
- **[📘 API Documentation](./API_DOCUMENTATION.md)** - Complete REST API reference
- **[📋 Requirements Specification](./requirements-mamad.md)** - 20 MAMAD validation rules (Hebrew)
- **[📁 Project Structure](./docs/architecture.md)** - Codebase organization

## 🚀 Quick Start

### Prerequisites

- **Python 3.12** (required for Pydantic 2.10)
- **Node.js 18+** (for React frontend)
- **Azure Account** with:
  - Azure OpenAI Service (GPT-5.1 deployment)
  - Azure Cosmos DB
  - Azure Blob Storage
  - Azure CLI configured (`az login`)

### Required Azure RBAC Roles

Assign these roles to your Azure identity:

- **Cognitive Services OpenAI User** - for Azure OpenAI API
- **Storage Blob Data Contributor** - for Blob Storage
- **Cosmos DB Built-in Data Contributor** - for Cosmos DB

### Installation

1. **Clone and setup backend**
   ```bash
   git clone <repo-url>
   cd aga
   python3.12 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Setup frontend**
   ```bash
   cd frontend
   npm install
   ```

3. **Configure Azure resources**
   
   Update `src/config.py` with your Azure endpoints:
   ```python
   AZURE_OPENAI_ENDPOINT = "https://your-openai.openai.azure.com/"
   AZURE_OPENAI_DEPLOYMENT_NAME = "gpt-5.1"
   AZURE_STORAGE_ACCOUNT_NAME = "yourstorageaccount"
   AZURE_COSMOSDB_ENDPOINT = "https://your-cosmos.documents.azure.com:443/"
   ```

   **No `.env` file needed!** - Authentication via Azure Entra ID

### Optional: Token/Cost Tracking (Internal)

The app tracks Azure OpenAI token usage per request for internal cost analysis.

- Token/cost data is included only in exported artifacts (JSON/PDF) under an internal section (`_internal.llm_usage`).
- It is **not** shown in the normal UI.

Enable optional cost estimation (prices are per 1K tokens):

```bash
export AZURE_OPENAI_PRICE_PER_1K_INPUT_TOKENS_USD="..."
export AZURE_OPENAI_PRICE_PER_1K_OUTPUT_TOKENS_USD="..."
```

Enable backend log output (so you can grep token totals during runs):

```bash
export LOG_LLM_USAGE=true
# Optional (more verbose):
export LOG_LLM_USAGE_INCLUDE_CALLS=true
```

4. **Run the application**
   
   Terminal 1 (Backend):
   ```bash
   cd aga
   source .venv/bin/activate
   python -m uvicorn src.api.main:app --reload
   ```
   
   Terminal 2 (Frontend):
   ```bash
   cd aga/frontend
   npm run dev
   ```

5. **Access the application**
   - Frontend: http://localhost:5173
   - Backend API: http://localhost:8000
   - API Docs: http://localhost:8000/docs

## 🎯 Architecture

### Backend Stack
- **FastAPI 0.115.0** - Modern Python web framework
- **Pydantic 2.10** - Data validation with type hints
- **Azure OpenAI GPT-5.1** - Reasoning model with vision (o1-preview)
- **Azure Cosmos DB** - NoSQL database for validation results
- **Azure Blob Storage** - Architectural plan file storage
- **Azure Entra ID** - Zero-secrets authentication

### Frontend Stack
- **React 18** - Modern UI library
- **TypeScript 5.6** - Type-safe JavaScript
- **Vite 7.2** - Fast build tool
- **TailwindCSS 4.0** - Utility-first CSS framework
- **Lucide Icons** - Beautiful icon library

### Security
- ✅ **No API keys in code** - DefaultAzureCredential handles all auth
- ✅ **RBAC-based access** - Fine-grained permissions per service
- ✅ **Local development support** - Uses Azure CLI credentials
- ✅ **Production ready** - Seamless Managed Identity in Azure

## 📊 Demo Plans for Presentations

Located in `test_data/`:

### 1. `demo_plan_perfect.png` - Perfect Plan ✅
- **Status**: All 20 checks pass
- **Features**: 3 external walls (62cm), proper height (2.7m), correct spacing, all infrastructure
- **Use**: Show ideal validation result

### 2. `demo_plan_thin_walls.png` - Wall Thickness Issue ❌
- **Status**: Fails (3 violations)
- **Issue**: 4 external walls but only 35-40cm thick (requires 62cm)
- **Use**: Demonstrate thickness validation

### 3. `demo_plan_low_height.png` - Height Issue ❌
- **Status**: Fails (1 violation)
- **Issue**: Height 2.30m < 2.50m minimum requirement
- **Use**: Show height/volume validation

### 4. `demo_plan_door_spacing.png` - Spacing Issue ❌
- **Status**: Fails (1 violation)
- **Issue**: Door 60cm from wall (requires ≥90cm)
- **Use**: Demonstrate spacing requirements

See **[DEMO_GUIDE_HE.md](./DEMO_GUIDE_HE.md)** for detailed presentation scenarios.

## 🔧 Development

### Project Structure
```
aga/
├── src/
│   ├── api/          # FastAPI routes and endpoints
│   ├── services/     # Business logic (validation, extraction)
│   ├── azure/        # Azure client wrappers
│   ├── models/       # Pydantic data models
│   └── utils/        # Helper functions
├── frontend/
│   └── src/
│       ├── App.tsx   # Main React component
│       └── types.ts  # TypeScript interfaces
├── test_data/        # Demo architectural plans
├── requirements-mamad.md   # 20 validation rules (Hebrew)
└── docs/             # Additional documentation

### Running Tests

```bash
# Backend tests
pytest tests/

# Frontend tests
cd frontend && npm test
```

### API Health Check

```bash
curl http://localhost:8000/health
```

**Response**:
```json
{
  "status": "healthy",
  "services": {
    "openai": true,
    "blob_storage": true,
    "cosmos_db": true
  }
}
```

## 🎨 Screenshots

### Upload Interface
![Upload](docs/screenshots/upload.png)
Hebrew UI with drag-and-drop support

### Analysis in Progress
![Loading](docs/screenshots/loading.png)
GPT-5.1 reasoning with estimated time

### Results Dashboard
![Results](docs/screenshots/results.png)
Detailed validation results with Hebrew explanations

## 📈 Performance

- **GPT-5.1 Analysis Time**: 30-90 seconds (reasoning model is slower but more accurate)
- **Confidence Score**: 70-90% for high-quality plans with clear annotations
- **Supported Formats**: 
  - **Images**: PNG, JPG, JPEG
  - **Documents**: PDF
- **Recommended Resolution**: 1200x800+ pixels
- **Max File Size**: 10MB

## 🛠️ Troubleshooting

### "Azure CLI credentials not available"
```bash
az login
az account set --subscription <your-subscription-id>
```

### "Permission denied" on Azure resources
Verify RBAC roles are assigned:
```bash
az role assignment list --assignee $(az account show --query user.name -o tsv)
```

### Low confidence scores
- Upload higher resolution images
- Add clear measurement annotations
- Include Hebrew labels on the plan
- Ensure text is readable (not blurry)

### GPT-5.1 timeout
Normal for complex plans. Wait up to 90 seconds.

## 🤝 Contributing

This is a demo project. For production use:
1. Add comprehensive error handling
2. Implement retry logic for Azure services
3. Add monitoring with Application Insights
4. Set up CI/CD pipeline
5. Add unit and integration tests
6. Implement caching for requirements parsing

## 📝 License

MIT License - See [LICENSE](LICENSE) file

## 🙏 Acknowledgments

- Israeli Home Front Command for requirements specification
- Azure OpenAI team for GPT-5.1 reasoning model
- FastAPI and React communities

## 📧 Contact

For questions or feedback about this demo:
- Open an issue on GitHub
- Review the documentation in `DEMO_GUIDE_HE.md`

---

**🎉 Built with Azure OpenAI GPT-5.1 | FastAPI | React | TypeScript**

2. **Build and run with Docker**
   ```bash
   docker-compose up --build
   ```

3. **Access API**
   - API: http://localhost:8000
   - Docs: http://localhost:8000/docs
   - Health: http://localhost:8000/health

## Project Structure

```
aga/
├── src/                    # Application source code
│   ├── api/               # FastAPI routes and endpoints
│   ├── services/          # Business logic services
│   ├── models/            # Data models and schemas
│   ├── azure/             # Azure client wrappers
│   └── utils/             # Utility functions
├── docs/                  # Documentation
│   ├── project-status.md  # Development progress tracking
│   └── architecture.md    # Technical architecture
├── scripts/               # Utility scripts
├── tests/                 # Unit and integration tests
├── requirements-mamad.md  # ממ"ד validation requirements
├── Dockerfile            # Container definition
├── docker-compose.yml    # Multi-container orchestration
└── requirements.txt      # Python dependencies

```

## API Endpoints

- `POST /api/v1/validate` - Upload and validate architectural plan
- `GET /api/v1/results/{id}` - Retrieve validation results
- `GET /health` - Health check endpoint

## Development

See [docs/project-status.md](docs/project-status.md) for current development status and roadmap.

See [.github/copilot-instructions.md](.github/copilot-instructions.md) for development guidelines.

## License

Proprietary - Internal Use Only

## Contact

For questions or support, please contact the development team.
