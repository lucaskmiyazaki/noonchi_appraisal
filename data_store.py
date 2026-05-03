from __future__ import annotations

import csv
import json
import sqlite3
import threading
import uuid as _uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
MEETING_AUDIO_DIR = DATA_DIR / "meeting_audio"
JSON_MEETING_TRANSCRIPT_DIR = DATA_DIR / "meeting_transcript"
JSON_INTENTS_DIR = DATA_DIR / "intent_json"
JSON_REFLECTIONS_DIR = DATA_DIR / "reflection_json"
TRAINING_AUDIO_DIR = DATA_DIR / "training_audio"
UPLOAD_DIR = MEETING_AUDIO_DIR
AUDIO_DATA_DIR = DATA_DIR
JSON_AUDIO_RECORDS_DIR = JSON_MEETING_TRANSCRIPT_DIR
LEGACY_DB_CSV_PATH = DATA_DIR / "db.csv"
LEGACY_AUDIOS_CSV_PATH = DATA_DIR / "audios.csv"
REFLECTIONS_CSV_PATH = DATA_DIR / "reflections.csv"
INTENTS_CSV_PATH = DATA_DIR / "intents.csv"
JOURNAL_ENTRIES_CSV_PATH = DATA_DIR / "journal_entries.csv"
MEETINGS_CSV_PATH = DATA_DIR / "meetings.csv"
TRAINING_CSV_PATH = DATA_DIR / "training.csv"
USERS_CSV_PATH = DATA_DIR / "users.csv"
DB_PATH = DATA_DIR / "codesign2.db"

USERS_CSV_FIELDNAMES = [
    "id", "username", "name",
    "nudge_tone_difference", "nudge_elevation", "nudge_unclear_intent",
    "nudge_excellent_tone", "nudge_need_for_clarification",
]
REFLECTION_DB_FIELDNAMES = [
    "id", "user_id", "reflection_tree_file", "startms", "endms",
    "practice", "meeting_id", "tree_type", "has_journaling",
]
TRAINING_CSV_FIELDNAMES = [
    "training_id", "created_at", "meeting_id", "user_id", "reflection_id",
    "type", "valence", "arousal", "dominance", "done", "training_files",
    "transcription", "summary", "suggestions", "tree_type", "startms", "endms",
]
INTENTS_CSV_FIELDNAMES = ["intent_filename", "user_id", "startms", "endms", "meeting_id"]
JOURNAL_ENTRIES_CSV_FIELDNAMES = ["reflection_id", "journal_entry"]
MEETINGS_CSV_FIELDNAMES = [
    "id", "user_id", "session_name", "display_name", "safe_session_name",
    "original_name", "audio_filename", "transcript_file", "uploaded_at",
    "duration", "segment_count", "intent_filename",
]
AUDIO_RECORD_REQUIRED_KEYS = {"id", "audioUrl", "audioFilename", "transcript"}

# ---------------------------------------------------------------------------
# Database abstraction layer
#
# All SQL is isolated in this section. To migrate to PostgreSQL:
#   1. Replace `import sqlite3` with `import psycopg2 as sqlite3` (or psycopg3)
#   2. Update _db_connect() to open a PostgreSQL connection
#   3. Replace placeholder '?' with '%s' in every SQL string
#   4. Remove check_same_thread=False (not a PG concept)
#   5. Replace executescript() with execute() calls inside a transaction
# ---------------------------------------------------------------------------

_local = threading.local()


def _db_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def get_db() -> sqlite3.Connection:
    """Return a thread-local database connection."""
    if not getattr(_local, "conn", None):
        _local.conn = _db_connect()
    return _local.conn


def _db_execute(sql: str, params: tuple = ()) -> sqlite3.Cursor:
    return get_db().execute(sql, params)


def _db_commit() -> None:
    get_db().commit()


def _create_tables() -> None:
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            name TEXT DEFAULT '',
            nudge_tone_difference TEXT DEFAULT 'false',
            nudge_elevation TEXT DEFAULT 'false',
            nudge_unclear_intent TEXT DEFAULT 'false',
            nudge_excellent_tone TEXT DEFAULT 'false',
            nudge_need_for_clarification TEXT DEFAULT 'false'
        );
        CREATE TABLE IF NOT EXISTS meetings (
            id TEXT PRIMARY KEY,
            user_id TEXT REFERENCES users(id),
            session_name TEXT DEFAULT '',
            display_name TEXT DEFAULT '',
            safe_session_name TEXT DEFAULT '',
            original_name TEXT DEFAULT '',
            audio_filename TEXT DEFAULT '',
            transcript_file TEXT DEFAULT '',
            uploaded_at TEXT DEFAULT '',
            duration TEXT DEFAULT '',
            segment_count TEXT DEFAULT '',
            intent_filename TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS reflections (
            id TEXT PRIMARY KEY,
            user_id TEXT REFERENCES users(id),
            reflection_tree_file TEXT DEFAULT '',
            startms TEXT DEFAULT '',
            endms TEXT DEFAULT '',
            practice TEXT DEFAULT 'null',
            meeting_id TEXT REFERENCES meetings(id),
            tree_type TEXT DEFAULT '',
            has_journaling TEXT DEFAULT 'false'
        );
        CREATE TABLE IF NOT EXISTS journal_entries (
            reflection_id TEXT PRIMARY KEY REFERENCES reflections(id),
            journal_entry TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS training (
            training_id TEXT PRIMARY KEY,
            created_at TEXT DEFAULT '',
            meeting_id TEXT REFERENCES meetings(id),
            user_id TEXT REFERENCES users(id),
            reflection_id TEXT REFERENCES reflections(id),
            type TEXT DEFAULT 'valence',
            valence TEXT DEFAULT '',
            arousal TEXT DEFAULT '',
            dominance TEXT DEFAULT '',
            done TEXT DEFAULT 'false',
            training_files TEXT DEFAULT '',
            transcription TEXT DEFAULT '',
            summary TEXT DEFAULT '',
            suggestions TEXT DEFAULT '',
            tree_type TEXT DEFAULT '',
            startms TEXT DEFAULT '',
            endms TEXT DEFAULT ''
        );
    """)
    db.commit()


# ---------------------------------------------------------------------------
# CSV helpers (internal — used only during one-time migration)
# ---------------------------------------------------------------------------

def _read_csv_rows(csv_path: Path):
    if not csv_path.exists():
        return [], []
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader), list(reader.fieldnames or [])


def _write_csv_rows(csv_path: Path, rows, fieldnames) -> None:
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(fieldnames))
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def _backup_csv(path: Path) -> None:
    bak = path.with_suffix(path.suffix + ".bak")
    try:
        path.rename(bak)
    except OSError:
        pass


def _reflection_csv_path() -> Path:
    if REFLECTIONS_CSV_PATH.exists():
        return REFLECTIONS_CSV_PATH
    if LEGACY_DB_CSV_PATH.exists():
        try:
            LEGACY_DB_CSV_PATH.rename(REFLECTIONS_CSV_PATH)
        except OSError:
            REFLECTIONS_CSV_PATH.write_text(LEGACY_DB_CSV_PATH.read_text(encoding="utf-8"), encoding="utf-8")
            LEGACY_DB_CSV_PATH.unlink()
    return REFLECTIONS_CSV_PATH


# ---------------------------------------------------------------------------
# CSV → SQLite migration (runs once at startup, idempotent)
# ---------------------------------------------------------------------------

def _migrate_csv_to_sqlite() -> None:
    db = get_db()
    # Disable FK enforcement during bulk import so we don't fail on orphaned rows
    db.execute("PRAGMA foreign_keys=OFF")

    # users
    if USERS_CSV_PATH.exists():
        rows, _ = _read_csv_rows(USERS_CSV_PATH)
        for row in rows:
            uid = str(row.get("id", "") or "").strip()
            uname = str(row.get("username", "") or "").strip().lower()
            if not uid or not uname:
                continue
            db.execute(
                "INSERT OR IGNORE INTO users VALUES (?,?,?,?,?,?,?,?)",
                (uid, uname, str(row.get("name","") or ""),
                 str(row.get("nudge_tone_difference","false") or "false"),
                 str(row.get("nudge_elevation","false") or "false"),
                 str(row.get("nudge_unclear_intent","false") or "false"),
                 str(row.get("nudge_excellent_tone","false") or "false"),
                 str(row.get("nudge_need_for_clarification","false") or "false")),
            )
        db.commit()
        _backup_csv(USERS_CSV_PATH)

    # meetings (handle audios.csv → meetings.csv rename)
    if not MEETINGS_CSV_PATH.exists() and LEGACY_AUDIOS_CSV_PATH.exists():
        try:
            LEGACY_AUDIOS_CSV_PATH.rename(MEETINGS_CSV_PATH)
        except OSError:
            MEETINGS_CSV_PATH.write_text(LEGACY_AUDIOS_CSV_PATH.read_text(encoding="utf-8"), encoding="utf-8")
            LEGACY_AUDIOS_CSV_PATH.unlink()
    if MEETINGS_CSV_PATH.exists():
        rows, _ = _read_csv_rows(MEETINGS_CSV_PATH)
        for row in rows:
            mid = str(row.get("id","") or "").strip()
            if not mid:
                continue
            db.execute(
                "INSERT OR IGNORE INTO meetings VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (mid, str(row.get("user_id","") or ""), str(row.get("session_name","") or ""),
                 str(row.get("display_name","") or ""), str(row.get("safe_session_name","") or ""),
                 str(row.get("original_name","") or ""), str(row.get("audio_filename","") or ""),
                 str(row.get("transcript_file","") or ""), str(row.get("uploaded_at","") or ""),
                 str(row.get("duration","") or ""), str(row.get("segment_count","") or ""),
                 str(row.get("intent_filename","") or "")),
            )
        db.commit()
        _backup_csv(MEETINGS_CSV_PATH)

    # reflections
    refl_csv = _reflection_csv_path()
    if refl_csv.exists():
        rows, _ = _read_csv_rows(refl_csv)
        for row in rows:
            rid = str(row.get("id","") or "").strip() or _uuid.uuid4().hex
            db.execute(
                "INSERT OR IGNORE INTO reflections VALUES (?,?,?,?,?,?,?,?,?)",
                (rid, str(row.get("user_id","") or ""), str(row.get("reflection_tree_file","") or ""),
                 str(row.get("startms","") or ""), str(row.get("endms","") or ""),
                 normalize_practice_value(row.get("practice","null")),
                 str(row.get("meeting_id","") or ""), str(row.get("tree_type","") or ""),
                 str(row.get("has_journaling","false") or "false")),
            )
        db.commit()
        _backup_csv(refl_csv)

    # journal_entries
    if JOURNAL_ENTRIES_CSV_PATH.exists():
        rows, _ = _read_csv_rows(JOURNAL_ENTRIES_CSV_PATH)
        for row in rows:
            rid = str(row.get("reflection_id","") or "").strip()
            if not rid:
                rtf = str(row.get("reflection_tree_file","") or "").strip()
                if rtf:
                    r2 = db.execute("SELECT id FROM reflections WHERE reflection_tree_file=?", (rtf,)).fetchone()
                    if r2:
                        rid = r2[0]
            if not rid:
                continue
            db.execute(
                "INSERT OR REPLACE INTO journal_entries VALUES (?,?)",
                (rid, str(row.get("journal_entry","") or "")),
            )
        db.commit()
        _backup_csv(JOURNAL_ENTRIES_CSV_PATH)

    # training
    if TRAINING_CSV_PATH.exists():
        rows, _ = _read_csv_rows(TRAINING_CSV_PATH)
        for row in rows:
            tid = str(row.get("training_id","") or "").strip()
            if not tid:
                continue
            db.execute(
                "INSERT OR IGNORE INTO training VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (tid, str(row.get("created_at","") or ""), str(row.get("meeting_id","") or ""),
                 str(row.get("user_id","") or ""), str(row.get("reflection_id","") or ""),
                 normalize_training_type_str(row.get("type","valence")),
                 str(row.get("valence","") or ""), str(row.get("arousal","") or ""),
                 str(row.get("dominance","") or ""), normalize_done_str(row.get("done","false")),
                 str(row.get("training_files","") or ""), str(row.get("transcription","") or ""),
                 str(row.get("summary","") or ""), str(row.get("suggestions","") or ""),
                 str(row.get("tree_type","") or ""), str(row.get("startms","") or ""),
                 str(row.get("endms","") or "")),
            )
        db.commit()
        _backup_csv(TRAINING_CSV_PATH)

    db.execute("PRAGMA foreign_keys=ON")
    db.commit()


# ---------------------------------------------------------------------------
# ensure_data_layout
# ---------------------------------------------------------------------------

def _tree_has_journaling_node(tree) -> bool:
    """Return True if any node in the reflection tree has type 'journaling'."""
    nodes = tree.get("nodes") or {}
    if isinstance(nodes, dict):
        return any(
            str(n.get("type", "") or "").strip().lower() == "journaling"
            for n in nodes.values()
            if isinstance(n, dict)
        )
    return False


def _fix_has_journaling_flags() -> None:
    """Set has_journaling='true' for any reflection whose JSON tree has a journaling node.
    Runs at startup; idempotent — only touches rows not already marked true."""
    rows = _db_execute(
        "SELECT id, reflection_tree_file FROM reflections WHERE has_journaling != 'true'"
    ).fetchall()
    changed = False
    for row in rows:
        rtf = row["reflection_tree_file"] or ""
        if not rtf or not rtf.endswith(".json"):
            continue
        path = JSON_REFLECTIONS_DIR / rtf
        if not path.exists():
            continue
        try:
            tree = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if _tree_has_journaling_node(tree):
            _db_execute("UPDATE reflections SET has_journaling='true' WHERE id=?", (row["id"],))
            changed = True
    if changed:
        _db_commit()


def ensure_data_layout() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MEETING_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    JSON_MEETING_TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    JSON_INTENTS_DIR.mkdir(parents=True, exist_ok=True)
    JSON_REFLECTIONS_DIR.mkdir(parents=True, exist_ok=True)
    TRAINING_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    _create_tables()
    _pre_migrate_folder_structure()
    _pre_migrate_move_stray_audio_files()
    _pre_migrate_intents_to_meetings_csv()
    _pre_migrate_audio_records_to_csv()
    _migrate_csv_to_sqlite()
    _fix_meeting_user_ids()
    _fix_has_journaling_flags()


# ---------------------------------------------------------------------------
# Pre-migration CSV helpers (only run before first SQLite import)
# ---------------------------------------------------------------------------

def _pre_migrate_folder_structure() -> None:
    legacy = DATA_DIR / "audio_records"
    if not (legacy.exists() and legacy.is_dir()):
        return
    JSON_MEETING_TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    for file in list(legacy.iterdir()):
        if file.is_file():
            dst = JSON_MEETING_TRANSCRIPT_DIR / file.name
            if not dst.exists():
                try:
                    file.rename(dst)
                except OSError:
                    dst.write_bytes(file.read_bytes())
                    file.unlink()
    try:
        legacy.rmdir()
    except OSError:
        pass


def _pre_migrate_move_stray_audio_files() -> None:
    audio_extensions = {".mp3", ".wav", ".m4a", ".ogg", ".webm", ".mp4", ".mpeg", ".mpga"}
    for file in DATA_DIR.iterdir():
        if file.is_file() and file.suffix.lower() in audio_extensions:
            dst = MEETING_AUDIO_DIR / file.name
            if not dst.exists():
                try:
                    file.rename(dst)
                except OSError:
                    dst.write_bytes(file.read_bytes())
                    file.unlink()


def _pre_migrate_intents_to_meetings_csv() -> None:
    if not INTENTS_CSV_PATH.exists():
        return
    raw_intent_rows, _ = _read_csv_rows(INTENTS_CSV_PATH)
    intent_by_meeting: dict[str, str] = {}
    for row in raw_intent_rows:
        mid = str(row.get("meeting_id","") or "").strip()
        fname = str(row.get("intent_filename","") or "").strip()
        if mid and fname:
            intent_by_meeting[mid] = fname
    if intent_by_meeting and MEETINGS_CSV_PATH.exists():
        meeting_rows, meeting_fieldnames = _read_csv_rows(MEETINGS_CSV_PATH)
        changed = False
        for row in meeting_rows:
            mid = str(row.get("id","") or "").strip()
            if mid in intent_by_meeting and not str(row.get("intent_filename","")).strip():
                row["intent_filename"] = intent_by_meeting[mid]
                changed = True
        if changed:
            _write_csv_rows(MEETINGS_CSV_PATH, meeting_rows, meeting_fieldnames)
    _backup_csv(INTENTS_CSV_PATH)


def _pre_migrate_audio_records_to_csv() -> None:
    # Skip if CSV or its backup exists, or if meetings table already has rows
    if MEETINGS_CSV_PATH.exists() or LEGACY_AUDIOS_CSV_PATH.exists():
        return
    if get_db().execute("SELECT COUNT(*) FROM meetings").fetchone()[0] > 0:
        return
    rows = []
    for json_file in JSON_MEETING_TRANSCRIPT_DIR.glob("*.json"):
        try:
            record = read_json(json_file)
            if is_audio_record(record):
                transcript = record.get("transcript", [])
                last_segment = transcript[-1] if transcript else {}
                rows.append({
                    "id": record.get("id",""),
                    "user_id": "",
                    "session_name": record.get("sessionName",""),
                    "display_name": record.get("displayName",""),
                    "safe_session_name": record.get("safeSessionName",""),
                    "original_name": record.get("originalName",""),
                    "audio_filename": record.get("audioFilename",""),
                    "transcript_file": json_file.name,
                    "uploaded_at": record.get("uploadedAt",""),
                    "duration": str(float(last_segment.get("end", 0.0) or 0.0)),
                    "segment_count": str(len(transcript)),
                    "intent_filename": "",
                })
        except (OSError, json.JSONDecodeError):
            continue
    if rows:
        _write_csv_rows(MEETINGS_CSV_PATH, rows, MEETINGS_CSV_FIELDNAMES)


def _fix_meeting_user_ids() -> None:
    rows = _db_execute(
        "SELECT id, display_name FROM meetings WHERE user_id IS NULL OR user_id=''"
    ).fetchall()
    changed = False
    for row in rows:
        display_name = str(row["display_name"] or "")
        if " - " not in display_name:
            continue
        suffix = display_name.rsplit(" - ", 1)[-1].strip()
        if not suffix:
            continue
        user = _db_execute(
            "SELECT id FROM users WHERE LOWER(username)=? OR LOWER(username)=?",
            (suffix.lower(), suffix.lower()),
        ).fetchone()
        if user:
            _db_execute("UPDATE meetings SET user_id=? WHERE id=?", (user["id"], row["id"]))
            changed = True
    if changed:
        _db_commit()


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

def normalize_practice_value(value) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in {"done", "todo", "null"} else "null"


def normalize_done_str(value) -> str:
    return "true" if str(value or "").strip().lower() in {"true", "1", "yes", "done"} else "false"


def normalize_training_type_str(value) -> str:
    return "arousal" if str(value or "").strip().lower() == "arousal" else "valence"


# ---------------------------------------------------------------------------
# JSON file helpers (files stay on disk, not in DB)
# ---------------------------------------------------------------------------

def reflection_csv_path() -> Path:
    return _reflection_csv_path()


def meeting_record_path(record_id: str) -> Path:
    return JSON_MEETING_TRANSCRIPT_DIR / f"{record_id}.json"


def audio_record_path(record_id: str) -> Path:
    return meeting_record_path(record_id)


def intent_file_path(filename: str) -> Path:
    return JSON_INTENTS_DIR / filename


def is_json_filename(filename: str) -> bool:
    return bool(filename) and Path(filename).suffix == ".json"


def is_intent_json_filename(filename: str) -> bool:
    return bool(filename) and str(filename).endswith(".intent.json")


def is_reflection_json_filename(filename: str) -> bool:
    name = str(filename or "")
    return bool(name) and name.startswith("reflection_") and name.endswith(".json")


def json_storage_dir_for_filename(filename: str) -> Path:
    if is_intent_json_filename(filename):
        return JSON_INTENTS_DIR
    if is_reflection_json_filename(filename):
        return JSON_REFLECTIONS_DIR
    return JSON_AUDIO_RECORDS_DIR


def data_json_path(filename: str) -> Path:
    return json_storage_dir_for_filename(filename) / filename


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any, *, indent: int = 2, ensure_ascii: bool = True) -> None:
    path.write_text(json.dumps(payload, indent=indent, ensure_ascii=ensure_ascii), encoding="utf-8")


def iter_data_json_files():
    return sorted(
        JSON_AUDIO_RECORDS_DIR.glob("*.json"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )


def read_data_json_file(filename: str):
    if not is_json_filename(filename):
        return None
    path = data_json_path(filename)
    if not path.exists() or not path.is_file():
        return None
    return read_json(path)


def write_data_json_file(filename: str, payload: Any, *, indent: int = 2, ensure_ascii: bool = True) -> Path:
    path = data_json_path(filename)
    write_json(path, payload, indent=indent, ensure_ascii=ensure_ascii)
    return path


def delete_data_json_file(filename: str) -> bool:
    if not is_json_filename(filename):
        return False
    path = data_json_path(filename)
    if not path.exists() or not path.is_file():
        return False
    path.unlink()
    return True


def find_data_recording_file(session_name: str, suffixes=None):
    allowed = set(suffixes or {".webm", ".ogg"})
    for file in DATA_DIR.iterdir():
        if file.name.startswith(session_name) and file.suffix in allowed:
            return file
    return None


def is_audio_record(record) -> bool:
    return isinstance(record, dict) and AUDIO_RECORD_REQUIRED_KEYS.issubset(record.keys())


# ---------------------------------------------------------------------------
# Meetings
# ---------------------------------------------------------------------------

def _row_to_meeting_dict(row) -> dict:
    return {k: (row[k] or "") for k in MEETINGS_CSV_FIELDNAMES}


def load_meeting_rows():
    rows = _db_execute("SELECT * FROM meetings").fetchall()
    return [_row_to_meeting_dict(r) for r in rows], list(MEETINGS_CSV_FIELDNAMES)


def write_meeting_rows(rows, fieldnames=None) -> None:
    db = get_db()
    db.execute("PRAGMA foreign_keys=OFF")
    db.execute("DELETE FROM meetings")
    for row in rows:
        mid = str(row.get("id","") or "").strip()
        if not mid:
            continue
        db.execute(
            "INSERT INTO meetings VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (mid, str(row.get("user_id","") or ""), str(row.get("session_name","") or ""),
             str(row.get("display_name","") or ""), str(row.get("safe_session_name","") or ""),
             str(row.get("original_name","") or ""), str(row.get("audio_filename","") or ""),
             str(row.get("transcript_file","") or ""), str(row.get("uploaded_at","") or ""),
             str(row.get("duration","") or ""), str(row.get("segment_count","") or ""),
             str(row.get("intent_filename","") or "")),
        )
    db.commit()
    db.execute("PRAGMA foreign_keys=ON")


def save_meeting(record) -> None:
    record_id = str(record.get("id",""))
    write_json(meeting_record_path(record_id), record)
    transcript = record.get("transcript", [])
    last_segment = transcript[-1] if transcript else {}
    _raw_uid = str(record.get("userId", record.get("user_id","")) or "").strip()
    user_id = _raw_uid if _raw_uid else None  # NULL passes FK; empty string does not
    existing = _db_execute("SELECT intent_filename FROM meetings WHERE id=?", (record_id,)).fetchone()
    intent_filename = existing["intent_filename"] if existing else ""
    db = get_db()
    db.execute(
        "INSERT INTO meetings VALUES (?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
        "user_id=excluded.user_id, session_name=excluded.session_name, display_name=excluded.display_name, "
        "safe_session_name=excluded.safe_session_name, original_name=excluded.original_name, "
        "audio_filename=excluded.audio_filename, transcript_file=excluded.transcript_file, "
        "uploaded_at=excluded.uploaded_at, duration=excluded.duration, segment_count=excluded.segment_count",
        (record_id, user_id, str(record.get("sessionName","")), str(record.get("displayName","")),
         str(record.get("safeSessionName","")), str(record.get("originalName","")),
         str(record.get("audioFilename","")), f"{record_id}.json",
         str(record.get("uploadedAt","")),
         str(float(last_segment.get("end", 0.0) or 0.0)),
         str(len(transcript)), intent_filename),
    )
    db.commit()


def save_audio_record(record) -> None:
    save_meeting(record)


def load_meeting(record_id):
    record_path = meeting_record_path(str(record_id or ""))
    if not record_path.exists():
        return None
    return read_json(record_path)


def load_audio_record(record_id):
    return load_meeting(record_id)


def delete_meeting(record_id) -> bool:
    record_path = meeting_record_path(str(record_id or ""))
    deleted_json = False
    if record_path.exists():
        record_path.unlink()
        deleted_json = True
    cur = _db_execute("DELETE FROM meetings WHERE id=?", (str(record_id),))
    _db_commit()
    return cur.rowcount > 0 or deleted_json


def delete_audio_record(record_id) -> bool:
    return delete_meeting(record_id)


def iter_meetings():
    rows = _db_execute("SELECT * FROM meetings").fetchall()
    records = []
    for row in rows:
        record_id = row["id"]
        if not record_id:
            continue
        transcript = []
        transcript_file = row["transcript_file"] or ""
        if transcript_file:
            t = read_data_json_file(transcript_file)
            if isinstance(t, list):
                transcript = t
            elif isinstance(t, dict):
                transcript = t.get("transcript", [])
        records.append({
            "id": record_id,
            "userId": row["user_id"] or "",
            "sessionName": row["session_name"] or "",
            "displayName": row["display_name"] or "",
            "safeSessionName": row["safe_session_name"] or "",
            "originalName": row["original_name"] or "",
            "audioFilename": row["audio_filename"] or "",
            "audioUrl": f"/uploads/{row['audio_filename'] or ''}",
            "uploadedAt": row["uploaded_at"] or "",
            "transcript": transcript,
        })
    return records


def iter_audio_records():
    return iter_meetings()


def lookup_meeting_id_by_audio_filename(audio_filename: str) -> str:
    target = str(audio_filename or "").strip()
    if not target:
        return ""
    row = _db_execute("SELECT id FROM meetings WHERE audio_filename=?", (target,)).fetchone()
    return row["id"] if row else ""


def lookup_meeting_id_by_session_name(session_name: str) -> str:
    target = str(session_name or "").strip().lower()
    if not target:
        return ""
    row = _db_execute("SELECT id FROM meetings WHERE LOWER(session_name)=?", (target,)).fetchone()
    return row["id"] if row else ""


def lookup_session_name_by_meeting_id(meeting_id: str) -> str:
    target = str(meeting_id or "").strip()
    if not target:
        return ""
    row = _db_execute("SELECT session_name FROM meetings WHERE id=?", (target,)).fetchone()
    return row["session_name"] if row else ""


def list_meeting_sessions_for_user(username: str) -> list[dict]:
    user_record = lookup_user_by_username(username)
    user_id = user_record.get("id","") if user_record else ""
    if user_id:
        rows = _db_execute(
            "SELECT session_name, display_name FROM meetings WHERE user_id=? ORDER BY session_name",
            (user_id,),
        ).fetchall()
    else:
        rows = _db_execute(
            "SELECT session_name, display_name FROM meetings ORDER BY session_name"
        ).fetchall()
    return [
        {"sessionName": r["session_name"] or "", "displayName": r["display_name"] or r["session_name"] or ""}
        for r in rows if r["session_name"]
    ]


def iter_meetings_for_username(username: str = "") -> list[dict]:
    user_id_filter = ""
    clean_username = str(username or "").strip()
    if clean_username:
        user = lookup_user_by_username(clean_username)
        user_id_filter = user.get("id","") if user else ""
    return [
        record for record in iter_meetings()
        if not user_id_filter or record.get("userId","") == user_id_filter
    ]


def enrich_meeting_user_fields(record: dict, meeting_id: str = "") -> dict:
    if not isinstance(record, dict):
        return record
    resolved_id = str(meeting_id or record.get("id","") or "").strip()
    user_id = str(record.get("userId","") or record.get("user_id","") or "").strip()
    if not user_id and resolved_id:
        row = _db_execute("SELECT user_id FROM meetings WHERE id=?", (resolved_id,)).fetchone()
        if row:
            user_id = row["user_id"] or ""
    if user_id:
        record["userId"] = user_id
        record["user_id"] = user_id
    record["username"] = lookup_username_by_user_id(user_id)
    return record


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def _row_to_user_dict(row) -> dict:
    return {k: (row[k] or "") for k in USERS_CSV_FIELDNAMES}


def load_user_rows():
    rows = _db_execute("SELECT * FROM users").fetchall()
    return [_row_to_user_dict(r) for r in rows], list(USERS_CSV_FIELDNAMES)


def write_user_rows(rows, fieldnames=None) -> None:
    db = get_db()
    db.execute("PRAGMA foreign_keys=OFF")
    db.execute("DELETE FROM users")
    for row in rows:
        uid = str(row.get("id","") or "").strip()
        uname = str(row.get("username","") or "").strip().lower()
        if not uid or not uname:
            continue
        db.execute(
            "INSERT INTO users VALUES (?,?,?,?,?,?,?,?)",
            (uid, uname, str(row.get("name","") or ""),
             str(row.get("nudge_tone_difference","false") or "false"),
             str(row.get("nudge_elevation","false") or "false"),
             str(row.get("nudge_unclear_intent","false") or "false"),
             str(row.get("nudge_excellent_tone","false") or "false"),
             str(row.get("nudge_need_for_clarification","false") or "false")),
        )
    db.commit()
    db.execute("PRAGMA foreign_keys=ON")


def lookup_user_by_id(user_id: str) -> dict | None:
    target = str(user_id or "").strip()
    if not target:
        return None
    row = _db_execute("SELECT * FROM users WHERE id=?", (target,)).fetchone()
    return _row_to_user_dict(row) if row else None


def lookup_user_by_username(username: str) -> dict | None:
    target = str(username or "").strip().lower()
    if not target:
        return None
    row = _db_execute("SELECT * FROM users WHERE LOWER(username)=?", (target,)).fetchone()
    return _row_to_user_dict(row) if row else None


def lookup_user_id_by_username(username: str) -> str:
    row = lookup_user_by_username(username)
    return row.get("id","") if row else ""


def lookup_username_by_user_id(user_id: str) -> str:
    row = lookup_user_by_id(user_id)
    return row.get("username","") if row else ""


def nudge_fieldnames() -> list[str]:
    return [f for f in USERS_CSV_FIELDNAMES if f.startswith("nudge_")]


def normalize_user_updates(updates: dict | None) -> dict:
    payload = updates or {}
    allowed = set(USERS_CSV_FIELDNAMES) - {"id"}
    normalized: dict[str, str] = {}
    for field in allowed:
        if field not in payload:
            continue
        value = payload[field]
        if field.startswith("nudge_"):
            normalized[field] = "true" if str(value).strip().lower() in {"true","1","yes","on"} else "false"
        else:
            normalized[field] = str(value).strip() if not isinstance(value, bool) else str(value).lower()
    return normalized


def create_user(username: str, name: str = "", updates: dict | None = None) -> dict:
    clean_username = str(username or "").strip()
    clean_name = str(name or "").strip() or clean_username
    if not clean_username:
        raise ValueError("username is required")
    payload = {"username": clean_username, "name": clean_name}
    payload.update(normalize_user_updates(updates))
    return save_user(payload)


def update_user(username: str, updates: dict | None = None) -> dict | None:
    existing = lookup_user_by_username(username)
    if existing is None:
        return None
    existing.update(normalize_user_updates(updates))
    return save_user(existing)


def save_user(user: dict) -> dict:
    db = get_db()
    user_id = str(user.get("id","") or "").strip()
    if not user_id:
        user_id = _uuid.uuid4().hex
        user = dict(user, id=user_id)
    username = str(user.get("username","") or "").strip().lower()
    if not username:
        raise ValueError("username is required")
    conflict = db.execute(
        "SELECT id FROM users WHERE LOWER(username)=? AND id!=?", (username, user_id)
    ).fetchone()
    if conflict:
        raise ValueError(f"username '{username}' is already taken")
    for field in nudge_fieldnames():
        if str(user.get(field,"") or "").strip() == "":
            user[field] = "false"
    db.execute(
        "INSERT INTO users VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
        "username=excluded.username, name=excluded.name, "
        "nudge_tone_difference=excluded.nudge_tone_difference, nudge_elevation=excluded.nudge_elevation, "
        "nudge_unclear_intent=excluded.nudge_unclear_intent, nudge_excellent_tone=excluded.nudge_excellent_tone, "
        "nudge_need_for_clarification=excluded.nudge_need_for_clarification",
        (user_id, username, str(user.get("name","") or ""),
         str(user.get("nudge_tone_difference","false") or "false"),
         str(user.get("nudge_elevation","false") or "false"),
         str(user.get("nudge_unclear_intent","false") or "false"),
         str(user.get("nudge_excellent_tone","false") or "false"),
         str(user.get("nudge_need_for_clarification","false") or "false")),
    )
    db.commit()
    return lookup_user_by_id(user_id) or user


# ---------------------------------------------------------------------------
# Reflections
# ---------------------------------------------------------------------------

def _row_to_reflection_dict(row) -> dict:
    meeting_id = row["meeting_id"] or ""
    return {
        "id": row["id"],
        "user_id": row["user_id"] or "",
        "reflection_tree_file": row["reflection_tree_file"] or "",
        "startms": row["startms"] or "",
        "endms": row["endms"] or "",
        "practice": normalize_practice_value(row["practice"]),
        "meeting_id": meeting_id,
        "tree_type": row["tree_type"] or "",
        "has_journaling": row["has_journaling"] or "",
        "session_name": lookup_session_name_by_meeting_id(meeting_id) if meeting_id else "",
    }


def load_reflection_db_rows():
    rows = _db_execute("SELECT * FROM reflections").fetchall()
    return [_row_to_reflection_dict(r) for r in rows], list(REFLECTION_DB_FIELDNAMES)


def write_reflection_db_rows(rows, fieldnames=None) -> None:
    db = get_db()
    db.execute("PRAGMA foreign_keys=OFF")
    db.execute("DELETE FROM reflections")
    for row in rows:
        rid = str(row.get("id","") or "").strip() or _uuid.uuid4().hex
        db.execute(
            "INSERT INTO reflections VALUES (?,?,?,?,?,?,?,?,?)",
            (rid,
             str(row.get("user_id","") or "") or None,
             str(row.get("reflection_tree_file","") or ""),
             str(row.get("startms","") or ""), str(row.get("endms","") or ""),
             normalize_practice_value(row.get("practice","null")),
             str(row.get("meeting_id","") or "") or None,
             str(row.get("tree_type","") or ""),
             str(row.get("has_journaling","") or "")),
        )
    db.commit()
    db.execute("PRAGMA foreign_keys=ON")


def list_reflection_rows_for_session(session_name: str) -> list[dict]:
    meeting_id = lookup_meeting_id_by_session_name(session_name)
    if not meeting_id:
        return []
    rows = _db_execute("SELECT * FROM reflections WHERE meeting_id=?", (meeting_id,)).fetchall()
    return [_row_to_reflection_dict(r) for r in rows]


def list_reflection_rows_for_audio(meeting_id: str) -> list[dict]:
    rows = _db_execute("SELECT * FROM reflections WHERE meeting_id=?", (meeting_id,)).fetchall()
    return [_row_to_reflection_dict(r) for r in rows]


def list_reflection_rows_for_user_session(username: str, session_name: str) -> list[dict]:
    user_record = lookup_user_by_username(username)
    user_id = user_record.get("id","") if user_record else ""
    meeting_id = lookup_meeting_id_by_session_name(session_name)
    if user_id and meeting_id:
        rows = _db_execute(
            "SELECT * FROM reflections WHERE user_id=? AND meeting_id=?", (user_id, meeting_id)
        ).fetchall()
    elif user_id:
        rows = _db_execute("SELECT * FROM reflections WHERE user_id=?", (user_id,)).fetchall()
    elif meeting_id:
        rows = _db_execute("SELECT * FROM reflections WHERE meeting_id=?", (meeting_id,)).fetchall()
    else:
        rows = _db_execute("SELECT * FROM reflections").fetchall()
    return [_row_to_reflection_dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Journal entries
# ---------------------------------------------------------------------------

def load_journal_rows():
    rows = _db_execute("SELECT * FROM journal_entries").fetchall()
    return [{"reflection_id": r["reflection_id"], "journal_entry": r["journal_entry"] or ""} for r in rows], list(JOURNAL_ENTRIES_CSV_FIELDNAMES)


def write_journal_rows(rows, fieldnames=None) -> None:
    db = get_db()
    db.execute("DELETE FROM journal_entries")
    for row in rows:
        rid = str(row.get("reflection_id","") or "").strip()
        if not rid:
            continue
        db.execute(
            "INSERT INTO journal_entries VALUES (?,?)",
            (rid, str(row.get("journal_entry","") or "")),
        )
    db.commit()


def load_journal_entry_raw(reflection_id: str) -> str:
    target = str(reflection_id or "").strip()
    if not target:
        return ""
    row = _db_execute(
        "SELECT journal_entry FROM journal_entries WHERE reflection_id=?", (target,)
    ).fetchone()
    return row["journal_entry"] if row else ""


def upsert_journal_entry_raw(reflection_id: str, journal_entry: str) -> None:
    target = str(reflection_id or "").strip()
    if not target:
        return
    _db_execute(
        "INSERT INTO journal_entries VALUES (?,?) ON CONFLICT(reflection_id) DO UPDATE SET journal_entry=excluded.journal_entry",
        (target, str(journal_entry or "")),
    )
    _db_commit()


def delete_journal_entry_row(reflection_id: str) -> bool:
    target = str(reflection_id or "").strip()
    if not target:
        return False
    cur = _db_execute("DELETE FROM journal_entries WHERE reflection_id=?", (target,))
    _db_commit()
    return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Intents (stored as intent_filename on meetings table)
# ---------------------------------------------------------------------------

def load_intent_rows():
    rows = _db_execute(
        "SELECT id, user_id, session_name, intent_filename FROM meetings WHERE intent_filename IS NOT NULL AND intent_filename!=''"
    ).fetchall()
    return [
        {"intent_filename": r["intent_filename"], "user_id": r["user_id"] or "",
         "startms": "", "endms": "", "meeting_id": r["id"], "session_name": r["session_name"] or ""}
        for r in rows
    ], list(INTENTS_CSV_FIELDNAMES)


def write_intent_rows(rows, fieldnames=None) -> None:
    for row in rows:
        mid = str(row.get("meeting_id","") or "").strip()
        fname = str(row.get("intent_filename","") or "").strip()
        if mid and fname:
            _db_execute("UPDATE meetings SET intent_filename=? WHERE id=?", (fname, mid))
    _db_commit()


def delete_intent_row(intent_file: str) -> bool:
    safe = str(intent_file or "").strip()
    if not safe:
        return False
    cur = _db_execute("UPDATE meetings SET intent_filename='' WHERE intent_filename=?", (safe,))
    _db_commit()
    return cur.rowcount > 0


def upsert_intent_reflection_row(session_name: str, intent_file: str, user_id: str = "", meeting_id: str = "") -> None:
    safe_intent = str(intent_file or "").strip()
    if not safe_intent:
        return
    target_id = str(meeting_id or "").strip()
    target_session = str(session_name or "").strip()
    if target_id:
        _db_execute("UPDATE meetings SET intent_filename=? WHERE id=?", (safe_intent, target_id))
    elif target_session:
        _db_execute("UPDATE meetings SET intent_filename=? WHERE session_name=?", (safe_intent, target_session))
    _db_commit()


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def _row_to_training_dict(row) -> dict:
    meeting_id = row["meeting_id"] or ""
    return {
        "training_id": row["training_id"],
        "created_at": row["created_at"] or "",
        "meeting_id": meeting_id,
        "user_id": row["user_id"] or "",
        "session_name": lookup_session_name_by_meeting_id(meeting_id) if meeting_id else "",
        "reflection_id": row["reflection_id"] or "",
        "type": normalize_training_type_str(row["type"]),
        "valence": row["valence"] or "",
        "arousal": row["arousal"] or "",
        "dominance": row["dominance"] or "",
        "done": normalize_done_str(row["done"]),
        "training_files": row["training_files"] or "",
        "transcription": row["transcription"] or "",
        "summary": row["summary"] or "",
        "suggestions": row["suggestions"] or "",
        "tree_type": row["tree_type"] or "",
        "startms": row["startms"] or "",
        "endms": row["endms"] or "",
    }


def load_training_rows():
    rows = _db_execute("SELECT * FROM training").fetchall()
    return [_row_to_training_dict(r) for r in rows]


def write_training_rows(rows) -> None:
    db = get_db()
    db.execute("DELETE FROM training")
    for row in rows:
        tid = str(row.get("training_id","") or "").strip()
        if not tid:
            continue
        db.execute(
            "INSERT INTO training VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (tid, str(row.get("created_at","") or ""), str(row.get("meeting_id","") or ""),
             str(row.get("user_id","") or ""), str(row.get("reflection_id","") or ""),
             normalize_training_type_str(row.get("type","valence")),
             str(row.get("valence","") or ""), str(row.get("arousal","") or ""),
             str(row.get("dominance","") or ""), normalize_done_str(row.get("done","false")),
             str(row.get("training_files","") or ""), str(row.get("transcription","") or ""),
             str(row.get("summary","") or ""), str(row.get("suggestions","") or ""),
             str(row.get("tree_type","") or ""), str(row.get("startms","") or ""),
             str(row.get("endms","") or "")),
        )
    db.commit()


def append_training_row(
    training_id: str, meeting_id: str, reflection_id: str = "", user_id: str = "",
    training_type: str = "valence", valence: float | None = None, arousal: float | None = None,
    dominance: float | None = None, training_files: list[str] | None = None,
    transcription: str = "", summary: str = "", suggestions: list[str] | None = None,
    tree_type: str = "", startms: str = "", endms: str = "", done: str = "false",
) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _t_uid = str(user_id or "").strip()
    _t_mid = str(meeting_id or "").strip()
    _t_rid = str(reflection_id or "").strip()
    _db_execute(
        "INSERT OR IGNORE INTO training VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (str(training_id or "").strip(), datetime.now(timezone.utc).isoformat(),
         _t_mid or None, _t_uid or None,
         _t_rid or None, normalize_training_type_str(training_type),
         "" if valence is None else str(valence),
         "" if arousal is None else str(arousal),
         "" if dominance is None else str(dominance),
         normalize_done_str(done), ";".join(training_files or []),
         str(transcription or "").strip(), str(summary or "").strip(),
         "|".join(suggestions or []), str(tree_type or "").strip(),
         str(startms or "").strip(), str(endms or "").strip()),
    )
    _db_commit()


def update_training_row_files(training_id: str, training_files: list[str], suggestions: list[str]) -> None:
    _db_execute(
        "UPDATE training SET training_files=?, suggestions=? WHERE training_id=?",
        (";".join(training_files or []), "|".join(suggestions or []), str(training_id or "").strip()),
    )
    _db_commit()


# ---------------------------------------------------------------------------
# Audio / training file helpers
# ---------------------------------------------------------------------------

def _sanitize_storage_name(value: str, fallback: str) -> str:
    normalized = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(value or ""))
    normalized = "_".join(p for p in normalized.split("_") if p)
    return normalized or fallback


def save_training_audio_variants(
    training_id: str, meeting_id: str, emotion: str,
    tagged_audio: list[tuple[str, bytes]], output_dir: str | Path | None = None,
) -> list[str]:
    output_root = Path(output_dir) if output_dir else TRAINING_AUDIO_DIR
    output_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_session = _sanitize_storage_name(meeting_id, "session")
    safe_emotion = _sanitize_storage_name(emotion, "emotion")
    output_files: list[str] = []
    for index, (tag, audio_bytes) in enumerate(tagged_audio, start=1):
        safe_tag = _sanitize_storage_name(tag, f"tag{index}")
        filename = f"{training_id}_{safe_session}_{safe_emotion}_{safe_tag}_{timestamp}_{index}.mp3"
        (output_root / filename).write_bytes(audio_bytes)
        output_files.append(filename)
    return output_files


# ---------------------------------------------------------------------------
# Backwards-compatible CSV aliases (for any code that imports read/write_csv_rows)
# ---------------------------------------------------------------------------

def read_csv_rows(csv_path: Path):
    return _read_csv_rows(csv_path)


def write_csv_rows(csv_path: Path, rows, fieldnames) -> None:
    _write_csv_rows(csv_path, rows, fieldnames)
