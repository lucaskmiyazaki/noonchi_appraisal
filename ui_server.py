"""
User server — port 5001.

Serves user-facing analysis / journaling / practice / nudges pages
and the read-oriented API endpoints those pages call.
"""
from __future__ import annotations

import atexit
import json
import os
from datetime import datetime, timezone
from urllib.parse import quote

from flask import Flask, jsonify, request, render_template, redirect, send_from_directory, abort, Response
from flask_cors import CORS
from pathlib import Path
from werkzeug.utils import secure_filename

from data_store import (
    DATA_DIR,
    TRAINING_AUDIO_DIR,
    UPLOAD_DIR,
    ensure_data_layout,
    find_data_recording_file,
    is_json_filename,
    iter_meetings,
    iter_meetings_for_username,
    list_meeting_sessions_for_user,
    list_reflection_rows_for_audio,
    list_reflection_rows_for_session,
    list_reflection_rows_for_user_session,
    load_meeting,
    load_journal_entry_raw,
    lookup_meeting_id_by_session_name,
    lookup_user_by_id,
    lookup_user_by_username,
    lookup_user_id_by_username,
    lookup_username_by_user_id,
    normalize_done_str,
    normalize_practice_value,
    load_training_rows,
    read_data_json_file,
    update_user as ds_update_user,
    enrich_meeting_user_fields,
    save_meeting,
    upsert_journal_entry_raw,
    write_reflection_db_rows,
    write_training_rows,
)
from server_helpers import (
    _parse_bool,
    _parse_journal_entry_map,
    _serialize_journal_entry_map,
    build_emotion_session_payload,
    build_journaling_items_for_user,
    build_practice_items_for_user,
    build_reflection_response_row,
    build_session_analysis_payload,
    find_latest_audio_record,
    load_reflection_db_rows,
    start_ngrok,
    stop_ngrok,
)

app = Flask(__name__)
CORS(app)

ensure_data_layout()


# ── Local helper ──────────────────────────────────────────────────────────────

def summarize_audio_record(record: dict) -> dict:
    session_name = str(record.get("sessionName", "") or "")
    audio_url = str(record.get("audioUrl", "") or "")
    uploaded_at = str(record.get("uploadedAt", "") or "")
    transcript = record.get("transcript") or []

    first_text = ""
    for chunk in transcript:
        text = str(chunk.get("text", "") or "").strip()
        if text:
            first_text = text
            break

    return {
        "id": record.get("id"),
        "sessionName": session_name,
        "safeSessionName": record.get("safeSessionName", ""),
        "displayName": record.get("displayName", ""),
        "audioUrl": audio_url,
        "audioFilename": record.get("audioFilename", ""),
        "uploadedAt": uploaded_at,
        "segmentCount": len(transcript),
        "firstSegmentText": first_text,
        "userId": record.get("userId", "") or record.get("user_id", ""),
    }


# ── Page routes ───────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return redirect("/login")


@app.get("/login")
def login():
    return render_template("login.html")


@app.get("/user")
def user_interface():
    return redirect("/login")


@app.get("/<user_name>")
def user_home(user_name):
    current_user_record = lookup_user_by_username(user_name) or {}
    return render_template("dashboard.html", current_user=user_name, current_user_record=current_user_record)


@app.get("/<user_name>/analysis")
def user_analysis(user_name):
    current_user_record = lookup_user_by_username(user_name) or {}
    return render_template("analysis.html", current_user=user_name, current_user_record=current_user_record)


@app.get("/<user_name>/analysis/<session_name>")
def user_analysis_session(user_name, session_name):
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


@app.get("/<user_name>/practice")
def user_practice(user_name):
    current_user_record = lookup_user_by_username(user_name) or {}
    return render_template("practice.html", current_user=user_name, current_user_record=current_user_record)


@app.get("/<user_name>/journaling")
def user_journaling(user_name):
    current_user_record = lookup_user_by_username(user_name) or {}
    return render_template("journaling.html", current_user=user_name, current_user_record=current_user_record)


@app.get("/<user_name>/nudges")
def user_nudges(user_name):
    current_user_record = lookup_user_by_username(user_name) or {}
    return render_template("nudge_settings.html", current_user=user_name, current_user_record=current_user_record)


@app.get("/<user_name>/nudges/custom")
def user_nudges_custom(user_name):
    current_user_record = lookup_user_by_username(user_name) or {}
    return render_template("custom_nudge.html", current_user=user_name, current_user_record=current_user_record)


@app.get("/emotion/<session_name>")
def emotion_detail(session_name):
    return render_template("emotion_session.html", current_session=session_name)


@app.get("/intent/<session_name>")
def intent_detail(session_name):
    return render_template("intent_session.html", current_session=session_name)


# ── Audio endpoints ───────────────────────────────────────────────────────────

@app.get("/api/audio/latest")
def get_latest_audio():
    session_name = str(request.args.get("session_name", "") or "").strip()
    record = find_latest_audio_record(session_name)
    if record is None:
        return jsonify({"error": "No uploaded audio found."}), 404
    return jsonify(record)


@app.get("/api/audio/sessions")
def list_audio_sessions():
    user_name = str(request.args.get("username", "") or request.args.get("user", "") or "").strip()
    records_raw = list(iter_meetings_for_username(user_name) if user_name else iter_meetings())
    sessions = [summarize_audio_record(r) for r in records_raw]
    return jsonify({"sessions": sessions, "count": len(sessions)})


@app.get("/api/audio/<audio_id>")
def get_audio(audio_id):
    record = load_meeting(audio_id)
    if record is None:
        return jsonify({"error": "Not found"}), 404
    record.setdefault("displayName", record.get("sessionName"))
    enrich_meeting_user_fields(record, audio_id)
    return jsonify(record)


@app.get("/api/audio/session/<session_name>/reflections")
def list_session_reflections(session_name):
    reflections = []
    meeting_id = lookup_meeting_id_by_session_name(session_name)

    for row in list_reflection_rows_for_session(session_name):
        reflection_file = row.get("reflection_tree_file", "")
        if not reflection_file:
            continue
        reflection_payload = build_reflection_response_row(row, reflection_file)
        if reflection_payload is None:
            continue
        reflections.append(reflection_payload)

    reflections.sort(key=lambda item: float(item.get("startms") or 0))
    return jsonify({"session": session_name, "reflections": reflections, "meeting_id": meeting_id})


@app.get("/api/audio/session/<session_name>/emotion")
def get_session_emotion(session_name):
    try:
        payload = build_emotion_session_payload(session_name)
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"error": f"Failed to build emotion payload: {exc}"}), 500
    return jsonify(payload)


@app.get("/api/audio/session/<session_name>/analysis")
def get_session_analysis(session_name):
    try:
        payload = build_session_analysis_payload(session_name)
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"error": f"Failed to analyze session: {exc}"}), 500
    return jsonify(payload)


@app.get("/api/audio/<audio_id>/reflections")
def list_reflections_for_audio(audio_id):
    record = load_meeting(audio_id)
    if record is None:
        return jsonify({"error": "Not found"}), 404

    session_name = str(record.get("sessionName", "") or "").strip()
    reflections = []
    for row in list_reflection_rows_for_audio(audio_id):
        reflection_file = row.get("reflection_tree_file", "")
        if not reflection_file:
            continue
        reflection_payload = build_reflection_response_row(row, reflection_file)
        if reflection_payload is None:
            continue
        reflections.append(reflection_payload)

    reflections.sort(key=lambda item: float(item.get("startms") or 0))
    return jsonify({"session": session_name, "reflections": reflections})


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


# ── Reflection tree views ─────────────────────────────────────────────────────

@app.get("/reflection/<user>")
def list_reflections_for_user(user):
    sessions = list_meeting_sessions_for_user(user)
    return jsonify({"user": user, "session_names": [s["sessionName"] for s in sessions], "sessions": sessions})


@app.get("/reflection/<user>/<session>")
def list_reflection_files_for_user_session(user, session):
    results = []
    for row in list_reflection_rows_for_user_session(user, session):
        row_user_id = row.get("user_id", "")
        results.append({
            "reflection_tree_file": row.get("reflection_tree_file", ""),
            "user_id": row_user_id,
            "username": user,
            "startms": row.get("startms", ""),
            "endms": row.get("endms", ""),
            "practice": row.get("practice", "null"),
        })
    return jsonify({"user": user, "session": session, "reflections": results})


@app.get("/reflection_tree/<filename>")
def get_reflection_tree(filename):
    if not is_json_filename(filename):
        abort(404, description="Reflection tree not found")
    data = read_data_json_file(filename)
    if data is None:
        abort(404, description="Reflection tree not found")
    return jsonify(data)


# ── Journaling ────────────────────────────────────────────────────────────────

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


@app.get("/api/journaling/<user_name>")
def list_journaling_items(user_name):
    items = build_journaling_items_for_user(user_name)
    return jsonify({"user": user_name, "items": items})


# ── Practice ──────────────────────────────────────────────────────────────────

@app.get("/api/practice/<user_name>")
def list_practice_items(user_name):
    items = build_practice_items_for_user(user_name)
    return jsonify({"user": user_name, "items": items})


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


# ── User profile ──────────────────────────────────────────────────────────────

@app.get("/api/users/<username>")
def get_user(username):
    user = lookup_user_by_username(username)
    if user is None:
        return jsonify({"error": "User not found"}), 404
    return jsonify(user)


@app.patch("/api/users/<username>")
def update_user(username):
    existing = lookup_user_by_username(username)
    if existing is None:
        return jsonify({"error": "User not found"}), 404

    payload = request.get_json() or {}
    try:
        saved = ds_update_user(username, payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 409

    if saved is None:
        return jsonify({"error": "User not found"}), 404

    return jsonify(saved)


# ── Static file serving ───────────────────────────────────────────────────────

@app.get("/uploads/<path:filename>")
def serve_uploaded_audio(filename):
    return send_from_directory(UPLOAD_DIR, filename, conditional=True)


@app.get("/training_audio/<path:filename>")
def serve_training_audio(filename):
    return send_from_directory(TRAINING_AUDIO_DIR, filename, conditional=True)


@app.get("/recording/<session_name>")
def serve_recording(session_name):
    file = find_data_recording_file(session_name, suffixes={'.webm', '.ogg'})
    if file is not None:
        mimetype = "audio/webm" if file.suffix == ".webm" else "audio/ogg"
        return send_from_directory(DATA_DIR, file.name, mimetype=mimetype, conditional=True)
    abort(404, description="Recording not found")


if __name__ == "__main__":
    debug_enabled = str(os.environ.get("DEBUG", "true")).strip().lower() in {"1", "true", "yes", "on"}
    app.run(debug=debug_enabled, port=5001)
