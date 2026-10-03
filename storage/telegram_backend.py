"""
Telegram Cloud Storage Backend.
Leverages Telegram's unlimited cloud servers to provide 5TB+ free storage forever.
Handles chunking, uploading, downloading, and verification with high-performance connection pooling.
"""
import io
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Dict, Any, Tuple, Optional, Callable

class TelegramBackend:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token.strip()
        self.chat_id = str(chat_id).strip()
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.file_api_url = f"https://api.telegram.org/file/bot{self.bot_token}"
        
        # High-performance connection-pooled session with HTTP keep-alive
        self.session = requests.Session()
        retries = Retry(total=3, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504])
        adapter = HTTPAdapter(pool_connections=25, pool_maxsize=25, max_retries=retries)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def test_connection(self) -> Tuple[bool, str]:
        """Test bot token and channel access."""
        if not self.bot_token:
            return False, "Bot Token is missing."
        if not self.chat_id:
            return False, "Chat/Channel ID is missing."
        try:
            # 1. Test getMe
            r = self.session.get(f"{self.api_url}/getMe", timeout=10)
            if r.status_code != 200:
                return False, f"Invalid Bot Token (HTTP {r.status_code})"
            data = r.json()
            if not data.get("ok"):
                return False, data.get("description", "Failed to verify Bot")
            bot_username = data["result"].get("username", "Bot")

            # 2. Test chat access
            r_chat = self.session.get(
                f"{self.api_url}/getChat",
                params={"chat_id": self.chat_id},
                timeout=10
            )
            chat_data = r_chat.json()
            if not chat_data.get("ok"):
                return False, f"Connected to @{bot_username}, but cannot access Chat ID: {chat_data.get('description', '')}"

            chat_title = chat_data["result"].get("title") or chat_data["result"].get("first_name") or self.chat_id
            return True, f"Connected to @{bot_username} (Storage Channel: {chat_title})"
        except requests.exceptions.RequestException as e:
            return False, f"Network error: {str(e)}"
        except Exception as e:
            return False, str(e)

    def upload_chunk(
        self,
        chunk_data: bytes,
        chunk_name: str,
        caption: str = "",
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> Dict[str, Any]:
        """Upload a single chunk/file to Telegram Channel with automatic retry and rate-limiting handling."""
        url = f"{self.api_url}/sendDocument"
        data = {
            "chat_id": self.chat_id,
            "caption": caption
        }

        for attempt in range(4):
            try:
                files = {
                    "document": (chunk_name, io.BytesIO(chunk_data))
                }
                response = self.session.post(url, data=data, files=files, timeout=180)
                res_json = response.json()
                
                if res_json.get("ok"):
                    doc = res_json["result"]["document"]
                    return {
                        "file_id": doc["file_id"],
                        "file_unique_id": doc.get("file_unique_id", ""),
                        "file_size": doc.get("file_size", len(chunk_data)),
                        "message_id": res_json["result"]["message_id"]
                    }
                elif res_json.get("error_code") == 429:
                    wait_sec = res_json.get("parameters", {}).get("retry_after", 2)
                    time.sleep(wait_sec)
                    continue
                else:
                    err_msg = res_json.get("description", "Unknown error")
                    if attempt < 3:
                        time.sleep(1)
                        continue
                    raise RuntimeError(f"Telegram upload failed: {err_msg}")
            except (requests.exceptions.RequestException, RuntimeError) as e:
                if attempt == 3:
                    raise e
                time.sleep(1)

        raise RuntimeError("Telegram upload failed after 4 attempts")

    def download_chunk(
        self,
        file_id: str,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> bytes:
        """Download a chunk by its Telegram file_id using fast buffered streaming."""
        # 1. Get file path
        url = f"{self.api_url}/getFile"
        r = self.session.get(url, params={"file_id": file_id}, timeout=30)
        res_json = r.json()
        if not res_json.get("ok"):
            raise RuntimeError(f"Telegram getFile failed: {res_json.get('description', 'Unknown error')}")

        file_path = res_json["result"]["file_path"]
        download_url = f"{self.file_api_url}/{file_path}"

        # 2. Download content with larger 256KB buffer for maximum throughput
        r_down = self.session.get(download_url, stream=True, timeout=180)
        r_down.raise_for_status()

        total_length = int(r_down.headers.get("content-length", 0))
        chunks = []
        downloaded = 0

        for chunk in r_down.iter_content(chunk_size=256 * 1024):
            if chunk:
                chunks.append(chunk)
                downloaded += len(chunk)
                if progress_callback and total_length > 0:
                    progress_callback(downloaded, total_length)

        return b"".join(chunks)

    def delete_message(self, message_id: int) -> bool:
        """Optionally delete message from channel when file is permanently purged."""
        try:
            url = f"{self.api_url}/deleteMessage"
            r = self.session.post(url, data={"chat_id": self.chat_id, "message_id": message_id}, timeout=10)
            return r.json().get("ok", False)
        except Exception:
            return False

    def send_message(
        self,
        chat_id: str,
        text: str,
        reply_markup: Optional[Dict[str, Any]] = None,
        parse_mode: Optional[str] = "HTML"
    ) -> Dict[str, Any]:
        """Send text message to a chat/channel with optional inline markup."""
        import json
        url = f"{self.api_url}/sendMessage"
        payload: Dict[str, Any] = {
            "chat_id": str(chat_id).strip(),
            "text": text
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_markup is not None:
            payload["reply_markup"] = json.dumps(reply_markup)
        r = self.session.post(url, data=payload, timeout=20)
        return r.json()

    def edit_message_text(
        self,
        chat_id: str,
        message_id: int,
        text: str,
        reply_markup: Optional[Dict[str, Any]] = None,
        parse_mode: Optional[str] = "HTML"
    ) -> Dict[str, Any]:
        """Edit an existing message text and markup."""
        import json
        url = f"{self.api_url}/editMessageText"
        payload: Dict[str, Any] = {
            "chat_id": str(chat_id).strip(),
            "message_id": message_id,
            "text": text
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_markup is not None:
            payload["reply_markup"] = json.dumps(reply_markup)
        r = self.session.post(url, data=payload, timeout=20)
        return r.json()

    def answer_callback_query(
        self,
        callback_query_id: str,
        text: str = "",
        show_alert: bool = False
    ) -> Dict[str, Any]:
        """Acknowledge button tap."""
        url = f"{self.api_url}/answerCallbackQuery"
        r = self.session.post(
            url,
            data={"callback_query_id": callback_query_id, "text": text, "show_alert": show_alert},
            timeout=10
        )
        return r.json()

    def send_file_to_chat(
        self,
        chat_id: str,
        file_data: bytes,
        file_name: str,
        caption: str = ""
    ) -> Dict[str, Any]:
        """Send a document file directly to a specified chat_id (user or channel)."""
        url = f"{self.api_url}/sendDocument"
        files = {
            "document": (file_name, io.BytesIO(file_data))
        }
        data = {
            "chat_id": str(chat_id).strip(),
            "caption": caption
        }
        r = self.session.post(url, data=data, files=files, timeout=180)
        return r.json()

    def get_updates(
        self,
        offset: Optional[int] = None,
        timeout: int = 20
    ) -> List[Dict[str, Any]]:
        """Fetch incoming bot updates using long-polling."""
        url = f"{self.api_url}/getUpdates"
        params: Dict[str, Any] = {"timeout": timeout}
        if offset is not None:
            params["offset"] = offset
        try:
            r = self.session.get(url, params=params, timeout=timeout + 10)
            data = r.json()
            if data.get("ok"):
                return data.get("result", [])
        except Exception:
            pass
        return []
