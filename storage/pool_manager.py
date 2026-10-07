"""
Multi-Cloud Storage Pool Manager (Aggregator).
Aggregates multiple cloud storage providers (Telegram, Cloudflare R2/S3, Local)
into a unified high-performance storage pool.
"""
from typing import Dict, Any, List, Optional, Tuple
from storage.base import BaseStorageBackend
from storage.telegram_backend import TelegramBackend
from storage.s3_backend import S3CompatibleBackend
from storage.local_backend import LocalBackend

class StoragePoolManager:
    def __init__(self, settings: Dict[str, Any]):
        self.settings = settings
        self.backends: Dict[str, BaseStorageBackend] = {}
        self._init_providers()

    def _init_providers(self):
        """Initializes all registered storage backends."""
        self.backends.clear()

        # 1. Local Backend (Always available as fallback & offline)
        self.backends["local"] = LocalBackend()

        # 2. Telegram Cloud (High-capacity archive / bulk storage)
        tg_token = self.settings.get("telegram_bot_token", "").strip()
        tg_chat = str(self.settings.get("telegram_chat_id", "")).strip()
        if tg_token and tg_chat:
            self.backends["telegram"] = TelegramBackend(tg_token, tg_chat)

        # 3. S3 / Cloudflare R2 (Ultra fast tier)
        s3_endpoint = self.settings.get("s3_endpoint_url", "").strip()
        s3_key = self.settings.get("s3_access_key_id", "").strip()
        s3_secret = self.settings.get("s3_secret_access_key", "").strip()
        s3_bucket = self.settings.get("s3_bucket_name", "").strip()
        s3_region = self.settings.get("s3_region", "auto").strip()

        if s3_endpoint and s3_key and s3_secret and s3_bucket:
            self.backends["s3_r2"] = S3CompatibleBackend(
                endpoint_url=s3_endpoint,
                access_key_id=s3_key,
                secret_access_key=s3_secret,
                bucket_name=s3_bucket,
                region=s3_region
            )

    def get_backend(self, provider_name: str) -> BaseStorageBackend:
        """Retrieves backend by name or falls back to local."""
        return self.backends.get(provider_name, self.backends["local"])

    def select_backend_for_upload(self, file_size: int, requested_backend: Optional[str] = None) -> Tuple[str, BaseStorageBackend]:
        """
        Smart Routing for Multi-Cloud Aggregation:
        - If requested_backend is explicitly chosen ('telegram', 's3_r2', 'local'), uses it.
        - If 'auto_pool':
            - Files <= fast_tier_limit (e.g. 50MB) route to ultra-fast S3/R2 (if configured).
            - Large files or if S3 not configured route to Telegram Cloud.
            - Fallback to Local if none configured.
        """
        mode = requested_backend or self.settings.get("backend", "auto_pool")

        # Explicit user selection
        if mode in self.backends and self.backends[mode].is_configured():
            return mode, self.backends[mode]

        # Automatic Pooling logic
        fast_limit_bytes = int(self.settings.get("s3_fast_tier_limit_mb", 50)) * 1024 * 1024

        # 1. Check if S3 / R2 fast tier is available for small/medium files
        if "s3_r2" in self.backends and self.backends["s3_r2"].is_configured():
            if file_size <= fast_limit_bytes:
                return "s3_r2", self.backends["s3_r2"]

        # 2. Check if Telegram backend is ready for large files or default
        if "telegram" in self.backends and self.backends["telegram"].is_configured():
            return "telegram", self.backends["telegram"]

        # 3. If S3 is configured, but file is large and Telegram isn't available, route to S3
        if "s3_r2" in self.backends and self.backends["s3_r2"].is_configured():
            return "s3_r2", self.backends["s3_r2"]

        # Fallback to local
        return "local", self.backends["local"]

    def get_pool_status(self) -> List[Dict[str, Any]]:
        """Returns health and configuration overview of all pooled providers."""
        status_list = []
        for name, backend in self.backends.items():
            status_list.append({
                "provider": name,
                "display_name": backend.display_name,
                "configured": backend.is_configured(),
            })
        return status_list
