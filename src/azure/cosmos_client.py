"""Azure Cosmos DB client wrapper with Entra ID authentication."""
from typing import Optional, Any, Dict, List
from azure.identity import DefaultAzureCredential
from azure.cosmos import CosmosClient, DatabaseProxy, ContainerProxy
from azure.cosmos.exceptions import CosmosResourceNotFoundError, CosmosHttpResponseError

from src.config import settings
from src.utils.logging import get_logger

logger = get_logger(__name__)


class CosmosDBClient:
    """Wrapper for Azure Cosmos DB client with managed identity authentication."""
    
    def __init__(self):
        """Initialize Cosmos DB client with DefaultAzureCredential."""
        self._credential = DefaultAzureCredential()
        self._cosmos_client: Optional[CosmosClient] = None
        self._database: Optional[DatabaseProxy] = None
        self._container: Optional[ContainerProxy] = None
    
    @property
    def client(self) -> CosmosClient:
        """Get or create Cosmos client instance.
        
        Returns:
            Configured CosmosClient
        """
        if self._cosmos_client is None:
            logger.info("Initializing Azure Cosmos DB client", 
                       endpoint=settings.azure_cosmosdb_endpoint)
            
            self._cosmos_client = CosmosClient(
                url=settings.azure_cosmosdb_endpoint,
                credential=self._credential
            )
            
            logger.info("Azure Cosmos DB client initialized successfully")
        
        return self._cosmos_client
    
    @property
    def database(self) -> DatabaseProxy:
        """Get database instance, creating if necessary.
        
        Returns:
            DatabaseProxy instance
        """
        if self._database is None:
            logger.info("Getting database", database=settings.azure_cosmosdb_database_name)
            self._database = self.client.get_database_client(
                settings.azure_cosmosdb_database_name
            )
        
        return self._database
    
    @property
    def container(self) -> ContainerProxy:
        """Get container instance.
        
        Returns:
            ContainerProxy instance
        """
        if self._container is None:
            logger.info("Getting container", container=settings.azure_cosmosdb_container_name)
            self._container = self.database.get_container_client(
                settings.azure_cosmosdb_container_name
            )
        
        return self._container
    
    async def create_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Create an item in Cosmos DB.
        
        Args:
            item: Item data to create (must include 'id' field)
            
        Returns:
            Created item with metadata
            
        Raises:
            CosmosHttpResponseError: If creation fails
        """
        try:
            logger.info("Creating item in Cosmos DB", item_id=item.get('id'))
            
            created_item = self.container.create_item(body=item)
            
            logger.info("Item created successfully", item_id=created_item['id'])
            return created_item
            
        except CosmosHttpResponseError as e:
            logger.error("Failed to create item", error=str(e), item_id=item.get('id'))
            raise
    
    async def read_item(self, item_id: str, partition_key: str) -> Optional[Dict[str, Any]]:
        """Read an item from Cosmos DB.
        
        Args:
            item_id: ID of the item to read
            partition_key: Partition key value
            
        Returns:
            Item data or None if not found
        """
        try:
            logger.info("Reading item from Cosmos DB", item_id=item_id)
            
            item = self.container.read_item(
                item=item_id,
                partition_key=partition_key
            )
            
            logger.info("Item read successfully", item_id=item_id)
            return item
            
        except CosmosResourceNotFoundError:
            logger.warning("Item not found", item_id=item_id)
            return None
        except CosmosHttpResponseError as e:
            logger.error("Failed to read item", error=str(e), item_id=item_id)
            raise
    
    async def query_items(
        self, 
        query: str, 
        parameters: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """Query items from Cosmos DB.
        
        Args:
            query: SQL query string
            parameters: Query parameters
            
        Returns:
            List of matching items
        """
        try:
            logger.info("Querying items from Cosmos DB", query=query)
            
            items = list(self.container.query_items(
                query=query,
                parameters=parameters,
                enable_cross_partition_query=True
            ))
            
            logger.info("Query completed", result_count=len(items))
            return items
            
        except CosmosHttpResponseError as e:
            logger.error("Failed to query items", error=str(e), query=query)
            raise
    
    async def upsert_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Create or update an item in Cosmos DB.
        
        Args:
            item: Item data (must include 'id' field)
            
        Returns:
            Upserted item with metadata
        """
        try:
            logger.info("Upserting item in Cosmos DB", item_id=item.get('id'))
            
            upserted_item = self.container.upsert_item(body=item)
            
            logger.info("Item upserted successfully", item_id=upserted_item['id'])
            return upserted_item
            
        except CosmosHttpResponseError as e:
            logger.error("Failed to upsert item", error=str(e), item_id=item.get('id'))
            raise
    
    async def delete_item(self, item_id: str, partition_key: str) -> bool:
        """Delete an item from Cosmos DB.
        
        Args:
            item_id: ID of the item to delete
            partition_key: Partition key value
            
        Returns:
            True if deleted, False if not found
        """
        try:
            logger.info("Deleting item from Cosmos DB", item_id=item_id)
            
            self.container.delete_item(
                item=item_id,
                partition_key=partition_key
            )
            
            logger.info("Item deleted successfully", item_id=item_id)
            return True
            
        except CosmosResourceNotFoundError:
            logger.warning("Item not found for deletion", item_id=item_id)
            return False
        except CosmosHttpResponseError as e:
            logger.error("Failed to delete item", error=str(e), item_id=item_id)
            raise
    
    async def health_check(self) -> bool:
        """Check if Cosmos DB service is accessible.
        
        Returns:
            True if service is healthy, False otherwise
        """
        try:
            # Try to read database properties
            _ = self.database.read()
            logger.info("Azure Cosmos DB health check passed")
            return True
        except Exception as e:
            logger.error("Azure Cosmos DB health check failed", error=str(e))
            return False


# Global singleton instance
_cosmos_client: Optional[CosmosDBClient] = None


def get_cosmos_client() -> CosmosDBClient:
    """Get the global Cosmos DB client instance.
    
    Returns:
        CosmosDBClient singleton
    """
    global _cosmos_client
    if _cosmos_client is None:
        _cosmos_client = CosmosDBClient()
    return _cosmos_client
