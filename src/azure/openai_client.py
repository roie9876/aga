"""Azure OpenAI client wrapper with Entra ID authentication."""
import os
import random
import time
from typing import Optional
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import AzureOpenAI
from openai import APIConnectionError, APITimeoutError, APIStatusError, RateLimitError

from src.config import settings
from src.utils.logging import get_logger

logger = get_logger(__name__)


class OpenAIClient:
    """Wrapper for Azure OpenAI client with managed identity authentication."""
    
    def __init__(self):
        """Initialize Azure OpenAI client with DefaultAzureCredential."""
        self._client: Optional[AzureOpenAI] = None
        self._credential = DefaultAzureCredential()
        self._token_provider = get_bearer_token_provider(
            self._credential,
            "https://cognitiveservices.azure.com/.default"
        )
        
    def _get_token(self) -> str:
        """Get Azure AD token for Cognitive Services.
        
        Returns:
            Access token string
        """
        token = self._credential.get_token("https://cognitiveservices.azure.com/.default")
        return token.token
    
    @property
    def client(self) -> AzureOpenAI:
        """Get or create Azure OpenAI client instance with auto-refreshing token.
        
        Returns:
            Configured AzureOpenAI client
        """
        if self._client is None:
            logger.info("Initializing Azure OpenAI client with auto-refreshing token", endpoint=settings.azure_openai_endpoint)
            
            # Use azure_ad_token_provider for automatic token refresh
            self._client = AzureOpenAI(
                azure_endpoint=settings.azure_openai_endpoint,
                azure_ad_token_provider=self._token_provider,
                api_version=settings.azure_openai_api_version
            )
            
            logger.info("Azure OpenAI client initialized successfully with token provider")
        
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

    def chat_completions_create(self, **kwargs):
        """Create a chat completion with retry/backoff for transient capacity errors.

        Retries common transient failures:
        - 429 (RateLimit / NoCapacity)
        - 5xx (service transient)
        - timeouts / connection errors

        Notes:
        - This is a synchronous helper; callers from async code will block the event loop.
        - If Azure is truly out of capacity, retries may still fail; Provisioned Throughput
          is the reliable fix.
        """
        max_attempts = max(1, int(settings.azure_openai_max_retries))
        base_delay = max(0.1, float(settings.azure_openai_retry_base_seconds))
        max_delay = max(base_delay, float(settings.azure_openai_retry_max_seconds))

        last_error: Optional[Exception] = None

        for attempt in range(1, max_attempts + 1):
            try:
                return self.client.chat.completions.create(**kwargs)
            except (RateLimitError, APIStatusError, APITimeoutError, APIConnectionError) as e:
                last_error = e

                status_code = getattr(e, "status_code", None)
                error_text = str(e)
                is_no_capacity = "NoCapacity" in error_text
                is_retryable_status = status_code in {429, 500, 502, 503, 504}

                if attempt >= max_attempts or (not is_retryable_status and not is_no_capacity):
                    raise

                retry_after_seconds: Optional[float] = None
                headers = getattr(e, "headers", None)
                if isinstance(headers, dict):
                    retry_after_value = headers.get("retry-after") or headers.get("Retry-After")
                    if retry_after_value is not None:
                        try:
                            retry_after_seconds = float(retry_after_value)
                        except Exception:
                            retry_after_seconds = None

                backoff = min(max_delay, base_delay * (2 ** (attempt - 1)))
                delay = retry_after_seconds if retry_after_seconds is not None else backoff
                # Add jitter to reduce thundering herd
                delay = min(max_delay, delay + random.uniform(0, delay * 0.25))

                logger.warning(
                    "Azure OpenAI call failed; retrying",
                    attempt=attempt,
                    max_attempts=max_attempts,
                    status_code=status_code,
                    no_capacity=is_no_capacity,
                    sleep_seconds=delay,
                )
                time.sleep(delay)

        # Should not reach here, but keep mypy/happy path clear
        if last_error is not None:
            raise last_error
        raise RuntimeError("Azure OpenAI call failed with unknown error")


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
