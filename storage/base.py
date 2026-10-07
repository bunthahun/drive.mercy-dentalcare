"""
Abstract Base Class for all Cloud Storage Backends.
Enforces standard interfaces across all providers (Telegram, Cloudflare R2/S3, Local, etc.)
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Tuple, Optional, Callable

class BaseStorageBackend(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Unique identifier name for this provider: e.g. 'telegram', 's3', 'local'."""
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """User-friendly display title: e.g. 'Telegram Cloud (1000TB)', 'Cloudflare R2 (10GB Ultra Fast)'."""
        pass

    @abstractmethod
    def is_configured(self) -> bool:
        """Returns True if required credentials / settings are present."""
        pass

    @abstractmethod
    def test_connection(self) -> Tuple[bool, str]:
        """Validates connection and returns (is_ok, message)."""
        pass

    @abstractmethod
    def upload_chunk(
        self,
        chunk_data: bytes,
        chunk_name: str,
        caption: str = "",
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> Dict[str, Any]:
        """
        Uploads a single chunk of bytes.
        Returns metadata dictionary containing at minimum:
        {
            "file_id": str,
            "file_unique_id": str,
            "file_size": int,
            "message_id": int
        }
        """
        pass

    @abstractmethod
    def download_chunk(
        self,
        file_id: str,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> bytes:
        """Downloads chunk bytes by file_id."""
        pass

    @abstractmethod
    def delete_chunk(self, file_id: str, message_id: int = 0) -> bool:
        """Deletes a chunk from cloud storage if supported."""
        pass
