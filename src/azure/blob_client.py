"""Azure Blob Storage client wrapper with Entra ID authentication."""
from typing import Optional, BinaryIO
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, BlobClient
from azure.core.exceptions import ResourceNotFoundError, AzureError

from src.config import settings
from src.utils.logging import get_logger

logger = get_logger(__name__)


class BlobStorageClient:
    """Wrapper for Azure Blob Storage client with managed identity authentication."""
    
    def __init__(self):
        """Initialize Blob Storage client with DefaultAzureCredential."""
        self._credential = DefaultAzureCredential()
        self._blob_service_client: Optional[BlobServiceClient] = None
    
    @property
    def client(self) -> BlobServiceClient:
        """Get or create Blob Service client instance.
        
        Returns:
            Configured BlobServiceClient
        """
        if self._blob_service_client is None:
            logger.info("Initializing Azure Blob Storage client", 
                       account_url=settings.storage_account_url)
            
            self._blob_service_client = BlobServiceClient(
                account_url=settings.storage_account_url,
                credential=self._credential
            )
            
            logger.info("Azure Blob Storage client initialized successfully")
        
        return self._blob_service_client
    
    async def upload_blob(
        self, 
        blob_name: str, 
        data: BinaryIO,
        container_name: Optional[str] = None,
        overwrite: bool = True
    ) -> str:
        """Upload a blob to Azure Storage.
        
        Args:
            blob_name: Name for the blob
            data: Binary data to upload
            container_name: Container name (default: from settings)
            overwrite: Whether to overwrite existing blob
            
        Returns:
            URL of the uploaded blob
            
        Raises:
            AzureError: If upload fails
        """
        container = container_name or settings.azure_storage_container_name
        
        try:
            logger.info("Uploading blob", blob_name=blob_name, container=container)
            
            blob_client = self.client.get_blob_client(
                container=container,
                blob=blob_name
            )
            
            blob_client.upload_blob(data, overwrite=overwrite)
            
            blob_url = blob_client.url
            logger.info("Blob uploaded successfully", blob_url=blob_url)
            
            return blob_url
            
        except AzureError as e:
            logger.error("Failed to upload blob", error=str(e), blob_name=blob_name)
            raise
    
    async def download_blob(
        self, 
        blob_name: str,
        container_name: Optional[str] = None
    ) -> bytes:
        """Download a blob from Azure Storage.
        
        Args:
            blob_name: Name of the blob to download
            container_name: Container name (default: from settings)
            
        Returns:
            Blob content as bytes
            
        Raises:
            ResourceNotFoundError: If blob doesn't exist
            AzureError: If download fails
        """
        container = container_name or settings.azure_storage_container_name
        
        try:
            logger.info("Downloading blob", blob_name=blob_name, container=container)
            
            blob_client = self.client.get_blob_client(
                container=container,
                blob=blob_name
            )
            
            blob_data = blob_client.download_blob().readall()
            
            logger.info("Blob downloaded successfully", blob_name=blob_name, 
                       size_bytes=len(blob_data))
            
            return blob_data
            
        except ResourceNotFoundError:
            logger.error("Blob not found", blob_name=blob_name)
            raise
        except AzureError as e:
            logger.error("Failed to download blob", error=str(e), blob_name=blob_name)
            raise
    
    async def delete_blob(
        self, 
        blob_name: str,
        container_name: Optional[str] = None
    ) -> bool:
        """Delete a blob from Azure Storage.
        
        Args:
            blob_name: Name of the blob to delete
            container_name: Container name (default: from settings)
            
        Returns:
            True if deleted, False if not found
        """
        container = container_name or settings.azure_storage_container_name
        
        try:
            logger.info("Deleting blob", blob_name=blob_name, container=container)
            
            blob_client = self.client.get_blob_client(
                container=container,
                blob=blob_name
            )
            
            blob_client.delete_blob()
            
            logger.info("Blob deleted successfully", blob_name=blob_name)
            return True
            
        except ResourceNotFoundError:
            logger.warning("Blob not found for deletion", blob_name=blob_name)
            return False
        except AzureError as e:
            logger.error("Failed to delete blob", error=str(e), blob_name=blob_name)
            raise
    
    async def health_check(self) -> bool:
        """Check if Blob Storage service is accessible.
        
        Returns:
            True if service is healthy, False otherwise
        """
        try:
            # Try to list containers (minimal operation)
            container_list = self.client.list_containers()
            next(iter(container_list), None)  # Get first container or None
            logger.info("Azure Blob Storage health check passed")
            return True
        except Exception as e:
            logger.error("Azure Blob Storage health check failed", error=str(e))
            return False


# Global singleton instance
_blob_client: Optional[BlobStorageClient] = None


def get_blob_client() -> BlobStorageClient:
    """Get the global Blob Storage client instance.
    
    Returns:
        BlobStorageClient singleton
    """
    global _blob_client
    if _blob_client is None:
        _blob_client = BlobStorageClient()
    return _blob_client
