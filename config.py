"""
Configuration module for 5TB Cloud Storage App.
"""
import os
import json
from pathlib import Path

# Base Paths
APP_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = APP_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

CACHE_DIR = DATA_DIR / "cache"
CACHE_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "cloud_storage.db"
CONFIG_FILE = DATA_DIR / "settings.json"

# Quota settings: 1000 TB (1 Petabyte) in bytes
THOUSAND_TB_BYTES = 1000 * 1024 * 1024 * 1024 * 1024  # 1,099,511,627,776,000 Bytes (~1,024,000 GB)
FIVE_TB_BYTES = THOUSAND_TB_BYTES  # Alias for backward compatibility
STORAGE_QUOTA_BYTES = THOUSAND_TB_BYTES
TOTAL_STORAGE_TB = 1000

# Default Settings
DEFAULT_SETTINGS = {
    "language": "km",  # "km" for Khmer, "en" for English
    "backend": "telegram",  # "telegram" or "local"
    "telegram_bot_token": os.environ.get("TELEGRAM_BOT_TOKEN", "8118440382:AAFaTFKfcfOibxeOT9ED-nYsQyPu0GJUkjU"),
    "telegram_chat_id": os.environ.get("TELEGRAM_CHAT_ID", "-1003986966662"),
    "encryption_enabled": True,
    "encryption_key": os.environ.get("ENCRYPTION_KEY", "cloud-storage-1000tb-buntha"),
    "chunk_size_mb": 19,  # 19MB per chunk for Telegram Bot limits
    "theme": "dark",
    "view_mode": "grid",  # "grid" or "list"
    "cache_dir": str(CACHE_DIR),
    "website_password": os.environ.get("WEBSITE_PASSWORD", "1234"),
    "password_buntha": os.environ.get("PASSWORD_BUNTHA", "1111"),
    "password_vuochlin": os.environ.get("PASSWORD_VUOCHLIN", "2222"),
    "password_mercy": os.environ.get("PASSWORD_MERCY", "3333"),
}

def load_settings() -> dict:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                merged = DEFAULT_SETTINGS.copy()
                merged.update(data)
                return merged
        except Exception:
            return DEFAULT_SETTINGS.copy()
    return DEFAULT_SETTINGS.copy()

def save_settings(settings: dict) -> bool:
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error saving settings: {e}")
        return False
