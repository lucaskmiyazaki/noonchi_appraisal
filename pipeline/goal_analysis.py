import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
from tqdm import tqdm

# Load environment variables
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

PROMPT = (Path(__file__).resolve().parent / "gpt prompt").read_text(encoding="utf-8")

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
    for idx, result in zip(indices, results):
        seg = transcript[idx]
        rephrased_goal = result.get("rephrased_goal", "")
        is_goal = result.get("is_goal", bool(rephrased_goal))
        is_clear = result.get("is_clear", False)
        if not is_goal or not rephrased_goal:
            # No goal from AI — preserve any existing value
            continue
        seg["rephrased_goal"] = rephrased_goal
        seg["goal_clarity"] = "clear" if is_clear else "unclear"
        seg["is_goal_status"] = "ongoing"

def classify_goals(sentences, batch_size=10):
    """Send sentences to GPT in batches, return ordered list of result dicts."""
    all_results = []
    n = len(sentences)
    bar = tqdm(total=n, desc="Annotating goal clarity", unit="sentence")
    for i in range(0, n, batch_size):
        batch = sentences[i:i+batch_size]
        gpt_input = {"goals": batch}
        try:
            response = client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[
                    {"role": "system", "content": PROMPT},
                    {"role": "user", "content": json.dumps(gpt_input, ensure_ascii=False)}
                ]
            )
            output = json.loads(response.choices[0].message.content)
            batch_results = output["results"]
            if len(batch_results) != len(batch):
                raise ValueError(f"Expected {len(batch)} results, got {len(batch_results)}")
            all_results.extend(batch_results)
            bar.update(len(batch))
        except Exception as e:
            print(f"\nBatch {i//batch_size + 1} failed ({e}), falling back to per-sentence")
            for sentence in batch:
                try:
                    single_resp = client.chat.completions.create(
                        model="gpt-4.1-mini",
                        messages=[
                            {"role": "system", "content": PROMPT},
                            {"role": "user", "content": json.dumps({"goals": [sentence]}, ensure_ascii=False)}
                        ]
                    )
                    single_output = json.loads(single_resp.choices[0].message.content)
                    all_results.append(single_output["results"][0])
                except Exception:
                    all_results.append({"goal_index": len(all_results), "rephrased_goal": "", "is_goal": False, "is_clear": False})
                bar.update(1)
    bar.close()
    return all_results


def main(json_path):
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    transcript = data.get("transcript", data)
    indices, sentences = extract_goal_sentences(transcript)
    if not sentences:
        print("No desire or negative evaluation sentences found.")
        return
    results = classify_goals(sentences)
    if len(results) != len(sentences):
        print(f"Mismatch: expected {len(sentences)} results, got {len(results)}")
        return
    annotate_transcript(transcript, indices, results)
    Path(json_path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Annotated {json_path} with goal_clarity.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python goal_analysis_v2.py <transcript.json>")
        sys.exit(1)
    main(sys.argv[1])
