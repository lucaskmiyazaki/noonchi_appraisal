import os
import csv
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs

from models.constants import EMOTION_CATEGORY_BY_EMOTION, UNIFIED_TAGS_BY_CATEGORY, SUGGESTIONS_BY_CATEGORY, OPPOSITE_CATEGORY, classify_emotion_from_vad


load_dotenv()


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR.parent / "data"
TRAINING_AUDIO_DIR = DATA_DIR / "training_audio"
TRAINING_CSV_PATH = DATA_DIR / "training.csv"
TRAINING_CSV_FIELDNAMES = [
    "training_id",
    "session",
    "session_name",
    "reflection_id",
    "wearer_agent",
    "training_files",
    "transcription",
    "summary",
    "suggestions",
]


def _sanitize_name(value: str, fallback: str) -> str:
    normalized = "".join(char if char.isalnum() or char in "-_" else "_" for char in str(value or ""))
    normalized = "_".join(part for part in normalized.split("_") if part)
    return normalized or fallback


def _append_training_csv_row(training_id: str, session_name: str, training_files: list[str], transcription: str, summary: str = "", reflection_id: str = "", suggestions: list[str] | None = None, wearer_agent: str = "") -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    csv_exists = TRAINING_CSV_PATH.exists()

    with TRAINING_CSV_PATH.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=TRAINING_CSV_FIELDNAMES)
        if not csv_exists:
            writer.writeheader()
        writer.writerow({
            "training_id": training_id,
            "session": session_name,
            "session_name": session_name,
            "reflection_id": reflection_id,
            "wearer_agent": wearer_agent,
            "training_files": ";".join(training_files),
            "transcription": transcription,
            "summary": summary,
            "suggestions": "|".join(suggestions) if suggestions else "",
        })


def generate_tagged_voice(
    transcript: str,
    session_name: str,
    emotion: str,
    voice_id: str = "b3tuFWghbXYRa9Cs9MJf",
    model_id: str = "eleven_v3",
    output_dir: str | None = None,
    summary: str = "",
    reflection_id: str = "",
    wearer_agent: str = "",
    valence: float | None = None,
    arousal: float | None = None,
    dominance: float | None = None,
) -> dict:
    """Generate multiple ElevenLabs audio files for an emotion-specific tag set.

    Args:
        transcript: The text to synthesize.
        session_name: Session identifier used in output filenames and CSV row.
        emotion: Emotion key used to resolve a list of three tags.
        voice_id: ElevenLabs voice ID.
        model_id: ElevenLabs model ID.
        output_dir: Optional directory where generated mp3 files are written.

    Returns:
        A dictionary with training_id, emotion, tags, output_files, and transcription.

    Raises:
        ValueError: If required values are missing or emotion is unsupported.
    """
    clean_transcript = str(transcript or "").strip()
    clean_session_name = str(session_name or "").strip()
    clean_emotion = str(emotion or "").strip().lower()

    if not clean_transcript:
        raise ValueError("transcript must be a non-empty string")

    if not clean_session_name:
        raise ValueError("session_name must be a non-empty string")

    if not clean_emotion:
        raise ValueError("emotion must be a non-empty string")

    category = EMOTION_CATEGORY_BY_EMOTION.get(clean_emotion, "")
    if not category and valence is not None and arousal is not None and dominance is not None:
        clean_emotion = classify_emotion_from_vad(valence, arousal, dominance)
        category = EMOTION_CATEGORY_BY_EMOTION.get(clean_emotion, "")
    if not category:
        supported = ", ".join(sorted(EMOTION_CATEGORY_BY_EMOTION.keys()))
        raise ValueError(f"Unsupported emotion '{clean_emotion}'. Supported emotions: {supported}")

    # Generate audio for the opposite valence category (practice goal)
    target_category = OPPOSITE_CATEGORY[category]
    tags = UNIFIED_TAGS_BY_CATEGORY[target_category]
    suggestions = SUGGESTIONS_BY_CATEGORY[target_category]

    api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not api_key:
        raise ValueError("ELEVENLABS_API_KEY is not set")

    output_root = Path(output_dir) if output_dir else TRAINING_AUDIO_DIR
    output_root.mkdir(parents=True, exist_ok=True)

    training_id = uuid.uuid4().hex
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_session = _sanitize_name(clean_session_name, "session")

    client = ElevenLabs(api_key=api_key)
    output_files: list[str] = []

    for index, tag in enumerate(tags, start=1):
        tagged_text = f"[{tag}] {clean_transcript}"
        response = client.text_to_speech.convert(
            voice_id=voice_id,
            text=tagged_text,
            model_id=model_id,
            voice_settings={"stability": 0.3},
        )

        audio_bytes = b"".join(chunk for chunk in response if chunk)
        safe_tag = _sanitize_name(tag, f"tag{index}")
        filename = f"{training_id}_{safe_session}_{clean_emotion}_{safe_tag}_{timestamp}_{index}.mp3"
        file_path = output_root / filename
        file_path.write_bytes(audio_bytes)
        output_files.append(filename)

    clean_summary = str(summary or "").strip()
    clean_reflection_id = str(reflection_id or "").strip()
    clean_wearer_agent = str(wearer_agent or "").strip()

    _append_training_csv_row(
        training_id=training_id,
        session_name=clean_session_name,
        training_files=output_files,
        transcription=clean_transcript,
        summary=clean_summary,
        reflection_id=clean_reflection_id,
        suggestions=list(suggestions),
        wearer_agent=clean_wearer_agent,
    )

    return {
        "training_id": training_id,
        "session_name": clean_session_name,
        "reflection_id": clean_reflection_id,
        "wearer_agent": clean_wearer_agent,
        "emotion": clean_emotion,
        "category": category,
        "target_category": target_category,
        "tags": list(tags),
        "suggestions": list(suggestions),
        "output_files": output_files,
        "transcription": clean_transcript,
        "summary": clean_summary,
    }
