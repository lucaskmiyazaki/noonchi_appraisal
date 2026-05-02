from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
MEETING_AUDIO_DIR = DATA_DIR / "meeting_audio"
JSON_MEETING_TRANSCRIPT_DIR = DATA_DIR / "meeting_transcript"
JSON_INTENTS_DIR = DATA_DIR / "intent_json"
JSON_REFLECTIONS_DIR = DATA_DIR / "reflection_json"
TRAINING_AUDIO_DIR = DATA_DIR / "training_audio"
# Audio files go to meeting_audio folder, legacy support as UPLOAD_DIR
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

REFLECTION_DB_FIELDNAMES = [
    "wearer_agent",
    "reflection_tree_file",
    "startms",
    "endms",
    "practice",
    "meeting_id",
    "tree_type",
    "has_journaling",
]

TRAINING_CSV_FIELDNAMES = [
    "training_id",
    "meeting_id",
    "reflection_id",
    "wearer_agent",
    "type",
    "valence",
    "arousal",
    "dominance",
    "done",
    "training_files",
    "transcription",
    "summary",
    "suggestions",
    "tree_type",
    "startms",
    "endms",
]

INTENTS_CSV_FIELDNAMES = [
    "intent_filename",
    "wearer_agent",
    "startms",
    "endms",
    "meeting_id",
]

JOURNAL_ENTRIES_CSV_FIELDNAMES = [
    "reflection_tree_file",
    "journal_entry",
]

MEETINGS_CSV_FIELDNAMES = [
    "id",
    "session_name",
    "display_name",
    "safe_session_name",
    "original_name",
    "audio_filename",
    "transcript_file",
    "uploaded_at",
    "duration",
    "segment_count",
]

AUDIO_RECORD_REQUIRED_KEYS = {
    "id",
    "audioUrl",
    "audioFilename",
    "transcript",
}


def ensure_data_layout() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MEETING_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    JSON_MEETING_TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    JSON_INTENTS_DIR.mkdir(parents=True, exist_ok=True)
    JSON_REFLECTIONS_DIR.mkdir(parents=True, exist_ok=True)
    TRAINING_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    migrate_folder_structure()
    migrate_legacy_reflection_embedded_tables()
    migrate_audio_records_to_csv()
    migrate_audio_filename_to_meeting_id()
    migrate_training_to_meeting_id()


def reflection_csv_path() -> Path:
    # Migrate legacy data/db.csv to data/reflections.csv once.
    if REFLECTIONS_CSV_PATH.exists():
        return REFLECTIONS_CSV_PATH
    if LEGACY_DB_CSV_PATH.exists() and LEGACY_DB_CSV_PATH.is_file():
        try:
            LEGACY_DB_CSV_PATH.rename(REFLECTIONS_CSV_PATH)
        except OSError:
            # Fallback for cross-device or permission edge cases.
            REFLECTIONS_CSV_PATH.write_text(LEGACY_DB_CSV_PATH.read_text(encoding="utf-8"), encoding="utf-8")
            LEGACY_DB_CSV_PATH.unlink()
    return REFLECTIONS_CSV_PATH


def meeting_record_path(record_id: str) -> Path:
    return JSON_MEETING_TRANSCRIPT_DIR / f"{record_id}.json"


# Keep old name as alias
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
    # Keep routing logic in one place so callers remain filename-only.
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
    path.write_text(
        json.dumps(payload, indent=indent, ensure_ascii=ensure_ascii),
        encoding="utf-8",
    )


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


def save_meeting(record) -> None:
    record_id = str(record.get("id", ""))
    write_json(meeting_record_path(record_id), record)

    # Also write to meetings.csv
    transcript = record.get("transcript", [])
    last_segment = transcript[-1] if transcript else {}
    meeting_row = {
        "id": record_id,
        "session_name": record.get("sessionName", ""),
        "display_name": record.get("displayName", ""),
        "safe_session_name": record.get("safeSessionName", ""),
        "original_name": record.get("originalName", ""),
        "audio_filename": record.get("audioFilename", ""),
        "transcript_file": f"{record_id}.json",
        "uploaded_at": record.get("uploadedAt", ""),
        "duration": str(float(last_segment.get("end", 0.0) or 0.0)),
        "segment_count": str(len(transcript)),
    }

    # Update or insert row in CSV
    rows, fieldnames = load_meeting_rows()
    found = False
    for i, row in enumerate(rows):
        if row.get("id", "") == record_id:
            rows[i] = meeting_row
            found = True
            break
    if not found:
        rows.append(meeting_row)
    write_meeting_rows(rows, fieldnames)


# Keep old name as alias
def save_audio_record(record) -> None:
    save_meeting(record)


def load_meeting(record_id):
    record_path = meeting_record_path(str(record_id or ""))
    if not record_path.exists():
        return None
    return read_json(record_path)


# Keep old name as alias
def load_audio_record(record_id):
    return load_meeting(record_id)


def delete_meeting(record_id) -> bool:
    record_path = meeting_record_path(str(record_id or ""))
    deleted_json = False
    if record_path.exists():
        record_path.unlink()
        deleted_json = True

    # Also remove from meetings.csv
    rows, fieldnames = load_meeting_rows()
    original_count = len(rows)
    rows = [row for row in rows if row.get("id", "") != str(record_id)]
    if len(rows) < original_count:
        write_meeting_rows(rows, fieldnames)
        return True

    return deleted_json


# Keep old name as alias
def delete_audio_record(record_id) -> bool:
    return delete_meeting(record_id)


def iter_meetings():
    """Load all meeting records from CSV + transcript JSON files."""
    records = []
    rows, _ = load_meeting_rows()

    for row in rows:
        record_id = row.get("id", "").strip()
        if not record_id:
            continue

        # Load full transcript from JSON
        transcript = []
        transcript_file = row.get("transcript_file", "").strip()
        if transcript_file:
            transcript_json = read_data_json_file(transcript_file)
            if isinstance(transcript_json, list):
                transcript = transcript_json
            elif isinstance(transcript_json, dict):
                transcript = transcript_json.get("transcript", [])

        # Build record from CSV + loaded transcript
        record = {
            "id": record_id,
            "sessionName": row.get("session_name", ""),
            "displayName": row.get("display_name", ""),
            "safeSessionName": row.get("safe_session_name", ""),
            "originalName": row.get("original_name", ""),
            "audioFilename": row.get("audio_filename", ""),
            "audioUrl": f"/uploads/{row.get('audio_filename', '')}",
            "uploadedAt": row.get("uploaded_at", ""),
            "transcript": transcript,
        }
        records.append(record)

    return records


# Keep old name as alias
def iter_audio_records():
    return iter_meetings()


def read_csv_rows(csv_path: Path):
    if not csv_path.exists():
        return [], []

    with csv_path.open(newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        return list(reader), list(reader.fieldnames or [])


def write_csv_rows(csv_path: Path, rows, fieldnames) -> None:
    with csv_path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=list(fieldnames))
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def normalize_practice_value(value) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"done", "todo", "null"}:
        return normalized
    return "null"


def normalize_done_str(value) -> str:
    normalized = str(value or "").strip().lower()
    return "true" if normalized in {"true", "1", "yes", "done"} else "false"


def normalize_training_type_str(value) -> str:
    normalized = str(value or "").strip().lower()
    return "arousal" if normalized == "arousal" else "valence"


def reflection_db_fieldnames(fieldnames=None):
    ordered = []
    for name in list(fieldnames or []) + REFLECTION_DB_FIELDNAMES:
        if name in {"intent_filename", "journal_entry", "audio_filename", "session_name"}:
            continue
        if name and name not in ordered:
            ordered.append(name)
    return ordered


def intents_fieldnames(fieldnames=None):
    ordered = []
    for name in list(fieldnames or []) + INTENTS_CSV_FIELDNAMES:
        if name in {"audio_filename", "session_name"}:
            continue
        if name and name not in ordered:
            ordered.append(name)
    return ordered


def journal_entries_fieldnames(fieldnames=None):
    ordered = []
    for name in list(fieldnames or []) + JOURNAL_ENTRIES_CSV_FIELDNAMES:
        if name and name not in ordered:
            ordered.append(name)
    return ordered


def load_reflection_db_rows():
    csv_path = reflection_csv_path()
    if not csv_path.exists():
        return [], list(REFLECTION_DB_FIELDNAMES)

    raw_rows, raw_fieldnames = read_csv_rows(csv_path)
    fieldnames = reflection_db_fieldnames(raw_fieldnames)
    rows = []
    for row in raw_rows:
        normalized_row = {field: row.get(field, "") for field in fieldnames}
        normalized_row["practice"] = normalize_practice_value(normalized_row.get("practice"))
        # Derive session_name from meetings (authoritative)
        meeting_id = str(normalized_row.get("meeting_id", "") or "").strip()
        if meeting_id:
            normalized_row["session_name"] = lookup_session_name_by_meeting_id(meeting_id)
        rows.append(normalized_row)
    return rows, fieldnames


def write_reflection_db_rows(rows, fieldnames=None) -> None:
    resolved_fieldnames = reflection_db_fieldnames(fieldnames)
    write_csv_rows(reflection_csv_path(), rows, resolved_fieldnames)


def load_intent_rows():
    if not INTENTS_CSV_PATH.exists():
        return [], list(INTENTS_CSV_FIELDNAMES)

    raw_rows, raw_fieldnames = read_csv_rows(INTENTS_CSV_PATH)
    fieldnames = intents_fieldnames(raw_fieldnames)
    rows = []
    for row in raw_rows:
        normalized = {field: str(row.get(field, "") or "").strip() for field in fieldnames}
        # Derive session_name from meetings (authoritative)
        meeting_id = normalized.get("meeting_id", "")
        if meeting_id:
            normalized["session_name"] = lookup_session_name_by_meeting_id(meeting_id)
        rows.append(normalized)
    return rows, fieldnames


def write_intent_rows(rows, fieldnames=None) -> None:
    resolved_fieldnames = intents_fieldnames(fieldnames)
    normalized = []
    for row in rows:
        normalized.append({field: str(row.get(field, "") or "").strip() for field in resolved_fieldnames})
    write_csv_rows(INTENTS_CSV_PATH, normalized, resolved_fieldnames)


def delete_intent_row(intent_file: str) -> bool:
    safe_intent = str(intent_file or "").strip()
    if not safe_intent:
        return False
    rows, fieldnames = load_intent_rows()
    remaining = []
    removed = False
    for row in rows:
        if str(row.get("intent_filename", "") or "") == safe_intent:
            removed = True
            continue
        remaining.append(row)
    if removed:
        write_intent_rows(remaining, fieldnames)
    return removed


def load_journal_rows():
    if not JOURNAL_ENTRIES_CSV_PATH.exists():
        return [], list(JOURNAL_ENTRIES_CSV_FIELDNAMES)

    raw_rows, raw_fieldnames = read_csv_rows(JOURNAL_ENTRIES_CSV_PATH)
    fieldnames = journal_entries_fieldnames(raw_fieldnames)
    rows = []
    for row in raw_rows:
        rows.append({field: str(row.get(field, "") or "") for field in fieldnames})
    return rows, fieldnames


def write_journal_rows(rows, fieldnames=None) -> None:
    resolved_fieldnames = journal_entries_fieldnames(fieldnames)
    normalized = []
    for row in rows:
        normalized.append({field: str(row.get(field, "") or "") for field in resolved_fieldnames})
    write_csv_rows(JOURNAL_ENTRIES_CSV_PATH, normalized, resolved_fieldnames)


def load_meeting_rows():
    csv_path = MEETINGS_CSV_PATH
    # Migrate audios.csv → meetings.csv on first access
    if not csv_path.exists() and LEGACY_AUDIOS_CSV_PATH.exists():
        try:
            LEGACY_AUDIOS_CSV_PATH.rename(csv_path)
        except OSError:
            csv_path.write_text(LEGACY_AUDIOS_CSV_PATH.read_text(encoding="utf-8"), encoding="utf-8")
            LEGACY_AUDIOS_CSV_PATH.unlink()
    if not csv_path.exists():
        return [], list(MEETINGS_CSV_FIELDNAMES)

    raw_rows, raw_fieldnames = read_csv_rows(csv_path)
    fieldnames = meeting_entries_fieldnames(raw_fieldnames)
    rows = []
    for row in raw_rows:
        rows.append({field: str(row.get(field, "") or "") for field in fieldnames})
    return rows, fieldnames


def write_meeting_rows(rows, fieldnames=None) -> None:
    resolved_fieldnames = meeting_entries_fieldnames(fieldnames)
    normalized = []
    for row in rows:
        normalized.append({field: str(row.get(field, "") or "") for field in resolved_fieldnames})
    write_csv_rows(MEETINGS_CSV_PATH, normalized, resolved_fieldnames)


def meeting_entries_fieldnames(fieldnames=None):
    ordered = []
    for name in list(fieldnames or []) + MEETINGS_CSV_FIELDNAMES:
        if name and name not in ordered:
            ordered.append(name)
    return ordered


def lookup_meeting_id_by_audio_filename(audio_filename: str) -> str:
    target = str(audio_filename or "").strip()
    if not target:
        return ""
    rows, _ = load_meeting_rows()
    for row in rows:
        if row.get("audio_filename", "").strip() == target:
            return row.get("id", "")
    return ""


def lookup_meeting_id_by_session_name(session_name: str) -> str:
    target = str(session_name or "").strip().lower()
    if not target:
        return ""
    rows, _ = load_meeting_rows()
    for row in rows:
        if row.get("session_name", "").strip().lower() == target:
            return row.get("id", "")
    return ""


def lookup_session_name_by_meeting_id(meeting_id: str) -> str:
    target = str(meeting_id or "").strip()
    if not target:
        return ""
    rows, _ = load_meeting_rows()
    for row in rows:
        if row.get("id", "").strip() == target:
            return row.get("session_name", "")
    return ""


def load_journal_entry_raw(reflection_tree_file: str) -> str:
    target = str(reflection_tree_file or "").strip()
    if not target:
        return ""
    rows, _ = load_journal_rows()
    for row in rows:
        if str(row.get("reflection_tree_file", "") or "").strip() == target:
            return str(row.get("journal_entry", "") or "")
    return ""


def upsert_journal_entry_raw(reflection_tree_file: str, journal_entry: str) -> None:
    target = str(reflection_tree_file or "").strip()
    if not target:
        return
    rows, fieldnames = load_journal_rows()
    replaced = False
    for row in rows:
        if str(row.get("reflection_tree_file", "") or "").strip() == target:
            row["journal_entry"] = str(journal_entry or "")
            replaced = True
            break
    if not replaced:
        rows.append({
            "reflection_tree_file": target,
            "journal_entry": str(journal_entry or ""),
        })
    write_journal_rows(rows, fieldnames)


def delete_journal_entry_row(reflection_tree_file: str) -> bool:
    target = str(reflection_tree_file or "").strip()
    if not target:
        return False
    rows, fieldnames = load_journal_rows()
    remaining = []
    removed = False
    for row in rows:
        if str(row.get("reflection_tree_file", "") or "").strip() == target:
            removed = True
            continue
        remaining.append(row)
    if removed:
        write_journal_rows(remaining, fieldnames)
    return removed


def migrate_folder_structure() -> None:
    """Migrate from audio_records/ to meeting_transcript/ (one-time)."""
    legacy_audio_records = DATA_DIR / "audio_records"
    # Check if migration is needed: audio_records exists AND meeting_transcript is empty
    if legacy_audio_records.exists() and legacy_audio_records.is_dir():
        # Count files in legacy folder
        legacy_files = list(legacy_audio_records.iterdir())
        if legacy_files:
            # Files exist in legacy folder, need to migrate
            JSON_MEETING_TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
            for file in legacy_files:
                if file.is_file():
                    dst = JSON_MEETING_TRANSCRIPT_DIR / file.name
                    if not dst.exists():
                        try:
                            file.rename(dst)
                        except OSError:
                            # Cross-device or permission issue: copy files
                            dst.write_bytes(file.read_bytes())
                            file.unlink()
            # Remove legacy folder if empty
            try:
                legacy_audio_records.rmdir()
            except OSError:
                pass


def migrate_audio_records_to_csv() -> None:
    """Migrate audio record JSONs to meetings.csv and move audio files to meeting_audio/ (one-time)."""
    # Move any stray audio files to meeting_audio regardless
    _move_stray_audio_files()

    if MEETINGS_CSV_PATH.exists() or LEGACY_AUDIOS_CSV_PATH.exists():
        return  # Already migrated (rename happens lazily in load_meeting_rows)

    rows = []
    for json_file in JSON_MEETING_TRANSCRIPT_DIR.glob("*.json"):
        try:
            record = read_json(json_file)
            if is_audio_record(record):
                transcript = record.get("transcript", [])
                last_segment = transcript[-1] if transcript else {}
                row = {
                    "id": record.get("id", ""),
                    "session_name": record.get("sessionName", ""),
                    "display_name": record.get("displayName", ""),
                    "safe_session_name": record.get("safeSessionName", ""),
                    "original_name": record.get("originalName", ""),
                    "audio_filename": record.get("audioFilename", ""),
                    "transcript_file": json_file.name,
                    "uploaded_at": record.get("uploadedAt", ""),
                    "duration": str(float(last_segment.get("end", 0.0) or 0.0)),
                    "segment_count": str(len(transcript)),
                }
                rows.append(row)
        except (OSError, json.JSONDecodeError):
            continue

    if rows:
        write_meeting_rows(rows)


def _move_stray_audio_files() -> None:
    """Move audio files in DATA_DIR root into MEETING_AUDIO_DIR."""
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


def migrate_audio_filename_to_meeting_id() -> None:
    """One-time migration: replace audio_filename FK with meeting_id in intents and reflections."""
    meeting_rows, _ = load_meeting_rows()
    by_audio_filename = {r.get("audio_filename", "").strip(): r.get("id", "") for r in meeting_rows}

    # Migrate intents.csv - read raw to access audio_filename before filtering
    if INTENTS_CSV_PATH.exists():
        raw_rows, raw_fieldnames = read_csv_rows(INTENTS_CSV_PATH)
        if any(r.get("audio_filename") and not r.get("meeting_id") for r in raw_rows):
            for row in raw_rows:
                if not str(row.get("meeting_id", "")).strip():
                    af = str(row.get("audio_filename", "") or "").strip()
                    if af and af in by_audio_filename:
                        row["meeting_id"] = af and by_audio_filename[af]
            write_intent_rows(list(raw_rows))

    # Migrate reflections.csv - read raw to access audio_filename before filtering
    csv_path = reflection_csv_path()
    if csv_path.exists():
        raw_rows, raw_fieldnames = read_csv_rows(csv_path)
        needs = any(r.get("audio_filename") and not r.get("meeting_id") for r in raw_rows)
        if needs:
            for row in raw_rows:
                if not str(row.get("meeting_id", "")).strip():
                    af = str(row.get("audio_filename", "") or "").strip()
                    if af and af in by_audio_filename:
                        row["meeting_id"] = by_audio_filename[af]
                    elif not af:
                        # Fallback: look up by session_name
                        sn = str(row.get("session_name", "") or "").strip().lower()
                        for mr in meeting_rows:
                            if mr.get("session_name", "").strip().lower() == sn:
                                row["meeting_id"] = mr.get("id", "")
                                break
            # Write with filtered fieldnames (no audio_filename)
            new_fieldnames = [
                f for f in raw_fieldnames
                if f not in {"audio_filename", "intent_filename", "journal_entry"}
            ]
            if "meeting_id" not in new_fieldnames:
                new_fieldnames.append("meeting_id")
            write_csv_rows(csv_path, list(raw_rows), new_fieldnames)


def migrate_training_to_meeting_id() -> None:
    """One-time migration: replace session/session_name columns with meeting_id in training.csv."""
    if not TRAINING_CSV_PATH.exists():
        return
    raw_rows, raw_fieldnames = read_csv_rows(TRAINING_CSV_PATH)
    if not raw_rows:
        return
    # Check if any row is missing meeting_id (has legacy session/session_name instead)
    needs = any(
        (str(row.get("session", "") or row.get("session_name", "")).strip())
        and not str(row.get("meeting_id", "")).strip()
        for row in raw_rows
    )
    if not needs:
        return
    for row in raw_rows:
        if not str(row.get("meeting_id", "")).strip():
            legacy_session = str(row.get("session", "") or row.get("session_name", "") or "").strip()
            if legacy_session:
                row["meeting_id"] = lookup_meeting_id_by_session_name(legacy_session)
    write_training_rows(list(raw_rows))


def _load_reflection_db_rows_direct():
    """Load reflection rows without server.py's session-name backfill wrapper."""
    csv_path = reflection_csv_path()
    if not csv_path.exists():
        return [], list(REFLECTION_DB_FIELDNAMES)
    raw_rows, raw_fieldnames = read_csv_rows(csv_path)
    fieldnames = reflection_db_fieldnames(raw_fieldnames)
    rows = []
    for row in raw_rows:
        normalized_row = {field: row.get(field, "") for field in fieldnames}
        normalized_row["practice"] = normalize_practice_value(normalized_row.get("practice"))
        rows.append(normalized_row)
    return rows, fieldnames


def migrate_legacy_reflection_embedded_tables() -> None:
    csv_path = reflection_csv_path()
    raw_rows, raw_fieldnames = read_csv_rows(csv_path)
    rows = [dict(row) for row in raw_rows]
    fieldnames = reflection_db_fieldnames(raw_fieldnames)
    intent_rows, intent_fieldnames = load_intent_rows()
    journal_rows, journal_fieldnames = load_journal_rows()

    intents_by_filename = {
        str(row.get("intent_filename", "") or "").strip()
        for row in intent_rows
        if str(row.get("intent_filename", "") or "").strip()
    }
    journals_by_reflection = {
        str(row.get("reflection_tree_file", "") or "").strip()
        for row in journal_rows
        if str(row.get("reflection_tree_file", "") or "").strip()
    }

    migrated_rows = []
    changed = False
    for row in rows:
        intent_filename = str(row.get("intent_filename", "") or "").strip()
        journal_entry = str(row.get("journal_entry", "") or "")
        reflection_tree_file = str(row.get("reflection_tree_file", "") or "").strip()

        if intent_filename and intent_filename not in intents_by_filename:
            intent_rows.append({
                "intent_filename": intent_filename,
                "wearer_agent": str(row.get("wearer_agent", "") or "").strip(),
                "startms": str(row.get("startms", "") or "").strip(),
                "endms": str(row.get("endms", "") or "").strip(),
                "meeting_id": str(row.get("meeting_id", "") or row.get("audio_filename", "") or "").strip(),
            })
            intents_by_filename.add(intent_filename)
            changed = True

        if reflection_tree_file and journal_entry and reflection_tree_file not in journals_by_reflection:
            journal_rows.append({
                "reflection_tree_file": reflection_tree_file,
                "journal_entry": journal_entry,
            })
            journals_by_reflection.add(reflection_tree_file)
            changed = True

        if intent_filename and not reflection_tree_file:
            # Legacy intent-only rows move fully to intents.csv and are removed from reflections.csv
            changed = True
            continue

        if intent_filename or journal_entry:
            row = dict(row)
            row["intent_filename"] = ""
            row["journal_entry"] = ""
            changed = True

        migrated_rows.append(row)

    if not changed:
        return

    write_intent_rows(intent_rows, intent_fieldnames)
    write_journal_rows(journal_rows, journal_fieldnames)
    write_reflection_db_rows(migrated_rows, fieldnames)


def upsert_intent_reflection_row(session_name: str, intent_file: str, wearer_agent: str = "", meeting_id: str = "") -> None:
    intent_rows, fieldnames = load_intent_rows()
    safe_intent = str(intent_file or "").strip()
    if not safe_intent:
        return
    intent_rows = [
        row for row in intent_rows
        if str(row.get("intent_filename", "") or "") != safe_intent
    ]
    intent_rows.append({
        "intent_filename": safe_intent,
        "wearer_agent": str(wearer_agent or "").strip(),
        "startms": "",
        "endms": "",
        "meeting_id": str(meeting_id or "").strip(),
    })
    write_intent_rows(intent_rows, fieldnames)


def load_training_rows():
    if not TRAINING_CSV_PATH.exists():
        return []

    raw_rows, _ = read_csv_rows(TRAINING_CSV_PATH)
    normalized_rows = []
    for row in raw_rows:
        # Handle legacy rows that have session/session_name but no meeting_id
        meeting_id = str(row.get("meeting_id", "") or "").strip()
        if not meeting_id:
            legacy_session = str(row.get("session", "") or row.get("session_name", "") or "").strip()
            if legacy_session:
                meeting_id = lookup_meeting_id_by_session_name(legacy_session)
        # Derive session_name from meetings (authoritative)
        session_name = lookup_session_name_by_meeting_id(meeting_id) if meeting_id else ""
        normalized_rows.append({
            "training_id": str(row.get("training_id", "") or "").strip(),
            "meeting_id": meeting_id,
            "session_name": session_name,
            "reflection_id": str(row.get("reflection_id", "") or "").strip(),
            "wearer_agent": str(row.get("wearer_agent", "") or "").strip(),
            "type": normalize_training_type_str(row.get("type", "valence")),
            "valence": str(row.get("valence", "") or "").strip(),
            "arousal": str(row.get("arousal", "") or "").strip(),
            "dominance": str(row.get("dominance", "") or "").strip(),
            "done": normalize_done_str(row.get("done", "false")),
            "training_files": str(row.get("training_files", "") or "").strip(),
            "transcription": str(row.get("transcription", "") or "").strip(),
            "summary": str(row.get("summary", "") or "").strip(),
            "suggestions": str(row.get("suggestions", "") or "").strip(),
            "tree_type": str(row.get("tree_type", "") or "").strip(),
            "startms": str(row.get("startms", "") or "").strip(),
            "endms": str(row.get("endms", "") or "").strip(),
        })
    return normalized_rows


def write_training_rows(rows) -> None:
    normalized_rows = []
    for row in rows:
        normalized_rows.append({
            "training_id": str(row.get("training_id", "") or "").strip(),
            "meeting_id": str(row.get("meeting_id", "") or "").strip(),
            "reflection_id": str(row.get("reflection_id", "") or "").strip(),
            "wearer_agent": str(row.get("wearer_agent", "") or "").strip(),
            "type": normalize_training_type_str(row.get("type", "valence")),
            "valence": str(row.get("valence", "") or "").strip(),
            "arousal": str(row.get("arousal", "") or "").strip(),
            "dominance": str(row.get("dominance", "") or "").strip(),
            "done": normalize_done_str(row.get("done", "false")),
            "training_files": str(row.get("training_files", "") or "").strip(),
            "transcription": str(row.get("transcription", "") or "").strip(),
            "summary": str(row.get("summary", "") or "").strip(),
            "suggestions": str(row.get("suggestions", "") or "").strip(),
            "tree_type": str(row.get("tree_type", "") or "").strip(),
            "startms": str(row.get("startms", "") or "").strip(),
            "endms": str(row.get("endms", "") or "").strip(),
        })
    write_csv_rows(TRAINING_CSV_PATH, normalized_rows, TRAINING_CSV_FIELDNAMES)
