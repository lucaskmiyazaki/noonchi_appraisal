from dotenv import load_dotenv
import os
import sys
import json
from openai import OpenAI

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

CLUSTER_PROMPT = """
Compress each list into the fewest items without losing meaning.

Rules:
- Merge only items with the same or very similar meaning
- Do not add or invent new ideas
- Do not lose information
- Keep wording close to the original
- Keep distinct or conflicting items separate
- Output only JSON
"""

def extract_desires_and_negative_evaluations(json_path):
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    transcript = data.get("transcript", data)

    desires = []
    negative_evaluations = []

    for seg in transcript:
        label = seg.get("intent_label")
        text = seg.get("text", "").strip()

        if not text:
            continue

        if label == "desire":
            desires.append(text)
        elif label == "negative evaluation":
            negative_evaluations.append(text)

    return desires, negative_evaluations


def cluster_lists(desires, negative_evaluations):
    response = client.responses.create(
        model="gpt-4.1-mini",
        input=[
            {"role": "system", "content": CLUSTER_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "desires": desires,
                        "negative_evaluations": negative_evaluations
                    },
                    ensure_ascii=False
                )
            }
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "clustered_goals_blockers",
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "goals": {
                            "type": "array",
                            "items": {"type": "string"}
                        },
                        "blockers": {
                            "type": "array",
                            "items": {"type": "string"}
                        }
                    },
                    "required": ["goals", "blockers"]
                },
                "strict": True
            }
        }
    )

    return json.loads(response.output_text)


def main(json_path):
    desires, negative_evaluations = extract_desires_and_negative_evaluations(json_path)

    clustered = cluster_lists(desires, negative_evaluations)

    print(json.dumps(clustered, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python goal_analysis.py <transcript.json>")
        sys.exit(1)

    main(sys.argv[1])