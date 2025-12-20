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

    # Azure OpenAI reliability
    azure_openai_max_retries: int = 6
    azure_openai_retry_base_seconds: float = 1.0
    azure_openai_retry_max_seconds: float = 30.0

    # Performance / parallelism controls
    # These are conservative defaults intended to improve throughput without
    # increasing the risk of 429/NoCapacity or missing context.
    validation_max_concurrent_llm_requests: int = 4
    validation_max_concurrent_downloads: int = 12
    segment_image_cache_max_items: int = 32
    
    # Azure Cosmos DB
    azure_cosmosdb_endpoint: str
    azure_cosmosdb_database_name: str = "mamad-validation"
    azure_cosmosdb_container_name: str = "validation-results"
    
    # Azure Blob Storage
    azure_storage_account_name: str
    azure_storage_container_name: str = "architectural-plans"

    # Decomposition tuning
    decomposition_merge_enabled: bool = False
    decomposition_merge_margin_ratio: float = 0.02

    # Decomposition post-processing (helps keep only the "top-level" drawings)
    decomposition_filter_nested_frames_enabled: bool = True
    decomposition_nested_containment_threshold: float = 0.90
    decomposition_min_box_area_ratio: float = 0.005

    # OCR (best-effort, for scanned/bitmap-heavy documents)
    ocr_enabled: bool = True
    ocr_tesseract_cmd: str = "tesseract"
    ocr_languages: str = "heb+eng"
    ocr_psm: int = 6
    ocr_oem: int = 1

    # Preflight LLM settings (signature detection)
    preflight_llm_signature_max_segments: int = 4
    preflight_llm_signature_concurrency: int = 4
    preflight_llm_area_table_max_segments: int = 4
    preflight_llm_area_table_concurrency: int = 4
    preflight_llm_check_max_segments: int = 4
    preflight_llm_check_concurrency: int = 4

    # Segment analysis streaming (preflight auto-analysis UX)
    segment_analysis_concurrency: int = 4
    segment_analysis_timeout_seconds: int = 300

    # DWF tiling (local export troubleshooting)
    full_plan_local_export_dir: Optional[str] = None
    dwf_tiling_enabled: bool = False
    dwf_tile_size: int = 3000
    dwf_tile_overlap: int = 100
    dwf_tile_crop_enabled: bool = True
    dwf_tile_crop_threshold: int = 250

    # PDF high-res cropping (manual ROI quality)
    pdf_crop_render_dpi: int = 600
    pdf_crop_max_pixels: int = 120_000_000
    
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
