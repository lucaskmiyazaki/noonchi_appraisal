"""
Wizard server — port 5002.

Serves wizard.html / wizard_session.html and all the heavy-processing API
endpoints those pages call: audio upload + transcription, pipeline SSE,
intent CRUD, diagram evaluation, reflection generation.
"""
from __future__ import annotations

import atexit
import json
import os
import threading
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from urllib.parse import quote

from flask import Flask, jsonify, request, render_template, redirect, send_from_directory, abort, Response
from flask_cors import CORS
from pathlib import Path
from werkzeug.utils import secure_filename

from data_store import (
    DATA_DIR,
    TRAINING_AUDIO_DIR,
    UPLOAD_DIR,
    audio_record_path,
    delete_data_json_file,
    delete_intent_row,
    delete_journal_entry_row,
    delete_meeting,
    ensure_data_layout,
    find_data_recording_file,
    is_json_filename,
    list_reflection_rows_for_audio,
    load_intent_rows,
    load_meeting,
    load_user_rows,
    lookup_user_by_id,
    lookup_user_by_username,
    lookup_user_id_by_username,
    lookup_username_by_user_id,
    read_data_json_file,
    create_user as ds_create_user,
    update_user as ds_update_user,
    enrich_meeting_user_fields,
    save_meeting,
    upsert_intent_reflection_row,
    write_reflection_db_rows,
    write_data_json_file,
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
    summarize_intensity_issue,
    summarize_rule_issue,
    summarize_tone_issue,
)
from server_helpers import (
    _tree_has_journaling,
    build_reflection_response_row,
    build_session_analysis_payload,
    evaluate_diagram_for_reflection,
    find_latest_audio_record,
    load_reflection_db_rows,
    post_tip_to_bangle,
    start_ngrok,
    stop_ngrok,
)

app = Flask(__name__)
CORS(app)

ensure_data_layout()

AUDIO_ALLOWED_EXTENSIONS = {"mp3", "wav", "m4a", "ogg", "webm", "mp4", "mpeg", "mpga"}


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
    import whisper as _whisper
    import numpy as _np
    audio = _whisper.load_audio(str(file_path))
    if audio is None or len(audio) == 0:
        raise ValueError("Audio file appears to be empty or silent.")
    # Whisper's internal STFT uses chunks of 3000 mel frames (30 s).
    # Any non-zero length audio is safe to transcribe.
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


@app.get("/wizard")
@app.get("/wizard/")
def wizard():
    return render_template("wizard.html")


@app.get("/wizard/<session_name>")
def wizard_session(session_name):
    return render_template("wizard_session.html", session_name=session_name)


@app.get("/wizard/<session_name>/emotion")
def wizard_emotion_detail(session_name):
    return render_template("emotion_session.html", current_session=session_name)


@app.get("/wizard/<session_name>/intent")
def wizard_intent_detail(session_name):
    return render_template("intent_session.html", current_session=session_name)


# ── Audio upload ──────────────────────────────────────────────────────────────

_upload_jobs: dict = {}  # job_id -> {status, message, [record]}


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
    except Exception as exc:
        if output_path.exists():
            output_path.unlink()
        return jsonify({"error": f"Failed to save audio: {exc}"}), 500

    job_id = str(uuid.uuid4())
    original_name = audio.filename
    _upload_jobs[job_id] = {"status": "transcribing", "progress": 0, "message": "Transcribing audio…"}

    def _run():
        import time as _time
        try:
            # Send heartbeat progress ticks while Whisper runs (indeterminate)
            import threading as _threading
            _stop = _threading.Event()
            _tick = [0]

            def _heartbeat():
                while not _stop.wait(2):
                    # Oscillate progress 0–90 to show activity
                    _tick[0] = (_tick[0] + 10) % 91
                    if _upload_jobs.get(job_id, {}).get("status") == "transcribing":
                        _upload_jobs[job_id]["progress"] = _tick[0]

            _ht = _threading.Thread(target=_heartbeat, daemon=True)
            _ht.start()

            transcript = transcribe_audio_file(output_path)
            _stop.set()
            record = {
                "id": audio_id,
                "audioUrl": f"/uploads/{stored_filename}",
                "audioFilename": stored_filename,
                "originalName": original_name,
                "sessionName": session_name,
                "safeSessionName": secure_filename(session_name),
                "uploadedAt": datetime.now(timezone.utc).isoformat(),
                "transcript": transcript,
            }
            save_meeting(record)
            _upload_jobs[job_id] = {"status": "done", "progress": 100, "message": "Transcription complete.", "record": record}
        except RuntimeError as exc:
            if output_path.exists():
                output_path.unlink()
            _upload_jobs[job_id] = {"status": "error", "progress": 0, "message": str(exc)}
        except Exception as exc:
            if output_path.exists():
                output_path.unlink()
            _upload_jobs[job_id] = {"status": "error", "progress": 0, "message": f"Failed to process audio: {exc}"}
        finally:
            # Keep the result in memory for 5 minutes so a page refresh can still reconnect
            def _cleanup():
                import time as _t
                _t.sleep(300)
                _upload_jobs.pop(job_id, None)
            threading.Thread(target=_cleanup, daemon=True).start()

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"job_id": job_id, "audio_id": audio_id}), 202


@app.get("/api/audio/upload/job/<job_id>")
def upload_job_status(job_id):
    """Quick poll endpoint — returns current job state or 404 if not found."""
    safe_job_id = str(job_id or "").strip()
    job = _upload_jobs.get(safe_job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    # Don't send the full record (could be large); just status/progress/message
    return jsonify({
        "status": job.get("status"),
        "progress": job.get("progress"),
        "message": job.get("message"),
    })


@app.get("/api/audio/upload/jobs/active")
def upload_jobs_active():
    """Returns the most recent in-progress transcription job, if any."""
    # Find the most recently created transcribing job (last inserted key in dict)
    active = None
    for jid, job in reversed(list(_upload_jobs.items())):
        if job.get("status") == "transcribing":
            active = {"job_id": jid, "status": job.get("status"), "progress": job.get("progress"), "message": job.get("message")}
            break
    if active:
        return jsonify(active)
    return jsonify({"job_id": None})


@app.get("/api/audio/upload/job/<job_id>/stream")
def upload_job_stream(job_id):
    """SSE stream for a transcription job."""
    import json as _json, time as _time
    safe_job_id = str(job_id or "").strip()

    def _generate():
        for _ in range(7200):  # max 2 hours
            job = _upload_jobs.get(safe_job_id)
            if not job:
                yield f"data: {_json.dumps({'status': 'error', 'message': 'Job not found'})}\n\n"
                return
            yield f"data: {_json.dumps(job)}\n\n"
            if job["status"] in ("done", "error"):
                # Don't pop here — let the delayed cleanup in _run() handle it
                # so a page refresh can reconnect and still see the final state
                return
            _time.sleep(1)

    return Response(
        _generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Pipeline SSE ──────────────────────────────────────────────────────────────

_pipeline_jobs: dict = {}  # job_id -> {status, progress, total, message, [error]}


@app.post("/api/pipeline/run/<record_id>")
def run_pipeline_start(record_id):
    """Start pipeline in background, return job_id immediately."""
    safe_id = secure_filename(record_id or "")
    if not safe_id:
        return jsonify({"error": "Invalid record id."}), 400

    json_path = audio_record_path(safe_id)
    if not json_path.exists():
        return jsonify({"error": "Record not found."}), 404

    job_id = str(uuid.uuid4())
    STEPS_TOTAL = 5
    _pipeline_jobs[job_id] = {"status": "running", "progress": 0, "total": STEPS_TOTAL, "message": "Starting pipeline…", "record_id": safe_id}

    def do_run():
        import pipeline as pl
        import re as _re
        step = [0]
        _seg_pattern = _re.compile(r"^Emotion analysis: (\d+)/(\d+) segments$")
        # Any "Emotion analysis: …" message that isn't a segment count keeps the
        # current step counter so model/audio loading doesn't skip a step.
        _emo_status_prefix = "Emotion analysis:"

        def log(msg):
            msg_str = str(msg)
            m = _seg_pattern.match(msg_str)
            if m:
                done, total = int(m.group(1)), int(m.group(2))
                _pipeline_jobs[job_id].update({
                    "progress": step[0],
                    "sub_progress": done,
                    "sub_total": total,
                    "message": msg_str,
                })
            elif msg_str.startswith(_emo_status_prefix):
                # Status update within emotion step — don't advance the step counter
                _pipeline_jobs[job_id].update({
                    "progress": step[0],
                    "sub_progress": None,
                    "sub_total": None,
                    "message": msg_str,
                })
            else:
                step[0] += 1
                _pipeline_jobs[job_id].update({
                    "progress": min(step[0], STEPS_TOTAL),
                    "sub_progress": None,
                    "sub_total": None,
                    "message": msg_str,
                })

        try:
            pl.run_pipeline(str(json_path), log=log)
            _pipeline_jobs[job_id] = {"status": "done", "progress": STEPS_TOTAL, "total": STEPS_TOTAL, "message": "Pipeline complete.", "record_id": safe_id}
        except Exception as exc:
            _pipeline_jobs[job_id] = {"status": "error", "progress": STEPS_TOTAL, "total": STEPS_TOTAL, "message": f"Error: {exc}", "error": True, "record_id": safe_id}
        finally:
            # Keep job alive for 5 minutes so a page refresh can see final state
            def _cleanup():
                import time as _t; _t.sleep(300)
                _pipeline_jobs.pop(job_id, None)
            threading.Thread(target=_cleanup, daemon=True).start()

    threading.Thread(target=do_run, daemon=True).start()
    return jsonify({"job_id": job_id}), 202


@app.get("/api/pipeline/jobs/active")
def pipeline_jobs_active():
    """Returns the most recent running OR recently-finished pipeline job, if any."""
    active = None
    for jid, job in reversed(list(_pipeline_jobs.items())):
        if job.get("status") in ("running", "done", "error"):
            active = {"job_id": jid, "status": job.get("status"), "progress": job.get("progress"), "total": job.get("total"), "message": job.get("message"), "record_id": job.get("record_id")}
            break
    if active:
        return jsonify(active)
    return jsonify({"job_id": None})


@app.get("/api/pipeline/job/<job_id>/stream")
def pipeline_job_stream(job_id):
    """SSE stream for a running pipeline job."""
    import json as _json, time as _time
    safe_job_id = str(job_id or "").strip()

    def _generate():
        for _ in range(7200):  # max 2 hours
            job = _pipeline_jobs.get(safe_job_id)
            if not job:
                yield f"data: {_json.dumps({'status': 'error', 'message': 'Job not found', 'error': True})}\n\n"
                yield "event: done\ndata: {}\n\n"
                return
            yield f"data: {_json.dumps(job)}\n\n"
            if job["status"] in ("done", "error"):
                # Don't pop here — delayed cleanup in do_run() keeps job for 5 min
                yield "event: done\ndata: {}\n\n"
                return
            _time.sleep(1)

    return Response(
        _generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Audio record access (needed by sidebar-upload.js) ─────────────────────────

@app.get("/api/audio/<audio_id>")
def get_audio(audio_id):
    record = load_meeting(audio_id)
    if record is None:
        return jsonify({"error": "Not found"}), 404
    record.setdefault("displayName", record.get("sessionName"))
    enrich_meeting_user_fields(record, audio_id)
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
                delete_journal_entry_row(str(row.get("id", "") or ""))
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


# ── Intent CRUD ───────────────────────────────────────────────────────────────

@app.delete("/api/audio/intent/<intent_filename>")
def delete_intent(intent_filename):
    safe_filename = secure_filename(intent_filename or "")
    if not is_json_filename(safe_filename):
        return jsonify({"error": "Invalid intent filename."}), 400

    deleted_row = delete_intent_row(safe_filename)
    file_deleted = delete_data_json_file(safe_filename)

    if not deleted_row and not file_deleted:
        return jsonify({"error": "Intent not found."}), 404

    return jsonify({"message": "intent deleted", "intent_file": safe_filename})


@app.post("/api/audio/session/save_intent")
def save_intent():
    payload = request.get_json() or {}
    session_name = payload.get("session_name", "").strip()
    user_id = str(payload.get("user_id", "") or payload.get("wearer_agent", "") or "").strip()
    intent_file = payload.get("intent_file", "").strip()
    intent_data = payload.get("intent_data")

    if not session_name or not intent_file or intent_data is None:
        return jsonify({"error": "Missing required fields."}), 400

    try:
        write_data_json_file(intent_file, intent_data)
    except Exception as e:
        return jsonify({"error": f"Failed to save intent file: {e}"}), 500

    meeting_record = find_latest_audio_record(session_name)
    meeting_id = meeting_record.get("id", "") if meeting_record else ""

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


# ── Reflection generation ─────────────────────────────────────────────────────

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
        resolved_user_id = lookup_user_id_by_username(wearer_agent_name) if wearer_agent_name else ""
        new_reflection_id = str(uuid.uuid4().hex)
        rows.append({
            "id": new_reflection_id,
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
            "id": new_reflection_id,
            "reflection_tree": reflection_tree,
            "reflection_tree_file": reflection_filename,
            "user_id": resolved_user_id,
            "username": wearer_agent_name,
            "startms": diagram.get("startms"),
            "endms": diagram.get("endms"),
        })

    write_reflection_db_rows(rows, fieldnames)
    return jsonify({"generated": len(results), "reflections": results})


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
    delete_journal_entry_row(str(deleted_row.get("id", "") or "") if deleted_row else "")

    if deleted_row is None and not file_deleted:
        return jsonify({"error": "Reflection not found."}), 404

    return jsonify({"message": "reflection deleted", "reflection_tree_file": safe_filename})


# ── Voice generation ──────────────────────────────────────────────────────────

_voice_jobs: dict = {}  # job_id -> {status, progress, message, [result]}


@app.post("/api/voice/generate")
def voice_generate():
    payload = request.get_json(silent=True) or {}
    session_name = str(payload.get("session_name", "") or "").strip()
    reflection_id = str(payload.get("reflection_id", "") or "").strip()
    user_id = str(payload.get("user_id", "") or payload.get("wearer_agent", "") or "").strip()
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

    from data_store import (
        append_training_row,
        is_json_filename,
        lookup_meeting_id_by_session_name,
        read_data_json_file,
    )
    meeting_id = lookup_meeting_id_by_session_name(session_name)

    # Pre-save the training row immediately (empty audio files) so the
    # practice item appears in the list right away while generation runs.
    training_id = uuid.uuid4().hex
    _tree_type = _startms = _endms = ""
    if reflection_id and is_json_filename(reflection_id):
        try:
            _ref_tree = read_data_json_file(reflection_id) or {}
            _tree_type = str(_ref_tree.get("type", "") or "")
            _startms = str(_ref_tree.get("startMs", "") or "")
            _endms = str(_ref_tree.get("endMs", "") or "")
        except Exception:
            pass

    append_training_row(
        training_id=training_id,
        meeting_id=meeting_id,
        reflection_id=reflection_id,
        user_id=user_id,
        training_type=training_type,
        valence=valence,
        arousal=arousal,
        dominance=dominance,
        training_files=[],
        transcription=transcription,
        summary=summary,
        suggestions=[],
        tree_type=_tree_type,
        startms=_startms,
        endms=_endms,
    )

    job_id = str(uuid.uuid4())
    _voice_jobs[job_id] = {"status": "pending", "progress": 0, "message": "Starting voice generation…"}

    def _run():
        try:
            _voice_jobs[job_id].update({"progress": 20, "message": "Generating AI voice…"})
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
                existing_training_id=training_id,
            )
            _voice_jobs[job_id] = {"status": "done", "progress": 100, "message": "Voice ready.", "result": result}
        except ValueError as exc:
            _voice_jobs[job_id] = {"status": "error", "message": str(exc)}
        except Exception as exc:
            _voice_jobs[job_id] = {"status": "error", "message": f"Voice generation failed: {exc}"}

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"job_id": job_id, "training_id": training_id}), 202


@app.get("/api/voice/job/<job_id>/stream")
def voice_job_stream(job_id):
    import json as _json, time as _time
    safe_job_id = str(job_id or "").strip()

    def _generate():
        for _ in range(600):
            job = _voice_jobs.get(safe_job_id)
            if not job:
                yield f"data: {_json.dumps({'status': 'error', 'message': 'Job not found'})}\n\n"
                return
            yield f"data: {_json.dumps(job)}\n\n"
            if job["status"] in ("done", "error"):
                _voice_jobs.pop(safe_job_id, None)
                return
            _time.sleep(1)

    return Response(
        _generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Graph play (live diagram evaluation) ──────────────────────────────────────

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
    wearer_id, wearer_agent = find_wearer(built["agents"])

    tone_check = {"wearer_agent_id": wearer_id, "wearer_found": wearer_agent is not None, "is_tone_coherent": None, "incoherent_goals": []}
    unclear_feedback_check = {"wearer_agent_id": wearer_id, "wearer_found": wearer_agent is not None, "has_unclear_feedback": None, "issue": None}
    good_feedback_check = {"wearer_agent_id": wearer_id, "wearer_found": wearer_agent is not None, "has_good_feedback": None, "issue": None}
    unclear_concerns_check = {"wearer_agent_id": wearer_id, "wearer_found": wearer_agent is not None, "has_unclear_concerns": None, "issue": None}
    good_concern_check = {"wearer_agent_id": wearer_id, "wearer_found": wearer_agent is not None, "has_good_concern": None, "issue": None}
    good_excitement_check = {"wearer_agent_id": wearer_id, "wearer_found": wearer_agent is not None, "has_good_excitement": None, "issue": None}
    intensity_check = {"wearer_agent_id": wearer_id, "wearer_found": wearer_agent is not None, "is_intensity_coherent": None, "issues": []}

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
            reflection_tree = ReflectionTree().build_from_unclear_feedback_issue(unclear_feedback_issue, wearer=wearer_agent).to_dict()
        if reflection_tree is None and unclear_concern_issue is not None:
            reflection_tree = ReflectionTree().build_from_unclear_concerns_issue(unclear_concern_issue, wearer=wearer_agent, blockers_without_actionables=unclear_concern_issue.get("blockers_without_actionables")).to_dict()
        if reflection_tree is None and tone_issue is not None:
            reflection_tree = ReflectionTree().build_from_incoherent_tone(tone_issue["goal"], wearer=wearer_agent).to_dict()
        if reflection_tree is None and intensity_issue is not None:
            reflection_tree = ReflectionTree().build_from_incoherent_intensity_issue(intensity_issue["issue"], wearer=wearer_agent).to_dict()
        if reflection_tree is None and good_feedback_issue is not None:
            reflection_tree = ReflectionTree().build_from_good_feedback_issue(good_feedback_issue, wearer=wearer_agent).to_dict()
        if reflection_tree is None and good_concern_issue is not None:
            reflection_tree = ReflectionTree().build_from_good_concern_issue(good_concern_issue, wearer=wearer_agent).to_dict()
        if reflection_tree is None and good_excitement_issue is not None:
            reflection_tree = ReflectionTree().build_from_good_excitement_issue(good_excitement_issue, wearer=wearer_agent).to_dict()

    if reflection_tree is None and participant_unclear_feedback_issue is not None:
        reflection_tree = ReflectionTree().build_from_participant_unclear_feedback_issue(participant_unclear_feedback_issue, agent=participant_unclear_feedback_issue.get("agent")).to_dict()
    if reflection_tree is None and participant_unclear_concern_issue is not None:
        reflection_tree = ReflectionTree().build_from_participant_unclear_concern_issue(participant_unclear_concern_issue, agent=participant_unclear_concern_issue.get("agent")).to_dict()

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

        if wearer_agent is not None:
            wearer_agent_name = getattr(wearer_agent, 'name', None) or getattr(wearer_agent, 'role', None) or wearer_id
        else:
            wearer_agent_name = wearer_id
        resolved_user_id = lookup_user_id_by_username(wearer_agent_name) if wearer_agent_name else ""
        latest_audio_record = find_latest_audio_record(reflection_tree.get("session_name", ""))
        rows, fieldnames = load_reflection_db_rows()
        rows.append({
            "id": str(uuid.uuid4().hex),
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


# ── Users (needed by sidebar-upload.js to assign wearer) ─────────────────────

@app.get("/api/users")
def list_users():
    rows, _ = load_user_rows()
    return jsonify({"users": rows})


@app.post("/api/users")
def create_user():
    payload = request.get_json() or {}
    username = str(payload.get("username", "") or "").strip()
    name = str(payload.get("name", "") or "").strip()
    try:
        saved = ds_create_user(username=username, name=name, updates=payload)
    except ValueError as exc:
        status = 400 if "required" in str(exc).lower() else 409
        return jsonify({"error": str(exc)}), status
    return jsonify(saved), 201


@app.get("/api/users/<username>")
def get_user(username):
    user = lookup_user_by_username(username)
    if user is None:
        return jsonify({"error": "User not found"}), 404
    return jsonify(user)


# ── Static file serving ───────────────────────────────────────────────────────

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
    return jsonify({"message": "recording saved", "filename": filename, "path": str(output_path)})


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
    app.run(debug=debug_enabled, port=5002)
