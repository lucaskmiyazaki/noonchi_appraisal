from __future__ import annotations

import json
from urllib import error as url_error
from urllib import request as url_request

from flask import Flask, jsonify, request, render_template
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
DATA_DIR.mkdir(exist_ok=True)

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


@app.get("/")
def index():
    return render_template("index.html")


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
            reflection_tree = ReflectionTree().build_from_incoherent_goal(
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

    if reflection_tree:
        start_node_id = reflection_tree.get("start_node")
        first_node = reflection_tree.get("nodes", {}).get(start_node_id, {}) if start_node_id else {}
        first_message = first_node.get("text")

        if first_message:
            post_tip_to_bangle(first_message)

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
    })

@app.post("/save_recording")
def save_recording():
    audio = request.files.get("audio")
    session_name = (request.form.get("session_name") or "recording").strip()

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

if __name__ == "__main__":
    app.run(debug=True, port=5001)