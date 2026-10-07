"""
Unified Cloud Storage Engine.
Orchestrates high-speed file chunking, AES-256 encryption, parallel uploads, and downloads.
"""
import os
import math
import hashlib
import mimetypes
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import load_settings
from storage.crypto import derive_key, encrypt_bytes, decrypt_bytes
from storage.telegram_backend import TelegramBackend
from storage.local_backend import LocalBackend
from storage.pool_manager import StoragePoolManager
import database

class StorageEngine:
    def __init__(self):
        self.settings = load_settings()
        self.pool = StoragePoolManager(self.settings)
        self.reload_backend()

    def reload_backend(self):
        self.settings = load_settings()
        self.pool = StoragePoolManager(self.settings)
        # Primary default backend
        backend_type = self.settings.get("backend", "auto_pool")
        if backend_type == "auto_pool":
            _, self.backend = self.pool.select_backend_for_upload(file_size=0)
        else:
            self.backend = self.pool.get_backend(backend_type)
        self.is_telegram = (getattr(self.backend, "provider_name", "") == "telegram")

    def is_cloud_ready(self) -> bool:
        # Ready if either Telegram or S3/R2 is configured
        tg = self.pool.get_backend("telegram")
        s3 = self.pool.get_backend("s3_r2")
        return (tg and tg.is_configured()) or (s3 and s3.is_configured())

    def get_backend_name(self) -> str:
        backend_type = self.settings.get("backend", "auto_pool")
        if backend_type == "auto_pool":
            return "Multi-Cloud Aggregator Pool (Auto ⚡)"
        return getattr(self.backend, "display_name", "Storage Node")

    def upload_file(
        self,
        local_path: str,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        drive_owner: str = "buntha",
        custom_filename: Optional[str] = None,
        folder_id: Optional[int] = None,
        preferred_backend: Optional[str] = None,
        uploader_email: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Uploads a file by splitting into chunks and encrypting with high-speed parallel uploading.
        Single-pass SHA256 checksum and concurrent chunk transmission.
        progress_callback signature: (bytes_done, total_bytes, status_text)
        """
        p = Path(local_path)
        if not p.exists():
            raise FileNotFoundError(f"File not found: {local_path}")

        file_size = p.stat().st_size
        file_name = custom_filename or p.name
        if file_name.startswith("up_"):
            file_name = file_name[3:]
        mime_type, _ = mimetypes.guess_type(file_name)
        mime_type = mime_type or "application/octet-stream"

        # Settings & AES key
        enc_enabled = self.settings.get("encryption_enabled", True)
        enc_pass = self.settings.get("encryption_key", "cloud-storage-1000tb-buntha")
        aes_key = derive_key(enc_pass) if enc_enabled else None

        chunk_size_mb = self.settings.get("chunk_size_mb", 19)
        chunk_size_bytes = chunk_size_mb * 1024 * 1024

        total_chunks = max(1, math.ceil(file_size / chunk_size_bytes))
        chunks_data = []
        hasher = hashlib.sha256()

        if progress_callback:
            progress_callback(0, file_size, "Preparing turbo parallel upload...")

        # Single-pass read: compute SHA-256 and encrypt chunks in memory
        with open(local_path, "rb") as f:
            for part_idx in range(total_chunks):
                raw_chunk = f.read(chunk_size_bytes)
                if not raw_chunk and part_idx > 0:
                    break
                hasher.update(raw_chunk)
                chunk_name = f"{file_name}.part{part_idx}" if total_chunks > 1 else file_name
                chunk_to_upload = encrypt_bytes(raw_chunk, aes_key) if (enc_enabled and aes_key) else raw_chunk
                chunks_data.append((part_idx, chunk_name, chunk_to_upload, len(raw_chunk)))

        sha256_hash = hasher.hexdigest()
        actual_chunks_count = len(chunks_data)
        chunks_info: List[Optional[Dict[str, Any]]] = [None] * actual_chunks_count

        # Smart Routing across pooled backends
        provider_name, target_backend = self.pool.select_backend_for_upload(file_size, preferred_backend)

        def upload_single_chunk(item):
            part_idx, c_name, c_data, raw_sz = item
            caption = f"📦 {file_name} [Part {part_idx + 1}/{actual_chunks_count}]"
            res = target_backend.upload_chunk(
                chunk_data=c_data,
                chunk_name=c_name,
                caption=caption
            )
            return {
                "part": part_idx,
                "file_id": res["file_id"],
                "size": res["file_size"],
                "raw_size": raw_sz,
                "message_id": res.get("message_id", 0)
            }

        # Multi-threaded concurrent chunk uploading
        max_workers = min(5, actual_chunks_count)
        if max_workers <= 1:
            for idx, item in enumerate(chunks_data):
                chunks_info[idx] = upload_single_chunk(item)
                if progress_callback:
                    progress_callback(file_size, file_size, f"Uploaded {file_name}")
        else:
            completed_count = 0
            completed_bytes = 0
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_part = {executor.submit(upload_single_chunk, item): item[0] for item in chunks_data}
                for future in as_completed(future_to_part):
                    part_num = future_to_part[future]
                    result_item = future.result()
                    chunks_info[part_num] = result_item
                    completed_count += 1
                    completed_bytes += result_item["raw_size"]
                    if progress_callback:
                        progress_callback(
                            completed_bytes,
                            file_size,
                            f"Turbo upload {completed_count}/{actual_chunks_count} chunks..."
                        )

        # Store in database with actual cloud_backend used
        file_db_id = database.add_file(
            file_name=file_name,
            file_size=file_size,
            mime_type=mime_type,
            sha256=sha256_hash,
            is_encrypted=enc_enabled,
            cloud_backend=provider_name,
            chunks=chunks_info,
            drive_owner=drive_owner,
            folder_id=folder_id,
            uploader_email=uploader_email
        )

        return {
            "id": file_db_id,
            "file_name": file_name,
            "file_size": file_size,
            "chunks_count": len(chunks_info),
            "sha256": sha256_hash,
            "cloud_backend": provider_name
        }

    def download_file(
        self,
        file_id: int,
        target_path: str,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> str:
        """
        Downloads a file from cloud, decrypts, and writes to target_path using parallel chunk downloads.
        Automatically resolves the appropriate backend (Telegram, S3/R2, Local) stored for this file.
        """
        file_info = database.get_file_by_id(file_id)
        if not file_info:
            raise ValueError(f"File ID {file_id} not found in database.")

        file_size = file_info["file_size"]
        chunks = file_info.get("chunks", [])
        is_encrypted = bool(file_info.get("is_encrypted", 1))
        backend_name = file_info.get("cloud_backend", "telegram")
        active_backend = self.pool.get_backend(backend_name)

        enc_pass = self.settings.get("encryption_key", "cloud-storage-1000tb-buntha")
        aes_key = derive_key(enc_pass) if is_encrypted else None

        # Ensure directory exists
        out_file = Path(target_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)

        # If cached file already exists with exact size, reuse immediately
        if out_file.exists() and out_file.stat().st_size == file_size:
            if progress_callback:
                progress_callback(file_size, file_size, "Download completed!")
            return str(target_path)

        total_chunks = len(chunks)
        chunks_sorted = sorted(chunks, key=lambda c: c.get("part", 0))

        # Stream directly to temporary file to keep RAM usage minimal (~12MB instead of all chunks)
        temp_target = str(target_path) + ".tmp"
        try:
            with open(temp_target, "wb") as f_out:
                for idx, chunk_meta in enumerate(chunks_sorted):
                    downloaded_data = active_backend.download_chunk(chunk_meta["file_id"])
                    if is_encrypted and aes_key:
                        plain_data = decrypt_bytes(downloaded_data, aes_key)
                    else:
                        plain_data = downloaded_data
                    
                    f_out.write(plain_data)
                    del plain_data
                    del downloaded_data
                    if (idx + 1) % 2 == 0:
                        import gc
                        gc.collect()

                    if progress_callback:
                        progress_callback(min(file_size, (idx + 1) * 12582912), file_size, f"Chunk {idx+1}/{total_chunks}")
            
            # Atomic rename when download is complete
            import shutil
            shutil.move(temp_target, str(target_path))
        except Exception:
            if Path(temp_target).exists():
                try: Path(temp_target).unlink()
                except Exception: pass
            raise

        if progress_callback:
            progress_callback(file_size, file_size, "Download completed!")

        return str(target_path)

    def delete_file(self, file_id: int) -> bool:
        """Permanently purges chunks from the corresponding cloud backend and removes database entry."""
        file_info = database.get_file_by_id(file_id)
        if not file_info:
            return False

        backend_name = file_info.get("cloud_backend", "telegram")
        active_backend = self.pool.get_backend(backend_name)

        chunks = file_info.get("chunks", [])
        for chunk in chunks:
            chunk_file_id = chunk.get("file_id", "")
            msg_id = chunk.get("message_id", 0)
            if chunk_file_id:
                try:
                    active_backend.delete_chunk(chunk_file_id, msg_id)
                except Exception:
                    pass

        res = database.delete_permanently(file_id)
        return bool(res)
