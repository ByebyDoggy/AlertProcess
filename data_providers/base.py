"""
DataProvider architecture for on-demand data fetching
Allows users to configure how additional data is loaded for rule evaluation
"""
from abc import ABC, abstractmethod
from typing import Any, Optional
from models import AlertInput, TransactionContext, DataFetchResult
from datetime import datetime
import time


class DataProvider(ABC):
    """
    Base class for data providers
    
    DataProviders are responsible for fetching additional data needed
    for rule evaluation. Each provider can fetch specific types of data
    and handles its own caching and error handling.
    
    Users can implement their own DataProviders and register them
    to support custom data fetching strategies.
    """
    
    def __init__(self):
        self._cache: dict[str, tuple[Any, datetime]] = {}
        self._cache_ttl_seconds: int = 300  # 5 minutes default TTL
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique provider name"""
        pass
    
    @property
    def description(self) -> str:
        """Human-readable description"""
        return ""
    
    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        """Get JSON schema for provider configuration"""
        return {}
    
    async def fetch(
        self, 
        alert: AlertInput, 
        context: TransactionContext,
        params: dict[str, Any]
    ) -> DataFetchResult:
        """
        Fetch data based on alert, context and parameters
        
        Args:
            alert: The alert input
            context: The transaction context
            params: Parameters for this fetch operation (user-configured)
            
        Returns:
            DataFetchResult containing the fetched data or error
        """
        start_time = time.time()
        cache_key = self._make_cache_key(alert, context, params)
        
        # Check cache
        cached = self._get_from_cache(cache_key)
        if cached is not None:
            return DataFetchResult(
                provider_name=self.name,
                data=cached,
                cached=True,
                fetch_time_ms=(time.time() - start_time) * 1000
            )
        
        try:
            data = await self._fetch(alert, context, params)
            self._set_cache(cache_key, data)
            return DataFetchResult(
                provider_name=self.name,
                data=data,
                cached=False,
                fetch_time_ms=(time.time() - start_time) * 1000
            )
        except Exception as e:
            return DataFetchResult(
                provider_name=self.name,
                data=None,
                error=str(e),
                fetch_time_ms=(time.time() - start_time) * 1000
            )
    
    @abstractmethod
    async def _fetch(
        self, 
        alert: AlertInput, 
        context: TransactionContext,
        params: dict[str, Any]
    ) -> Any:
        """
        Internal fetch implementation to be overridden by subclasses
        """
        pass
    
    def _make_cache_key(
        self, 
        alert: AlertInput, 
        context: TransactionContext,
        params: dict[str, Any]
    ) -> str:
        """Generate cache key"""
        return f"{self.name}:{alert.chain_id}:{alert.tx_hash}:{hash(frozenset(params.items()))}"
    
    def _get_from_cache(self, key: str) -> Any | None:
        """Get value from cache if not expired"""
        if key in self._cache:
            data, timestamp = self._cache[key]
            age = (datetime.now() - timestamp).total_seconds()
            if age < self._cache_ttl_seconds:
                return data
            del self._cache[key]
        return None
    
    def _set_cache(self, key: str, data: Any):
        """Set cache value"""
        self._cache[key] = (data, datetime.now())
    
    def clear_cache(self):
        """Clear all cached data"""
        self._cache.clear()


class Web3DataProvider(DataProvider):
    """
    Built-in DataProvider for fetching on-chain data via web3
    """
    
    def __init__(self, chain_id_to_provider_url: dict[int, str] | None = None):
        super().__init__()
        self._chain_id_to_provider_url = chain_id_to_provider_url or {}
        self._web3_instances: dict[int, Any] = {}
    
    @property
    def name(self) -> str:
        return "web3"
    
    @property
    def description(self) -> str:
        return "Fetches on-chain transaction data via web3"
    
    def get_web3(self, chain_id: int):
        """Get or create web3 instance for chain"""
        if chain_id not in self._web3_instances:
            try:
                from web3 import Web3
                provider_url = self._chain_id_to_provider_url.get(chain_id)
                if provider_url:
                    self._web3_instances[chain_id] = Web3(Web3.HTTPProvider(provider_url))
                else:
                    return None
            except ImportError:
                return None
        return self._web3_instances.get(chain_id)
    
    async def _fetch(
        self, 
        alert: AlertInput, 
        context: TransactionContext,
        params: dict[str, Any]
    ) -> Any:
        """Fetch transaction receipt data"""
        web3 = self.get_web3(alert.chain_id)
        if not web3:
            raise ValueError(f"No web3 provider configured for chain {alert.chain_id}")
        
        data_type = params.get("type", "transaction")
        
        if data_type == "transaction":
            return web3.eth.get_transaction(alert.tx_hash)
        elif data_type == "receipt":
            return web3.eth.get_transaction_receipt(alert.tx_hash)
        elif data_type == "block":
            tx = await self._sync_get_transaction(web3, alert.tx_hash)
            if tx:
                return web3.eth.get_block(tx.blockNumber)
        elif data_type == "receipt_with_logs":
            receipt = await self._sync_get_transaction_receipt(web3, alert.tx_hash)
            return receipt
        
        return None
    
    async def _sync_get_transaction(self, web3, tx_hash: str):
        """Synchronously get transaction"""
        return web3.eth.get_transaction(tx_hash)
    
    async def _sync_get_transaction_receipt(self, web3, tx_hash: str):
        """Synchronously get transaction receipt"""
        return web3.eth.get_transaction_receipt(tx_hash)


class DataProviderRegistry:
    """
    Registry for managing data providers
    """
    
    _providers: dict[str, DataProvider] = {}
    
    @classmethod
    def register(cls, provider: DataProvider):
        """Register a data provider instance"""
        cls._providers[provider.name] = provider
        return provider
    
    @classmethod
    def get(cls, name: str) -> DataProvider | None:
        """Get provider by name"""
        return cls._providers.get(name)
    
    @classmethod
    def list_providers(cls) -> list[str]:
        """List all registered provider names"""
        return list(cls._providers.keys())
    
    @classmethod
    async def fetch(
        cls, 
        provider_name: str,
        alert: AlertInput, 
        context: TransactionContext,
        params: dict[str, Any]
    ) -> DataFetchResult | None:
        """Fetch data using specified provider"""
        provider = cls.get(provider_name)
        if not provider:
            return DataFetchResult(
                provider_name=provider_name,
                data=None,
                error=f"Provider '{provider_name}' not found"
            )
        return await provider.fetch(alert, context, params)
