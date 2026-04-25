from __future__ import annotations

import os
import json
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
import re
import argparse

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
LABELS = [
    "request", "question", "desire", "apology", "state",
    "positive evaluation", "negative evaluation",
    "informing", "greeting", "None"
]

SYSTEM_PROMPT = """
Classify each sentence into EXACTLY ONE label:

- request (ask for action, including orders, instructions, suggestions, proposals—even if phrased as a question)
- question (ask for information or clarification ONLY, not action)
- desire (speaker’s OWN goals/wishes)
- apology (acknowledgement of mistake or regret)
- state (speaker expresses inability, confusion, or emotional condition without stating a goal)
- positive evaluation (praise/appreciation)
- negative evaluation (criticism/complaint or judgment)
- informing (speaker’s OWN past or future actions)
- greeting
- None

Rules:
- Use ONLY these labels.
- Classify based on INTENT, not grammatical form.
- If unsure → "None".
- "state" = internal feelings, not judgment.
- Return only labels, in the same order as the input sentences.
"""

def split_sentences(text):
    text = re.sub(r"\s+", " ", text.strip())
    return re.split(r"(?<=[.!?])\s+", text)

def classify_intents(sentences, client, batch_size=25):
    labels = []
    n = len(sentences)
    for i in range(0, n, batch_size):
        batch = sentences[i:i+batch_size]
        try:
            response = client.responses.create(
                model="gpt-4.1-mini",
                input=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": json.dumps({
                            "sentence_count": len(batch),
                            "sentences": batch
                        }, ensure_ascii=False)
                    }
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "labels_only",
                        "schema": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "labels": {
                                    "type": "array", "items": {"type": "string", "enum": LABELS}
                                }
                            },
                            "required": ["labels"]
                        },
                        "strict": True
                    }
                }
            )
            data = json.loads(response.output_text)
            batch_labels = data["labels"]
            if len(batch_labels) != len(batch):
                # fallback: classify each sentence individually in this batch
                batch_labels = []
                for sentence in batch:
                    single_resp = client.responses.create(
                        model="gpt-4.1-mini",
                        input=[
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {
                                "role": "user",
                                "content": json.dumps({
                                    "sentence_count": 1,
                                    "sentences": [sentence]
                                }, ensure_ascii=False)
                            }
                        ],
                        text={
                            "format": {
                                "type": "json_schema",
                                "name": "labels_only",
                                "schema": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "labels": {
                                            "type": "array", "items": {"type": "string", "enum": LABELS}
                                        }
                                    },
                                    "required": ["labels"]
                                },
                                "strict": True
                            }
                        }
                    )
                    single_data = json.loads(single_resp.output_text)
                    label = single_data["labels"][0] if single_data["labels"] else "None"
                    batch_labels.append(label)
            labels.extend(batch_labels)
        except Exception as e:
            # fallback: classify each sentence individually in this batch
            for sentence in batch:
                try:
                    single_resp = client.responses.create(
                        model="gpt-4.1-mini",
                        input=[
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {
                                "role": "user",
                                "content": json.dumps({
                                    "sentence_count": 1,
                                    "sentences": [sentence]
                                }, ensure_ascii=False)
                            }
                        ],
                        text={
                            "format": {
                                "type": "json_schema",
                                "name": "labels_only",
                                "schema": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "labels": {
                                            "type": "array", "items": {"type": "string", "enum": LABELS}
                                        }
                                    },
                                    "required": ["labels"]
                                },
                                "strict": True
                            }
                        }
                    )
                    single_data = json.loads(single_resp.output_text)
                    label = single_data["labels"][0] if single_data["labels"] else "None"
                    labels.append(label)
                except Exception:
                    labels.append("None")
    return labels

def process_record(record_path, client):
    record = json.loads(Path(record_path).read_text(encoding="utf-8"))
    transcript = record.get("transcript", [])
    sentences = [chunk["text"] for chunk in transcript]
    if not sentences:
        return False
    labels = classify_intents(sentences, client)
    if len(labels) != len(transcript):
        raise ValueError(f"Mismatch: expected {len(transcript)} labels, got {len(labels)}")
    for chunk, label in zip(transcript, labels):
        chunk["intent_label"] = label
    Path(record_path).write_text(json.dumps(record, indent=2), encoding="utf-8")
    return True

def main():
    load_dotenv()
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    parser = argparse.ArgumentParser(description="Annotate transcript segments with intent labels using OpenAI GPT API.")
    parser.add_argument("--record-id", default="", help="Process a specific saved audio record by id.")
    parser.add_argument("--all", action="store_true", help="Process all saved audio records.")
    args = parser.parse_args()
    if args.all:
        paths = sorted(DATA_DIR.glob("*.json"))
    elif args.record_id:
        paths = [DATA_DIR / f"{args.record_id}.json"]
    else:
        print("Specify --all or --record-id.")
        return
    for path in paths:
        if not path.exists():
            print(f"File not found: {path}")
            continue
        try:
            updated = process_record(path, client)
            if updated:
                print(f"Annotated {path.name} with intent labels.")
        except Exception as e:
            print(f"Failed to process {path.name}: {e}")

if __name__ == "__main__":
    main()
