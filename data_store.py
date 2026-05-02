from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR
AUDIO_DATA_DIR = DATA_DIR
TRAINING_AUDIO_DIR = DATA_DIR / "training_audio"
DB_CSV_PATH = DATA_DIR / "db.csv"
TRAINING_CSV_PATH = DATA_DIR / "training.csv"

REFLECTION_DB_FIELDNAMES = [
    "wearer_agent",
    "session_name",
    "reflection_tree_file",
    "startms",
    "endms",
    "practice",
    "audio_filename",
    "journal_entry",
    "intent_filename",
    "tree_type",
    "has_journaling",
]

TRAINING_CSV_FIELDNAMES = [
    "training_id",
    "session",
    "session_name",
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

AUDIO_RECORD_REQUIRED_KEYS = {
    "id",
    "audioUrl",
    "audioFilename",
    "transcript",
}


def ensure_data_layout() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    TRAINING_AUDIO_DIR.mkdir(parents=True, exist_ok=True)


def audio_record_path(record_id: str) -> Path:
    return AUDIO_DATA_DIR / f"{record_id}.json"


def intent_file_path(filename: str) -> Path:
    return DATA_DIR / filename


def is_json_filename(filename: str) -> bool:
    return bool(filename) and Path(filename).suffix == ".json"


def data_json_path(filename: str) -> Path:
    return DATA_DIR / filename


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any, *, indent: int = 2, ensure_ascii: bool = True) -> None:
    path.write_text(
        json.dumps(payload, indent=indent, ensure_ascii=ensure_ascii),
        encoding="utf-8",
    )


def iter_data_json_files():
    return sorted(
        DATA_DIR.glob("*.json"),
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


def save_audio_record(record) -> None:
    write_json(audio_record_path(str(record.get("id", ""))), record)


def load_audio_record(record_id):
    record_path = audio_record_path(str(record_id or ""))
    if not record_path.exists():
        return None
    return read_json(record_path)


def delete_audio_record(record_id) -> bool:
    record_path = audio_record_path(str(record_id or ""))
    if not record_path.exists():
        return False
    record_path.unlink()
    return True


def iter_audio_records():
    records = []
    for path in iter_data_json_files():
        try:
            record = read_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        if is_audio_record(record):
            records.append(record)
    return records


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
        if name and name not in ordered:
            ordered.append(name)
    return ordered


def load_reflection_db_rows():
    if not DB_CSV_PATH.exists():
        return [], list(REFLECTION_DB_FIELDNAMES)

    raw_rows, raw_fieldnames = read_csv_rows(DB_CSV_PATH)
    fieldnames = reflection_db_fieldnames(raw_fieldnames)
    rows = []
    for row in raw_rows:
        normalized_row = {field: row.get(field, "") for field in fieldnames}
        normalized_row["practice"] = normalize_practice_value(normalized_row.get("practice"))
        rows.append(normalized_row)
    return rows, fieldnames


def write_reflection_db_rows(rows, fieldnames=None) -> None:
    resolved_fieldnames = reflection_db_fieldnames(fieldnames)
    write_csv_rows(DB_CSV_PATH, rows, resolved_fieldnames)


def upsert_intent_reflection_row(session_name: str, intent_file: str, wearer_agent: str = "") -> None:
    rows, fieldnames = load_reflection_db_rows()
    rows = [row for row in rows if str(row.get("intent_filename", "") or "") != intent_file]
    rows.append({
        "wearer_agent": str(wearer_agent or "").strip(),
        "session_name": str(session_name or "").strip(),
        "reflection_tree_file": "",
        "startms": "",
        "endms": "",
        "practice": "null",
        "audio_filename": "",
        "journal_entry": "",
        "intent_filename": str(intent_file or "").strip(),
    })
    write_reflection_db_rows(rows, fieldnames)


def load_training_rows():
    if not TRAINING_CSV_PATH.exists():
        return []

    raw_rows, _ = read_csv_rows(TRAINING_CSV_PATH)
    normalized_rows = []
    for row in raw_rows:
        session_value = str(row.get("session", "") or row.get("session_name", "") or "").strip()
        normalized_rows.append({
            "training_id": str(row.get("training_id", "") or "").strip(),
            "session": session_value,
            "session_name": str(row.get("session_name", "") or session_value),
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
        session_value = str(row.get("session", "") or row.get("session_name", "") or "").strip()
        normalized_rows.append({
            "training_id": str(row.get("training_id", "") or "").strip(),
            "session": session_value,
            "session_name": str(row.get("session_name", "") or session_value),
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
