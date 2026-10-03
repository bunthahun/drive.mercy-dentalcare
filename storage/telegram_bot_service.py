"""
Interactive Telegram Bot Service for 1000TB Cloud Storage.
Enables bidirectional syncing:
1. Sending files INTO Cloud Storage via Telegram Bot (with Drive and Folder selection).
2. Sending files OUT from Cloud Storage to Telegram chats.
"""
import io
import os
import time
import json
import logging
import threading
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger("telegram_bot_service")

# In-memory session tracking for active Telegram users
# Structure: chat_id -> { "current_drive": "buntha", "current_folder_id": None, "pending_file": {...}, "waiting_for": None }
USER_SESSIONS: Dict[str, Dict[str, Any]] = {}

DRIVE_NAMES = {
    "buntha": "HUN BUNTHA",
    "vuochlin": "NEANG VUOCHLIN",
    "mercy": "Mercy Dental Care"
}

def format_bytes(size_bytes: int) -> str:
    if not size_bytes:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    s = float(size_bytes)
    while s >= 1024.0 and i < len(units) - 1:
        s /= 1024.0
        i += 1
    return f"{s:.1f} {units[i]}"

def get_user_session(chat_id: str) -> Dict[str, Any]:
    cid = str(chat_id)
    if cid not in USER_SESSIONS:
        USER_SESSIONS[cid] = {
            "current_drive": "buntha",
            "current_folder_id": None,
            "pending_file": None,
            "waiting_for": None
        }
    return USER_SESSIONS[cid]

class TelegramBotService:
    def __init__(self, backend, engine, db, cache_dir: Path, backup_callback=None):
        self.backend = backend
        self.engine = engine
        self.db = db
        self.cache_dir = Path(cache_dir)
        self.backup_callback = backup_callback
        self.is_running = False
        self.thread: Optional[threading.Thread] = None

    def start(self):
        if not self.backend or not self.backend.is_configured():
            print("Telegram Bot Service: Bot is not configured, skipping start.")
            return
        if self.is_running:
            return
        self.is_running = True
        self.thread = threading.Thread(target=self._polling_loop, daemon=True, name="TelegramBotPolling")
        self.thread.start()
        print("🚀 Telegram Bot Service started (@buntha_1000tb_bot interactive polling active)")

    def stop(self):
        self.is_running = False

    def _polling_loop(self):
        offset = None
        # Discard stale backlog on boot to start fresh
        try:
            updates = self.backend.get_updates(timeout=1)
            if updates:
                offset = updates[-1]["update_id"] + 1
        except Exception:
            pass

        while self.is_running:
            try:
                updates = self.backend.get_updates(offset=offset, timeout=20)
                for update in updates:
                    offset = update["update_id"] + 1
                    try:
                        self.handle_update(update)
                    except Exception as e:
                        print(f"Error handling Telegram update: {e}")
            except Exception as e:
                time.sleep(2)

    def handle_update(self, update: Dict[str, Any]):
        # Handle Callback Queries (Button Clicks)
        if "callback_query" in update:
            self._handle_callback_query(update["callback_query"])
            return

        # Handle Messages
        msg = update.get("message")
        if not msg:
            return

        chat = msg.get("chat", {})
        chat_id = str(chat.get("id"))
        from_user = msg.get("from", {})
        sender_name = from_user.get("first_name", "") or chat.get("title", "")
        username = from_user.get("username", "")

        # Save active chat to database
        self.db.record_telegram_chat(chat_id, title=sender_name, username=username)

        session = get_user_session(chat_id)

        # Check if user was waiting to enter a new folder name
        if session.get("waiting_for") == "new_folder_name" and msg.get("text"):
            self._handle_new_folder_input(chat_id, msg["text"].strip())
            return

        # Handle File Attachments (Documents, Photos, Videos, Audio)
        file_obj, file_name, file_size = self._extract_file_info(msg)
        if file_obj:
            self._handle_incoming_file(chat_id, file_obj["file_id"], file_name, file_size)
            return

        # Handle Text Commands
        text = (msg.get("text") or "").strip()
        if text.startswith("/"):
            self._handle_command(chat_id, text, sender_name)
        elif text:
            # Friendly greeting / instructions
            self._send_welcome(chat_id, sender_name)

    def _extract_file_info(self, msg: Dict[str, Any]):
        if "document" in msg:
            doc = msg["document"]
            return doc, doc.get("file_name", "document.bin"), doc.get("file_size", 0)
        elif "photo" in msg:
            photo = msg["photo"][-1]
            return photo, f"photo_{int(time.time())}.jpg", photo.get("file_size", 0)
        elif "video" in msg:
            vid = msg["video"]
            return vid, vid.get("file_name", f"video_{int(time.time())}.mp4"), vid.get("file_size", 0)
        elif "audio" in msg:
            aud = msg["audio"]
            return aud, aud.get("file_name", f"audio_{int(time.time())}.mp3"), aud.get("file_size", 0)
        elif "voice" in msg:
            vc = msg["voice"]
            return vc, f"voice_{int(time.time())}.ogg", vc.get("file_size", 0)
        return None, "", 0

    def _handle_command(self, chat_id: str, text: str, sender_name: str):
        cmd = text.split()[0].lower()
        session = get_user_session(chat_id)

        if cmd in ["/start", "/help"]:
            self._send_welcome(chat_id, sender_name)
        elif cmd == "/status":
            stats = self.db.get_storage_stats()
            used_str = stats.get("used_bytes_formatted", "0 B")
            files_cnt = stats.get("total_files", 0)
            folders_cnt = stats.get("total_folders", 0)
            txt = (
                f"📊 <b>ស្ថានភាពទំហំផ្ទុក Cloud Storage (1000 TB):</b>\n\n"
                f"• <b>ទំហំប្រើប្រាស់៖</b> {used_str} / 1,000 TB\n"
                f"• <b>ឯកសារសរុប៖</b> {files_cnt} ឯកសារ\n"
                f"• <b>ថតសរុប (Folders)៖</b> {folders_cnt} ថត\n\n"
                f"💾 <b>Drive របស់អ្នក៖</b>\n"
                f"1. <b>HUN BUNTHA</b> (1000 TB)\n"
                f"2. <b>NEANG VUOCHLIN</b> (1000 TB)\n"
                f"3. <b>Mercy Dental Care</b> (1000 TB)"
            )
            self.backend.send_message(chat_id, txt)
        elif cmd == "/drives":
            self._show_drive_picker(chat_id, "សូមជ្រើសរើស Drive លំនាំដើមរបស់អ្នក៖")
        elif cmd == "/folders":
            drive = session.get("current_drive", "buntha")
            self._show_folder_picker(chat_id, drive, "សូមជ្រើសរើស Folder លំនាំដើមរបស់អ្នក៖")
        else:
            self._send_welcome(chat_id, sender_name)

    def _send_welcome(self, chat_id: str, sender_name: str):
        session = get_user_session(chat_id)
        drive_key = session.get("current_drive", "buntha")
        drive_name = DRIVE_NAMES.get(drive_key, "HUN BUNTHA")
        folder_id = session.get("current_folder_id")

        folder_name = "ដើម (Root)"
        if folder_id:
            all_f = self.db.get_folders(drive_owner=drive_key)
            found = next((f for f in all_f if f["id"] == folder_id), None)
            if found:
                folder_name = found["folder_name"]

        txt = (
            f"👋 <b>សួស្តី {sender_name}!</b>\n\n"
            f"សូមស្វាគមន៍មកកាន់ <b>1000TB Cloud Storage Bot</b>!\n\n"
            f"💾 <b>Drive បច្ចុប្បន្ន៖</b> <code>{drive_name}</code>\n"
            f"📁 <b>Folder បច្ចុប្បន្ន៖</b> <code>{folder_name}</code>\n\n"
            f"📤 <b>របៀបផ្ញើឯកសារចូល Cloud Storage៖</b>\n"
            f"• គ្រាន់តែ <b>ផ្ញើរូបភាព វីដេអូ ឬឯកសារ (Files)</b> មកកាន់ទីនេះ\n"
            f"• អ្នកអាចរើស Drive និង Folder ដែលចង់រក្សាទុក\n"
            f"• ឯកសារនឹងត្រូវអ៊ិនគ្រីប AES-256 និងរក្សាទុកក្នុង Cloud Storage ភ្លាមៗ!\n\n"
            f"📥 <b>របៀបផ្ញើឯកសារចេញមក Telegram៖</b>\n"
            f"• ក្នុង Web App ឬទូរស័ព្ទ ចុចលើឯកសារ រួចជ្រើសរើស <b>«✈️ ផ្ញើទៅ Telegram»</b>"
        )
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "💾 ប្តូរ Drive", "callback_data": "menu:choose_drive"},
                    {"text": "📁 ប្តូរ Folder", "callback_data": "menu:choose_folder"}
                ],
                [
                    {"text": "📊 មើលទំហំផ្ទុក (Stats)", "callback_data": "menu:stats"},
                    {"text": "🌐 បើកកម្មវិធី Cloud Storage", "url": "https://hunbuntha.onrender.com"}
                ]
            ]
        }
        self.backend.send_message(chat_id, txt, reply_markup=keyboard)

    def _handle_incoming_file(self, chat_id: str, file_id: str, file_name: str, file_size: int):
        session = get_user_session(chat_id)
        drive_key = session.get("current_drive", "buntha")
        drive_name = DRIVE_NAMES.get(drive_key, "HUN BUNTHA")
        folder_id = session.get("current_folder_id")

        folder_name = "ដើម (Root)"
        if folder_id:
            all_f = self.db.get_folders(drive_owner=drive_key)
            found = next((f for f in all_f if f["id"] == folder_id), None)
            if found:
                folder_name = found["folder_name"]

        session["pending_file"] = {
            "file_id": file_id,
            "file_name": file_name,
            "file_size": file_size
        }

        txt = (
            f"📥 <b>ទទួលបានឯកសារថ្មី!</b>\n\n"
            f"📄 <b>ឈ្មោះ៖</b> <code>{file_name}</code>\n"
            f"📦 <b>ទំហំ៖</b> <code>{format_bytes(file_size)}</code>\n\n"
            f"💾 <b>សូមជ្រើសរើស Drive ដើម្បីរក្សាទុក៖</b>"
        )

        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "💾 HUN BUNTHA", "callback_data": f"f_drive:buntha:{file_id}"},
                    {"text": "💾 NEANG VUOCHLIN", "callback_data": f"f_drive:vuochlin:{file_id}"}
                ],
                [
                    {"text": "💾 Mercy Dental Care", "callback_data": f"f_drive:mercy:{file_id}"}
                ],
                [
                    {
                        "text": f"⚡ រក្សាទុកភ្លាមក្នុង [{drive_name} > {folder_name}]",
                        "callback_data": f"f_quick:{drive_key}:{folder_id or 0}:{file_id}"
                    }
                ]
            ]
        }
        self.backend.send_message(chat_id, txt, reply_markup=keyboard)

    def _handle_callback_query(self, query: Dict[str, Any]):
        cq_id = query["id"]
        data = query.get("data", "")
        message = query.get("message", {})
        chat_id = str(message.get("chat", {}).get("id"))
        msg_id = message.get("message_id")

        session = get_user_session(chat_id)
        self.backend.answer_callback_query(cq_id)

        # 1. Menu navigation
        if data == "menu:choose_drive":
            self._edit_to_drive_picker(chat_id, msg_id, "សូមជ្រើសរើស Drive លំនាំដើម៖", mode="set_default")
            return
        elif data == "menu:choose_folder":
            drive = session.get("current_drive", "buntha")
            self._edit_to_folder_picker(chat_id, msg_id, drive, "សូមជ្រើសរើស Folder លំនាំដើម៖", mode="set_default")
            return
        elif data == "menu:stats":
            stats = self.db.get_storage_stats()
            used_str = stats.get("used_bytes_formatted", "0 B")
            txt = (
                f"📊 <b>ទំហំផ្ទុក Cloud Storage (1000 TB)៖</b>\n\n"
                f"• ប្រើប្រាស់៖ <b>{used_str} / 1000 TB</b>\n"
                f"• ឯកសារសរុប៖ <b>{stats.get('total_files', 0)}</b>\n"
                f"• ថតសរុប៖ <b>{stats.get('total_folders', 0)}</b>"
            )
            keyboard = {"inline_keyboard": [[{"text": "« ត្រឡប់ក្រោយ", "callback_data": "menu:back_home"}]]}
            self.backend.edit_message_text(chat_id, msg_id, txt, reply_markup=keyboard)
            return
        elif data == "menu:back_home":
            sender_name = message.get("chat", {}).get("first_name", "User")
            self._send_welcome(chat_id, sender_name)
            return

        # 2. Set Default Drive
        if data.startswith("set_def_drive:"):
            chosen_drive = data.split(":")[1]
            session["current_drive"] = chosen_drive
            session["current_folder_id"] = None
            self.db.update_telegram_chat_context(chat_id, chosen_drive, None)
            dname = DRIVE_NAMES.get(chosen_drive, chosen_drive)
            txt = f"✅ បានកំណត់ <b>{dname}</b> ជា Drive លំនាំដើមរបស់អ្នក!"
            keyboard = {"inline_keyboard": [
                [{"text": "📁 ជ្រើសរើស Folder ក្នុង Drive នេះ", "callback_data": f"menu:choose_folder"}],
                [{"text": "« ត្រឡប់ទៅ Menu ដើម", "callback_data": "menu:back_home"}]
            ]}
            self.backend.edit_message_text(chat_id, msg_id, txt, reply_markup=keyboard)
            return

        # 3. Set Default Folder
        if data.startswith("set_def_folder:"):
            parts = data.split(":")
            chosen_drive = parts[1]
            f_id = int(parts[2]) if parts[2] != "0" else None
            session["current_drive"] = chosen_drive
            session["current_folder_id"] = f_id
            self.db.update_telegram_chat_context(chat_id, chosen_drive, f_id)
            dname = DRIVE_NAMES.get(chosen_drive, chosen_drive)
            fname = "ដើម (Root)"
            if f_id:
                all_f = self.db.get_folders(drive_owner=chosen_drive)
                found = next((f for f in all_f if f["id"] == f_id), None)
                if found: fname = found["folder_name"]
            txt = f"✅ បានកំណត់ Folder លំនាំដើម៖ <b>{dname} > {fname}</b>"
            keyboard = {"inline_keyboard": [[{"text": "« ត្រឡប់ទៅ Menu ដើម", "callback_data": "menu:back_home"}]]}
            self.backend.edit_message_text(chat_id, msg_id, txt, reply_markup=keyboard)
            return

        # 4. Incoming File: Drive Chosen
        if data.startswith("f_drive:"):
            parts = data.split(":")
            chosen_drive = parts[1]
            file_id = parts[2]
            session["current_drive"] = chosen_drive
            self._edit_to_folder_picker(chat_id, msg_id, chosen_drive, f"📁 ជ្រើសរើស Folder ក្នុង Drive [{DRIVE_NAMES.get(chosen_drive)}]៖", mode=f"save:{file_id}")
            return

        # 5. Incoming File: Save Triggered
        if data.startswith("f_save:") or data.startswith("f_quick:"):
            parts = data.split(":")
            chosen_drive = parts[1]
            folder_id = int(parts[2]) if parts[2] != "0" else None
            file_id = parts[3]
            self._process_file_save(chat_id, msg_id, chosen_drive, folder_id, file_id)
            return

        # 6. Incoming File: Prompt create folder
        if data.startswith("f_new_folder:"):
            parts = data.split(":")
            chosen_drive = parts[1]
            file_id = parts[2]
            session["waiting_for"] = "new_folder_name"
            session["pending_save"] = {
                "drive": chosen_drive,
                "file_id": file_id
            }
            txt = (
                f"📁 <b>បង្កើត Folder ថ្មីក្នុង Drive [{DRIVE_NAMES.get(chosen_drive)}]៖</b>\n\n"
                f"✏️ សូមវាយបញ្ចូលឈ្មោះ Folder ថ្មី រួចផ្ញើមកទីនេះ (ឧទាហរណ៍៖ <code>កិច្ចសន្យា</code> ឬ <code>Documents</code>)៖"
            )
            self.backend.send_message(chat_id, txt)
            return

    def _edit_to_folder_picker(self, chat_id: str, msg_id: int, drive: str, prompt_text: str, mode: str):
        folders = self.db.get_folders(drive_owner=drive, is_trash=False)
        rows = []

        is_saving = mode.startswith("save:")
        file_id = mode.split(":")[1] if is_saving else ""

        # Root Folder Button
        root_data = f"f_save:{drive}:0:{file_id}" if is_saving else f"set_def_folder:{drive}:0"
        rows.append([{"text": "📂 ដើម (Root / គ្មាន Folder)", "callback_data": root_data}])

        # Folder items
        for f in folders[:10]:
            btn_data = f"f_save:{drive}:{f['id']}:{file_id}" if is_saving else f"set_def_folder:{drive}:{f['id']}"
            rows.append([{"text": f"📁 {f['folder_name']}", "callback_data": btn_data}])

        # New Folder Button
        if is_saving:
            rows.append([{"text": "➕ បង្កើត Folder ថ្មី...", "callback_data": f"f_new_folder:{drive}:{file_id}"}])

        keyboard = {"inline_keyboard": rows}
        self.backend.edit_message_text(chat_id, msg_id, prompt_text, reply_markup=keyboard)

    def _edit_to_drive_picker(self, chat_id: str, msg_id: int, prompt_text: str, mode: str):
        keyboard = {
            "inline_keyboard": [
                [{"text": "💾 HUN BUNTHA", "callback_data": "set_def_drive:buntha"}],
                [{"text": "💾 NEANG VUOCHLIN", "callback_data": "set_def_drive:vuochlin"}],
                [{"text": "💾 Mercy Dental Care", "callback_data": "set_def_drive:mercy"}],
                [{"text": "« ថយក្រោយ", "callback_data": "menu:back_home"}]
            ]
        }
        self.backend.edit_message_text(chat_id, msg_id, prompt_text, reply_markup=keyboard)

    def _show_drive_picker(self, chat_id: str, prompt_text: str):
        keyboard = {
            "inline_keyboard": [
                [{"text": "💾 HUN BUNTHA", "callback_data": "set_def_drive:buntha"}],
                [{"text": "💾 NEANG VUOCHLIN", "callback_data": "set_def_drive:vuochlin"}],
                [{"text": "💾 Mercy Dental Care", "callback_data": "set_def_drive:mercy"}]
            ]
        }
        self.backend.send_message(chat_id, prompt_text, reply_markup=keyboard)

    def _show_folder_picker(self, chat_id: str, drive: str, prompt_text: str):
        folders = self.db.get_folders(drive_owner=drive, is_trash=False)
        rows = [[{"text": "📂 ដើម (Root)", "callback_data": f"set_def_folder:{drive}:0"}]]
        for f in folders[:10]:
            rows.append([{"text": f"📁 {f['folder_name']}", "callback_data": f"set_def_folder:{drive}:{f['id']}"}])
        keyboard = {"inline_keyboard": rows}
        self.backend.send_message(chat_id, prompt_text, reply_markup=keyboard)

    def _handle_new_folder_input(self, chat_id: str, folder_name: str):
        session = get_user_session(chat_id)
        session["waiting_for"] = None
        pending = session.get("pending_save") or {}
        drive = pending.get("drive", "buntha")
        file_id = pending.get("file_id")

        if not folder_name:
            self.backend.send_message(chat_id, "⚠️ ឈ្មោះ Folder មិនអាចទទេបានទេ។")
            return

        new_folder_id = self.db.create_folder(folder_name=folder_name, drive_owner=drive)
        self.backend.send_message(chat_id, f"✅ បានបង្កើត Folder <b>[{folder_name}]</b> ជោគជ័យ!")

        if file_id:
            # Send message and process save
            res = self.backend.send_message(chat_id, "⏳ កំពុងដំណើរការរក្សាទុកឯកសារចូលទៅក្នុង Folder ថ្មី...")
            msg_id = res.get("result", {}).get("message_id")
            if msg_id:
                self._process_file_save(chat_id, msg_id, drive, new_folder_id, file_id)

    def _process_file_save(self, chat_id: str, msg_id: int, drive: str, folder_id: Optional[int], file_id: str):
        session = get_user_session(chat_id)
        pending_file = session.get("pending_file") or {}
        file_name = pending_file.get("file_name", "file.bin")
        file_size = pending_file.get("file_size", 0)

        drive_name = DRIVE_NAMES.get(drive, drive)
        folder_name = "ដើម (Root)"
        if folder_id:
            all_f = self.db.get_folders(drive_owner=drive)
            found = next((f for f in all_f if f["id"] == folder_id), None)
            if found: folder_name = found["folder_name"]

        self.backend.edit_message_text(
            chat_id, msg_id,
            f"⏳ <b>កំពុងទាញយក និងអ៊ិនគ្រីប...</b>\n"
            f"📄 ឯកសារ៖ <code>{file_name}</code>\n"
            f"💾 គោលដៅ៖ <b>{drive_name} > {folder_name}</b>\n"
            f"សូមរង់ចាំបន្តិច..."
        )

        try:
            # 1. Download file chunk from Telegram
            file_bytes = self.backend.download_chunk(file_id)
            if not file_bytes:
                raise RuntimeError("Empty file received from Telegram")

            # 2. Write to temporary cache file
            safe_name = "".join(c for c in file_name if c.isalnum() or c in "._- ") or "file.bin"
            temp_path = self.cache_dir / f"tg_up_{int(time.time())}_{safe_name}"
            with open(temp_path, "wb") as f:
                f.write(file_bytes)

            # 3. Upload to cloud storage engine
            res = self.engine.upload_file(
                str(temp_path),
                drive_owner=drive,
                custom_filename=file_name,
                folder_id=folder_id
            )

            if temp_path.exists():
                temp_path.unlink()

            if self.backup_callback:
                self.backup_callback()

            # Update session context
            session["current_drive"] = drive
            session["current_folder_id"] = folder_id
            self.db.update_telegram_chat_context(chat_id, drive, folder_id)

            success_txt = (
                f"✅ <b>បានរក្សាទុកក្នុង Cloud Storage ដោយជោគជ័យ!</b>\n\n"
                f"📄 <b>ឈ្មោះឯកសារ៖</b> <code>{file_name}</code>\n"
                f"📦 <b>ទំហំ៖</b> <code>{format_bytes(file_size or len(file_bytes))}</code>\n"
                f"💾 <b>Drive៖</b> <b>{drive_name}</b>\n"
                f"📁 <b>Folder៖</b> <b>{folder_name}</b>\n\n"
                f"🎉 អ្នកអាចចូលមើល ឬទាញយកឯកសារនេះបានគ្រប់ពេលតាមរយៈ Web App!"
            )
            keyboard = {
                "inline_keyboard": [
                    [{"text": "🌐 បើកកម្មវិធី Cloud Storage", "url": "https://hunbuntha.onrender.com"}]
                ]
            }
            self.backend.edit_message_text(chat_id, msg_id, success_txt, reply_markup=keyboard)

        except Exception as e:
            err_txt = f"❌ <b>មានបញ្ហាក្នុងការរក្សាទុកឯកសារ៖</b>\n<code>{str(e)}</code>"
            self.backend.edit_message_text(chat_id, msg_id, err_txt)
