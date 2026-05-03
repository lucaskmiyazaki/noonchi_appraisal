"""
Shared helper functions used by both processing_server.py and ui_server.py.
No Flask routes here — only pure Python utilities and ngrok management.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from urllib import error as url_error
from urllib import request as url_request
from urllib.parse import quote
from werkzeug.utils import secure_filename

from data_store import (
    is_json_filename,
    iter_audio_records,
    load_journal_entry_raw,
    load_meeting,
    load_reflection_db_rows as _load_reflection_db_rows,
    load_training_rows,
    lookup_user_by_id,
    lookup_user_by_username,
    lookup_user_id_by_username,
    lookup_username_by_user_id,
    normalize_done_str,
    normalize_training_type_str,
    read_data_json_file,
)
from models.reflection import ReflectionTree
from rules.business_rules import (
    detect_good_concern,
    detect_good_excitement,
    detect_good_feedback,
    detect_intensity_incoherence,
    detect_participant_unclear_concern,
    detect_participant_unclear_feedback,
    detect_tone_incoherence,
    detect_unclear_concern,
    detect_unclear_feedback,
    find_wearer,
)

NGROK_API_URL = "http://127.0.0.1:4040/api/tunnels"
NGROK_URL = (os.environ.get("NGROK_URL") or "https://noonchi.ngrok.io").strip()
NGROK_PROCESS = None


# ── Audio record lookup ───────────────────────────────────────────────────────

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

        record_display_name = str(record.get("displayName", "") or "").strip()
        if record_display_name and record_display_name == requested_session:
            return record

        if record_display_name and record_display_name.casefold() == requested_session_folded:
            return record

    return None


def load_reflection_db_rows():
    return _load_reflection_db_rows()


# ── Payload builders ──────────────────────────────────────────────────────────

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


def build_reflection_response_row(row, reflection_file):
    try:
        tree = read_data_json_file(reflection_file)
    except (OSError, json.JSONDecodeError):
        return None
    if tree is None:
        return None

    return {
        "id": row.get("id", ""),
        "reflection_tree_file": reflection_file,
        "user_id": row.get("user_id", ""),
        "username": lookup_username_by_user_id(row.get("user_id", "")),
        "startms": row.get("startms", ""),
        "endms": row.get("endms", ""),
        "practice": row.get("practice", "null"),
        "meeting_id": row.get("meeting_id", ""),
        "tree": tree,
    }


# ── Type helpers ──────────────────────────────────────────────────────────────

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


# ── Journal entry helpers ─────────────────────────────────────────────────────

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


# ── User data builders ────────────────────────────────────────────────────────

def build_journaling_items_for_user(user_name: str):
    rows, _ = load_reflection_db_rows()
    items = []
    user = lookup_user_by_username(user_name) or lookup_user_by_id(user_name)
    target_user_id = user.get("id", "") if user else ""

    for row in rows:
        row_user_id = str(row.get("user_id", "") or "").strip()
        if target_user_id and row_user_id != target_user_id:
            continue

        reflection_file = str(row.get("reflection_tree_file", "") or "").strip()
        if not is_json_filename(reflection_file):
            continue

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
        entry_map = _parse_journal_entry_map(load_journal_entry_raw(str(row.get("id", "") or "")))
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
            "created_at": str(row.get("created_at", "") or "").strip(),
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

    items.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return items


# ── Ngrok ─────────────────────────────────────────────────────────────────────

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


# ── Bangle.js tip ─────────────────────────────────────────────────────────────

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


# ── Diagram evaluation ────────────────────────────────────────────────────────

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
