"""Configuration management for the application."""
import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

# Get project root directory
PROJECT_ROOT = Path(__file__).parent.parent


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # Application
    environment: str = "development"
    log_level: str = "INFO"
    api_version: str = "v1"
    
    # Azure OpenAI
    azure_openai_endpoint: str
    azure_openai_deployment_name: str = "gpt-5.1"
    azure_openai_api_version: str = "2024-12-01-preview"
    
    # Azure Cosmos DB
    azure_cosmosdb_endpoint: str
    azure_cosmosdb_database_name: str = "mamad-validation"
    azure_cosmosdb_container_name: str = "validation-results"
    
    # Azure Blob Storage
    azure_storage_account_name: str
    azure_storage_container_name: str = "architectural-plans"
    
    # Optional Azure Identity
    azure_tenant_id: Optional[str] = None
    azure_client_id: Optional[str] = None
    
    @property
    def storage_account_url(self) -> str:
        """Get the full Blob Storage account URL."""
        return f"https://{self.azure_storage_account_name}.blob.core.windows.net"
    
    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment.lower() == "production"


# Global settings instance
settings = Settings()
