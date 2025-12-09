# אפליקציית ולידציה לתוכניות ממ"ד (Mamad Validation App)

FastAPI-based application for validating Israeli Home Front Command shelter (ממ"ד) architectural plans using Azure OpenAI GPT-4 Vision.

## Overview

This application automatically validates architectural plans for protected spaces (מרחב מוגן דירתי - ממ"ד) against official Israeli Home Front Command requirements. It extracts measurements and specifications from uploaded plans and checks compliance with all regulatory criteria.

## Architecture

- **Backend**: FastAPI (Python 3.11+)
- **AI**: Azure OpenAI GPT-5.1 (reasoning model with vision)
- **Storage**: Azure Blob Storage (plan files)
- **Database**: Azure Cosmos DB (validation results, rules)
- **Authentication**: Azure Entra ID (Managed Identity, no secrets)
- **Deployment**: Docker container

## Features

- ✅ Upload architectural plans (PDF, DWG, images)
- ✅ AI-powered extraction of measurements and specifications
- ✅ Comprehensive validation against all ממ"ד requirements
- ✅ Visual annotations highlighting compliance issues
- ✅ Detailed validation reports with regulation references
- ✅ RESTful API for integration
- ✅ No secrets management - Azure Entra ID authentication

## Prerequisites

- Docker & Docker Compose
- Azure subscription with:
  - Azure OpenAI Service (GPT-5.1 deployment)
  - Azure Cosmos DB account
  - Azure Blob Storage account
  - Managed Identity or Service Principal with appropriate RBAC roles

### Required Azure RBAC Roles

- **Cognitive Services OpenAI User** - for Azure OpenAI
- **Storage Blob Data Contributor** - for Blob Storage
- **Cosmos DB Account Contributor** - for Cosmos DB

## Quick Start

1. **Clone and configure**
   ```bash
   git clone <repo-url>
   cd aga
   cp .env.template .env
   # Edit .env with your Azure resource endpoints
   ```

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
