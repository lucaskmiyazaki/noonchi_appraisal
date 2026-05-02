from __future__ import annotations

import atexit
import json
import os
import queue
import shutil
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from urllib import error as url_error
from urllib.parse import quote
from urllib import request as url_request

from flask import Flask, jsonify, request, render_template, redirect, send_from_directory, abort, Response
from flask_cors import CORS

from pathlib import Path
from werkzeug.utils import secure_filename

from models.reflection import ReflectionTree
from data_store import (
    DATA_DIR,
    TRAINING_AUDIO_DIR,
    UPLOAD_DIR,
    audio_record_path,
    delete_audio_record,
    delete_meeting,
    delete_data_json_file,
    delete_intent_row,
    delete_journal_entry_row,
    ensure_data_layout,
    find_data_recording_file,
    iter_audio_records,
    iter_meetings,
    is_json_filename,
    load_audio_record,
    load_meeting,
    load_intent_rows,
    load_journal_entry_raw,
    load_meeting_rows,
    load_reflection_db_rows as _load_reflection_db_rows,
    load_user_rows,
    lookup_meeting_id_by_session_name,
    lookup_user_by_id,
    lookup_user_by_username,
    lookup_user_id_by_username,
    lookup_username_by_user_id,
    read_data_json_file,
    load_training_rows,
    normalize_done_str,
    normalize_practice_value,
    normalize_training_type_str,
    save_audio_record,
    save_meeting,
    save_user,
    upsert_journal_entry_raw,
    write_reflection_db_rows,
    write_data_json_file,
    write_training_rows,
    upsert_intent_reflection_row,
)
from rules.business_rules import (
    detect_participant_unclear_feedback,
    detect_participant_unclear_concern,
    find_wearer,
    detect_good_concern,
    detect_good_excitement,
    detect_good_feedback,
    detect_tone_incoherence,
    detect_intensity_incoherence,
    detect_unclear_feedback,
    detect_unclear_concern,
    summarize_rule_issue,
    summarize_tone_issue,
    summarize_intensity_issue,
)
app = Flask(__name__)
CORS(app)

ensure_data_layout()

NGROK_API_URL = "http://127.0.0.1:4040/api/tunnels"
NGROK_URL = (os.environ.get("NGROK_URL") or "https://noonchi.ngrok.io").strip()
NGROK_PROCESS = None

AUDIO_ALLOWED_EXTENSIONS = {
    "mp3",
    "wav",
    "m4a",
    "ogg",
    "webm",
    "mp4",
    "mpeg",
    "mpga",
}


def allowed_audio_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in AUDIO_ALLOWED_EXTENSIONS


def build_session_name(filename: str, provided_session_name: str = ""):
    explicit_name = provided_session_name.strip()
    if explicit_name:
        return explicit_name

    derived_name = secure_filename(Path(filename or "audio").stem)
    return derived_name or "audio"


@lru_cache(maxsize=1)
def get_whisper_model():
    try:
        import whisper
    except ImportError as exc:
        raise RuntimeError(
            "Whisper is not installed. Install openai-whisper to enable audio transcription."
        ) from exc

    return whisper.load_model("base")


def transcribe_audio_file(file_path: Path):
    result = get_whisper_model().transcribe(str(file_path), fp16=False)

    transcript = []
    for index, segment in enumerate(result.get("segments", []), start=1):
        text = str(segment.get("text", "")).strip()
        if not text:
            continue

        transcript.append({
            "id": index,
            "text": text,
            "start": float(segment.get("start", 0.0)),
            "end": float(segment.get("end", 0.0)),
            "selected": False,
        })

    return transcript


def summarize_audio_record(record):
    transcript = record.get("transcript") or []
    last_segment = transcript[-1] if transcript else {}
    return {
        "id": record.get("id"),
        "userId": record.get("userId", ""),
        "username": lookup_username_by_user_id(record.get("userId", "")),
        "sessionName": record.get("sessionName"),
        "displayName": record.get("displayName") or record.get("sessionName"),
        "safeSessionName": record.get("safeSessionName"),
        "originalName": record.get("originalName"),
        "audioFilename": record.get("audioFilename"),
        "audioUrl": record.get("audioUrl"),
        "uploadedAt": record.get("uploadedAt"),
        "segmentCount": len(transcript),
        "duration": float(last_segment.get("end", 0.0) or 0.0),
    }


def find_latest_audio_record(session_name=""):
    requested_session = session_name.strip()
    safe_session_name = secure_filename(requested_session)
    requested_session_folded = requested_session.casefold()
    safe_session_name_folded = safe_session_name.casefold()

    for record in iter_audio_records():
        if not requested_session:
            return record

        record_session_name = str(record.get("sessionName", "") or "").strip()
        record_safe_session_name = str(record.get("safeSessionName", "") or "").strip()

        if record_session_name == requested_session:
            return record

        if safe_session_name and record_safe_session_name == safe_session_name:
            return record

        if requested_session_folded and record_session_name.casefold() == requested_session_folded:
            return record

        if safe_session_name_folded and record_safe_session_name.casefold() == safe_session_name_folded:
            return record

        # Also match by displayName so renamed sessions can still be resolved
        record_display_name = str(record.get("displayName", "") or "").strip()
        if record_display_name and record_display_name == requested_session:
            return record

        if record_display_name and record_display_name.casefold() == requested_session_folded:
            return record

    return None


def load_reflection_db_rows():
    # session_name is now hydrated from meetings inside data_store.load_reflection_db_rows
    return _load_reflection_db_rows()


def build_emotion_session_payload(session_name=""):
    record = find_latest_audio_record(session_name)
    if record is None:
        raise FileNotFoundError("No uploaded audio found.")

    transcript_segments = []
    for chunk in list(record.get("transcript") or []):
        transcript_segments.append({
            "id": chunk.get("id"),
            "text": str(chunk.get("text", "")),
            "start": float(chunk.get("start", 0.0) or 0.0),
            "end": float(chunk.get("end", 0.0) or 0.0),
            "valence": chunk.get("valence"),
            "arousal": chunk.get("arousal"),
            "dominance": chunk.get("dominance"),
            "emotion_label": chunk.get("emotion_label"),
            "emotion_probabilities": chunk.get("emotion_probabilities") or [],
        })

    return {
        "id": record.get("id"),
        "sessionName": record.get("sessionName"),
        "audioFilename": record.get("audioFilename", ""),
        "audioUrl": record.get("audioUrl", ""),
        "uploadedAt": record.get("uploadedAt"),
        "segmentCount": len(transcript_segments),
        "segments": transcript_segments,
    }


def build_reflection_response_row(row, reflection_file):
    try:
        tree = read_data_json_file(reflection_file)
    except (OSError, json.JSONDecodeError):
        return None
    if tree is None:
        return None

    return {
        "reflection_tree_file": reflection_file,
        "user_id": row.get("user_id", ""),
        "username": lookup_username_by_user_id(row.get("user_id", "")),
        "startms": row.get("startms", ""),
        "endms": row.get("endms", ""),
        "practice": row.get("practice", "null"),
        "meeting_id": row.get("meeting_id", ""),
        "tree": tree,
    }


def _parse_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "done"}:
            return True
        if normalized in {"false", "0", "no", "todo", ""}:
            return False
    return None


def _tree_has_journaling(tree: dict) -> bool:
    nodes = tree.get("nodes") or {}
    if isinstance(nodes, dict):
        return any(
            str(n.get("type", "") or "").strip().lower() == "journaling"
            for n in nodes.values()
            if isinstance(n, dict)
        )
    return False


def format_reflection_type_label(tree_type: str) -> str:
    normalized = str(tree_type or "").strip().lower()
    if normalized == "incoherent intensity":
        return "elevation"
    if normalized == "incoherent tone":
        return "tone difference"
    return str(tree_type or "reflection").strip() or "reflection"


def _safe_float(value, fallback=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _parse_journal_entry_map(raw_value):
    text = str(raw_value or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {"_single": text}
    if not isinstance(parsed, dict):
        return {}
    normalized = {}
    for key, value in parsed.items():
        if not isinstance(key, str):
            continue
        normalized[key] = str(value or "")
    return normalized


def _serialize_journal_entry_map(value_map):
    cleaned = {}
    for key, value in (value_map or {}).items():
        key_str = str(key or "").strip()
        if not key_str:
            continue
        value_str = str(value or "").strip()
        if not value_str:
            continue
        cleaned[key_str] = value_str
    if not cleaned:
        return ""
    return json.dumps(cleaned, ensure_ascii=True)


def _collect_journaling_paths(tree):
    nodes = tree.get("nodes") or {}
    start_node_id = tree.get("start_node")
    if not isinstance(nodes, dict) or not start_node_id:
        return []

    results = []

    def walk(node_id, path, visited):
        if node_id in visited:
            return
        node = nodes.get(node_id) or {}
        node_type = str(node.get("type", "") or "").strip().lower()
        if node_type == "journaling":
            results.append({
                "node_id": node_id,
                "node_text": str(node.get("text", "") or ""),
                "path": list(path),
            })
            return

        options = node.get("options") or []
        next_visited = set(visited)
        next_visited.add(node_id)

        if not isinstance(options, list):
            return

        for option in options:
            if not isinstance(option, dict):
                continue
            next_id = str(option.get("next", "") or "").strip()
            if not next_id:
                continue

            next_path = list(path)
            if node_type == "question":
                answer_label = str(option.get("label", "") or option.get("value", "") or "").strip()
                next_path.append({
                    "question": str(node.get("text", "") or "").strip(),
                    "answer": answer_label,
                })
            walk(next_id, next_path, next_visited)

    walk(str(start_node_id), [], set())
    return results


def build_journaling_items_for_user(user_name: str):
    rows, _ = load_reflection_db_rows()
    items = []
    # Accept both username and user_id
    user = lookup_user_by_username(user_name) or lookup_user_by_id(user_name)
    target_user_id = user.get("id", "") if user else ""

    for row in rows:
        row_user_id = str(row.get("user_id", "") or "").strip()
        if target_user_id and row_user_id != target_user_id:
            continue

        reflection_file = str(row.get("reflection_tree_file", "") or "").strip()
        if not is_json_filename(reflection_file):
            continue

        # Skip trees known to have no journaling nodes (avoids opening JSON)
        if row.get("has_journaling") == "false":
            continue

        try:
            tree = read_data_json_file(reflection_file)
        except (OSError, json.JSONDecodeError):
            continue
        if tree is None:
            continue

        journaling_paths = _collect_journaling_paths(tree)
        if not journaling_paths:
            continue

        session_name = str(row.get("session_name", "") or "").strip()
        record = find_latest_audio_record(session_name) if session_name else None
        display_name = (record.get("displayName") if record else None) or session_name or "Untitled session"
        entry_map = _parse_journal_entry_map(load_journal_entry_raw(reflection_file))
        fallback_entry = entry_map.get("_single", "")

        for index, journaling_path in enumerate(journaling_paths):
            node_id = str(journaling_path.get("node_id", "") or "").strip()
            node_text = str(journaling_path.get("node_text", "") or "").strip()
            path_pairs = journaling_path.get("path") or []
            entry_value = entry_map.get(node_id, fallback_entry)
            if not str(entry_value or "").strip():
                continue

            title_type = format_reflection_type_label(row.get("tree_type", "") or tree.get("type", ""))
            title = f"{title_type} on {display_name.replace('_', ' ')}"
            if len(journaling_paths) > 1:
                title = f"{title} ({index + 1})"

            items.append({
                "item_id": f"{reflection_file}:{node_id}",
                "reflection_tree_file": reflection_file,
                "node_id": node_id,
                "session_name": session_name,
                "display_name": display_name,
                "user_id": row_user_id,
                "username": lookup_username_by_user_id(row_user_id),
                "title": title,
                "journaling_prompt": node_text,
                "qa_path": path_pairs,
                "journal_entry": entry_value,
            })

    items.sort(key=lambda item: item.get("reflection_tree_file", ""), reverse=True)
    return items


def build_practice_items_for_user(user_name: str):
    rows = load_training_rows()
    items = []
    # Accept both username and user_id
    user = lookup_user_by_username(user_name) or lookup_user_by_id(user_name)
    target_user_id = user.get("id", "") if user else ""

    for row in rows:
        row_user_id = str(row.get("user_id", "") or "").strip()
        if target_user_id and row_user_id != target_user_id:
            continue

        session_name = str(row.get("session_name", "") or "").strip()
        meeting_id = str(row.get("meeting_id", "") or "").strip()
        reflection_id = str(row.get("reflection_id", "") or "").strip()
        transcription = str(row.get("transcription", "") or "").strip()
        summary = str(row.get("summary", "") or "").strip()

        training_files = [
            file_name.strip()
            for file_name in str(row.get("training_files", "") or "").split(";")
            if file_name.strip()
        ]
        suggestions = [
            suggestion.strip()
            for suggestion in str(row.get("suggestions", "") or "").split("|")
            if suggestion.strip()
        ]

        tree = {}
        start_ms = str(row.get("startms", "") or "")
        end_ms = str(row.get("endms", "") or "")
        tree_type = str(row.get("tree_type", "") or "")
        # Fallback: open JSON only for rows written before metadata columns were added
        if not (start_ms or end_ms or tree_type) and is_json_filename(reflection_id):
            try:
                tree = read_data_json_file(reflection_id) or {}
            except (OSError, json.JSONDecodeError):
                tree = {}
            start_ms = str(tree.get("startMs", "") or "")
            end_ms = str(tree.get("endMs", "") or "")
            tree_type = str(tree.get("type", "") or "")

        record = load_meeting(meeting_id) if meeting_id else None
        display_name = (record.get("displayName") if record else None) or session_name or "Untitled session"
        original_audio_url = record.get("audioUrl", "") if record else ""

        ai_practice = []
        max_len = max(len(suggestions), len(training_files))
        for index in range(max_len):
            suggestion_text = suggestions[index] if index < len(suggestions) else ""
            ai_file = training_files[index] if index < len(training_files) else ""
            ai_practice.append({
                "index": index + 1,
                "suggestion": suggestion_text,
                "audio_file": ai_file,
                "audio_url": f"/training_audio/{quote(ai_file)}" if ai_file else "",
            })

        title = f"{format_reflection_type_label(tree_type)} on {display_name.replace('_', ' ')}"
        items.append({
            "training_id": str(row.get("training_id", "") or "").strip(),
            "session_name": session_name,
            "display_name": display_name,
            "reflection_id": reflection_id,
            "user_id": row_user_id,
            "username": lookup_username_by_user_id(row_user_id),
            "type": normalize_training_type_str(row.get("type", "valence")),
            "done": normalize_done_str(row.get("done", "false")) == "true",
            "title": title,
            "summary": summary,
            "transcription": transcription,
            "original_audio_url": original_audio_url,
            "startms": start_ms,
            "endms": end_ms,
            "ai_practice": ai_practice,
        })

    items.sort(key=lambda item: item.get("training_id", ""), reverse=True)
    return items


def stop_ngrok():
    global NGROK_PROCESS

    if NGROK_PROCESS is None or NGROK_PROCESS.poll() is not None:
        return

    NGROK_PROCESS.terminate()
    try:
        NGROK_PROCESS.wait(timeout=3)
    except subprocess.TimeoutExpired:
        NGROK_PROCESS.kill()
        NGROK_PROCESS.wait(timeout=3)


def start_ngrok(port: int = 5001):
    global NGROK_PROCESS

    if NGROK_PROCESS is not None and NGROK_PROCESS.poll() is None:
        return

    ngrok_path = shutil.which("ngrok")
    if ngrok_path is None:
        print("ngrok is not installed or not available on PATH. Skipping tunnel startup.")
        return

    ngrok_command = [ngrok_path, "http", str(port), "--scheme=http,https"]
    if NGROK_URL:
        ngrok_command.extend(["--url", NGROK_URL])

    NGROK_PROCESS = subprocess.Popen(
        ngrok_command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )

    for _ in range(10):
        if NGROK_PROCESS.poll() is not None:
            print("ngrok exited before the tunnel became available.")
            NGROK_PROCESS = None
            return

        time.sleep(1)

        try:
            with url_request.urlopen(NGROK_API_URL, timeout=2.0) as response:
                payload = json.load(response)
        except (url_error.URLError, TimeoutError, json.JSONDecodeError):
            continue

        tunnels = payload.get("tunnels", [])
        if not tunnels:
            continue

        print("\n===== NGROK URLS =====")
        for tunnel in tunnels:
            proto = str(tunnel.get("proto", "")).upper()
            url = tunnel.get("public_url")
            if url:
                print(f"{proto} URL: {url}")
        print("======================\n")
        return

    print("Could not get ngrok URL from the local ngrok API.")


atexit.register(stop_ngrok)

def post_tip_to_bangle(message):
    if not message:
        return

    payload = json.dumps({"tip": message}).encode("utf-8")
    req = url_request.Request(
        "http://127.0.0.1:5007/tips",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with url_request.urlopen(req, timeout=2.0) as response:
            response.read()
    except (url_error.URLError, TimeoutError) as exc:
        print(f"Failed to send tip to bangle.js: {exc}")

# --- NEW: Build analysis payload with both emotion and intent ---
def build_session_analysis_payload(session_name=""):
    record = find_latest_audio_record(session_name)
    if record is None:
        raise FileNotFoundError("No uploaded audio found.")

    transcript_segments = []
    for chunk in list(record.get("transcript") or []):
        transcript_segments.append({
            "id": chunk.get("id"),
            "text": str(chunk.get("text", "")),
            "start": float(chunk.get("start", 0.0) or 0.0),
            "end": float(chunk.get("end", 0.0) or 0.0),
            "valence": chunk.get("valence"),
            "arousal": chunk.get("arousal"),
            "dominance": chunk.get("dominance"),
            "emotion_label": chunk.get("emotion_label"),
            "emotion_probabilities": chunk.get("emotion_probabilities") or [],
            "intent_label": chunk.get("intent_label"),
            "goal_blocker_label": chunk.get("goal_blocker_label"),
            "goal_clarity": chunk.get("goal_clarity"),
            "rephrased_goal": chunk.get("rephrased_goal"),
            "is_goal_status": chunk.get("is_goal_status", ""),
        })

    return {
        "id": record.get("id"),
        "sessionName": record.get("sessionName"),
        "audioFilename": record.get("audioFilename", ""),
        "audioUrl": record.get("audioUrl", ""),
        "uploadedAt": record.get("uploadedAt"),
        "segmentCount": len(transcript_segments),
        "segments": transcript_segments,
    }


# --- API endpoint to delete intent file and db entry ---
@app.delete("/api/audio/intent/<intent_filename>")
def delete_intent(intent_filename):
    safe_filename = secure_filename(intent_filename or "")
    if not is_json_filename(safe_filename):
        return jsonify({"error": "Invalid intent filename."}), 400

    deleted_row = delete_intent_row(safe_filename)

    file_deleted = delete_data_json_file(safe_filename)

    if not deleted_row and not file_deleted:
        return jsonify({"error": "Intent not found."}), 404

    return jsonify({
        "message": "intent deleted",
        "intent_file": safe_filename,
    })

@app.post("/api/audio/session/save_intent")
def save_intent():
    payload = request.get_json() or {}
    session_name = payload.get("session_name", "").strip()
    # Accept user_id or wearer_agent (legacy) from client
    user_id = str(payload.get("user_id", "") or payload.get("wearer_agent", "") or "").strip()
    intent_file = payload.get("intent_file", "").strip()
    intent_data = payload.get("intent_data")
    if not session_name or not intent_file or intent_data is None:
        return jsonify({"error": "Missing required fields."}), 400

    # Save intent JSON
    try:
        write_data_json_file(intent_file, intent_data)
    except Exception as e:
        return jsonify({"error": f"Failed to save intent file: {e}"}), 500

    # Look up meeting_id for this session
    meeting_record = find_latest_audio_record(session_name)
    meeting_id = meeting_record.get("id", "") if meeting_record else ""

    # Resolve user_id if a username was passed
    if user_id and not lookup_user_by_id(user_id):
        user_id = lookup_user_id_by_username(user_id)

    upsert_intent_reflection_row(
        session_name=session_name,
        intent_file=intent_file,
        user_id=user_id,
        meeting_id=meeting_id,
    )

    return jsonify({"message": "Intent saved.", "intent_file": intent_file})

@app.put("/api/audio/intent/<intent_filename>")
def update_intent(intent_filename):
    safe_filename = secure_filename(intent_filename or "")
    if not is_json_filename(safe_filename):
        return jsonify({"error": "Invalid intent filename."}), 400

    full = read_data_json_file(safe_filename)
    if full is None:
        return jsonify({"error": "Intent file not found."}), 404

    payload = request.get_json() or {}
    diagram_data = payload.get("diagram_data")
    startms = payload.get("startms")
    if diagram_data is None:
        return jsonify({"error": "Missing diagram_data."}), 400

    diagrams = full.get("diagrams", [])
    matched = False
    if startms is not None:
        for i, d in enumerate(diagrams):
            if d.get("startms") == startms:
                diagrams[i] = {**d, "nodes": diagram_data.get("nodes", []), "edges": diagram_data.get("edges", [])}
                matched = True
                break
    if not matched:
        # Fallback: patch the first diagram
        if diagrams:
            diagrams[0] = {**diagrams[0], "nodes": diagram_data.get("nodes", []), "edges": diagram_data.get("edges", [])}
        else:
            diagrams.append(diagram_data)
    full["diagrams"] = diagrams

    try:
        write_data_json_file(safe_filename, full)
    except Exception as e:
        return jsonify({"error": f"Failed to update intent file: {e}"}), 500

    return jsonify({"message": "Intent updated.", "intent_file": safe_filename})


@app.get("/api/audio/intent/<intent_filename>")
def get_intent(intent_filename):
    safe_filename = secure_filename(intent_filename or "")
    if not is_json_filename(safe_filename):
        return jsonify({"error": "Invalid intent filename."}), 400

    intent_data = read_data_json_file(safe_filename)
    if intent_data is None:
        return jsonify({"error": "Intent file not found."}), 404

    return jsonify({"intent_file": safe_filename, "data": intent_data})


@app.get("/api/audio/session/<session_name>/analysis")
def get_session_analysis(session_name):
    try:
        payload = build_session_analysis_payload(session_name)
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 500
    except Exception as exc:
        return jsonify({"error": f"Failed to analyze session: {exc}"}), 500

    return jsonify(payload)


@app.get("/api/pipeline/run/<record_id>")
def run_pipeline_sse(record_id):
    """Stream pipeline progress as SSE. The client reads text/event-stream."""
    safe_id = secure_filename(record_id or "")
    if not safe_id:
        return jsonify({"error": "Invalid record id."}), 400

    json_path = audio_record_path(safe_id)
    if not json_path.exists():
        return jsonify({"error": "Record not found."}), 404

    log_queue = queue.Queue()
    STEPS_TOTAL = 5

    def do_run():
        try:
            import pipeline as pl
            import re as _re
            step = [0]
            _seg_pattern = _re.compile(r"^Emotion analysis: (\d+)/(\d+) segments$")

            def log(msg):
                msg_str = str(msg)
                m = _seg_pattern.match(msg_str)
                if m:
                    done, total = int(m.group(1)), int(m.group(2))
                    log_queue.put({
                        "progress": step[0],
                        "total": STEPS_TOTAL,
                        "sub_progress": done,
                        "sub_total": total,
                        "message": msg_str,
                    })
                else:
                    step[0] += 1
                    log_queue.put({
                        "progress": min(step[0], STEPS_TOTAL),
                        "total": STEPS_TOTAL,
                        "message": msg_str,
                    })
            pl.run_pipeline(str(json_path), log=log)
        except Exception as exc:
            log_queue.put({"progress": STEPS_TOTAL, "total": STEPS_TOTAL, "message": f"Error: {exc}", "error": True})
        finally:
            log_queue.put(None)  # sentinel

    thread = threading.Thread(target=do_run, daemon=True)
    thread.start()

    def generate():
        while True:
            item = log_queue.get()
            if item is None:
                yield "event: done\ndata: {}\n\n"
                break
            import json as _json
            yield f"data: {_json.dumps(item)}\n\n"

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/wizard")
@app.get("/wizard/")
def wizard():
    return render_template("wizard.html")

@app.get("/wizard/<session_name>")
def wizard_session(session_name):
    return render_template("wizard_session.html", session_name=session_name)

@app.get("/")
def root():
    return redirect("/login")

@app.get("/login")
def login():
    return render_template("login.html")

# Legacy entry point for the old user page.
@app.get("/user")
def user_interface():
    return redirect("/login")

@app.get("/<user_name>/analysis/<session_name>")
def user_session_detail(user_name, session_name):
    record = find_latest_audio_record(session_name)
    display_name = (record.get("displayName") if record else None) or session_name
    current_user_record = lookup_user_by_username(user_name) or {}
    return render_template(
        "session.html",
        current_user=user_name,
        current_user_record=current_user_record,
        current_session=session_name,
        display_name=display_name,
    )


@app.get("/emotion/<session_name>")
@app.get("/wizard/<session_name>/emotion")
def user_emotion_detail(session_name):
    return render_template(
        "emotion_session.html",
        current_session=session_name,
    )

@app.get("/intent/<session_name>")
@app.get("/wizard/<session_name>/intent")
def user_intent_detail(session_name):
    return render_template(
        "intent_session.html",
        current_session=session_name,
    )

@app.get("/<user_name>/practice")
def user_practice(user_name):
    current_user_record = lookup_user_by_username(user_name) or {}
    return render_template("practice.html", current_user=user_name, current_user_record=current_user_record)


@app.get("/<user_name>/journaling")
def user_journaling(user_name):
    current_user_record = lookup_user_by_username(user_name) or {}
    return render_template("journaling.html", current_user=user_name, current_user_record=current_user_record)

@app.get("/<user_name>/analysis")
def user_analysis(user_name):
    current_user_record = lookup_user_by_username(user_name) or {}
    return render_template("analysis.html", current_user=user_name, current_user_record=current_user_record)

@app.get("/<user_name>/nudges")
def user_nudges(user_name):
    current_user_record = lookup_user_by_username(user_name) or {}
    return render_template("nudge_settings.html", current_user=user_name, current_user_record=current_user_record)

@app.get("/<user_name>/nudges/custom")
def user_custom_nudge(user_name):
    current_user_record = lookup_user_by_username(user_name) or {}
    return render_template("custom_nudge.html", current_user=user_name, current_user_record=current_user_record)

@app.get("/<user_name>")
def user_sessions(user_name):
    current_user_record = lookup_user_by_username(user_name) or {}
    return render_template("dashboard.html", current_user=user_name, current_user_record=current_user_record)

def evaluate_diagram_for_reflection(diagram, session_name="", wearer_agent_override=None):
    """Evaluate one intent diagram and return a reflection_tree dict or None."""
    built = ReflectionTree().build_objects_from_graph(diagram)
    wearer_id, wearer_agent = find_wearer(built["agents"])
    if wearer_agent_override and wearer_agent is None:
        wearer_agent = wearer_agent_override

    reflection_tree = None
    participant_unclear_feedback_issue = detect_participant_unclear_feedback(built["agents"])
    participant_unclear_concern_issue = detect_participant_unclear_concern(built["agents"])

    if wearer_agent is not None:
        unclear_feedback_issue = detect_unclear_feedback(wearer_agent)
        good_feedback_issue = detect_good_feedback(wearer_agent)
        unclear_concern_issue = detect_unclear_concern(wearer_agent)
        good_concern_issue = detect_good_concern(wearer_agent)
        good_excitement_issue = detect_good_excitement(wearer_agent)
        tone_issue = detect_tone_incoherence(wearer_agent)
        intensity_issue = detect_intensity_incoherence(wearer_agent)

        if reflection_tree is None and tone_issue is not None:
            reflection_tree = ReflectionTree().build_from_incoherent_tone(tone_issue["goal"], wearer=wearer_agent).to_dict()
        if reflection_tree is None and intensity_issue is not None:
            reflection_tree = ReflectionTree().build_from_incoherent_intensity_issue(intensity_issue["issue"], wearer=wearer_agent).to_dict()
        if reflection_tree is None and unclear_feedback_issue is not None:
            reflection_tree = ReflectionTree().build_from_unclear_feedback_issue(unclear_feedback_issue, wearer=wearer_agent).to_dict()
        if reflection_tree is None and unclear_concern_issue is not None:
            reflection_tree = ReflectionTree().build_from_unclear_concerns_issue(
                unclear_concern_issue, wearer=wearer_agent,
                blockers_without_actionables=unclear_concern_issue.get("blockers_without_actionables"),
            ).to_dict()
        if reflection_tree is None and good_feedback_issue is not None:
            reflection_tree = ReflectionTree().build_from_good_feedback_issue(good_feedback_issue, wearer=wearer_agent).to_dict()
        if reflection_tree is None and good_concern_issue is not None:
            reflection_tree = ReflectionTree().build_from_good_concern_issue(good_concern_issue, wearer=wearer_agent).to_dict()
        if reflection_tree is None and good_excitement_issue is not None:
            reflection_tree = ReflectionTree().build_from_good_excitement_issue(good_excitement_issue, wearer=wearer_agent).to_dict()

    if reflection_tree is None and participant_unclear_feedback_issue is not None:
        reflection_tree = ReflectionTree().build_from_participant_unclear_feedback_issue(
            participant_unclear_feedback_issue, agent=participant_unclear_feedback_issue.get("agent"),
        ).to_dict()
    if reflection_tree is None and participant_unclear_concern_issue is not None:
        reflection_tree = ReflectionTree().build_from_participant_unclear_concern_issue(
            participant_unclear_concern_issue, agent=participant_unclear_concern_issue.get("agent"),
        ).to_dict()

    return reflection_tree, wearer_id, wearer_agent


@app.post("/api/audio/intent/<intent_filename>/generate_reflections")
def generate_reflections_from_intent(intent_filename):
    safe_filename = secure_filename(intent_filename or "")
    if not is_json_filename(safe_filename):
        return jsonify({"error": "Invalid intent filename."}), 400

    intent_data = read_data_json_file(safe_filename)
    if intent_data is None:
        return jsonify({"error": "Intent file not found."}), 404

    diagrams = intent_data.get("diagrams", [])
    session_name = intent_data.get("sessionName", "")
    results = []

    rows, fieldnames = load_reflection_db_rows()

    latest_audio_record = find_latest_audio_record(session_name)
    meeting_id = latest_audio_record.get("id", "") if latest_audio_record else ""

    for diagram in diagrams:
        reflection_tree, wearer_id, wearer_agent = evaluate_diagram_for_reflection(diagram, session_name)
        if reflection_tree is None:
            continue

        timestamp = datetime.now(timezone.utc).isoformat()
        safe_ts = timestamp.replace(":", "-").replace("+", "Z")

        reflection_tree["timestamp"] = timestamp
        reflection_tree["startMs"] = diagram.get("startms")
        reflection_tree["endMs"] = diagram.get("endms")
        reflection_tree["session_name"] = session_name

        start_node_id = reflection_tree.get("start_node")
        first_node = reflection_tree.get("nodes", {}).get(start_node_id, {}) if start_node_id else {}
        first_message = first_node.get("text")
        if first_message:
            post_tip_to_bangle(first_message)

        reflection_filename = f"reflection_{safe_ts}.json"
        write_data_json_file(reflection_filename, reflection_tree)

        wearer_agent_name = (
            getattr(wearer_agent, 'name', None) or getattr(wearer_agent, 'role', None) or wearer_id
            if wearer_agent is not None else wearer_id
        )
        # Map the diagram agent name to a user_id
        resolved_user_id = lookup_user_id_by_username(wearer_agent_name) if wearer_agent_name else ""
        rows.append({
            "user_id": resolved_user_id,
            "reflection_tree_file": reflection_filename,
            "startms": reflection_tree.get("startMs", ""),
            "endms": reflection_tree.get("endMs", ""),
            "practice": "null",
            "meeting_id": meeting_id,
            "tree_type": str(reflection_tree.get("type", "") or ""),
            "has_journaling": "true" if _tree_has_journaling(reflection_tree) else "false",
        })

        results.append({
            "reflection_tree": reflection_tree,
            "reflection_tree_file": reflection_filename,
            "user_id": resolved_user_id,
            "username": wearer_agent_name,
            "startms": diagram.get("startms"),
            "endms": diagram.get("endms"),
        })

    write_reflection_db_rows(rows, fieldnames)
    return jsonify({"generated": len(results), "reflections": results})


@app.post("/play_graph")
def play_graph():

    payload = request.get_json() or {}

    nodes = payload.get("nodes")
    edges = payload.get("edges")

    if not isinstance(nodes, list) or not isinstance(edges, list):
        return jsonify({"error": "nodes and edges must be lists"}), 400

    timestamp = datetime.now(timezone.utc).isoformat()
    safe_ts = timestamp.replace(":", "-").replace("+", "Z")

    built = ReflectionTree().build_objects_from_graph(payload)

    # Find wearer and evaluate tone/intensity coherence via business rules.
    wearer_id, wearer_agent = find_wearer(built["agents"])

    tone_check = {
        "wearer_agent_id": wearer_id,
        "wearer_found": wearer_agent is not None,
        "is_tone_coherent": None,
        "incoherent_goals": [],
    }
    unclear_feedback_check = {
        "wearer_agent_id": wearer_id,
        "wearer_found": wearer_agent is not None,
        "has_unclear_feedback": None,
        "issue": None,
    }
    good_feedback_check = {
        "wearer_agent_id": wearer_id,
        "wearer_found": wearer_agent is not None,
        "has_good_feedback": None,
        "issue": None,
    }
    unclear_concerns_check = {
        "wearer_agent_id": wearer_id,
        "wearer_found": wearer_agent is not None,
        "has_unclear_concerns": None,
        "issue": None,
    }
    good_concern_check = {
        "wearer_agent_id": wearer_id,
        "wearer_found": wearer_agent is not None,
        "has_good_concern": None,
        "issue": None,
    }
    good_excitement_check = {
        "wearer_agent_id": wearer_id,
        "wearer_found": wearer_agent is not None,
        "has_good_excitement": None,
        "issue": None,
    }
    intensity_check = {
        "wearer_agent_id": wearer_id,
        "wearer_found": wearer_agent is not None,
        "is_intensity_coherent": None,
        "issues": [],
    }
    reflection_tree = None
    participant_unclear_feedback_issue = None
    participant_unclear_concern_issue = None

    if wearer_agent is not None:
        participant_unclear_feedback_issue = detect_participant_unclear_feedback(built["agents"])
        participant_unclear_concern_issue = detect_participant_unclear_concern(built["agents"])
        unclear_feedback_issue = detect_unclear_feedback(wearer_agent)
        good_feedback_issue = detect_good_feedback(wearer_agent)
        unclear_concern_issue = detect_unclear_concern(wearer_agent)
        good_concern_issue = detect_good_concern(wearer_agent)
        good_excitement_issue = detect_good_excitement(wearer_agent)
        tone_issue = detect_tone_incoherence(wearer_agent)
        intensity_issue = detect_intensity_incoherence(wearer_agent)

        unclear_feedback_check["has_unclear_feedback"] = unclear_feedback_issue is not None
        unclear_feedback_check["issue"] = summarize_rule_issue(unclear_feedback_issue)

        good_feedback_check["has_good_feedback"] = good_feedback_issue is not None
        good_feedback_check["issue"] = summarize_rule_issue(good_feedback_issue)

        unclear_concerns_check["has_unclear_concerns"] = unclear_concern_issue is not None
        unclear_concerns_check["issue"] = summarize_rule_issue(unclear_concern_issue)

        good_concern_check["has_good_concern"] = good_concern_issue is not None
        good_concern_check["issue"] = summarize_rule_issue(good_concern_issue)

        good_excitement_check["has_good_excitement"] = good_excitement_issue is not None
        good_excitement_check["issue"] = summarize_rule_issue(good_excitement_issue)

        tone_check["is_tone_coherent"], tone_check["incoherent_goals"] = summarize_tone_issue(tone_issue)

        intensity_check["is_intensity_coherent"], intensity_check["issues"] = summarize_intensity_issue(intensity_issue)

        if reflection_tree is None and unclear_feedback_issue is not None:
            reflection_tree = ReflectionTree().build_from_unclear_feedback_issue(
                unclear_feedback_issue,
                wearer=wearer_agent,
            ).to_dict()

        if reflection_tree is None and unclear_concern_issue is not None:
            reflection_tree = ReflectionTree().build_from_unclear_concerns_issue(
                unclear_concern_issue,
                wearer=wearer_agent,
                blockers_without_actionables=unclear_concern_issue.get("blockers_without_actionables"),
            ).to_dict()

        if reflection_tree is None and tone_issue is not None:
            reflection_tree = ReflectionTree().build_from_incoherent_tone(
                tone_issue["goal"],
                wearer=wearer_agent,
            ).to_dict()

        if reflection_tree is None and intensity_issue is not None:
            reflection_tree = ReflectionTree().build_from_incoherent_intensity_issue(
                intensity_issue["issue"],
                wearer=wearer_agent,
            ).to_dict()

        if reflection_tree is None and good_feedback_issue is not None:
            reflection_tree = ReflectionTree().build_from_good_feedback_issue(
                good_feedback_issue,
                wearer=wearer_agent,
            ).to_dict()

        if reflection_tree is None and good_concern_issue is not None:
            reflection_tree = ReflectionTree().build_from_good_concern_issue(
                good_concern_issue,
                wearer=wearer_agent,
            ).to_dict()

        if reflection_tree is None and good_excitement_issue is not None:
            reflection_tree = ReflectionTree().build_from_good_excitement_issue(
                good_excitement_issue,
                wearer=wearer_agent,
            ).to_dict()

    if reflection_tree is None and participant_unclear_feedback_issue is not None:
        reflection_tree = ReflectionTree().build_from_participant_unclear_feedback_issue(
            participant_unclear_feedback_issue,
            agent=participant_unclear_feedback_issue.get("agent"),
        ).to_dict()

    if reflection_tree is None and participant_unclear_concern_issue is not None:
        reflection_tree = ReflectionTree().build_from_participant_unclear_concern_issue(
            participant_unclear_concern_issue,
            agent=participant_unclear_concern_issue.get("agent"),
        ).to_dict()

    print("\n=== GRAPH CREATED ===")
    for k, v in built["agents"].items():
        print(k, v)
    for k, v in built["goals"].items():
        print(k, v)
    for k, v in built["blockers"].items():
        print(k, v)
    for k, v in built["actionables"].items():
        print(k, v)
    for k, v in built["questions"].items():
        print(k, v)

    reflection_filename = None

    wearer_agent_name = None
    resolved_user_id = ""
    if reflection_tree:
        reflection_tree["timestamp"] = timestamp
        reflection_tree["startMs"] = payload.get("startMs")
        reflection_tree["endMs"] = payload.get("endMs")
        reflection_tree["session_name"] = payload.get("sessionName")

        start_node_id = reflection_tree.get("start_node")
        first_node = reflection_tree.get("nodes", {}).get(start_node_id, {}) if start_node_id else {}
        first_message = first_node.get("text")

        if first_message:
            post_tip_to_bangle(first_message)

        reflection_filename = f"reflection_{safe_ts}.json"
        reflection_path = write_data_json_file(reflection_filename, reflection_tree)

        wearer_agent_name = None
        if wearer_agent is not None:
            wearer_agent_name = getattr(wearer_agent, 'name', None) or getattr(wearer_agent, 'role', None) or wearer_id
        else:
            wearer_agent_name = wearer_id
        resolved_user_id = lookup_user_id_by_username(wearer_agent_name) if wearer_agent_name else ""
        latest_audio_record = find_latest_audio_record(reflection_tree.get("session_name", ""))
        rows, fieldnames = load_reflection_db_rows()

        rows.append({
            "user_id": resolved_user_id,
            "reflection_tree_file": str(reflection_path.name),
            "startms": reflection_tree.get("startMs", ""),
            "endms": reflection_tree.get("endMs", ""),
            "practice": "null",
            "audio_filename": latest_audio_record.get("audioFilename", "") if latest_audio_record else "",
            "tree_type": str(reflection_tree.get("type", "") or ""),
            "has_journaling": "true" if _tree_has_journaling(reflection_tree) else "false",
        })
        write_reflection_db_rows(rows, fieldnames)

    return jsonify({
        "message": "ok",
        "user_id": resolved_user_id if reflection_tree else None,
        "username": wearer_agent_name,
        "agents": {k: repr(v) for k, v in built["agents"].items()},
        "goals": {k: repr(v) for k, v in built["goals"].items()},
        "blockers": {k: repr(v) for k, v in built["blockers"].items()},
        "actionables": {k: repr(v) for k, v in built["actionables"].items()},
        "questions": {k: repr(v) for k, v in built["questions"].items()},
        "unclear_feedback_check": unclear_feedback_check,
        "good_feedback_check": good_feedback_check,
        "unclear_concerns_check": unclear_concerns_check,
        "good_concern_check": good_concern_check,
        "good_excitement_check": good_excitement_check,
        "tone_check": tone_check,
        "intensity_check": intensity_check,
        "reflection_tree": reflection_tree,
        "reflection_tree_file": reflection_filename,
    })


@app.delete("/api/audio/reflection/<reflection_filename>")
def delete_reflection(reflection_filename):
    safe_filename = secure_filename(reflection_filename or "")
    if not is_json_filename(safe_filename):
        return jsonify({"error": "Invalid reflection filename."}), 400

    remaining_rows = []
    deleted_row = None

    rows, fieldnames = load_reflection_db_rows()
    for row in rows:
        if row.get("reflection_tree_file", "") == safe_filename and deleted_row is None:
            deleted_row = row
            continue
        remaining_rows.append(row)

    write_reflection_db_rows(remaining_rows, fieldnames)

    file_deleted = delete_data_json_file(safe_filename)
    delete_journal_entry_row(safe_filename)

    if deleted_row is None and not file_deleted:
        return jsonify({"error": "Reflection not found."}), 404

    return jsonify({
        "message": "reflection deleted",
        "reflection_tree_file": safe_filename,
    })


@app.post("/api/audio/reflection/<reflection_filename>/practice")
def update_reflection_practice(reflection_filename):
    safe_filename = secure_filename(reflection_filename or "")
    if not is_json_filename(safe_filename):
        return jsonify({"error": "Invalid reflection filename."}), 400

    payload = request.get_json(silent=True) or {}
    requested_practice = payload.get("practice")
    raw_practice_value = str(requested_practice or "").strip().lower()
    if raw_practice_value not in {"done", "todo", "null"}:
        return jsonify({"error": "Invalid practice value."}), 400

    practice_value = normalize_practice_value(requested_practice)

    rows, fieldnames = load_reflection_db_rows()
    updated_row = None
    for row in rows:
        if row.get("reflection_tree_file", "") != safe_filename:
            continue
        row["practice"] = practice_value
        updated_row = row
        break

    if updated_row is None:
        return jsonify({"error": "Reflection not found."}), 404

    write_reflection_db_rows(rows, fieldnames)
    return jsonify({
        "message": "practice updated",
        "reflection_tree_file": safe_filename,
        "practice": updated_row.get("practice", "null"),
    })


@app.post("/api/voice/generate")
def voice_generate():
    payload = request.get_json(silent=True) or {}
    session_name = str(payload.get("session_name", "") or "").strip()
    reflection_id = str(payload.get("reflection_id", "") or "").strip()
    # Accept user_id or wearer_agent (legacy)
    user_id = str(payload.get("user_id", "") or payload.get("wearer_agent", "") or "").strip()
    # Resolve to user_id if a username was passed
    if user_id and not lookup_user_by_id(user_id):
        user_id = lookup_user_id_by_username(user_id)
    training_type = str(payload.get("type", "") or "").strip()
    transcription = str(payload.get("transcription", "") or "").strip()
    summary = str(payload.get("summary", "") or "").strip()
    emotion = str(payload.get("emotion", "") or "").strip()

    def _to_float(value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    valence = _to_float(payload.get("valence"))
    arousal = _to_float(payload.get("arousal"))
    dominance = _to_float(payload.get("dominance"))

    if not session_name or not transcription:
        return jsonify({"error": "Missing required parameters: session_name, transcription"}), 400

    if not emotion and not all(v is not None for v in (valence, arousal, dominance)):
        return jsonify({"error": "Provide either emotion or valence+arousal+dominance"}), 400

    meeting_id = lookup_meeting_id_by_session_name(session_name)

    try:
        from pipeline.elevenlabs_voice import generate_tagged_voice
        result = generate_tagged_voice(
            transcript=transcription,
            meeting_id=meeting_id,
            emotion=emotion,
            summary=summary,
            reflection_id=reflection_id,
            user_id=user_id,
            training_type=training_type,
            valence=valence,
            arousal=arousal,
            dominance=dominance,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"Voice generation failed: {exc}"}), 500

    return jsonify(result)


@app.post("/save_recording")
def save_recording():
    audio = request.files.get("audio")
    session_name = build_session_name(
        audio.filename if audio else "recording",
        request.form.get("session_name") or "",
    )

    if not audio:
        return jsonify({"error": "missing audio file"}), 400

    safe_session_name = secure_filename(session_name) or "recording"
    ext = Path(audio.filename or "").suffix or ".webm"

    filename = secure_filename(f"{safe_session_name}{ext}")
    output_path = DATA_DIR / filename

    audio.save(output_path)

    return jsonify({
        "message": "recording saved",
        "filename": filename,
        "path": str(output_path),
    })


@app.get("/uploads/<path:filename>")
def serve_uploaded_audio(filename):
    return send_from_directory(UPLOAD_DIR, filename, conditional=True)


@app.get("/training_audio/<path:filename>")
def serve_training_audio(filename):
    return send_from_directory(TRAINING_AUDIO_DIR, filename, conditional=True)


# ── User CRUD endpoints ──────────────────────────────────────────────────────

@app.get("/api/users")
def list_users():
    rows, _ = load_user_rows()
    return jsonify({"users": rows})


@app.post("/api/users")
def create_user():
    payload = request.get_json() or {}
    username = str(payload.get("username", "") or "").strip()
    name = str(payload.get("name", "") or "").strip()
    if not username:
        return jsonify({"error": "username is required"}), 400
    if not name:
        name = username
    user = {
        "username": username,
        "name": name,
    }
    # Copy nudge fields if provided
    from data_store import USERS_CSV_FIELDNAMES
    for field in USERS_CSV_FIELDNAMES:
        if field.startswith("nudge_") and field in payload:
            user[field] = str(payload[field]).lower()
    try:
        saved = save_user(user)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 409
    return jsonify(saved), 201


@app.get("/api/users/<username>")
def get_user(username):
    user = lookup_user_by_username(username)
    if user is None:
        return jsonify({"error": "User not found"}), 404
    return jsonify(user)


@app.patch("/api/users/<username>")
def update_user(username):
    user = lookup_user_by_username(username)
    if user is None:
        return jsonify({"error": "User not found"}), 404
    payload = request.get_json() or {}
    from data_store import USERS_CSV_FIELDNAMES
    allowed = set(USERS_CSV_FIELDNAMES) - {"id"}
    for field in allowed:
        if field in payload:
            user[field] = str(payload[field]).strip() if not isinstance(payload[field], bool) else str(payload[field]).lower()
    try:
        saved = save_user(user)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 409
    return jsonify(saved)


@app.get("/api/practice/<user_name>")
def list_practice_items(user_name):
    items = build_practice_items_for_user(user_name)
    return jsonify({"user": user_name, "items": items})


@app.get("/api/journaling/<user_name>")
def list_journaling_items(user_name):
    items = build_journaling_items_for_user(user_name)
    return jsonify({"user": user_name, "items": items})


@app.patch("/api/journaling/<reflection_filename>/<node_id>")
def update_journal_entry(reflection_filename, node_id):
    safe_filename = secure_filename(reflection_filename or "")
    safe_node_id = str(node_id or "").strip()
    if not is_json_filename(safe_filename):
        return jsonify({"error": "Invalid reflection filename."}), 400
    if not safe_node_id:
        return jsonify({"error": "Invalid journaling node id."}), 400

    payload = request.get_json(silent=True) or {}
    journal_entry = str(payload.get("journal_entry", "") or "").strip()

    rows, _ = load_reflection_db_rows()
    row_exists = any(
        str(row.get("reflection_tree_file", "") or "").strip() == safe_filename
        for row in rows
    )
    if not row_exists:
        return jsonify({"error": "Reflection row not found."}), 404

    entry_map = _parse_journal_entry_map(load_journal_entry_raw(safe_filename))
    entry_map[safe_node_id] = journal_entry
    upsert_journal_entry_raw(safe_filename, _serialize_journal_entry_map(entry_map))
    return jsonify({
        "reflection_tree_file": safe_filename,
        "node_id": safe_node_id,
        "journal_entry": journal_entry,
    })


@app.patch("/api/practice/<training_id>/done")
def update_practice_done(training_id):
    safe_training_id = str(training_id or "").strip()
    if not safe_training_id:
        return jsonify({"error": "Invalid training id."}), 400

    payload = request.get_json(silent=True) or {}
    done_value = _parse_bool(payload.get("done"))
    if done_value is None:
        return jsonify({"error": "Invalid done value."}), 400

    rows = load_training_rows()
    updated = None
    for row in rows:
        if str(row.get("training_id", "") or "").strip() != safe_training_id:
            continue
        row["done"] = "true" if done_value else "false"
        updated = row
        break

    if updated is None:
        return jsonify({"error": "Training row not found."}), 404

    write_training_rows(rows)
    return jsonify({
        "training_id": safe_training_id,
        "done": normalize_done_str(updated.get("done", "false")) == "true",
    })


@app.post("/api/audio/upload")
def upload_audio():
    audio = request.files.get("audio")

    if not audio:
        return jsonify({"error": "No audio file uploaded."}), 400

    if not audio.filename:
        return jsonify({"error": "Empty filename."}), 400

    if not allowed_audio_file(audio.filename):
        return jsonify({"error": "Unsupported file type."}), 400

    safe_name = secure_filename(audio.filename)
    if not safe_name:
        return jsonify({"error": "Invalid filename."}), 400

    session_name = build_session_name(audio.filename, request.form.get("session_name") or "")

    audio_id = str(uuid.uuid4())
    stored_filename = f"{audio_id}_{safe_name}"
    output_path = UPLOAD_DIR / stored_filename

    try:
        audio.save(output_path)
        transcript = transcribe_audio_file(output_path)
    except RuntimeError as exc:
        if output_path.exists():
            output_path.unlink()
        return jsonify({"error": str(exc)}), 500
    except Exception as exc:
        if output_path.exists():
            output_path.unlink()
        return jsonify({"error": f"Failed to process audio: {exc}"}), 500

    record = {
        "id": audio_id,
        "audioUrl": f"/uploads/{stored_filename}",
        "audioFilename": stored_filename,
        "originalName": audio.filename,
        "sessionName": session_name,
        "safeSessionName": secure_filename(session_name),
        "uploadedAt": datetime.now(timezone.utc).isoformat(),
        "transcript": transcript,
    }
    save_meeting(record)

    return jsonify(record)


@app.get("/api/audio/latest")
def get_latest_audio():
    session_name = request.args.get("session_name", "")
    record = find_latest_audio_record(session_name)

    if record is None:
        return jsonify({"error": "No uploaded audio found."}), 404

    return jsonify(record)


@app.get("/api/audio/sessions")
def list_audio_sessions():
    username = request.args.get("username", "").strip()
    user_id_filter = ""
    if username:
        user = lookup_user_by_username(username)
        user_id_filter = user.get("id", "") if user else ""
    sessions = [
        summarize_audio_record(record)
        for record in iter_meetings()
        if not user_id_filter or record.get("userId", "") == user_id_filter
    ]
    return jsonify({"sessions": sessions})


@app.get("/api/audio/session/<session_name>/reflections")
def list_session_reflection_trees(session_name):
    reflections = []
    rows, _ = load_reflection_db_rows()
    for row in rows:
        if row.get("session_name", "") != session_name:
            continue

        reflection_file = row.get("reflection_tree_file", "")
        if not reflection_file:
            continue

        reflection_payload = build_reflection_response_row(row, reflection_file)
        if reflection_payload is None:
            continue

        reflections.append(reflection_payload)

    reflections.sort(key=lambda item: float(item.get("startms") or 0))
    return jsonify({"session": session_name, "reflections": reflections})


# --- NEW: Endpoint for intent files for a session ---
@app.get("/api/audio/session/<session_name>/intents")
def list_session_intent_files(session_name):
    intents = []
    rows, _ = load_intent_rows()
    for row in rows:
        if row.get("session_name", "") != session_name:
            continue

        intent_file = row.get("intent_filename", "")
        if not is_json_filename(intent_file):
            continue
        intent_data = read_data_json_file(intent_file)
        if intent_data is None:
            continue

        intents.append({
            "intent_file": intent_file,
            "wearer_agent": row.get("wearer_agent", ""),
            "startms": row.get("startms", ""),
            "endms": row.get("endms", ""),
            "meeting_id": row.get("meeting_id", ""),
            "data": intent_data,
        })

    intents.sort(key=lambda item: float(item.get("startms") or 0))
    return jsonify({"session": session_name, "intents": intents})


@app.get("/api/audio/session/<session_name>/emotion")
def get_session_emotion(session_name):
    try:
        payload = build_emotion_session_payload(session_name)
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 500
    except Exception as exc:
        return jsonify({"error": f"Failed to analyze PAD for session: {exc}"}), 500

    return jsonify(payload)


@app.get("/api/audio/<audio_id>")
def get_audio(audio_id):
    record = load_meeting(audio_id)

    if record is None:
        return jsonify({"error": "Not found"}), 404

    record.setdefault("displayName", record.get("sessionName"))
    user_id = str(record.get("userId", "") or record.get("user_id", "") or "").strip()
    if not user_id:
        # Older transcript JSON files may not include userId; fall back to meetings.csv
        meeting_rows, _ = load_meeting_rows()
        for meeting_row in meeting_rows:
            if str(meeting_row.get("id", "") or "").strip() == str(audio_id or "").strip():
                user_id = str(meeting_row.get("user_id", "") or "").strip()
                if user_id:
                    record["userId"] = user_id
                    record["user_id"] = user_id
                break
    record["username"] = lookup_username_by_user_id(user_id)
    return jsonify(record)


@app.patch("/api/audio/<audio_id>")
def patch_audio(audio_id):
    record = load_meeting(audio_id)
    if record is None:
        return jsonify({"error": "Not found"}), 404

    body = request.get_json(force=True, silent=True) or {}
    new_name = str(body.get("displayName", "") or "").strip()
    new_user_id = str(body.get("userId", "") or "").strip()

    if not new_name and not new_user_id:
        return jsonify({"error": "displayName or userId is required"}), 400

    if new_name:
        record["displayName"] = new_name
    if new_user_id:
        record["userId"] = new_user_id
        record["user_id"] = new_user_id
    save_meeting(record)
    return jsonify({"displayName": record.get("displayName", ""), "userId": record.get("userId", "")})


@app.delete("/api/audio/<audio_id>")
def delete_audio(audio_id):
    record = load_meeting(audio_id)

    if record is None:
        return jsonify({"error": "Not found"}), 404

    audio_filename = str(record.get("audioFilename", "") or "").strip()
    deleted_reflection_files = []

    rows, fieldnames = load_reflection_db_rows()
    remaining_rows = []
    for row in rows:
        if audio_id and row.get("meeting_id", "") == audio_id:
            reflection_file = str(row.get("reflection_tree_file", "") or "").strip()
            if reflection_file:
                delete_data_json_file(reflection_file)
                delete_journal_entry_row(reflection_file)
                deleted_reflection_files.append(reflection_file)
            continue
        remaining_rows.append(row)

    write_reflection_db_rows(remaining_rows, fieldnames)

    deleted_audio_file = False
    if audio_filename:
        audio_path = UPLOAD_DIR / audio_filename
        if audio_path.exists() and audio_path.is_file():
            audio_path.unlink()
            deleted_audio_file = True

    delete_meeting(audio_id)

    return jsonify({
        "message": "audio deleted",
        "audio_id": audio_id,
        "audio_filename": audio_filename,
        "deleted_audio_file": deleted_audio_file,
        "deleted_reflection_files": deleted_reflection_files,
    })


@app.get("/api/audio/<audio_id>/reflections")
def list_reflections_for_audio(audio_id):
    record = load_meeting(audio_id)

    if record is None:
        return jsonify({"error": "Not found"}), 404

    session_name = str(record.get("sessionName", "") or "").strip()
    reflections = []
    rows, _ = load_reflection_db_rows()

    for row in rows:
        if row.get("meeting_id", "") != audio_id:
            continue

        reflection_file = row.get("reflection_tree_file", "")
        if not reflection_file:
            continue

        reflection_payload = build_reflection_response_row(row, reflection_file)
        if reflection_payload is None:
            continue

        reflections.append(reflection_payload)

    reflections.sort(key=lambda item: float(item.get("startms") or 0))
    return jsonify({"session": session_name, "reflections": reflections})


# Place the /reflection/<user> endpoint here, after all other route functions
@app.get("/reflection/<user>")
def list_reflections_for_user(user):
    # Resolve username -> user record
    user_record = lookup_user_by_username(user)
    user_id = user_record.get("id", "") if user_record else ""

    # List meetings from meetings.csv filtered by user_id
    rows, _ = load_meeting_rows()
    sessions = []
    for row in rows:
        if user_id and row.get("user_id", "") != user_id:
            continue
        sn = row.get("session_name", "").strip()
        display = row.get("display_name", "").strip() or sn
        if sn:
            sessions.append({"sessionName": sn, "displayName": display})
    sessions.sort(key=lambda s: s["sessionName"])
    return jsonify({"user": user, "session_names": [s["sessionName"] for s in sessions], "sessions": sessions})


# Place the /reflection/<user>/<session> endpoint here, after all other route functions
@app.get("/reflection/<user>/<session>")
def list_reflection_files_for_user_session(user, session):
    user_record = lookup_user_by_username(user)
    user_id = user_record.get("id", "") if user_record else ""
    results = []
    rows, _ = load_reflection_db_rows()
    for row in rows:
        row_user_id = row.get("user_id", "")
        row_session = row.get("session_name", "")
        if (user_id and row_user_id != user_id) or row_session != session:
            continue
        results.append({
            "reflection_tree_file": row.get("reflection_tree_file", ""),
            "user_id": row_user_id,
            "username": user,
            "startms": row.get("startms", ""),
            "endms": row.get("endms", ""),
            "practice": row.get("practice", "null"),
        })
    return jsonify({
        "user": user,
        "session": session,
        "reflections": results
    })

@app.get("/recording/<session_name>")
def serve_recording(session_name):
    file = find_data_recording_file(session_name, suffixes={'.webm', '.ogg'})
    if file is not None:
        mimetype = "audio/webm" if file.suffix == ".webm" else "audio/ogg"
        return send_from_directory(DATA_DIR, file.name, mimetype=mimetype, conditional=True)
    abort(404, description="Recording not found")

# Endpoint to return reflection tree JSON by file name
@app.get("/reflection_tree/<filename>")
def get_reflection_tree(filename):
    if not is_json_filename(filename):
        abort(404, description="Reflection tree not found")
    data = read_data_json_file(filename)
    if data is None:
        abort(404, description="Reflection tree not found")
    return jsonify(data)

if __name__ == "__main__":
    debug_enabled = True
    should_start_ngrok = not debug_enabled or os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    if should_start_ngrok:
        start_ngrok(port=5001)
    app.run(debug=debug_enabled, port=5001)