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
    folder_id: Optional[int] = None
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
            chunk_count, chunks_data, drive_owner, folder_id, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?, ?, ?, ?, ?, ?, ?)
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
        now,
        now
    ))
    conn.commit()
    file_id = cursor.lastrowid
    conn.close()
    return file_id

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

def update_folder_contents_drive(cursor, folder_id: int, new_drive: str):
    cursor.execute("UPDATE files SET drive_owner = ? WHERE folder_id = ?", (new_drive, folder_id))
    cursor.execute("SELECT id FROM folders WHERE parent_id = ?", (folder_id,))
    child_ids = [r["id"] for r in cursor.fetchall()]
    if child_ids:
        placeholders = ",".join("?" for _ in child_ids)
        cursor.execute(f"UPDATE folders SET drive_owner = ? WHERE id IN ({placeholders})", [new_drive] + child_ids)
        for cid in child_ids:
            update_folder_contents_drive(cursor, cid, new_drive)

def move_files_to_folder(file_ids: List[int], target_folder_id: Optional[int], target_drive: Optional[str] = None) -> bool:
    if not file_ids:
        return False
    conn = get_connection()
    cursor = conn.cursor()
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
    if target_drive:
        cursor.execute(f"UPDATE folders SET parent_id = ?, drive_owner = ? WHERE id IN ({placeholders})", [target_parent_id, target_drive] + list(valid_ids))
        for vid in valid_ids:
            update_folder_contents_drive(cursor, vid, target_drive)
    else:
        cursor.execute(f"UPDATE folders SET parent_id = ? WHERE id IN ({placeholders})", [target_parent_id] + list(valid_ids))
    conn.commit()
    conn.close()
    return True

def copy_file(file_id: int, target_folder_id: Optional[int] = None, target_drive: Optional[str] = None) -> Optional[int]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM files WHERE id = ?", (file_id,))
    f = cursor.fetchone()
    if not f:
        conn.close()
        return None

    orig_name = f["file_name"]
    dest_drive = target_drive if target_drive else f["drive_owner"]
    dest_folder = target_folder_id if target_folder_id is not None else f["folder_id"]

    new_name = orig_name
    if dest_drive == f["drive_owner"] and dest_folder == f["folder_id"]:
        if "." in orig_name:
            parts = orig_name.rsplit(".", 1)
            new_name = f"{parts[0]} - Copy.{parts[1]}"
        else:
            new_name = f"{orig_name} - Copy"

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        INSERT INTO files (
            file_name, file_size, mime_type, category, sha256,
            is_encrypted, is_favorite, is_trash, cloud_backend,
            chunk_count, chunks_data, drive_owner, folder_id,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?, ?, ?, ?, ?, ?, ?)
    """, (
        new_name, f["file_size"], f["mime_type"], f["category"], f["sha256"],
        f["is_encrypted"], f["cloud_backend"], f["chunk_count"], f["chunks_data"],
        dest_drive, dest_folder, now, now
    ))
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return new_id

def copy_folder(folder_id: int, target_parent_id: Optional[int] = None, target_drive: Optional[str] = None) -> Optional[int]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM folders WHERE id = ?", (folder_id,))
    folder = cursor.fetchone()
    if not folder:
        conn.close()
        return None

    dest_drive = target_drive if target_drive else folder["drive_owner"]
    dest_parent = target_parent_id if target_parent_id is not None else folder["parent_id"]

    orig_name = folder["folder_name"]
    new_name = orig_name
    if dest_drive == folder["drive_owner"] and dest_parent == folder["parent_id"]:
        new_name = f"{orig_name} - Copy"

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        INSERT INTO folders (folder_name, parent_id, drive_owner, is_trash, created_at, updated_at)
        VALUES (?, ?, ?, 0, ?, ?)
    """, (new_name, dest_parent, dest_drive, now, now))
    new_folder_id = cursor.lastrowid

    cursor.execute("SELECT id FROM files WHERE folder_id = ? AND is_trash = 0", (folder_id,))
    child_file_ids = [r["id"] for r in cursor.fetchall()]
    cursor.execute("SELECT id FROM folders WHERE parent_id = ? AND is_trash = 0", (folder_id,))
    child_folder_ids = [r["id"] for r in cursor.fetchall()]
    conn.commit()
    conn.close()

    for cfid in child_file_ids:
        copy_file(cfid, target_folder_id=new_folder_id, target_drive=dest_drive)

    for cfold_id in child_folder_ids:
        copy_folder(cfold_id, target_parent_id=new_folder_id, target_drive=dest_drive)

    return new_folder_id

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
        return True
    except Exception as e:
        print(f"Error saving settings to db: {e}")
        return False

# Initialize database immediately on module import
init_db()
