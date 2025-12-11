"""FastAPI application entry point."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings
from src.utils.logging import setup_logging, get_logger
from src.api.routes import health, validation, decomposition

# Setup logging before anything else
setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    logger.info("Starting application", environment=settings.environment)
    yield
    logger.info("Shutting down application")


# Create FastAPI application
app = FastAPI(
    title="Mamad Validation API",
    description="API for validating Israeli Home Front Command shelter (ממד) architectural plans",
    version=settings.api_version,
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if not settings.is_production else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, tags=["Health"])
app.include_router(
    validation.router, 
    prefix=f"/api/{settings.api_version}",
    tags=["Validation"]
)
app.include_router(
    decomposition.router,
    prefix=f"/api/{settings.api_version}",
    tags=["Decomposition"]
)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "Mamad Validation API",
        "version": settings.api_version,
        "environment": settings.environment,
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=not settings.is_production,
        log_level=settings.log_level.lower(),
    )
