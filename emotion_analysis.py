from __future__ import annotations

import argparse
import json
from functools import lru_cache
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
TARGET_SR = 16000
PAD_MODEL = "audeering/wav2vec2-large-robust-12-ft-emotion-msp-dim"
EMOTION_MODEL = "superb/wav2vec2-base-superb-er"
MIN_SEGMENT_SECONDS = 0.25


def clamp_unit_interval(value):
    return max(0.0, min(float(value), 1.0))


def normalize_pad_scores(scores):
    return {
        key: clamp_unit_interval(scores.get(key, 0.5))
        for key in ("arousal", "dominance", "valence")
    }


def _import_pad_dependencies():
    try:
        import librosa
        import numpy as np
        import torch
        import torch.nn as nn
        from huggingface_hub import hf_hub_download
        from transformers import (
            AutoFeatureExtractor,
            AutoModelForAudioClassification,
            Wav2Vec2Config,
            Wav2Vec2FeatureExtractor,
        )
        from transformers.models.wav2vec2.modeling_wav2vec2 import (
            Wav2Vec2Model,
            Wav2Vec2PreTrainedModel,
        )
    except ImportError as exc:
        raise RuntimeError(
            "PAD analysis dependencies are missing. Install librosa, torch, huggingface_hub, and transformers."
        ) from exc

    return {
        "librosa": librosa,
        "np": np,
        "torch": torch,
        "nn": nn,
        "hf_hub_download": hf_hub_download,
        "AutoFeatureExtractor": AutoFeatureExtractor,
        "AutoModelForAudioClassification": AutoModelForAudioClassification,
        "Wav2Vec2Config": Wav2Vec2Config,
        "Wav2Vec2FeatureExtractor": Wav2Vec2FeatureExtractor,
        "Wav2Vec2Model": Wav2Vec2Model,
        "Wav2Vec2PreTrainedModel": Wav2Vec2PreTrainedModel,
    }


@lru_cache(maxsize=1)
def load_pad_model_bundle():
    deps = _import_pad_dependencies()
    torch = deps["torch"]
    nn = deps["nn"]
    Wav2Vec2Config = deps["Wav2Vec2Config"]
    Wav2Vec2FeatureExtractor = deps["Wav2Vec2FeatureExtractor"]
    Wav2Vec2Model = deps["Wav2Vec2Model"]
    Wav2Vec2PreTrainedModel = deps["Wav2Vec2PreTrainedModel"]
    hf_hub_download = deps["hf_hub_download"]

    torch.set_num_threads(1)

    class RegressionHead(nn.Module):
        def __init__(self, config):
            super().__init__()
            self.dense = nn.Linear(config.hidden_size, config.hidden_size)
            self.dropout = nn.Dropout(config.final_dropout)
            self.out_proj = nn.Linear(config.hidden_size, config.num_labels)

        def forward(self, features):
            hidden = self.dropout(features)
            hidden = self.dense(hidden)
            hidden = torch.tanh(hidden)
            hidden = self.dropout(hidden)
            return self.out_proj(hidden)

    class PadEmotionModel(Wav2Vec2PreTrainedModel):
        def __init__(self, config):
            super().__init__(config)
            self.wav2vec2 = Wav2Vec2Model(config)
            self.classifier = RegressionHead(config)
            self.post_init()

        def forward(self, input_values):
            outputs = self.wav2vec2(input_values)
            hidden_states = outputs[0]
            pooled = torch.mean(hidden_states, dim=1)
            return self.classifier(pooled)

    config_path = hf_hub_download(repo_id=PAD_MODEL, filename="config.json")
    with open(config_path, "r", encoding="utf-8") as config_file:
        config_dict = json.load(config_file)

    if config_dict.get("vocab_size") is None:
        config_dict["vocab_size"] = 32

    config = Wav2Vec2Config.from_dict(config_dict)
    feature_extractor = Wav2Vec2FeatureExtractor.from_pretrained(PAD_MODEL)
    model = PadEmotionModel.from_pretrained(PAD_MODEL, config=config)
    model.eval()

    return feature_extractor, model, torch, deps["librosa"]


@lru_cache(maxsize=1)
def load_emotion_model_bundle():
    deps = _import_pad_dependencies()
    AutoFeatureExtractor = deps["AutoFeatureExtractor"]
    AutoModelForAudioClassification = deps["AutoModelForAudioClassification"]
    torch = deps["torch"]

    torch.set_num_threads(1)

    feature_extractor = AutoFeatureExtractor.from_pretrained(EMOTION_MODEL)
    model = AutoModelForAudioClassification.from_pretrained(EMOTION_MODEL)
    model.eval()

    return feature_extractor, model, torch


def _predict_pad(audio_samples, feature_extractor, model, torch):
    inputs = feature_extractor(
        audio_samples,
        sampling_rate=TARGET_SR,
        return_tensors="pt",
    )

    with torch.no_grad():
        logits = model(inputs["input_values"])[0].tolist()

    return {
        "arousal": float(logits[0]),
        "dominance": float(logits[1]),
        "valence": float(logits[2]),
    }


def _predict_emotion(audio_samples, feature_extractor, model, torch):
    inputs = feature_extractor(
        audio_samples,
        sampling_rate=TARGET_SR,
        return_tensors="pt",
        padding=True,
    )

    with torch.no_grad():
        logits = model(**inputs).logits

    probabilities = torch.softmax(logits, dim=-1)[0]
    results = [
        {"label": model.config.id2label[index], "score": float(probabilities[index])}
        for index in range(len(probabilities))
    ]
    results.sort(key=lambda item: item["score"], reverse=True)
    return results


def _prepare_segment_samples(audio_samples, start_seconds, end_seconds):
    start_index = max(0, int(float(start_seconds) * TARGET_SR))
    end_index = max(start_index, int(float(end_seconds) * TARGET_SR))
    segment = audio_samples[start_index:end_index]
    segment_array = segment.astype("float32", copy=False)

    minimum_samples = int(TARGET_SR * MIN_SEGMENT_SECONDS)
    if len(segment_array) >= minimum_samples:
        return segment_array

    np = _import_pad_dependencies()["np"]

    if len(segment_array) == 0:
        return np.zeros(minimum_samples, dtype="float32")

    padding = minimum_samples - len(segment_array)
    return np.pad(segment_array, (0, padding), mode="constant").astype("float32", copy=False)


@lru_cache(maxsize=24)
def _analyze_audio_segments_cached(audio_path_str, audio_mtime_ns, transcript_signature):
    del audio_mtime_ns
    audio_path = Path(audio_path_str)
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    pad_feature_extractor, pad_model, torch, librosa = load_pad_model_bundle()
    emotion_feature_extractor, emotion_model, _ = load_emotion_model_bundle()
    audio_samples, _ = librosa.load(str(audio_path), sr=TARGET_SR, mono=True)
    raw_segments = json.loads(transcript_signature)

    analyzed_segments = []
    for chunk in raw_segments:
        start_seconds = float(chunk.get("start", 0.0) or 0.0)
        end_seconds = float(chunk.get("end", start_seconds) or start_seconds)
        if end_seconds < start_seconds:
            end_seconds = start_seconds

        prepared_segment = _prepare_segment_samples(audio_samples, start_seconds, end_seconds)
        raw_pad = _predict_pad(prepared_segment, pad_feature_extractor, pad_model, torch)
        normalized_pad = normalize_pad_scores(raw_pad)
        emotion_probabilities = _predict_emotion(
            prepared_segment,
            emotion_feature_extractor,
            emotion_model,
            torch,
        )
        emotion_label = emotion_probabilities[0]["label"] if emotion_probabilities else None

        analyzed_segments.append({
            "id": chunk.get("id"),
            "text": str(chunk.get("text", "")),
            "start": start_seconds,
            "end": end_seconds,
            "pad": raw_pad,
            "normalized_pad": normalized_pad,
            "emotion_label": emotion_label,
            "emotion_probabilities": emotion_probabilities,
        })

    return analyzed_segments


def analyze_audio_segments(audio_path, transcript_segments):
    serialized_transcript = json.dumps(transcript_segments or [], sort_keys=True)
    path = Path(audio_path)
    return _analyze_audio_segments_cached(
        str(path),
        path.stat().st_mtime_ns,
        serialized_transcript,
    )


def load_audio_record(record_path):
    return json.loads(Path(record_path).read_text(encoding="utf-8"))


def save_audio_record(record_path, record):
    Path(record_path).write_text(json.dumps(record, indent=2), encoding="utf-8")


def is_audio_record(record):
    return isinstance(record, dict) and {
        "id",
        "audioUrl",
        "audioFilename",
        "transcript",
    }.issubset(record.keys())


def iter_audio_record_paths():
    for path in sorted(DATA_DIR.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            record = load_audio_record(path)
        except (OSError, json.JSONDecodeError):
            continue
        if is_audio_record(record):
            yield path, record


def resolve_record_paths(record_id="", session_name="", process_all=False):
    matches = []
    requested_record_id = str(record_id or "").strip()
    requested_session = str(session_name or "").strip()

    for path, record in iter_audio_record_paths():
        if process_all:
            matches.append((path, record))
            continue

        if requested_record_id and str(record.get("id", "")).strip() == requested_record_id:
            matches.append((path, record))
            continue

        if requested_session and str(record.get("sessionName", "")).strip() == requested_session:
            matches.append((path, record))

    if process_all:
        return matches

    return matches[:1]


def enrich_record_with_pad(record, audio_path):
    transcript_segments = list(record.get("transcript") or [])
    analyzed_segments = analyze_audio_segments(audio_path, transcript_segments)
    analyzed_by_id = {segment.get("id"): segment for segment in analyzed_segments}

    updated_segments = []
    for chunk in transcript_segments:
        analyzed = analyzed_by_id.get(chunk.get("id"), {})
        normalized = analyzed.get("normalized_pad", {})
        updated_chunk = dict(chunk)
        updated_chunk["valence"] = clamp_unit_interval(normalized.get("valence", 0.5))
        updated_chunk["arousal"] = clamp_unit_interval(normalized.get("arousal", 0.5))
        updated_chunk["dominance"] = clamp_unit_interval(normalized.get("dominance", 0.5))
        updated_chunk["emotion_label"] = analyzed.get("emotion_label")
        updated_chunk["emotion_probabilities"] = analyzed.get("emotion_probabilities", [])
        updated_segments.append(updated_chunk)

    updated_record = dict(record)
    updated_record["transcript"] = updated_segments
    return updated_record, len(updated_segments)


def process_record_file(record_path, record):
    audio_filename = str(record.get("audioFilename", "") or "").strip()
    if not audio_filename:
        raise FileNotFoundError(f"Audio filename missing in {record_path.name}")

    audio_path = DATA_DIR / audio_filename
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found for {record_path.name}: {audio_path.name}")

    updated_record, count = enrich_record_with_pad(record, audio_path)
    save_audio_record(record_path, updated_record)
    return count


def build_argument_parser():
    parser = argparse.ArgumentParser(
        description="Annotate saved transcript segments with PAD values and emotion probabilities.",
    )
    parser.add_argument("--record-id", default="", help="Process a specific saved audio record by id.")
    parser.add_argument("--session-name", default="", help="Process the latest matching session record by session name.")
    parser.add_argument("--all", action="store_true", help="Process all saved audio records.")
    return parser


def main():
    parser = build_argument_parser()
    args = parser.parse_args()

    targets = resolve_record_paths(
        record_id=args.record_id,
        session_name=args.session_name,
        process_all=args.all or (not args.record_id and not args.session_name),
    )

    if not targets:
        raise SystemExit("No matching audio records found.")

    processed_count = 0
    for record_path, record in targets:
        segment_count = process_record_file(record_path, record)
        processed_count += 1
        print(f"Annotated {record_path.name} with PAD for {segment_count} transcript segments.")

    print(f"Completed PAD annotation for {processed_count} record(s).")


if __name__ == "__main__":
    main()