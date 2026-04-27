import json
import librosa
import torch
import torch.nn as nn
import noisereduce as nr
from huggingface_hub import hf_hub_download
from transformers import (
    Wav2Vec2FeatureExtractor,
    Wav2Vec2Config,
    AutoFeatureExtractor,
    AutoModelForAudioClassification,
)
from transformers.models.wav2vec2.modeling_wav2vec2 import (
    Wav2Vec2Model,
    Wav2Vec2PreTrainedModel,
)

PAD_MODEL = "audeering/wav2vec2-large-robust-12-ft-emotion-msp-dim"
EMOTION_MODEL = "superb/wav2vec2-base-superb-er"
TARGET_SR = 16000

torch.set_num_threads(1)


class RegressionHead(nn.Module):
    def __init__(self, config):
        super().__init__()
        self.dense = nn.Linear(config.hidden_size, config.hidden_size)
        self.dropout = nn.Dropout(config.final_dropout)
        self.out_proj = nn.Linear(config.hidden_size, config.num_labels)

    def forward(self, features):
        x = self.dropout(features)
        x = self.dense(x)
        x = torch.tanh(x)
        x = self.dropout(x)
        x = self.out_proj(x)
        return x


class EmotionModel(Wav2Vec2PreTrainedModel):
    def __init__(self, config):
        super().__init__(config)
        self.wav2vec2 = Wav2Vec2Model(config)
        self.classifier = RegressionHead(config)
        self.post_init()

    def forward(self, input_values):
        outputs = self.wav2vec2(input_values)
        hidden_states = outputs[0]
        pooled = torch.mean(hidden_states, dim=1)
        logits = self.classifier(pooled)
        return logits


def reduce_noise(audio, sr):
    noise_sample = audio[: int(0.5 * sr)]

    reduced = nr.reduce_noise(
        y=audio,
        sr=sr,
        y_noise=noise_sample,
        prop_decrease=0.8,
    )
    return reduced


def load_pad_model():
    config_path = hf_hub_download(repo_id=PAD_MODEL, filename="config.json")
    with open(config_path, "r") as f:
        config_dict = json.load(f)

    if config_dict.get("vocab_size") is None:
        config_dict["vocab_size"] = 32

    config = Wav2Vec2Config.from_dict(config_dict)
    feature_extractor = Wav2Vec2FeatureExtractor.from_pretrained(PAD_MODEL)
    model = EmotionModel.from_pretrained(PAD_MODEL, config=config)
    model.eval()

    return feature_extractor, model


def predict_pad(audio, feature_extractor, model):
    inputs = feature_extractor(
        audio,
        sampling_rate=TARGET_SR,
        return_tensors="pt",
    )

    with torch.no_grad():
        logits = model(inputs["input_values"])[0].tolist()

    return {
        "arousal": logits[0],
        "dominance": logits[1],
        "valence": logits[2],
    }


def load_emotion_model():
    feature_extractor = AutoFeatureExtractor.from_pretrained(EMOTION_MODEL)
    model = AutoModelForAudioClassification.from_pretrained(EMOTION_MODEL)
    model.eval()
    return feature_extractor, model


def predict_emotion(audio, feature_extractor, model):
    inputs = feature_extractor(
        audio,
        sampling_rate=TARGET_SR,
        return_tensors="pt",
        padding=True,
    )

    with torch.no_grad():
        logits = model(**inputs).logits

    probs = torch.softmax(logits, dim=-1)[0]
    results = [
        {"label": model.config.id2label[i], "score": float(probs[i])}
        for i in range(len(probs))
    ]
    results.sort(key=lambda x: x["score"], reverse=True)
    return results


# ---------------------------- Load models ----------------------------
pad_feature_extractor, pad_model = load_pad_model()
emotion_feature_extractor, emotion_model = load_emotion_model()

# ---------------------------- Load audio ----------------------------
audio, sr = librosa.load("anxious.wav", sr=TARGET_SR, mono=True)
audio = reduce_noise(audio, sr)

# ---------------------------- Inference ----------------------------
pad = predict_pad(audio, pad_feature_extractor, pad_model)
emotions = predict_emotion(audio, emotion_feature_extractor, emotion_model)

print("PAD:")
print(f"  Arousal:   {pad['arousal']:.4f}")
print(f"  Dominance: {pad['dominance']:.4f}")
print(f"  Valence:   {pad['valence']:.4f}")

print("\nEmotion classification:")
for e in emotions:
    print(f"  {e['label']}: {e['score']:.4f}")