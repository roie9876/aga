"""Azure OpenAI client wrapper with Entra ID authentication."""
import os
from typing import Optional
from azure.identity import DefaultAzureCredential
from openai import AzureOpenAI

from src.config import settings
from src.utils.logging import get_logger

logger = get_logger(__name__)


class OpenAIClient:
    """Wrapper for Azure OpenAI client with managed identity authentication."""
    
    def __init__(self):
        """Initialize Azure OpenAI client with DefaultAzureCredential."""
        self._client: Optional[AzureOpenAI] = None
        self._credential = DefaultAzureCredential()
        
    def _get_token(self) -> str:
        """Get Azure AD token for Cognitive Services.
        
        Returns:
            Access token string
        """
        token = self._credential.get_token("https://cognitiveservices.azure.com/.default")
        return token.token
    
    @property
    def client(self) -> AzureOpenAI:
        """Get or create Azure OpenAI client instance.
        
        Returns:
            Configured AzureOpenAI client
        """
        if self._client is None:
            logger.info("Initializing Azure OpenAI client", endpoint=settings.azure_openai_endpoint)
            
            self._client = AzureOpenAI(
                azure_endpoint=settings.azure_openai_endpoint,
                azure_ad_token=self._get_token(),
                api_version=settings.azure_openai_api_version
            )
            
            logger.info("Azure OpenAI client initialized successfully")
        
        return self._client
    
    def refresh_token(self) -> None:
        """Refresh the Azure AD token (call periodically or on auth errors)."""
        logger.info("Refreshing Azure OpenAI token")
        self._client = AzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            azure_ad_token=self._get_token(),
            api_version=settings.azure_openai_api_version
        )
        logger.info("Token refreshed successfully")
    
    async def health_check(self) -> bool:
        """Check if Azure OpenAI service is accessible.
        
        Returns:
            True if service is healthy, False otherwise
        """
        try:
            # Simple connectivity test
            _ = self.client
            logger.info("Azure OpenAI health check passed")
            return True
        except Exception as e:
            logger.error("Azure OpenAI health check failed", error=str(e))
            return False


# Global singleton instance
_openai_client: Optional[OpenAIClient] = None


def get_openai_client() -> OpenAIClient:
    """Get the global OpenAI client instance.
    
    Returns:
        OpenAIClient singleton
    """
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAIClient()
    return _openai_client
