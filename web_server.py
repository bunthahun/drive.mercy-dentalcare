"""
Standalone Production Web Server for 1000TB Cloud Storage (Render / Cloud Deployment).
Fully self-contained: Embeds HTML, CSS, JS, Crypto, and Storage Engine.
"""
import os
import io
import math
import mimetypes
import hashlib
import requests
from pathlib import Path
from flask import Flask, render_template_string, request, jsonify, send_file
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

from config import load_settings, save_settings, STORAGE_QUOTA_BYTES, FIVE_TB_BYTES, DATA_DIR, CACHE_DIR
import database
from locales import STRINGS

# --- CRYPTOGRAPHY ---
SALT_FIXED = b"Antigravity_5TB_Cloud_Storage_Salt_2026"

def derive_key(passphrase: str) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=SALT_FIXED,
        iterations=100000,
    )
    return kdf.derive(passphrase.encode("utf-8"))

def encrypt_bytes(data: bytes, key: bytes) -> bytes:
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, data, None)
    return nonce + ciphertext

def decrypt_bytes(encrypted_data: bytes, key: bytes) -> bytes:
    if len(encrypted_data) < 12 + 16:
        raise ValueError("Invalid encrypted data length")
    nonce = encrypted_data[:12]
    ciphertext = encrypted_data[12:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None)

def compute_sha256(filepath: str) -> str:
    sha = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(1024 * 1024):
            sha.update(chunk)
    return sha.hexdigest()

# --- TELEGRAM CLOUD BACKEND ---
class TelegramBackend:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token.strip()
        self.chat_id = str(chat_id).strip()
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.file_api_url = f"https://api.telegram.org/file/bot{self.bot_token}"

    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def test_connection(self):
        if not self.bot_token or not self.chat_id:
            return False, "Bot Token or Chat ID missing"
        try:
            r = requests.get(f"{self.api_url}/getMe", timeout=10)
            data = r.json()
            if not data.get("ok"):
                return False, data.get("description", "Failed to verify Bot")
            bot_username = data["result"].get("username", "Bot")
            
            r_chat = requests.get(f"{self.api_url}/getChat", params={"chat_id": self.chat_id}, timeout=10)
            chat_data = r_chat.json()
            if not chat_data.get("ok"):
                return False, f"Connected to @{bot_username}, but cannot access Chat: {chat_data.get('description', '')}"
            chat_title = chat_data["result"].get("title") or self.chat_id
            return True, f"Connected to @{bot_username} ({chat_title})"
        except Exception as e:
            return False, str(e)

    def upload_chunk(self, chunk_data: bytes, chunk_name: str, caption: str = ""):
        url = f"{self.api_url}/sendDocument"
        files = {"document": (chunk_name, io.BytesIO(chunk_data))}
        data = {"chat_id": self.chat_id, "caption": caption}
        res = requests.post(url, data=data, files=files, timeout=120)
        res_json = res.json()
        if not res_json.get("ok"):
            raise RuntimeError(f"Upload failed: {res_json.get('description', 'Unknown error')}")
        doc = res_json["result"]["document"]
        return {
            "file_id": doc["file_id"],
            "file_unique_id": doc.get("file_unique_id", ""),
            "file_size": doc.get("file_size", len(chunk_data)),
            "message_id": res_json["result"]["message_id"]
        }

    def download_chunk(self, file_id: str):
        url = f"{self.api_url}/getFile"
        r = requests.get(url, params={"file_id": file_id}, timeout=30)
        res_json = r.json()
        if not res_json.get("ok"):
            raise RuntimeError(f"getFile failed: {res_json.get('description', 'Unknown error')}")
        file_path = res_json["result"]["file_path"]
        download_url = f"{self.file_api_url}/{file_path}"
        r_down = requests.get(download_url, timeout=120)
        r_down.raise_for_status()
        return r_down.content

# --- LOCAL BACKEND ---
class LocalBackend:
    def __init__(self):
        self.storage_dir = DATA_DIR / "local_cloud"
        self.storage_dir.mkdir(exist_ok=True)

    def is_configured(self): return True
    def test_connection(self): return True, "Local Storage Node Ready"

    def upload_chunk(self, chunk_data: bytes, chunk_name: str, caption: str = ""):
        import uuid
        file_id = f"local_{uuid.uuid4().hex}"
        with open(self.storage_dir / file_id, "wb") as f:
            f.write(chunk_data)
        return {"file_id": file_id, "file_size": len(chunk_data), "message_id": 0}

    def download_chunk(self, file_id: str):
        target = self.storage_dir / file_id
        if not target.exists(): raise FileNotFoundError("Local chunk not found")
        with open(target, "rb") as f: return f.read()

# --- STORAGE ENGINE ---
class StorageEngine:
    def __init__(self):
        self.reload_backend()

    def reload_backend(self):
        self.settings = load_settings()
        b_type = self.settings.get("backend", "telegram")
        token = self.settings.get("telegram_bot_token", "")
        chat_id = self.settings.get("telegram_chat_id", "")
        if b_type == "telegram" and token and chat_id:
            self.backend = TelegramBackend(token, chat_id)
            self.is_telegram = True
        else:
            self.backend = LocalBackend()
            self.is_telegram = False

    def is_cloud_ready(self):
        return self.is_telegram and self.backend.is_configured()

    def get_backend_name(self):
        return "Telegram 1000TB Cloud" if self.is_telegram else "Local Storage Node"

    def upload_file(self, local_path: str):
        p = Path(local_path)
        file_size = p.stat().st_size
        file_name = p.name
        mime_type, _ = mimetypes.guess_type(local_path)
        mime_type = mime_type or "application/octet-stream"
        sha256_hash = compute_sha256(local_path)

        enc_enabled = self.settings.get("encryption_enabled", True)
        enc_pass = self.settings.get("encryption_key", "cloud-storage-1000tb-buntha")
        aes_key = derive_key(enc_pass) if enc_enabled else None

        chunk_size_bytes = self.settings.get("chunk_size_mb", 19) * 1024 * 1024
        total_chunks = max(1, math.ceil(file_size / chunk_size_bytes))
        chunks_info = []

        with open(local_path, "rb") as f:
            for part_idx in range(total_chunks):
                raw_chunk = f.read(chunk_size_bytes)
                if not raw_chunk and part_idx > 0:
                    break
                chunk_name = f"{file_name}.part{part_idx}" if total_chunks > 1 else file_name
                chunk_to_upload = encrypt_bytes(raw_chunk, aes_key) if (enc_enabled and aes_key) else raw_chunk

                res = self.backend.upload_chunk(
                    chunk_data=chunk_to_upload,
                    chunk_name=chunk_name,
                    caption=f"📦 {file_name} [Part {part_idx + 1}/{total_chunks}]"
                )
                chunks_info.append({
                    "part": part_idx,
                    "file_id": res["file_id"],
                    "size": res["file_size"],
                    "raw_size": len(raw_chunk),
                    "message_id": res.get("message_id", 0)
                })

        cloud_type = "telegram" if self.is_telegram else "local"
        file_db_id = database.add_file(
            file_name=file_name,
            file_size=file_size,
            mime_type=mime_type,
            sha256=sha256_hash,
            is_encrypted=enc_enabled,
            cloud_backend=cloud_type,
            chunks=chunks_info
        )
        return {"id": file_db_id, "file_name": file_name, "file_size": file_size, "chunks_count": len(chunks_info)}

    def download_file(self, file_id: int, target_path: str):
        file_info = database.get_file_by_id(file_id)
        if not file_info: raise ValueError("File not found")
        chunks = file_info.get("chunks", [])
        is_encrypted = bool(file_info.get("is_encrypted", 1))
        aes_key = derive_key(self.settings.get("encryption_key", "cloud-storage-1000tb-buntha")) if is_encrypted else None

        Path(target_path).parent.mkdir(parents=True, exist_ok=True)
        chunks_sorted = sorted(chunks, key=lambda c: c.get("part", 0))

        with open(target_path, "wb") as f_out:
            for chunk_meta in chunks_sorted:
                data = self.backend.download_chunk(chunk_meta["file_id"])
                plain = decrypt_bytes(data, aes_key) if (is_encrypted and aes_key) else data
                f_out.write(plain)
        return target_path

# --- EMBEDDED WEB TEMPLATE ---
INDEX_HTML = """<!DOCTYPE html>
<html lang="km">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cloud Storage 1000TB Free - កម្មវិធីផ្ទុកទិន្នន័យ 1000TB ឥតគិតថ្លៃ</title>
    <meta name="description" content="កម្មវិធីផ្ទុកទិន្នន័យលើ Cloud ទំហំ 1000TB (1 Petabyte) ឥតគិតថ្លៃជារៀងរហូត ការពារដោយ AES-256 Encryption">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Kantumruy+Pro:wght@400;500;600;700&family=Outfit:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
/* ==========================================================================
   5TB Cloud Storage - Modern Dark Glassmorphic Design System
   ========================================================================== */

:root {
    --bg-dark: #070b14;
    --sidebar-bg: #0d1322;
    --card-bg: rgba(19, 27, 46, 0.85);
    --card-border: #1e293b;
    --card-hover: #17223b;
    --accent-blue: #3b82f6;
    --accent-cyan: #06b6d4;
    --accent-glow: rgba(56, 189, 248, 0.25);
    --text-primary: #f8fafc;
    --text-secondary: #94a3b8;
    --text-muted: #64748b;
    --success: #10b981;
    --warning: #f59e0b;
    --danger: #f43f5e;
    --radius-sm: 8px;
    --radius-md: 12px;
    --radius-lg: 16px;
    --font-stack: "Kantumruy Pro", "Outfit", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}

* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
    font-family: var(--font-stack);
}

body {
    background-color: var(--bg-dark);
    color: var(--text-primary);
    overflow: hidden;
    height: 100vh;
}

/* App Layout */
.app-layout {
    display: flex;
    height: 100vh;
    width: 100vw;
}

/* Sidebar */
.sidebar {
    width: 270px;
    background-color: var(--sidebar-bg);
    border-right: 1px solid var(--card-border);
    display: flex;
    flex-direction: column;
    padding: 18px 14px;
    flex-shrink: 0;
}

.sidebar-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 4px 6px 14px 6px;
}

.brand {
    display: flex;
    align-items: center;
    gap: 8px;
}

.brand-icon {
    font-size: 24px;
}

.brand-name {
    font-size: 18px;
    font-weight: 700;
    color: #38bdf8;
    letter-spacing: -0.5px;
}

.badge-free {
    background: linear-gradient(135deg, #1e3a8a, #2563eb);
    color: #93c5fd;
    font-size: 10px;
    font-weight: 700;
    padding: 3px 8px;
    border-radius: 20px;
}

/* 5TB Quota Card */
.quota-card {
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: var(--radius-md);
    padding: 12px 14px;
    margin-bottom: 14px;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
}

.quota-title {
    font-size: 11px;
    font-weight: 600;
    color: var(--text-secondary);
}

.quota-value {
    font-size: 15px;
    font-weight: 700;
    color: #38bdf8;
    margin: 4px 0;
}

.progress-bar-bg {
    width: 100%;
    height: 6px;
    background-color: #1e293b;
    border-radius: 10px;
    overflow: hidden;
    margin: 6px 0;
}

.progress-bar-fill {
    height: 100%;
    background: linear-gradient(90deg, #06b6d4, #3b82f6);
    border-radius: 10px;
    transition: width 0.4s ease;
}

.quota-sub {
    font-size: 11px;
    color: var(--text-muted);
    margin-bottom: 8px;
}

.status-pill {
    width: 100%;
    padding: 6px 10px;
    border-radius: 8px;
    font-size: 11px;
    font-weight: 600;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    cursor: default;
    border: 1px solid #059669;
    background-color: rgba(6, 78, 59, 0.4);
    color: #34d399;
    transition: all 0.2s;
}

.status-pill.warning {
    border-color: #d97706;
    background-color: rgba(69, 26, 3, 0.4);
    color: #fbbf24;
}

.status-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background-color: currentColor;
}

/* Nav Menu */
.nav-menu {
    display: flex;
    flex-direction: column;
    gap: 4px;
    flex-grow: 1;
    overflow-y: auto;
}

.nav-item {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 14px;
    border-radius: var(--radius-sm);
    color: var(--text-secondary);
    background: transparent;
    border: none;
    cursor: pointer;
    font-size: 13px;
    font-weight: 500;
    text-align: left;
    transition: all 0.2s;
}

.nav-item:hover {
    background-color: #17223b;
    color: var(--text-primary);
}

.nav-item.active {
    background: linear-gradient(135deg, #2563eb, #3b82f6);
    color: #ffffff;
    font-weight: 600;
    box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3);
}

/* Windows Style Drive Item */
.nav-item.drive-item {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 12px;
    border-radius: var(--radius-sm);
    background: rgba(30, 41, 59, 0.55);
    border: 1px solid rgba(255, 255, 255, 0.08);
    transition: all 0.2s ease;
}

.nav-item.drive-item:hover {
    background: rgba(30, 41, 59, 0.85);
    border-color: rgba(59, 130, 246, 0.4);
}

.nav-item.drive-item.active {
    background: rgba(37, 99, 235, 0.16);
    border: 1px solid #3b82f6;
    box-shadow: 0 4px 14px rgba(37, 99, 235, 0.22);
}

.drive-icon-container {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
}

.drive-img-icon {
    width: 44px;
    height: auto;
    object-fit: contain;
    filter: drop-shadow(0 2px 5px rgba(0, 0, 0, 0.45));
}

.drive-details {
    flex-grow: 1;
    display: flex;
    flex-direction: column;
    gap: 3px;
    min-width: 0;
}

.drive-label {
    font-size: 13.5px;
    font-weight: 700;
    color: #ffffff;
    letter-spacing: 0.3px;
}

.drive-bar-wrapper {
    width: 100%;
    height: 13px;
    background-color: #d1d5db;
    border: 1px solid #6b7280;
    border-radius: 2px;
    overflow: hidden;
    position: relative;
    box-sizing: border-box;
}

.drive-bar-fill {
    height: 100%;
    background-color: #2563eb;
    width: 1%;
    transition: width 0.3s ease;
}

.drive-subtext {
    font-size: 10.5px;
    color: #94a3b8;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.nav-icon {
    font-size: 16px;
}

/* Sidebar Footer */
.sidebar-footer {
    display: flex;
    gap: 8px;
    padding-top: 10px;
    border-top: 1px solid var(--card-border);
}

.btn-lang {
    flex-grow: 1;
    background-color: #1e293b;
    border: 1px solid var(--card-border);
    color: var(--text-primary);
    padding: 8px 12px;
    border-radius: var(--radius-sm);
    cursor: pointer;
    font-size: 12px;
    font-weight: 600;
    transition: background 0.2s;
}

.btn-lang:hover {
    background-color: #334155;
}

.btn-settings {
    width: 36px;
    height: 36px;
    display: flex;
    align-items: center;
    justify-content: center;
    background-color: #1e293b;
    border: 1px solid var(--card-border);
    color: var(--text-primary);
    border-radius: var(--radius-sm);
    cursor: pointer;
    font-size: 16px;
}

.btn-settings:hover {
    background-color: #334155;
}

/* Main Content */
.main-content {
    flex-grow: 1;
    display: flex;
    flex-direction: column;
    background-color: var(--bg-dark);
    position: relative;
    overflow: hidden;
}

/* Top App Bar */
.top-bar {
    height: 64px;
    background-color: var(--sidebar-bg);
    border-bottom: 1px solid var(--card-border);
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 24px;
    gap: 16px;
}

.top-left, .top-right {
    display: flex;
    align-items: center;
    gap: 10px;
}

.btn-primary {
    background: linear-gradient(135deg, #2563eb, #0284c7);
    color: #ffffff;
    border: none;
    border-radius: var(--radius-sm);
    padding: 8px 16px;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 8px;
    box-shadow: 0 4px 14px rgba(37, 99, 235, 0.35);
    transition: transform 0.15s, box-shadow 0.15s;
}

.btn-primary:hover {
    transform: translateY(-1px);
    box-shadow: 0 6px 18px rgba(37, 99, 235, 0.45);
}

.btn-danger {
    background-color: #991b1b;
    color: #fecaca;
    border: none;
    border-radius: var(--radius-sm);
    padding: 8px 14px;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
}

.search-box {
    display: flex;
    align-items: center;
    background-color: #131b2e;
    border: 1px solid var(--card-border);
    border-radius: var(--radius-sm);
    padding: 6px 12px;
    width: 320px;
    gap: 8px;
}

.search-box:focus-within {
    border-color: #38bdf8;
    box-shadow: 0 0 0 2px var(--accent-glow);
}

.search-box input {
    background: transparent;
    border: none;
    color: var(--text-primary);
    font-size: 13px;
    width: 100%;
    outline: none;
}

.search-clear {
    background: transparent;
    border: none;
    color: var(--text-muted);
    cursor: pointer;
    font-size: 12px;
    display: none;
}

.view-toggles {
    display: flex;
    background-color: #131b2e;
    border: 1px solid var(--card-border);
    border-radius: var(--radius-sm);
    padding: 2px;
}

.view-btn {
    background: transparent;
    border: none;
    color: var(--text-secondary);
    padding: 6px 10px;
    cursor: pointer;
    border-radius: 6px;
    font-size: 14px;
}

.view-btn.active {
    background-color: #2563eb;
    color: #ffffff;
}

.btn-icon {
    background-color: #131b2e;
    border: 1px solid var(--card-border);
    color: var(--text-secondary);
    width: 36px;
    height: 36px;
    border-radius: var(--radius-sm);
    cursor: pointer;
    font-size: 15px;
}

.btn-icon:hover {
    color: var(--text-primary);
    border-color: #334155;
}

/* Viewport Area & Drag-and-Drop */
.content-viewport {
    flex-grow: 1;
    overflow-y: auto;
    padding: 24px;
    position: relative;
}

.drop-overlay {
    position: absolute;
    inset: 12px;
    border: 2px dashed #38bdf8;
    background: rgba(11, 15, 25, 0.92);
    backdrop-filter: blur(8px);
    border-radius: var(--radius-lg);
    display: none;
    align-items: center;
    justify-content: center;
    z-index: 100;
}

.drop-content {
    text-align: center;
}

.drop-icon {
    font-size: 54px;
    display: block;
    margin-bottom: 12px;
}

/* Empty State */
.empty-state {
    text-align: center;
    padding: 80px 20px;
}

.empty-icon {
    font-size: 64px;
    margin-bottom: 16px;
}

.empty-hint {
    color: var(--text-muted);
    font-size: 13px;
    margin-top: 8px;
}

/* File Grid */
.file-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    gap: 16px;
}

.file-card {
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: var(--radius-md);
    padding: 14px;
    display: flex;
    flex-direction: column;
    transition: transform 0.2s, border-color 0.2s, box-shadow 0.2s;
    cursor: pointer;
    position: relative;
}

.file-card:hover {
    transform: translateY(-2px);
    border-color: #38bdf8;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
}

.card-top {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 12px;
}

.card-icon {
    font-size: 32px;
}

.card-star {
    background: transparent;
    border: none;
    color: var(--text-muted);
    font-size: 16px;
    cursor: pointer;
    transition: color 0.15s;
}

.card-star.active {
    color: #f59e0b;
}

.card-name {
    font-size: 13px;
    font-weight: 600;
    color: var(--text-primary);
    word-break: break-word;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    height: 38px;
    margin-bottom: 8px;
}

.card-meta {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 11px;
    color: var(--text-muted);
    margin-top: auto;
}

.card-actions {
    display: flex;
    gap: 6px;
    margin-top: 10px;
    border-top: 1px solid #1e293b;
    padding-top: 8px;
}

.btn-card-action {
    flex: 1;
    background: #1e293b;
    border: none;
    color: var(--text-secondary);
    padding: 5px;
    border-radius: 6px;
    font-size: 12px;
    cursor: pointer;
    text-align: center;
}

.btn-card-action:hover {
    background: #334155;
    color: #ffffff;
}

/* File Table */
.file-table-container {
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: var(--radius-md);
    overflow: hidden;
}

.file-table {
    width: 100%;
    border-collapse: collapse;
    text-align: left;
    font-size: 13px;
}

.file-table th {
    background-color: var(--sidebar-bg);
    padding: 12px 16px;
    color: var(--text-secondary);
    font-weight: 600;
    border-bottom: 1px solid var(--card-border);
}

.file-table td {
    padding: 12px 16px;
    border-bottom: 1px solid #1e293b;
    color: var(--text-primary);
}

.file-table tr:hover td {
    background-color: #17223b;
}

/* Transfer Manager Panel */
.transfer-panel {
    background: rgba(13, 19, 34, 0.95);
    border-top: 1px solid var(--card-border);
    padding: 10px 24px;
    backdrop-filter: blur(10px);
}

.transfer-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;
}

.transfer-title {
    font-size: 12px;
    font-weight: 600;
    color: var(--text-secondary);
}

.btn-clear-transfer {
    background: transparent;
    border: none;
    color: var(--text-muted);
    font-size: 11px;
    cursor: pointer;
}

.transfer-item {
    background-color: #131b2e;
    border: 1px solid var(--card-border);
    border-radius: 8px;
    padding: 8px 12px;
    margin-bottom: 6px;
}

.transfer-info {
    display: flex;
    justify-content: space-between;
    font-size: 12px;
    margin-bottom: 4px;
}

/* Modal Dialog */
.modal-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.75);
    backdrop-filter: blur(6px);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
}

.modal-card {
    background: #0f172a;
    border: 1px solid var(--card-border);
    border-radius: var(--radius-lg);
    width: 540px;
    max-width: 90vw;
    box-shadow: 0 20px 40px rgba(0, 0, 0, 0.6);
    overflow: hidden;
}

.modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 16px 20px;
    border-bottom: 1px solid var(--card-border);
}

.modal-body {
    padding: 20px;
}

.modal-footer {
    display: flex;
    justify-content: flex-end;
    gap: 10px;
    padding: 14px 20px;
    border-top: 1px solid var(--card-border);
}

.guide-box {
    background: #131b2e;
    border: 1px solid var(--card-border);
    border-radius: var(--radius-sm);
    padding: 12px 14px;
    margin-bottom: 16px;
    font-size: 12px;
}

.guide-title {
    font-weight: 700;
    color: #38bdf8;
    margin-bottom: 8px;
}

.guide-list {
    padding-left: 18px;
    color: var(--text-secondary);
    line-height: 1.6;
}

.form-group {
    margin-bottom: 12px;
}

.form-group label {
    display: block;
    font-size: 12px;
    font-weight: 600;
    color: var(--text-secondary);
    margin-bottom: 4px;
}

.form-group input {
    width: 100%;
    background-color: #1e293b;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 8px 12px;
    color: #ffffff;
    font-size: 13px;
    outline: none;
}

.form-group input:focus {
    border-color: #38bdf8;
}

.btn-secondary {
    background-color: #1e293b;
    border: 1px solid var(--card-border);
    color: var(--text-primary);
    padding: 8px 14px;
    border-radius: var(--radius-sm);
    font-size: 13px;
    cursor: pointer;
}

.test-row {
    display: flex;
    align-items: center;
    gap: 12px;
}

.test-feedback {
    font-size: 12px;
    font-weight: 600;
}

.btn-close-modal {
    background: transparent;
    border: none;
    color: var(--text-muted);
    font-size: 18px;
    cursor: pointer;
}

/* Mobile Responsiveness */
@media (max-width: 768px) {
    .app-layout {
        flex-direction: column;
    }
    .sidebar {
        width: 100%;
        height: auto;
        border-right: none;
        border-bottom: 1px solid var(--card-border);
        padding: 12px;
    }
    .quota-card {
        display: none;
    }
    .search-box {
        width: 180px;
    }
}

</style>
</head>
<body>
    <div class="app-layout">
        <!-- Sidebar Navigation -->
        <aside class="sidebar" id="sidebar">
            <div class="sidebar-header">
                <div class="brand">
                    <span class="brand-icon">☁️</span>
                    <span class="brand-name">Cloud 1000TB</span>
                </div>
            </div>

            <!-- 1000TB Quota Card -->
            <div class="quota-card">
                <div class="quota-header">
                    <span class="quota-title" id="tQuotaTitle">⚡ ទំហំផ្ទុកទិន្នន័យ Cloud</span>
                </div>
                <div class="quota-value" id="quotaValue">0.00 GB / 1,024,000 GB</div>
                <div class="progress-bar-bg">
                    <div class="progress-bar-fill" id="quotaFill" style="width: 1%;"></div>
                </div>
                <div class="quota-sub" id="quotaSub">នៅសល់ 1000.00 TB (100%)</div>
                <div class="status-pill connected" id="cloudStatusBtn" style="cursor: default; user-select: none;">
                    <span class="status-dot"></span>
                    <span id="cloudStatusText">Mercy Dental Care</span>
                </div>
            </div>

            <!-- Categories Menu -->
            <nav class="nav-menu">
                <button class="nav-item active drive-item" data-cat="all">
                    <div class="drive-icon-container">
                        <img src="data:image/png;base64,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" alt="Drive" class="drive-img-icon">
                    </div>
                    <div class="drive-details">
                        <div class="drive-label">HUN BUNTHA</div>
                        <div class="drive-bar-wrapper">
                            <div class="drive-bar-fill" id="driveNavFill" style="width: 1%;"></div>
                        </div>
                        <div class="drive-subtext" id="driveNavSub">1000 TB free of 1000 TB</div>
                    </div>
                </button>
                <button class="nav-item" data-cat="trash">
                    <span class="nav-icon">🗑️</span>
                    <span class="nav-label" id="tTrash">ធុងសំរាម</span>
                </button>
            </nav>

            <!-- Bottom Actions: Language & Settings -->
            <div class="sidebar-footer">
                <button class="btn-lang" id="btnLangToggle">🇰🇭 ភាសាខ្មែរ</button>
                <button class="btn-settings" id="btnSettingsOpen" title="Settings">⚙️</button>
            </div>
        </aside>

        <!-- Main Content Area -->
        <main class="main-content">
            <!-- Top App Bar -->
            <header class="top-bar">
                <div class="top-left">
                    <button class="btn-primary" id="btnUploadFile">
                        <span>📤</span>
                        <span id="tUploadFile">ផ្ទុកឯកសារឡើង</span>
                    </button>
                    <input type="file" id="fileInput" multiple style="display: none;">
                    
                    <button class="btn-danger" id="btnEmptyTrash" style="display: none;">
                        <span>🗑️</span>
                        <span id="tEmptyTrash">សម្អាតធុងសំរាម</span>
                    </button>
                </div>

                <div class="top-center">
                    <div class="search-box">
                        <span class="search-icon">🔍</span>
                        <input type="text" id="searchInput" placeholder="ស្វែងរកឯកសារតាមឈ្មោះ...">
                        <button class="search-clear" id="searchClear">✕</button>
                    </div>
                </div>

                <div class="top-right">
                    <div class="view-toggles">
                        <button class="view-btn active" id="btnGridView" title="Grid View">⊞</button>
                        <button class="view-btn" id="btnListView" title="List View">≡</button>
                    </div>
                    <button class="btn-icon" id="btnRefresh" title="Refresh">🔄</button>
                </div>
            </header>

            <!-- Drag & Drop Zone Area -->
            <div class="content-viewport" id="dropZone">
                <!-- Drop Overlay -->
                <div class="drop-overlay" id="dropOverlay">
                    <div class="drop-content">
                        <span class="drop-icon">📥</span>
                        <h2 id="tDropHint">ទម្លាក់ឯកសារនៅទីនេះដើម្បីផ្ទុកឡើង</h2>
                        <p>5TB Secure Cloud Storage with AES-256</p>
                    </div>
                </div>

                <!-- Empty State -->
                <div class="empty-state" id="emptyState" style="display: none;">
                    <div class="empty-icon">☁️</div>
                    <h3 id="tNoFiles">មិនទាន់មានឯកសារនៅឡើយទេ</h3>
                    <p class="empty-hint">អូសទម្លាក់ (Drag & Drop) ឯកសារមកទីនេះ ឬចុច "ផ្ទុកឯកសារឡើង"</p>
                </div>

                <!-- Grid View -->
                <div class="file-grid" id="fileGrid"></div>

                <!-- List View (Table) -->
                <div class="file-table-container" id="fileTableContainer" style="display: none;">
                    <table class="file-table">
                        <thead>
                            <tr>
                                <th id="thName">ឈ្មោះឯកសារ</th>
                                <th id="thSize">ទំហំ</th>
                                <th id="thDate">កាលបរិច្ឆេទ</th>
                                <th>Security</th>
                                <th>Cloud Parts</th>
                                <th style="text-align: right;" id="thActions">សកម្មភាព</th>
                            </tr>
                        </thead>
                        <tbody id="fileTableBody"></tbody>
                    </table>
                </div>
            </div>

            <!-- Transfer Floating / Bottom Panel -->
            <div class="transfer-panel" id="transferPanel" style="display: none;">
                <div class="transfer-header">
                    <span class="transfer-title" id="transferTitle">⚡ ការផ្ទេរទិន្នន័យ (0)</span>
                    <button class="btn-clear-transfer" id="btnClearCompleted">ជម្រះ</button>
                </div>
                <div class="transfer-list" id="transferList"></div>
            </div>
        </main>
    </div>

    <!-- Settings Modal -->
    <div class="modal-backdrop" id="settingsModal" style="display: none;">
        <div class="modal-card">
            <div class="modal-header">
                <h3 id="tSettingsTitle">⚙️ ការកំណត់ Cloud 5TB</h3>
                <button class="btn-close-modal" id="btnCloseSettings">✕</button>
            </div>
            <div class="modal-body">
                <div class="guide-box">
                    <div class="guide-title">💡 របៀបភ្ជាប់ Cloud 5TB ឥតគិតថ្លៃជារៀងរហូត៖</div>
                    <ol class="guide-list">
                        <li>បើក Telegram រួចស្វែងរក <b>@BotFather</b></li>
                        <li>វាយ <code>/newbot</code> ដើម្បីបង្កើត Bot និងទទួលបាន Token</li>
                        <li>បង្កើត Private Channel ក្នុង Telegram រួច Add Bot ជា <b>Admin</b></li>
                        <li>ចម្លង Channel ID (ឧទាហរណ៍: <code>-100xxxxxxxxx</code>) បិទភ្ជាប់ខាងក្រោម</li>
                        <li>ចុច "សាកល្បងការតភ្ជាប់" រួច Save!</li>
                    </ol>
                </div>

                <div class="form-group">
                    <label>Telegram Bot Token:</label>
                    <input type="text" id="cfgBotToken" placeholder="7123456789:AAHqj...">
                </div>

                <div class="form-group">
                    <label>Telegram Channel / Chat ID:</label>
                    <input type="text" id="cfgChatId" placeholder="-1001234567890">
                </div>

                <div class="test-row">
                    <button class="btn-secondary" id="btnTestConn">🔌 សាកល្បងការតភ្ជាប់</button>
                    <span class="test-feedback" id="testFeedback"></span>
                </div>

                <div class="form-group" style="margin-top: 14px;">
                    <label>AES-256 Passphrase (Master Key):</label>
                    <input type="password" id="cfgPassphrase" value="cloud-storage-5tb-secure-key">
                </div>
            </div>
            <div class="modal-footer">
                <button class="btn-secondary" id="btnCancelSettings">បោះបង់</button>
                <button class="btn-primary" id="btnSaveSettings">រក្សាទុកការកំណត់</button>
            </div>
        </div>
    </div>

    <script>
/**
 * 5TB Cloud Storage - Web Application Logic
 */

let currentCategory = "all";
let currentSearch = "";
let currentView = "grid";
let currentLang = "km";
let filesData = [];

// Localization dictionaries
const i18n = {
    km: {
        all_files: "ឯកសារទាំងអស់",
        documents: "ឯកសារអត្ថបទ",
        images: "រូបភាព",
        videos: "វីដេអូ",
        music: "តន្ត្រី / សំឡេង",
        archives: "ឯកសារបង្ហាប់",
        favorites: "សំណព្វចិត្ត",
        trash: "ធុងសំរាម",
        quota_title: "⚡ ទំហំផ្ទុកទិន្នន័យ Cloud",
        quota_free: "នៅសល់",
        upload_file: "ផ្ទុកឯកសារឡើង",
        empty_trash: "សម្អាតធុងសំរាម",
        search_placeholder: "ស្វែងរកឯកសារតាមឈ្មោះ...",
        drop_hint: "ទម្លាក់ឯកសារនៅទីនេះដើម្បីផ្ទុកឡើង",
        no_files: "មិនទាន់មានឯកសារនៅឡើយទេ",
        connected: "Mercy Dental Care",
        offline: "Mercy Dental Care",
        download: "ទាញយក",
        delete: "លុប",
        restore: "ស្តារឡើងវិញ",
        permanent: "លុបអចិន្ត្រៃយ៍",
        lang_btn: "🇰🇭 ភាសាខ្មែរ"
    },
    en: {
        all_files: "All Files",
        documents: "Documents",
        images: "Photos & Images",
        videos: "Videos",
        music: "Music & Audio",
        archives: "Archives (ZIP/RAR)",
        favorites: "Favorites",
        trash: "Recycle Bin",
        quota_title: "⚡ Cloud Storage Quota",
        quota_free: "Free",
        upload_file: "Upload File",
        empty_trash: "Empty Trash",
        search_placeholder: "Search files by name...",
        drop_hint: "Drop files here to upload",
        no_files: "No files found",
        connected: "Mercy Dental Care",
        offline: "Mercy Dental Care",
        download: "Download",
        delete: "Delete",
        restore: "Restore",
        permanent: "Delete Permanently",
        lang_btn: "🇺🇸 English"
    }
};

document.addEventListener("DOMContentLoaded", () => {
    initEventListeners();
    fetchStats();
    loadFiles();
});

function initEventListeners() {
    // Nav items
    document.querySelectorAll(".nav-item").forEach(btn => {
        btn.addEventListener("click", () => {
            document.querySelectorAll(".nav-item").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            currentCategory = btn.dataset.cat;

            const isTrash = currentCategory === "trash";
            document.getElementById("btnUploadFile").style.display = isTrash ? "none" : "flex";
            document.getElementById("btnEmptyTrash").style.display = isTrash ? "flex" : "none";

            loadFiles();
        });
    });

    // Language Toggle
    document.getElementById("btnLangToggle").addEventListener("click", () => {
        currentLang = currentLang === "km" ? "en" : "km";
        applyLanguage();
    });

    // View toggles
    document.getElementById("btnGridView").addEventListener("click", () => setViewMode("grid"));
    document.getElementById("btnListView").addEventListener("click", () => setViewMode("list"));

    // Search
    const searchInput = document.getElementById("searchInput");
    const searchClear = document.getElementById("searchClear");
    searchInput.addEventListener("input", (e) => {
        currentSearch = e.target.value.trim();
        searchClear.style.display = currentSearch ? "block" : "none";
        loadFiles();
    });
    searchClear.addEventListener("click", () => {
        searchInput.value = "";
        currentSearch = "";
        searchClear.style.display = "none";
        loadFiles();
    });

    // Refresh
    document.getElementById("btnRefresh").addEventListener("click", () => {
        fetchStats();
        loadFiles();
    });

    // Upload button & input
    const fileInput = document.getElementById("fileInput");
    document.getElementById("btnUploadFile").addEventListener("click", () => fileInput.click());
    fileInput.addEventListener("change", (e) => {
        if (e.target.files.length > 0) {
            handleFilesUpload(Array.from(e.target.files));
            fileInput.value = "";
        }
    });

    // Drag and Drop
    const dropZone = document.getElementById("dropZone");
    const dropOverlay = document.getElementById("dropOverlay");

    window.addEventListener("dragenter", (e) => {
        e.preventDefault();
        dropOverlay.style.display = "flex";
    });

    dropOverlay.addEventListener("dragleave", (e) => {
        if (e.relatedTarget === null || e.relatedTarget.id === "dropZone") {
            dropOverlay.style.display = "none";
        }
    });

    dropOverlay.addEventListener("dragover", (e) => e.preventDefault());

    dropOverlay.addEventListener("drop", (e) => {
        e.preventDefault();
        dropOverlay.style.display = "none";
        if (e.dataTransfer.files.length > 0) {
            handleFilesUpload(Array.from(e.dataTransfer.files));
        }
    });

    // Settings Modal
    const settingsModal = document.getElementById("settingsModal");
    const openSettings = () => {
        fetchSettings();
        settingsModal.style.display = "flex";
    };
    document.getElementById("btnSettingsOpen").addEventListener("click", openSettings);
    document.getElementById("btnCloseSettings").addEventListener("click", () => settingsModal.style.display = "none");
    document.getElementById("btnCancelSettings").addEventListener("click", () => settingsModal.style.display = "none");

    document.getElementById("btnTestConn").addEventListener("click", testTelegramConnection);
    document.getElementById("btnSaveSettings").addEventListener("click", saveSettingsToServer);

    // Empty trash
    document.getElementById("btnEmptyTrash").addEventListener("click", async () => {
        if (confirm("តើអ្នកពិតជាចង់សម្អាតធុងសំរាមមែនទេ? (Empty trash permanently?)")) {
            await fetch("/api/empty-trash", { method: "POST" });
            fetchStats();
            loadFiles();
        }
    });

    // Clear completed transfers
    document.getElementById("btnClearCompleted").addEventListener("click", () => {
        document.getElementById("transferList").innerHTML = "";
        document.getElementById("transferPanel").style.display = "none";
    });
}

function setViewMode(mode) {
    currentView = mode;
    document.getElementById("btnGridView").classList.toggle("active", mode === "grid");
    document.getElementById("btnListView").classList.toggle("active", mode === "list");
    renderFiles();
}

async function fetchStats() {
    try {
        const res = await fetch("/api/stats");
        const data = await res.json();

        const usedGb = data.used_bytes / (1024 ** 3);
        const freeTb = data.free_bytes / (1024 ** 4);
        const pct = Math.min(100, Math.max(0.1, (data.used_bytes / data.total_bytes) * 100));

        let valText = "";
        if (usedGb < 1) {
            valText = `${(data.used_bytes / (1024 ** 2)).toFixed(2)} MB / 1,024,000 GB`;
        } else if (usedGb < 1024) {
            valText = `${usedGb.toFixed(2)} GB / 1,024,000 GB`;
        } else {
            valText = `${(usedGb / 1024).toFixed(2)} TB / 1,000 TB`;
        }

        document.getElementById("quotaValue").textContent = valText;
        document.getElementById("quotaFill").style.width = `${pct}%`;
        document.getElementById("quotaSub").textContent = `${i18n[currentLang].quota_free} ${freeTb.toFixed(2)} TB (${(100 - pct).toFixed(1)}%)`;

        const statusBtn = document.getElementById("cloudStatusBtn");
        const statusTxt = document.getElementById("cloudStatusText");

        if (statusBtn && statusTxt) {
            statusBtn.className = "status-pill connected";
            statusTxt.textContent = "Mercy Dental Care";
        }

        const driveNavFill = document.getElementById("driveNavFill");
        const driveNavSub = document.getElementById("driveNavSub");
        if (driveNavFill) driveNavFill.style.width = `${pct}%`;
        if (driveNavSub) {
            driveNavSub.textContent = currentLang === "km" 
                ? `នៅសល់ ${freeTb.toFixed(2)} TB នៃ 1,000 TB`
                : `${freeTb.toFixed(2)} TB free of 1,000 TB`;
        }
    } catch (e) {
        console.error("Error fetching stats:", e);
    }
}

async function loadFiles() {
    try {
        const url = `/api/files?category=${currentCategory}&search=${encodeURIComponent(currentSearch)}`;
        const res = await fetch(url);
        const data = await res.json();
        filesData = data.files || [];
        renderFiles();
    } catch (e) {
        console.error("Error loading files:", e);
    }
}

function getFileIcon(cat) {
    const map = {
        documents: "📄",
        images: "🖼️",
        videos: "🎬",
        music: "🎵",
        archives: "📦",
        others: "📁"
    };
    return map[cat] || "📁";
}

function formatSize(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 ** 2) return (bytes / 1024).toFixed(2) + " KB";
    if (bytes < 1024 ** 3) return (bytes / (1024 ** 2)).toFixed(2) + " MB";
    return (bytes / (1024 ** 3)).toFixed(2) + " GB";
}

function renderFiles() {
    const grid = document.getElementById("fileGrid");
    const tableContainer = document.getElementById("fileTableContainer");
    const tbody = document.getElementById("fileTableBody");
    const emptyState = document.getElementById("emptyState");

    if (filesData.length === 0) {
        grid.style.display = "none";
        tableContainer.style.display = "none";
        emptyState.style.display = "block";
        return;
    }

    emptyState.style.display = "none";

    if (currentView === "grid") {
        grid.style.display = "grid";
        tableContainer.style.display = "none";
        grid.innerHTML = "";

        filesData.forEach(file => {
            const card = document.createElement("div");
            card.className = "file-card";
            const icon = getFileIcon(file.category);
            const isFav = file.is_favorite ? "active" : "";

            card.innerHTML = `
                <div class="card-top">
                    <span class="card-icon">${icon}</span>
                    <button class="card-star ${isFav}" title="Favorite">★</button>
                </div>
                <div class="card-name" title="${file.file_name}">${file.file_name}</div>
                <div class="card-meta">
                    <span>${formatSize(file.file_size)}</span>
                    <span>${file.is_encrypted ? "🔒" : "☁️"}</span>
                </div>
                <div class="card-actions">
                    ${!file.is_trash ? `
                        <button class="btn-card-action btn-dl" style="background: linear-gradient(135deg, #2563eb, #0284c7); color: #ffffff; font-weight: 600; padding: 6px 10px;" title="${i18n[currentLang].download}">
                            📥 ${i18n[currentLang].download}
                        </button>
                        <button class="btn-card-action btn-del" style="max-width: 36px;" title="${i18n[currentLang].delete}">🗑️</button>
                    ` : `
                        <button class="btn-card-action btn-restore" title="${i18n[currentLang].restore}">♻️ ${i18n[currentLang].restore}</button>
                        <button class="btn-card-action btn-perm" style="max-width: 36px; color: #f43f5e;" title="${i18n[currentLang].permanent}">❌</button>
                    `}
                </div>
            `;

            // Card Events
            card.querySelector(".card-star").addEventListener("click", (e) => {
                e.stopPropagation();
                toggleFavorite(file.id);
            });

            if (!file.is_trash) {
                card.querySelector(".btn-dl").addEventListener("click", (e) => {
                    e.stopPropagation();
                    downloadFile(file.id);
                });
                card.querySelector(".btn-del").addEventListener("click", (e) => {
                    e.stopPropagation();
                    trashFile(file.id);
                });
            } else {
                card.querySelector(".btn-restore").addEventListener("click", (e) => {
                    e.stopPropagation();
                    restoreFile(file.id);
                });
                card.querySelector(".btn-perm").addEventListener("click", (e) => {
                    e.stopPropagation();
                    deletePermanent(file.id);
                });
            }

            grid.appendChild(card);
        });

    } else {
        grid.style.display = "none";
        tableContainer.style.display = "block";
        tbody.innerHTML = "";

        filesData.forEach(file => {
            const tr = document.createElement("tr");
            const icon = getFileIcon(file.category);

            tr.innerHTML = `
                <td>${icon} ${file.file_name}</td>
                <td>${formatSize(file.file_size)}</td>
                <td>${file.created_at}</td>
                <td>${file.is_encrypted ? "🔒 AES-256" : "🔓 Plain"}</td>
                <td>${file.chunk_count || 1} parts</td>
                <td style="text-align: right;">
                    ${!file.is_trash ? `
                        <button class="btn-primary" style="padding: 4px 10px; font-size: 11px; margin-right: 4px;" onclick="downloadFile(${file.id})">📥 ${i18n[currentLang].download}</button>
                        <button class="btn-secondary" style="padding: 4px 8px;" onclick="trashFile(${file.id})">🗑️</button>
                    ` : `
                        <button class="btn-secondary" style="padding: 4px 8px; margin-right: 4px;" onclick="restoreFile(${file.id})">♻️ ${i18n[currentLang].restore}</button>
                        <button class="btn-secondary" style="padding: 4px 8px; color: #f43f5e;" onclick="deletePermanent(${file.id})">❌</button>
                    `}
                </td>
            `;
            tbody.appendChild(tr);
        });
    }
}

// Upload Handling
async function handleFilesUpload(files) {
    const panel = document.getElementById("transferPanel");
    const list = document.getElementById("transferList");
    panel.style.display = "block";

    for (const file of files) {
        const item = document.createElement("div");
        item.className = "transfer-item";
        item.innerHTML = `
            <div class="transfer-info">
                <span>📤 ${file.name}</span>
                <span class="status-txt">Uploading to Cloud...</span>
            </div>
            <div class="progress-bar-bg">
                <div class="progress-bar-fill" style="width: 20%;"></div>
            </div>
        `;
        list.appendChild(item);

        const formData = new FormData();
        formData.append("file", file);

        try {
            const fill = item.querySelector(".progress-bar-fill");
            const status = item.querySelector(".status-txt");
            fill.style.width = "60%";

            const res = await fetch("/api/upload", {
                method: "POST",
                body: formData
            });

            const result = await res.json();
            if (result.success) {
                fill.style.width = "100%";
                status.textContent = "✓ ជោគជ័យ (Done)";
                status.style.color = "#10b981";
            } else {
                status.textContent = "✕ បរាជ័យ: " + (result.error || "Error");
                status.style.color = "#f43f5e";
            }
        } catch (err) {
            item.querySelector(".status-txt").textContent = "✕ Error: " + err.message;
        }
    }

    fetchStats();
    loadFiles();
}

function downloadFile(id) {
    window.location.href = `/api/download/${id}`;
}

async function toggleFavorite(id) {
    await fetch(`/api/favorite/${id}`, { method: "POST" });
    loadFiles();
}

async function trashFile(id) {
    await fetch(`/api/trash/${id}`, { method: "POST" });
    fetchStats();
    loadFiles();
}

async function restoreFile(id) {
    await fetch(`/api/restore/${id}`, { method: "POST" });
    fetchStats();
    loadFiles();
}

async function deletePermanent(id) {
    if (confirm("ឯកសារនេះនឹងត្រូវលុបជាអចិន្ត្រៃយ៍! តើអ្នកប្រាកដទេ?")) {
        await fetch(`/api/delete-permanent/${id}`, { method: "DELETE" });
        fetchStats();
        loadFiles();
    }
}

// Settings
async function fetchSettings() {
    try {
        const res = await fetch("/api/settings");
        const data = await res.json();
        if (data.settings) {
            document.getElementById("cfgBotToken").value = data.settings.telegram_bot_token || "";
            document.getElementById("cfgChatId").value = data.settings.telegram_chat_id || "";
            document.getElementById("cfgPassphrase").value = data.settings.encryption_key || "cloud-storage-5tb-secure-key";
        }
    } catch (e) {
        console.error(e);
    }
}

async function testTelegramConnection() {
    const token = document.getElementById("cfgBotToken").value.trim();
    const chatId = document.getElementById("cfgChatId").value.trim();
    const fb = document.getElementById("testFeedback");

    fb.textContent = "Testing connection...";
    fb.style.color = "#38bdf8";

    try {
        const res = await fetch("/api/test-telegram", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ bot_token: token, chat_id: chatId })
        });
        const data = await res.json();
        if (data.success) {
            fb.textContent = "✓ " + data.message;
            fb.style.color = "#10b981";
        } else {
            fb.textContent = "✕ " + (data.error || data.message);
            fb.style.color = "#f43f5e";
        }
    } catch (e) {
        fb.textContent = "✕ Network error: " + e.message;
        fb.style.color = "#f43f5e";
    }
}

async function saveSettingsToServer() {
    const payload = {
        telegram_bot_token: document.getElementById("cfgBotToken").value.trim(),
        telegram_chat_id: document.getElementById("cfgChatId").value.trim(),
        encryption_key: document.getElementById("cfgPassphrase").value.trim(),
        backend: "telegram"
    };

    await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
    });

    document.getElementById("settingsModal").style.display = "none";
    fetchStats();
    loadFiles();
}

function applyLanguage() {
    const t = i18n[currentLang];
    const setTxt = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.textContent = val;
    };
    setTxt("tAllFiles", t.all_files);
    setTxt("tDocuments", t.documents);
    setTxt("tImages", t.images);
    setTxt("tVideos", t.videos);
    setTxt("tMusic", t.music);
    setTxt("tArchives", t.archives);
    setTxt("tFavorites", t.favorites);
    setTxt("tTrash", t.trash);
    setTxt("tQuotaTitle", t.quota_title);
    setTxt("tUploadFile", t.upload_file);
    setTxt("tEmptyTrash", t.empty_trash);
    const searchEl = document.getElementById("searchInput");
    if (searchEl) searchEl.placeholder = t.search_placeholder;
    setTxt("tDropHint", t.drop_hint);
    setTxt("tNoFiles", t.no_files);
    setTxt("btnLangToggle", t.lang_btn);
    fetchStats();
    renderFiles();
}

</script>
</body>
</html>
"""

# --- FLASK APPLICATION ---
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024 * 1024

engine = StorageEngine()

@app.route("/")
def index():
    return render_template_string(INDEX_HTML)

@app.route("/static/css/style.css")
def css_fallback():
    return "", 204

@app.route("/static/js/app.js")
def js_fallback():
    return "", 204

@app.route("/api/stats", methods=["GET"])
def get_stats():
    engine.reload_backend()
    stats = database.get_storage_stats()
    used_bytes = stats["used_bytes"]
    free_bytes = max(0, STORAGE_QUOTA_BYTES - used_bytes)
    settings = load_settings()
    return jsonify({
        "used_bytes": used_bytes,
        "free_bytes": free_bytes,
        "total_bytes": STORAGE_QUOTA_BYTES,
        "file_count": stats["file_count"],
        "trash_count": stats["trash_count"],
        "is_cloud_connected": engine.is_cloud_ready(),
        "backend_name": engine.get_backend_name(),
        "language": settings.get("language", "km")
    })

@app.route("/api/files", methods=["GET"])
def list_files():
    cat = request.args.get("category", "all")
    search = request.args.get("search", "").strip()
    is_trash = (cat == "trash")
    is_fav = True if cat == "favorites" else None
    cat_filter = None if cat in ["all", "favorites", "trash"] else cat
    files = database.get_files(
        category=cat_filter,
        search_query=search if search else None,
        is_trash=is_trash,
        is_favorite=is_fav,
        sort_by=request.args.get("sort_by", "date"),
        sort_desc=request.args.get("sort_desc", "true").lower() == "true"
    )
    return jsonify({"success": True, "files": files})

@app.route("/api/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files: return jsonify({"success": False, "error": "No file"}), 400
    uploaded_file = request.files["file"]
    if not uploaded_file.filename: return jsonify({"success": False, "error": "Empty filename"}), 400
    temp_path = CACHE_DIR / f"up_{uploaded_file.filename}"
    uploaded_file.save(str(temp_path))
    try:
        res = engine.upload_file(str(temp_path))
        if temp_path.exists(): temp_path.unlink()
        return jsonify({"success": True, "file": res})
    except Exception as e:
        if temp_path.exists(): temp_path.unlink()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/download/<int:file_id>", methods=["GET"])
def download_file(file_id):
    file_info = database.get_file_by_id(file_id)
    if not file_info: return jsonify({"success": False, "error": "Not found"}), 404
    name = file_info["file_name"]
    temp_path = CACHE_DIR / f"dl_{file_id}_{name}"
    try:
        engine.download_file(file_id, str(temp_path))
        return send_file(str(temp_path), as_attachment=True, download_name=name)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/favorite/<int:file_id>", methods=["POST"])
def toggle_fav(file_id):
    return jsonify({"success": True, "is_favorite": database.toggle_favorite(file_id)})

@app.route("/api/trash/<int:file_id>", methods=["POST"])
def trash_file(file_id):
    database.move_to_trash(file_id)
    return jsonify({"success": True})

@app.route("/api/restore/<int:file_id>", methods=["POST"])
def restore_file(file_id):
    database.restore_from_trash(file_id)
    return jsonify({"success": True})

@app.route("/api/delete-permanent/<int:file_id>", methods=["DELETE"])
def delete_perm(file_id):
    return jsonify({"success": True, "file": database.delete_permanently(file_id)})

@app.route("/api/empty-trash", methods=["POST"])
def empty_trash_route():
    return jsonify({"success": True, "count": len(database.empty_trash())})

@app.route("/api/settings", methods=["GET", "POST"])
def settings_route():
    if request.method == "POST":
        curr = load_settings()
        curr.update(request.json or {})
        save_settings(curr)
        engine.reload_backend()
        return jsonify({"success": True, "settings": curr})
    return jsonify({"success": True, "settings": load_settings()})

@app.route("/api/test-telegram", methods=["POST"])
def test_tg_route():
    d = request.json or {}
    tb = TelegramBackend(d.get("bot_token", ""), str(d.get("chat_id", "")))
    ok, msg = tb.test_connection()
    return jsonify({"success": ok, "message": msg})

@app.route("/api/locales/<lang>", methods=["GET"])
def locales_route(lang):
    return jsonify(STRINGS.get(lang, STRINGS["km"]))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"🚀 1000TB Cloud Server running on http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
