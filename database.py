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
    cursor.execute("UPDATE files SET file_name = SUBSTR(file_name, 4) WHERE file_name LIKE 'up_%'")
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
    drive_owner: str = "buntha"
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
            chunk_count, chunks_data, drive_owner, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?, ?, ?, ?, ?, ?)
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
        now,
        now
    ))
    conn.commit()
    file_id = cursor.lastrowid
    conn.close()
    return file_id

def get_files(
    category: Optional[str] = None,
    drive_owner: Optional[str] = None,
    search_query: Optional[str] = None,
    is_trash: bool = False,
    is_favorite: Optional[bool] = None,
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

    if category and category not in ["all", "buntha", "vuochlin", "trash", "favorites"] and not is_trash:
        query += " AND category = ?"
        params.append(category)
        
    if is_favorite is not None and not is_trash:
        query += " AND is_favorite = ?"
        params.append(1 if is_favorite else 0)
        
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
    except Exception:
        buntha_bytes = total_bytes
        vuochlin_bytes = 0

    conn.close()
    return {
        "used_bytes": total_bytes,
        "file_count": file_count,
        "trash_bytes": trash_bytes,
        "trash_count": trash_count,
        "buntha_bytes": buntha_bytes,
        "vuochlin_bytes": vuochlin_bytes
    }

def rename_file(file_id: int, new_name: str):
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("UPDATE files SET file_name = ?, updated_at = ? WHERE id = ?", (new_name, now, file_id))
    conn.commit()
    conn.close()

# Initialize database immediately on module import
init_db()
