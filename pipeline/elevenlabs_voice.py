import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs
from data_store import (
    DATA_DIR,
    TRAINING_AUDIO_DIR,
    is_json_filename,
    load_training_rows,
    normalize_training_type_str,
    read_data_json_file,
    write_training_rows,
)

from models.constants import EMOTION_CATEGORY_BY_EMOTION, UNIFIED_TAGS_BY_CATEGORY, SUGGESTIONS_BY_CATEGORY, OPPOSITE_CATEGORY, classify_emotion_from_vad


load_dotenv()

EMOTION_CATEGORY_ALIASES = {
    "hap": "positive",
    "joy": "positive",
    "ang": "negative",
    "sad": "negative",
    # Keep neutral unresolved so PAD/VAD can determine direction.
    "neu": "",
}


def _sanitize_name(value: str, fallback: str) -> str:
    normalized = "".join(char if char.isalnum() or char in "-_" else "_" for char in str(value or ""))
    normalized = "_".join(part for part in normalized.split("_") if part)
    return normalized or fallback


def _resolve_source_category(emotion: str, valence: float | None, arousal: float | None, dominance: float | None) -> tuple[str, str]:
    normalized_emotion = str(emotion or "").strip().lower()

    category = EMOTION_CATEGORY_ALIASES.get(normalized_emotion, "")
    if not category:
        category = EMOTION_CATEGORY_BY_EMOTION.get(normalized_emotion, "")

    resolved_emotion = normalized_emotion
    if not category and valence is not None and arousal is not None and dominance is not None:
        resolved_emotion = classify_emotion_from_vad(valence, arousal, dominance)
        category = EMOTION_CATEGORY_BY_EMOTION.get(resolved_emotion, "")

    return category, resolved_emotion


def _append_training_csv_row(training_id: str, meeting_id: str, training_files: list[str], transcription: str, summary: str = "", reflection_id: str = "", suggestions: list[str] | None = None, user_id: str = "", training_type: str = "valence", valence: float | None = None, arousal: float | None = None, dominance: float | None = None, tree_type: str = "", startms: str = "", endms: str = "") -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    existing_rows = load_training_rows()
    existing_rows.append({
        "training_id": training_id,
        "meeting_id": meeting_id,
        "reflection_id": reflection_id,
        "user_id": user_id,
        "type": normalize_training_type_str(training_type),
        "valence": "" if valence is None else str(valence),
        "arousal": "" if arousal is None else str(arousal),
        "dominance": "" if dominance is None else str(dominance),
        "done": "false",
        "training_files": ";".join(training_files),
        "transcription": transcription,
        "summary": summary,
        "suggestions": "|".join(suggestions) if suggestions else "",
        "tree_type": tree_type,
        "startms": startms,
        "endms": endms,
    })
    write_training_rows(existing_rows)


def generate_tagged_voice(
    transcript: str,
    meeting_id: str,
    emotion: str,
    voice_id: str = "b3tuFWghbXYRa9Cs9MJf",
    model_id: str = "eleven_v3",
    output_dir: str | None = None,
    summary: str = "",
    reflection_id: str = "",
    user_id: str = "",
    training_type: str = "valence",
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
    clean_meeting_id = str(meeting_id or "").strip()
    clean_emotion = str(emotion or "").strip().lower()

    if not clean_transcript:
        raise ValueError("transcript must be a non-empty string")

    if not clean_meeting_id:
        raise ValueError("meeting_id must be a non-empty string")

    if not clean_emotion:
        raise ValueError("emotion must be a non-empty string")

    training_id = uuid.uuid4().hex
    clean_training_type = normalize_training_type_str(training_type)
    category = ""
    target_category = ""
    tags: list[str] = []
    suggestions: list[str] = []
    output_files: list[str] = []

    if clean_training_type == "valence":
        category, clean_emotion = _resolve_source_category(clean_emotion, valence, arousal, dominance)
        if not category:
            supported = ", ".join(sorted(EMOTION_CATEGORY_BY_EMOTION.keys()))
            raise ValueError(f"Unsupported emotion '{clean_emotion}'. Supported emotions: {supported}, hap, ang, sad, neu")

        target_category = OPPOSITE_CATEGORY[category]
        tags = list(UNIFIED_TAGS_BY_CATEGORY[target_category])
        suggestions = list(SUGGESTIONS_BY_CATEGORY[target_category])

        api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
        if not api_key:
            raise ValueError("ELEVENLABS_API_KEY is not set")

        output_root = Path(output_dir) if output_dir else TRAINING_AUDIO_DIR
        output_root.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        safe_session = _sanitize_name(clean_meeting_id, "session")
        client = ElevenLabs(api_key=api_key)

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
    clean_user_id = str(user_id or "").strip()

    # Read reflection tree metadata once so listing never needs to open JSON
    _tree_type = ""
    _startms = ""
    _endms = ""
    if clean_reflection_id and is_json_filename(clean_reflection_id):
        try:
            _ref_tree = read_data_json_file(clean_reflection_id) or {}
            _tree_type = str(_ref_tree.get("type", "") or "")
            _startms = str(_ref_tree.get("startMs", "") or "")
            _endms = str(_ref_tree.get("endMs", "") or "")
        except Exception:
            pass

    _append_training_csv_row(
        training_id=training_id,
        meeting_id=clean_meeting_id,
        training_files=output_files,
        transcription=clean_transcript,
        summary=clean_summary,
        reflection_id=clean_reflection_id,
        suggestions=list(suggestions),
        user_id=clean_user_id,
        training_type=clean_training_type,
        valence=valence,
        arousal=arousal,
        dominance=dominance,
        tree_type=_tree_type,
        startms=_startms,
        endms=_endms,
    )

    return {
        "training_id": training_id,
        "meeting_id": clean_meeting_id,
        "reflection_id": clean_reflection_id,
        "user_id": clean_user_id,
        "type": clean_training_type,
        "emotion": clean_emotion,
        "category": category,
        "target_category": target_category,
        "tags": list(tags),
        "suggestions": list(suggestions),
        "output_files": output_files,
        "transcription": clean_transcript,
        "summary": clean_summary,
    }
