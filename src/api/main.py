"""FastAPI application entry point."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from src.config import settings
from src.utils.logging import setup_logging, get_logger
from src.utils.llm_usage import start_request_llm_usage, end_request_llm_usage, get_llm_usage_snapshot
from src.api.routes import health, validation, decomposition, segment_validation, requirements, preflight

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


@app.middleware("http")
async def llm_usage_middleware(request, call_next):
    """Track Azure OpenAI token usage per request (internal only)."""

    token = start_request_llm_usage()
    try:
        response = await call_next(request)
    except Exception:
        end_request_llm_usage(token)
        raise

    # Streaming responses may keep executing after middleware returns.
    # Wrap the body iterator so we only reset the context after streaming completes.
    if isinstance(response, StreamingResponse):
        original_iterator = response.body_iterator

        async def wrapped_iterator():
            try:
                async for chunk in original_iterator:
                    yield chunk
            finally:
                if getattr(settings, "log_llm_usage", False):
                    try:
                        logger.info(
                            "LLM usage (request complete)",
                            method=getattr(request, "method", None),
                            path=str(getattr(request, "url", "")),
                            llm_usage=get_llm_usage_snapshot(
                                include_calls=bool(getattr(settings, "log_llm_usage_include_calls", False))
                            ),
                        )
                    except Exception:
                        pass
                end_request_llm_usage(token)

        response.body_iterator = wrapped_iterator()
        return response

    if getattr(settings, "log_llm_usage", False):
        try:
            logger.info(
                "LLM usage (request complete)",
                method=getattr(request, "method", None),
                path=str(getattr(request, "url", "")),
                llm_usage=get_llm_usage_snapshot(
                    include_calls=bool(getattr(settings, "log_llm_usage_include_calls", False))
                ),
            )
        except Exception:
            pass

    end_request_llm_usage(token)
    return response

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
app.include_router(
    segment_validation.router,
    prefix=f"/api/{settings.api_version}/segments",
    tags=["Segment Validation"]
)
app.include_router(
    requirements.router,
    prefix=f"/api/{settings.api_version}",
    tags=["Requirements"]
)
app.include_router(
    preflight.router,
    prefix=f"/api/{settings.api_version}",
    tags=["Preflight"],
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
