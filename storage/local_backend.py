"""
Local simulated Cloud storage backend for offline mode or initial testing.
"""
import os
import uuid
from pathlib import Path
from typing import Dict, Any, Tuple, Optional, Callable
from config import DATA_DIR
from storage.base import BaseStorageBackend

LOCAL_STORAGE_DIR = DATA_DIR / "local_cloud"
LOCAL_STORAGE_DIR.mkdir(exist_ok=True)

class LocalBackend(BaseStorageBackend):
    @property
    def provider_name(self) -> str:
        return "local"

    @property
    def display_name(self) -> str:
        return "Local Storage Node"

    def __init__(self):
        self.storage_dir = LOCAL_STORAGE_DIR

    def is_configured(self) -> bool:
        return True

    def test_connection(self) -> Tuple[bool, str]:
        return True, "Local Cloud Storage Ready"

    def upload_chunk(
        self,
        chunk_data: bytes,
        chunk_name: str,
        caption: str = "",
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> Dict[str, Any]:
        file_id = f"local_{uuid.uuid4().hex}"
        target_path = self.storage_dir / file_id
        with open(target_path, "wb") as f:
            f.write(chunk_data)
            
        if progress_callback:
            progress_callback(len(chunk_data), len(chunk_data))
            
        return {
            "file_id": file_id,
            "file_unique_id": file_id,
            "file_size": len(chunk_data),
            "message_id": 0
        }

    def download_chunk(
        self,
        file_id: str,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> bytes:
        target_path = self.storage_dir / file_id
        if not target_path.exists():
            raise FileNotFoundError(f"Local chunk not found: {file_id}")
        with open(target_path, "rb") as f:
            data = f.read()
        if progress_callback:
            progress_callback(len(data), len(data))
        return data

    def delete_message(self, message_id: int) -> bool:
        return True

    def delete_chunk(self, file_id: str, message_id: int = 0) -> bool:
        try:
            target_path = self.storage_dir / file_id
            if target_path.exists():
                target_path.unlink()
            return True
        except Exception:
            return False
