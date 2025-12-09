"""Health check endpoints."""
from fastapi import APIRouter

from src.models import HealthResponse
from src.azure import get_openai_client, get_blob_client, get_cosmos_client
from src.utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint for all services.
    
    Returns:
        HealthResponse with status of all Azure services
    """
    logger.info("Performing health check")
    
    # Check each Azure service
    services_status = {
        "openai": False,
        "blob_storage": False,
        "cosmos_db": False,
    }
    
    try:
        openai_client = get_openai_client()
        services_status["openai"] = await openai_client.health_check()
    except Exception as e:
        logger.error("OpenAI health check error", error=str(e))
    
    try:
        blob_client = get_blob_client()
        services_status["blob_storage"] = await blob_client.health_check()
    except Exception as e:
        logger.error("Blob Storage health check error", error=str(e))
    
    try:
        cosmos_client = get_cosmos_client()
        services_status["cosmos_db"] = await cosmos_client.health_check()
    except Exception as e:
        logger.error("Cosmos DB health check error", error=str(e))
    
    # Determine overall status
    all_healthy = all(services_status.values())
    status = "healthy" if all_healthy else "degraded"
    
    logger.info("Health check completed", status=status, services=services_status)
    
    return HealthResponse(
        status=status,
        services=services_status
    )
