import os
import json
import uuid
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
import whisper

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = "uploads"
DATA_FOLDER = "data"
ALLOWED_EXTENSIONS = {
    "mp3", "wav", "m4a", "ogg", "webm", "mp4", "mpeg", "mpga"
}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DATA_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["DATA_FOLDER"] = DATA_FOLDER

model = whisper.load_model("base")


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def transcribe_with_whisper(file_path):
    result = model.transcribe(file_path, fp16=False)

    transcript = []
    for i, segment in enumerate(result.get("segments", []), start=1):
        text = segment.get("text", "").strip()
        start = float(segment.get("start", 0.0))
        end = float(segment.get("end", 0.0))

        if text:
            transcript.append({
                "id": i,
                "text": text,
                "start": start,
                "end": end
            })

    return transcript


@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


@app.route("/api/audio/upload", methods=["POST"])
def upload_audio():
    if "audio" not in request.files:
        return jsonify({"error": "No audio file uploaded."}), 400

    file = request.files["audio"]

    if file.filename == "":
        return jsonify({"error": "Empty filename."}), 400

    if not allowed_file(file.filename):
        return jsonify({"error": "Unsupported file type."}), 400

    safe_name = secure_filename(file.filename)
    unique_filename = f"{uuid.uuid4()}_{safe_name}"
    file_path = os.path.join(app.config["UPLOAD_FOLDER"], unique_filename)

    try:
        file.save(file_path)

        transcript = transcribe_with_whisper(file_path)

        audio_id = str(uuid.uuid4())
        audio_url = f"http://localhost:4000/uploads/{unique_filename}"

        record = {
            "id": audio_id,
            "audioUrl": audio_url,
            "originalName": file.filename,
            "transcript": transcript
        }

        # save JSON
        with open(os.path.join(DATA_FOLDER, f"{audio_id}.json"), "w") as f:
            json.dump(record, f, indent=2)

        return jsonify(record)

    except Exception as e:
        return jsonify({"error": f"Failed to process audio: {str(e)}"}), 500


@app.route("/api/audio/<audio_id>", methods=["GET"])
def get_audio(audio_id):
    file_path = os.path.join(DATA_FOLDER, f"{audio_id}.json")

    if not os.path.exists(file_path):
        return jsonify({"error": "Not found"}), 404

    with open(file_path, "r") as f:
        data = json.load(f)

    return jsonify(data)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=4000, debug=True)