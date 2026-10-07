"""
Database module for storing cloud files metadata, chunks, and state.
"""
import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from config import DB_PATH

def get_connection():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name TEXT NOT NULL,
            file_size INTEGER NOT NULL,
            mime_type TEXT,
            category TEXT NOT NULL,
            sha256 TEXT,
            is_encrypted INTEGER DEFAULT 1,
            is_favorite INTEGER DEFAULT 0,
            is_trash INTEGER DEFAULT 0,
            cloud_backend TEXT DEFAULT 'telegram',
            chunk_count INTEGER DEFAULT 1,
            chunks_data TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    try:
        cursor.execute("ALTER TABLE files ADD COLUMN drive_owner TEXT DEFAULT 'buntha'")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE files ADD COLUMN folder_id INTEGER DEFAULT NULL")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE files ADD COLUMN uploader_email TEXT DEFAULT NULL")
    except sqlite3.OperationalError:
        pass
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS folders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folder_name TEXT NOT NULL,
            parent_id INTEGER DEFAULT NULL,
            drive_owner TEXT DEFAULT 'buntha',
            is_trash INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS telegram_chats (
            chat_id TEXT PRIMARY KEY,
            title TEXT,
            username TEXT,
            last_active TEXT,
            current_drive TEXT DEFAULT 'buntha',
            current_folder_id INTEGER DEFAULT NULL
        )
    """)
    cursor.execute("UPDATE files SET file_name = SUBSTR(file_name, 4) WHERE SUBSTR(file_name, 1, 3) = 'up_'")
    cursor.execute("UPDATE files SET file_name = 'upload_welcome_test.txt' WHERE file_name = 'oad_welcome_test.txt'")
    conn.commit()
    conn.close()

def categorize_file(filename: str) -> str:
    ext = filename.lower().split('.')[-1] if '.' in filename else ''
    
    docs = {'pdf', 'doc', 'docx', 'txt', 'rtf', 'odt', 'xlsx', 'xls', 'csv', 'pptx', 'ppt', 'md', 'epub'}
    images = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'svg', 'ico', 'tiff', 'heic'}
    videos = {'mp4', 'mkv', 'avi', 'mov', 'wmv', 'flv', 'webm', 'm4v', '3gp'}
    music = {'mp3', 'wav', 'aac', 'flac', 'ogg', 'wma', 'm4a', 'opus'}
    archives = {'zip', 'rar', '7z', 'tar', 'gz', 'bz2', 'iso', 'xz'}
    
    if ext in docs:
        return 'documents'
    elif ext in images:
        return 'images'
    elif ext in videos:
        return 'videos'
    elif ext in music:
        return 'music'
    elif ext in archives:
        return 'archives'
    return 'others'

def add_file(
    file_name: str,
    file_size: int,
    mime_type: str,
    sha256: str,
    is_encrypted: bool,
    cloud_backend: str,
    chunks: List[Dict[str, Any]],
    category: Optional[str] = None,
    drive_owner: str = "buntha",
    folder_id: Optional[int] = None,
    uploader_email: Optional[str] = None
) -> int:
    if file_name.startswith("up_"):
        file_name = file_name[3:]
    if not category:
        category = categorize_file(file_name)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO files (
            file_name, file_size, mime_type, category, sha256,
            is_encrypted, is_favorite, is_trash, cloud_backend,
            chunk_count, chunks_data, drive_owner, folder_id, uploader_email, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        file_name,
        file_size,
        mime_type,
        category,
        sha256,
        1 if is_encrypted else 0,
        cloud_backend,
        len(chunks),
        json.dumps(chunks),
        drive_owner,
        folder_id,
        uploader_email.strip().lower() if uploader_email else None,
        now,
        now
    ))
    conn.commit()
    file_id = cursor.lastrowid
    conn.close()
    return file_id

def get_gmail_media_files(gmail: Optional[str] = None, media_type: str = "all", drive_owner: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM files WHERE is_trash = 0"
    params = []

    if gmail and gmail.strip():
        clean_email = gmail.strip().lower()
        query += " AND (uploader_email = ? OR (uploader_email IS NULL AND category IN ('videos', 'images')))"
        params.append(clean_email)
    else:
        query += " AND category IN ('videos', 'images')"

    if media_type == "video":
        query += " AND category = 'videos'"
    elif media_type == "image":
        query += " AND category = 'images'"
    else:
        query += " AND category IN ('videos', 'images')"

    if drive_owner and drive_owner != "all":
        query += " AND drive_owner = ?"
        params.append(drive_owner)

    query += " ORDER BY id DESC LIMIT 200"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    results = [dict(r) for r in rows]
    conn.close()
    return results

def create_folder(folder_name: str, drive_owner: str = "buntha", parent_id: Optional[int] = None) -> int:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO folders (folder_name, parent_id, drive_owner, is_trash, created_at, updated_at)
        VALUES (?, ?, ?, 0, ?, ?)
    """, (folder_name, parent_id, drive_owner, now, now))
    conn.commit()
    f_id = cursor.lastrowid
    conn.close()
    return f_id

def get_folders(drive_owner: str = "buntha", parent_id: Optional[int] = None, is_trash: bool = False) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM folders WHERE is_trash = ?"
    params: List[Any] = [1 if is_trash else 0]
    if drive_owner == "buntha":
        query += " AND (drive_owner = 'buntha' OR drive_owner IS NULL)"
    else:
        query += " AND drive_owner = ?"
        params.append(drive_owner)
    
    if parent_id is not None:
        query += " AND parent_id = ?"
        params.append(parent_id)
    else:
        query += " AND (parent_id IS NULL OR parent_id = 0)"
        
    query += " ORDER BY folder_name ASC"
    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def rename_folder(folder_id: int, new_name: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE folders SET folder_name = ? WHERE id = ?", (new_name, folder_id))
    conn.commit()
    conn.close()
    return True

def delete_folder(folder_id: int) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    to_delete = [folder_id]
    idx = 0
    while idx < len(to_delete):
        curr_id = to_delete[idx]
        cursor.execute("SELECT id FROM folders WHERE parent_id = ?", (curr_id,))
        for row in cursor.fetchall():
            to_delete.append(row["id"])
        idx += 1
    placeholders = ",".join("?" for _ in to_delete)
    cursor.execute(f"DELETE FROM folders WHERE id IN ({placeholders})", to_delete)
    cursor.execute(f"DELETE FROM files WHERE folder_id IN ({placeholders})", to_delete)
    conn.commit()
    conn.close()
    return True

def rename_file(file_id: int, new_name: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE files SET file_name = ? WHERE id = ?", (new_name, file_id))
    conn.commit()
    conn.close()
    return True

def update_folder_tree_drive(cursor, folder_ids: List[int], new_drive: str):
    tree = list(folder_ids)
    idx = 0
    while idx < len(tree):
        curr_id = tree[idx]
        cursor.execute("SELECT id FROM folders WHERE parent_id = ?", (curr_id,))
        for row in cursor.fetchall():
            tree.append(row["id"])
        idx += 1
    placeholders = ",".join("?" for _ in tree)
    cursor.execute(f"UPDATE folders SET drive_owner = ? WHERE id IN ({placeholders})", [new_drive] + tree)
    cursor.execute(f"UPDATE files SET drive_owner = ? WHERE folder_id IN ({placeholders})", [new_drive] + tree)

def move_files_to_folder(file_ids: List[int], target_folder_id: Optional[int], target_drive: Optional[str] = None) -> bool:
    if not file_ids:
        return False
    conn = get_connection()
    cursor = conn.cursor()
    if not target_drive and target_folder_id is not None:
        cursor.execute("SELECT drive_owner FROM folders WHERE id = ?", (target_folder_id,))
        row = cursor.fetchone()
        if row and row["drive_owner"]:
            target_drive = row["drive_owner"]
    placeholders = ",".join("?" for _ in file_ids)
    if target_drive:
        cursor.execute(f"UPDATE files SET folder_id = ?, drive_owner = ? WHERE id IN ({placeholders})", [target_folder_id, target_drive] + list(file_ids))
    else:
        cursor.execute(f"UPDATE files SET folder_id = ? WHERE id IN ({placeholders})", [target_folder_id] + list(file_ids))
    conn.commit()
    conn.close()
    return True

def is_descendant_folder(cursor, folder_id: int, potential_ancestor_id: int) -> bool:
    curr = folder_id
    visited = set()
    while curr and curr not in visited:
        visited.add(curr)
        if curr == potential_ancestor_id:
            return True
        cursor.execute("SELECT parent_id FROM folders WHERE id = ?", (curr,))
        row = cursor.fetchone()
        if not row or not row["parent_id"]:
            break
        curr = row["parent_id"]
    return False

def move_folders_to_folder(folder_ids: List[int], target_parent_id: Optional[int], target_drive: Optional[str] = None) -> bool:
    if not folder_ids:
        return False
    conn = get_connection()
    cursor = conn.cursor()
    
    if not target_drive and target_parent_id is not None:
        cursor.execute("SELECT drive_owner FROM folders WHERE id = ?", (target_parent_id,))
        row = cursor.fetchone()
        if row and row["drive_owner"]:
            target_drive = row["drive_owner"]

    valid_ids = []
    for fid in folder_ids:
        if target_parent_id is not None:
            if fid == target_parent_id:
                continue
            if is_descendant_folder(cursor, target_parent_id, fid):
                continue
        valid_ids.append(fid)

    if not valid_ids:
        conn.close()
        return False

    placeholders = ",".join("?" for _ in valid_ids)
    cursor.execute(f"UPDATE folders SET parent_id = ? WHERE id IN ({placeholders})", [target_parent_id] + list(valid_ids))
    
    if target_drive:
        update_folder_tree_drive(cursor, valid_ids, target_drive)

    conn.commit()
    conn.close()
    return True

def copy_file_record(cursor, file_id: int, target_folder_id: Optional[int] = None, target_drive: Optional[str] = None) -> Optional[int]:
    cursor.execute("SELECT * FROM files WHERE id = ?", (file_id,))
    row = cursor.fetchone()
    if not row:
        return None
    d = dict(row)
    orig_name = d["file_name"]
    same_location = (d.get("folder_id") == target_folder_id) and (target_drive is None or target_drive == d.get("drive_owner"))
    if same_location:
        if "." in orig_name:
            base, ext = orig_name.rsplit(".", 1)
            new_name = f"{base} - Copy.{ext}"
        else:
            new_name = f"{orig_name} - Copy"
    else:
        new_name = orig_name
    
    new_drive = target_drive or d.get("drive_owner", "buntha")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        INSERT INTO files (
            file_name, file_size, mime_type, category, sha256,
            is_encrypted, is_favorite, is_trash, cloud_backend,
            chunk_count, chunks_data, drive_owner, folder_id, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?)
    """, (
        new_name,
        d["file_size"],
        d["mime_type"],
        d["category"],
        d["sha256"],
        d["is_encrypted"],
        d["is_favorite"],
        d["cloud_backend"],
        d["chunk_count"],
        d["chunks_data"],
        new_drive,
        target_folder_id,
        now,
        now
    ))
    return cursor.lastrowid

def copy_folder_recursive(cursor, folder_id: int, target_parent_id: Optional[int] = None, target_drive: Optional[str] = None) -> Optional[int]:
    cursor.execute("SELECT * FROM folders WHERE id = ?", (folder_id,))
    row = cursor.fetchone()
    if not row:
        return None
    d = dict(row)
    orig_name = d["folder_name"]
    same_location = (d.get("parent_id") == target_parent_id) and (target_drive is None or target_drive == d.get("drive_owner"))
    if same_location:
        new_folder_name = f"{orig_name} - Copy"
    else:
        new_folder_name = orig_name
    new_drive = target_drive or d.get("drive_owner", "buntha")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute("""
        INSERT INTO folders (folder_name, parent_id, drive_owner, is_trash, created_at, updated_at)
        VALUES (?, ?, ?, 0, ?, ?)
    """, (new_folder_name, target_parent_id, new_drive, now, now))
    new_folder_id = cursor.lastrowid

    cursor.execute("SELECT id FROM files WHERE folder_id = ? AND is_trash = 0", (folder_id,))
    file_rows = cursor.fetchall()
    for fr in file_rows:
        copy_file_record(cursor, fr["id"], target_folder_id=new_folder_id, target_drive=new_drive)

    cursor.execute("SELECT id FROM folders WHERE parent_id = ? AND is_trash = 0", (folder_id,))
    sub_rows = cursor.fetchall()
    for sr in sub_rows:
        copy_folder_recursive(cursor, sr["id"], target_parent_id=new_folder_id, target_drive=new_drive)

    return new_folder_id

def copy_files_to_folder(file_ids: List[int], target_folder_id: Optional[int], target_drive: Optional[str] = None) -> int:
    if not file_ids:
        return 0
    conn = get_connection()
    cursor = conn.cursor()
    if not target_drive and target_folder_id is not None:
        cursor.execute("SELECT drive_owner FROM folders WHERE id = ?", (target_folder_id,))
        row = cursor.fetchone()
        if row and row["drive_owner"]:
            target_drive = row["drive_owner"]
    copied = 0
    for fid in file_ids:
        if copy_file_record(cursor, fid, target_folder_id, target_drive):
            copied += 1
    conn.commit()
    conn.close()
    return copied

def copy_folders_to_folder(folder_ids: List[int], target_parent_id: Optional[int], target_drive: Optional[str] = None) -> int:
    if not folder_ids:
        return 0
    conn = get_connection()
    cursor = conn.cursor()
    if not target_drive and target_parent_id is not None:
        cursor.execute("SELECT drive_owner FROM folders WHERE id = ?", (target_parent_id,))
        row = cursor.fetchone()
        if row and row["drive_owner"]:
            target_drive = row["drive_owner"]
    copied = 0
    for fid in folder_ids:
        if target_parent_id is not None:
            if fid == target_parent_id or is_descendant_folder(cursor, target_parent_id, fid):
                continue
        if copy_folder_recursive(cursor, fid, target_parent_id, target_drive):
            copied += 1
    conn.commit()
    conn.close()
    return copied

def get_files(
    category: Optional[str] = None,
    drive_owner: Optional[str] = None,
    search_query: Optional[str] = None,
    is_trash: bool = False,
    is_favorite: Optional[bool] = None,
    folder_id: Optional[int] = None,
    sort_by: str = "date",
    sort_desc: bool = True
) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    
    query = "SELECT * FROM files WHERE is_trash = ?"
    params: List[Any] = [1 if is_trash else 0]
    
    if drive_owner and not is_trash:
        if drive_owner == "buntha":
            query += " AND (drive_owner = 'buntha' OR drive_owner IS NULL)"
        else:
            query += " AND drive_owner = ?"
            params.append(drive_owner)

    if category and category not in ["all", "buntha", "vuochlin", "mercy", "trash", "favorites"] and not is_trash:
        query += " AND category = ?"
        params.append(category)
        
    if is_favorite is not None and not is_trash:
        query += " AND is_favorite = ?"
        params.append(1 if is_favorite else 0)

    if not is_trash and not search_query and category not in ["favorites", "trash"]:
        if folder_id is not None:
            query += " AND folder_id = ?"
            params.append(folder_id)
        else:
            query += " AND (folder_id IS NULL OR folder_id = 0)"
        
    if search_query:
        query += " AND file_name LIKE ?"
        params.append(f"%{search_query}%")
        
    # Sorting
    order_col = "created_at"
    if sort_by == "name":
        order_col = "file_name COLLATE NOCASE"
    elif sort_by == "size":
        order_col = "file_size"
        
    order_dir = "DESC" if sort_desc else "ASC"
    query += f" ORDER BY {order_col} {order_dir}"
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    
    result = []
    for r in rows:
        d = dict(r)
        if d.get("chunks_data"):
            try:
                d["chunks"] = json.loads(d["chunks_data"])
            except Exception:
                d["chunks"] = []
        else:
            d["chunks"] = []
        result.append(d)
        
    conn.close()
    return result

def get_file_by_id(file_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM files WHERE id = ?", (file_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        d = dict(row)
        if d.get("chunks_data"):
            try:
                d["chunks"] = json.loads(d["chunks_data"])
            except Exception:
                d["chunks"] = []
        else:
            d["chunks"] = []
        return d
    return None

def toggle_favorite(file_id: int) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT is_favorite FROM files WHERE id = ?", (file_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False
    new_fav = 0 if row["is_favorite"] == 1 else 1
    cursor.execute("UPDATE files SET is_favorite = ? WHERE id = ?", (new_fav, file_id))
    conn.commit()
    conn.close()
    return bool(new_fav)

def move_to_trash(file_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE files SET is_trash = 1 WHERE id = ?", (file_id,))
    conn.commit()
    conn.close()

def restore_from_trash(file_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE files SET is_trash = 0 WHERE id = ?", (file_id,))
    conn.commit()
    conn.close()

def delete_permanently(file_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM files WHERE id = ?", (file_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None
    file_dict = dict(row)
    cursor.execute("DELETE FROM files WHERE id = ?", (file_id,))
    conn.commit()
    conn.close()
    return file_dict

def empty_trash() -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM files WHERE is_trash = 1")
    rows = cursor.fetchall()
    results = [dict(r) for r in rows]
    cursor.execute("DELETE FROM files WHERE is_trash = 1")
    conn.commit()
    conn.close()
    return results

def get_storage_stats() -> Dict[str, Any]:
    conn = get_connection()
    cursor = conn.cursor()
    # Total active files size (excluding trash)
    cursor.execute("SELECT COALESCE(SUM(file_size), 0) AS total_bytes, COUNT(id) AS file_count FROM files WHERE is_trash = 0")
    row = cursor.fetchone()
    total_bytes = row["total_bytes"] if row else 0
    file_count = row["file_count"] if row else 0
    
    # Trash stats
    cursor.execute("SELECT COALESCE(SUM(file_size), 0) AS trash_bytes, COUNT(id) AS trash_count FROM files WHERE is_trash = 1")
    t_row = cursor.fetchone()
    trash_bytes = t_row["trash_bytes"] if t_row else 0
    trash_count = t_row["trash_count"] if t_row else 0
    
    # Per-drive stats
    try:
        cursor.execute("SELECT COALESCE(SUM(file_size), 0) AS bytes FROM files WHERE is_trash = 0 AND (drive_owner = 'buntha' OR drive_owner IS NULL)")
        buntha_bytes = cursor.fetchone()["bytes"]
        cursor.execute("SELECT COALESCE(SUM(file_size), 0) AS bytes FROM files WHERE is_trash = 0 AND drive_owner = 'vuochlin'")
        vuochlin_bytes = cursor.fetchone()["bytes"]
        cursor.execute("SELECT COALESCE(SUM(file_size), 0) AS bytes FROM files WHERE is_trash = 0 AND drive_owner = 'mercy'")
        mercy_bytes = cursor.fetchone()["bytes"]
    except Exception:
        buntha_bytes = total_bytes
        vuochlin_bytes = 0
        mercy_bytes = 0

    conn.close()
    return {
        "used_bytes": total_bytes,
        "file_count": file_count,
        "trash_bytes": trash_bytes,
        "trash_count": trash_count,
        "buntha_bytes": buntha_bytes,
        "vuochlin_bytes": vuochlin_bytes,
        "mercy_bytes": mercy_bytes
    }

def rename_file(file_id: int, new_name: str):
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("UPDATE files SET file_name = ?, updated_at = ? WHERE id = ?", (new_name, now, file_id))
    conn.commit()
    conn.close()

def get_db_settings() -> Dict[str, Any]:
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT)")
        cursor.execute("SELECT key, value FROM app_settings")
        rows = cursor.fetchall()
        settings = {}
        for r in rows:
            try:
                settings[r["key"]] = json.loads(r["value"])
            except Exception:
                settings[r["key"]] = r["value"]
        conn.close()
        return settings
    except Exception:
        return {}

def save_db_settings(settings: Dict[str, Any]) -> bool:
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT)")
        for k, v in settings.items():
            cursor.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)", (k, json.dumps(v, ensure_ascii=False)))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error saving settings to db: {e}")
        return False

def record_telegram_chat(chat_id: str, title: str = "", username: str = ""):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            INSERT INTO telegram_chats (chat_id, title, username, last_active)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                title = COALESCE(NULLIF(excluded.title, ''), telegram_chats.title),
                username = COALESCE(NULLIF(excluded.username, ''), telegram_chats.username),
                last_active = excluded.last_active
        """, (str(chat_id), title, username, now))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error recording telegram chat: {e}")

def get_recent_telegram_chats() -> List[Dict[str, Any]]:
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM telegram_chats ORDER BY last_active DESC LIMIT 20")
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows
    except Exception:
        return []

def update_telegram_chat_context(chat_id: str, current_drive: str, current_folder_id: Optional[int] = None):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE telegram_chats
            SET current_drive = ?, current_folder_id = ?
            WHERE chat_id = ?
        """, (current_drive, current_folder_id, str(chat_id)))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error updating telegram chat context: {e}")

# Initialize database immediately on module import
init_db()

