import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

PROMPT = Path("gpt prompt").read_text(encoding="utf-8")

def extract_goal_sentences(transcript):
    """Return (indices, sentences) for all desire/negative evaluation segments."""
    indices = []
    sentences = []
    for i, seg in enumerate(transcript):
        label = seg.get("intent_label")
        text = seg.get("text", "").strip()
        if label in ("desire") and text:
            indices.append(i)
            sentences.append(text)
    return indices, sentences

def annotate_transcript(transcript, indices, results):
    """Mark each segment as 'clear', 'unclear', or 'no goal' for goal clarity."""
    for i, seg in enumerate(transcript):
        seg["goal_clarity"] = "no goal"
        seg["rephrased_goal"] = ""
    for idx, result in zip(indices, results):
        seg = transcript[idx]
        seg["rephrased_goal"] = result["rephrased_goal"]
        is_goal = result.get("is_goal", True if result["rephrased_goal"] else False)
        is_clear = result.get("is_clear", False)
        if not is_goal:
            seg["goal_clarity"] = "no goal"
        elif is_goal and not is_clear:
            seg["goal_clarity"] = "unclear"
        elif is_goal and is_clear:
            seg["goal_clarity"] = "clear"

def main(json_path):
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    transcript = data.get("transcript", data)
    indices, sentences = extract_goal_sentences(transcript)
    if not sentences:
        print("No desire or negative evaluation sentences found.")
        return
    # Prepare GPT input
    gpt_input = {"goals": sentences}
    print("\n--- GPT API INPUT ---")
    print(json.dumps(gpt_input, indent=2, ensure_ascii=False))
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": json.dumps(gpt_input, ensure_ascii=False)}
        ]
    )
    print("\n--- GPT API OUTPUT ---")
    print(response.choices[0].message.content)
    # Parse GPT output
    try:
        output = json.loads(response.choices[0].message.content)
        results = output["results"]
    except Exception as e:
        print("Failed to parse GPT output:", e)
        print(response.choices[0].message.content)
        return
    # Print rephrased goals
    for r in results:
        print(f"[{r['goal_index']}] rephrased_goal: {r['rephrased_goal']}")
    # Annotate transcript
    annotate_transcript(transcript, indices, results)
    Path(json_path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Annotated {json_path} with goal_clarity.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python goal_analysis_v2.py <transcript.json>")
        sys.exit(1)
    main(sys.argv[1])
