from __future__ import annotations

import atexit
import json
import os
import shutil
import subprocess
import time
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from urllib import error as url_error
from urllib import request as url_request

from flask import Flask, jsonify, request, render_template, redirect, send_from_directory, abort
from flask_cors import CORS

from pathlib import Path
from werkzeug.utils import secure_filename

from reflection import ReflectionTree
from business_rules import (
    find_speaker,
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

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR
AUDIO_DATA_DIR = DATA_DIR
DATA_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(exist_ok=True)

NGROK_API_URL = "http://127.0.0.1:4040/api/tunnels"
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


def save_audio_record(record):
    record_path = AUDIO_DATA_DIR / f"{record['id']}.json"
    record_path.write_text(json.dumps(record, indent=2), encoding="utf-8")


def load_audio_record(record_id):
    record_path = AUDIO_DATA_DIR / f"{record_id}.json"
    if not record_path.exists():
        return None
    return json.loads(record_path.read_text(encoding="utf-8"))


def is_audio_record(record):
    return isinstance(record, dict) and {
        "id",
        "audioUrl",
        "audioFilename",
        "transcript",
    }.issubset(record.keys())


def iter_audio_records():
    records = []
    for path in sorted(DATA_DIR.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        if is_audio_record(record):
            records.append(record)

    return records


def summarize_audio_record(record):
    transcript = record.get("transcript") or []
    last_segment = transcript[-1] if transcript else {}
    return {
        "id": record.get("id"),
        "sessionName": record.get("sessionName"),
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

    for record in iter_audio_records():
        if not requested_session:
            return record

        if record.get("sessionName") == requested_session:
            return record

        if safe_session_name and record.get("safeSessionName") == safe_session_name:
            return record

    if requested_session:
        return find_latest_audio_record("")

    return None


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

    NGROK_PROCESS = subprocess.Popen(
        [ngrok_path, "http", str(port), "--scheme=http,https"],
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


@app.get("/wizard")
def wizard():
    return render_template("wizard.html")

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

@app.get("/<user_name>/<session_name>")
def user_session_detail(user_name, session_name):
    return render_template(
        "session.html",
        current_user=user_name,
        current_session=session_name,
    )

@app.get("/<user_name>")
def user_sessions(user_name):
    return render_template("user.html", current_user=user_name)

@app.post("/play_graph")
def play_graph():
    payload = request.get_json() or {}

    nodes = payload.get("nodes")
    edges = payload.get("edges")

    if not isinstance(nodes, list) or not isinstance(edges, list):
        return jsonify({"error": "nodes and edges must be lists"}), 400

    built = ReflectionTree().build_objects_from_graph(payload)

    # Find speaker and evaluate tone/intensity coherence via business rules.
    speaker_id, speaker_agent = find_speaker(built["agents"])

    tone_check = {
        "speaker_agent_id": speaker_id,
        "speaker_found": speaker_agent is not None,
        "is_tone_coherent": None,
        "incoherent_goals": [],
    }
    unclear_feedback_check = {
        "speaker_agent_id": speaker_id,
        "speaker_found": speaker_agent is not None,
        "has_unclear_feedback": None,
        "issue": None,
    }
    unclear_concerns_check = {
        "speaker_agent_id": speaker_id,
        "speaker_found": speaker_agent is not None,
        "has_unclear_concerns": None,
        "issue": None,
    }
    intensity_check = {
        "speaker_agent_id": speaker_id,
        "speaker_found": speaker_agent is not None,
        "is_intensity_coherent": None,
        "issues": [],
    }
    reflection_tree = None

    if speaker_agent is not None:
        unclear_feedback_issue = detect_unclear_feedback(speaker_agent)
        unclear_concern_issue = detect_unclear_concern(speaker_agent)
        tone_issue = detect_tone_incoherence(speaker_agent)
        intensity_issue = detect_intensity_incoherence(speaker_agent)

        unclear_feedback_check["has_unclear_feedback"] = unclear_feedback_issue is not None
        unclear_feedback_check["issue"] = summarize_rule_issue(unclear_feedback_issue)

        unclear_concerns_check["has_unclear_concerns"] = unclear_concern_issue is not None
        unclear_concerns_check["issue"] = summarize_rule_issue(unclear_concern_issue)

        tone_check["is_tone_coherent"], tone_check["incoherent_goals"] = summarize_tone_issue(tone_issue)

        intensity_check["is_intensity_coherent"], intensity_check["issues"] = summarize_intensity_issue(intensity_issue)

        if reflection_tree is None and tone_issue is not None:
            reflection_tree = ReflectionTree().build_from_incoherent_tone(
                tone_issue["goal"],
                speaker=speaker_agent,
            ).to_dict()

        if reflection_tree is None and unclear_feedback_issue is not None:
            reflection_tree = ReflectionTree().build_from_unclear_feedback_issue(
                unclear_feedback_issue,
                speaker=speaker_agent,
            ).to_dict()

        if reflection_tree is None and unclear_concern_issue is not None:
            reflection_tree = ReflectionTree().build_from_unclear_concerns_issue(
                unclear_concern_issue,
                speaker=speaker_agent,
                blockers_without_actionables=unclear_concern_issue.get("blockers_without_actionables"),
            ).to_dict()

        if reflection_tree is None and intensity_issue is not None:
            reflection_tree = ReflectionTree().build_from_incoherent_intensity_issue(
                intensity_issue["issue"],
                speaker=speaker_agent,
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

    timestamp = datetime.now(timezone.utc).isoformat()

    reflection_filename = None

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

        safe_ts = timestamp.replace(":", "-").replace("+", "Z")
        reflection_filename = f"reflection_{safe_ts}.json"
        reflection_path = DATA_DIR / reflection_filename
        reflection_path.write_text(json.dumps(reflection_tree, indent=2))

        # --- DB CSV LOGIC ---
        import csv
        db_path = DATA_DIR / "db.csv"
        db_exists = db_path.exists()
        speaker_agent_name = None
        if speaker_agent is not None:
            # Try to get a readable name, fallback to id
            speaker_agent_name = getattr(speaker_agent, 'name', None) or getattr(speaker_agent, 'role', None) or speaker_id
        else:
            speaker_agent_name = speaker_id
        row = [
            speaker_agent_name,
            reflection_tree.get("session_name", ""),
            str(reflection_path.name),
            reflection_tree.get("startMs", ""),
            reflection_tree.get("endMs", ""),
        ]
        with open(db_path, "a", newline="") as csvfile:
            writer = csv.writer(csvfile)
            if not db_exists:
                writer.writerow(["speaker_agent", "session_name", "reflection_tree_file", "startms", "endms"])
            writer.writerow(row)

    return jsonify({
        "message": "ok",
        "agents": {k: repr(v) for k, v in built["agents"].items()},
        "goals": {k: repr(v) for k, v in built["goals"].items()},
        "blockers": {k: repr(v) for k, v in built["blockers"].items()},
        "actionables": {k: repr(v) for k, v in built["actionables"].items()},
        "questions": {k: repr(v) for k, v in built["questions"].items()},
        "unclear_feedback_check": unclear_feedback_check,
        "unclear_concerns_check": unclear_concerns_check,
        "tone_check": tone_check,
        "intensity_check": intensity_check,
        "reflection_tree": reflection_tree,
        "reflection_tree_file": reflection_filename,
    })


@app.delete("/api/audio/reflection/<reflection_filename>")
def delete_reflection(reflection_filename):
    import csv

    safe_filename = secure_filename(reflection_filename or "")
    if not safe_filename or Path(safe_filename).suffix != ".json":
        return jsonify({"error": "Invalid reflection filename."}), 400

    db_path = DATA_DIR / "db.csv"
    remaining_rows = []
    deleted_row = None

    if db_path.exists():
        with open(db_path, newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            fieldnames = reader.fieldnames or ["speaker_agent", "session_name", "reflection_tree_file", "startms", "endms"]

            for row in reader:
                if row.get("reflection_tree_file", "") == safe_filename and deleted_row is None:
                    deleted_row = row
                    continue
                remaining_rows.append(row)

        with open(db_path, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(remaining_rows)

    reflection_path = DATA_DIR / safe_filename
    file_deleted = False
    if reflection_path.exists() and reflection_path.is_file():
        reflection_path.unlink()
        file_deleted = True

    if deleted_row is None and not file_deleted:
        return jsonify({"error": "Reflection not found."}), 404

    return jsonify({
        "message": "reflection deleted",
        "reflection_tree_file": safe_filename,
    })

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
    save_audio_record(record)

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
    sessions = [summarize_audio_record(record) for record in iter_audio_records()]
    return jsonify({"sessions": sessions})


@app.get("/api/audio/session/<session_name>/reflections")
def list_session_reflection_trees(session_name):
    import csv

    db_path = DATA_DIR / "db.csv"
    reflections = []
    if db_path.exists():
        with open(db_path, newline="") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                if row.get("session_name", "") != session_name:
                    continue

                reflection_file = row.get("reflection_tree_file", "")
                if not reflection_file:
                    continue

                reflection_path = DATA_DIR / reflection_file
                if not reflection_path.exists() or reflection_path.suffix != ".json":
                    continue

                try:
                    tree = json.loads(reflection_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue

                reflections.append({
                    "reflection_tree_file": reflection_file,
                    "startms": row.get("startms", ""),
                    "endms": row.get("endms", ""),
                    "tree": tree,
                })

    reflections.sort(key=lambda item: int(item.get("startms") or 0))
    return jsonify({"session": session_name, "reflections": reflections})


@app.get("/api/audio/<audio_id>")
def get_audio(audio_id):
    record = load_audio_record(audio_id)

    if record is None:
        return jsonify({"error": "Not found"}), 404

    return jsonify(record)


# Place the /reflection/<user> endpoint here, after all other route functions
@app.get("/reflection/<user>")
def list_reflections_for_user(user):
    import csv
    db_path = DATA_DIR / "db.csv"
    session_names = set()
    if db_path.exists():
        with open(db_path, newline="") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                # Case-insensitive match for user
                session = row.get("session_name", "")
                if row.get("speaker_agent", "").lower() == user.lower() and session:
                    session_names.add(session)
    return jsonify({"user": user, "session_names": sorted(session_names)})


# Place the /reflection/<user>/<session> endpoint here, after all other route functions
@app.get("/reflection/<user>/<session>")
def list_reflection_files_for_user_session(user, session):
    import csv
    db_path = DATA_DIR / "db.csv"
    results = []
    if db_path.exists():
        with open(db_path, newline="") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                # Case-insensitive match for user and exact match for session
                if row.get("speaker_agent", "").lower() == user.lower() and row.get("session_name", "") == session:
                    results.append({
                        "reflection_tree_file": row.get("reflection_tree_file", ""),
                        "startms": row.get("startms", ""),
                        "endms": row.get("endms", "")
                    })
    return jsonify({
        "user": user,
        "session": session,
        "reflections": results
    })

@app.get("/recording/<session_name>")
def serve_recording(session_name):
    # Try to find a file in DATA_DIR with the session_name as prefix
    for file in DATA_DIR.iterdir():
        if file.name.startswith(session_name) and file.suffix in {'.webm', '.ogg'}:
            mimetype = "audio/webm" if file.suffix == ".webm" else "audio/ogg"
            return send_from_directory(DATA_DIR, file.name, mimetype=mimetype, conditional=True)
    abort(404, description="Recording not found")

# Endpoint to return reflection tree JSON by file name
@app.get("/reflection_tree/<filename>")
def get_reflection_tree(filename):
    file_path = DATA_DIR / filename
    if not file_path.exists() or not file_path.suffix == '.json':
        abort(404, description="Reflection tree not found")
    with open(file_path, 'r', encoding='utf-8') as f:
        data = f.read()
    return data, 200, {'Content-Type': 'application/json'}

if __name__ == "__main__":
    debug_enabled = True
    should_start_ngrok = not debug_enabled or os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    if should_start_ngrok:
        start_ngrok(port=5001)
    app.run(debug=debug_enabled, port=5001)