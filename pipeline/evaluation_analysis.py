import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
from tqdm import tqdm
from data_store import read_json, write_json

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

PROMPT = """
You analyze positive and negative evaluations.

Return STRICT JSON only.

Input:
{
  "evaluations": ["string"]
}

Output:
{
  "results": [
    {
      "evaluation_index": int,
      "rephrased_goal": "string",
      is_goal: true | false,
      "is_clear": true | false,
      "unclear_reason": "missing_object" | "incomplete" | "external_context_needed" | "no_explicit_goal" | "none"
    }
  ]
}

Rules:
- Process every input item in order.
- evaluation_index = index in the input array.

is_goal:
- true → the sentence explicitly states something the speaker or group wanted to achieve but failed or succeeded in achieving. or is struggling to achieve.
- false -> a statement of fact, feeling, or opinion without a goal.

rephrased_goal if goal exists:
- Extract ONLY what is stated.
- Dont infer goal from the context, but you can use opposite words, for example:
    - "I am upset that presentation went poorly" → "presenting well to the client"
    - "I am concerned about our team reputation" → "maintaining a good team reputation"
    - "We did a good job presenting to the client" → "presenting well to the client"
    - "That was confusing" → ""
- Use -ing verb form.
- Structure: <verb> <object> <condition>
- If none → ""

unclear_reason:
- "not_goal" → the input is not a goal.
- "missing_object" → goal has an action but no object.
- "external_context_needed" → the goal cannot be understood on its own and requires clarification. This includes:
  - vague references: "this", "that", "it" when not tied to a specific noun
    Examples: "fix this", "handle it"
  - generic nouns that do not define the object
    Examples: "solve this problem", "handle the issue", "fix the situation"
- "none" → the goal is fully understandable and actionable on its own.

is_clear:
- If is_goal = false, is_clear MUST be false.
- If is_goal = false, unclear_reason MUST be "not_goal".
- If is_goal = true, is_clear is true ONLY if unclear_reason = "none".
- If is_goal = true and unclear_reason is not "none", is_clear MUST be false.

Strict constraints:
- DO NOT infer goals.
- Be conservative.
"""

def extract_evaluation_sentences(transcript):
    indices = []
    sentences = []

    for i, seg in enumerate(transcript):
        label = seg.get("intent_label")
        text = seg.get("text", "").strip()

        if label in ("positive evaluation", "negative evaluation") and text:
            indices.append(i)
            sentences.append(text)

    return indices, sentences


def annotate_transcript(transcript, indices, results):
    for idx, result in zip(indices, results):
        seg = transcript[idx]

        rephrased_goal = result.get("rephrased_goal", "")
        goal_is_clear = result.get("goal_is_clear", False)

        if not rephrased_goal:
            # No goal from AI — preserve any existing value
            continue

        seg["rephrased_goal"] = rephrased_goal
        seg["goal_clarity"] = "clear" if goal_is_clear else "unclear"

        label = seg.get("intent_label", "")
        if label == "positive evaluation":
            seg["is_goal_status"] = "success"
        elif label == "negative evaluation":
            seg["is_goal_status"] = "failed"


def classify_evaluation_goals(sentences, batch_size=10):
    all_results = []
    n = len(sentences)

    bar = tqdm(total=n, desc="Annotating evaluation goals", unit="sentence")

    for i in range(0, n, batch_size):
        batch = sentences[i:i + batch_size]
        gpt_input = {"evaluations": batch}

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
            print(f"\nBatch {i // batch_size + 1} failed ({e}), falling back to per-sentence")

            for sentence in batch:
                try:
                    single_resp = client.chat.completions.create(
                        model="gpt-4.1-mini",
                        messages=[
                            {"role": "system", "content": PROMPT},
                            {"role": "user", "content": json.dumps({"evaluations": [sentence]}, ensure_ascii=False)}
                        ]
                    )

                    single_output = json.loads(single_resp.choices[0].message.content)
                    all_results.append(single_output["results"][0])

                except Exception:
                    all_results.append({
                        "evaluation_index": len(all_results),
                        "rephrased_goal": "",
                        "goal_is_clear": False,
                        "unclear_reason": "no_explicit_goal"
                    })

                bar.update(1)

    bar.close()
    return all_results


def main(json_path):
    data = read_json(Path(json_path))
    transcript = data.get("transcript", data)

    indices, sentences = extract_evaluation_sentences(transcript)

    if not sentences:
        print("No positive or negative evaluation sentences found.")
        return

    results = classify_evaluation_goals(sentences)

    if len(results) != len(sentences):
        print(f"Mismatch: expected {len(sentences)} results, got {len(results)}")
        return

    annotate_transcript(transcript, indices, results)

    for sentence, result in zip(sentences, results):
        rephrased_goal = result.get("rephrased_goal", "")
        clarity = result.get("unclear_reason", "")
        goal_str = f'"{rephrased_goal}"' if rephrased_goal else "(none)"
        print(f"  [{clarity}] {goal_str}  ←  {sentence}")

    write_json(Path(json_path), data, ensure_ascii=False)

    print(f"Annotated {json_path} with evaluation_goal_clarity.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python evaluation_goal_analysis.py <transcript.json>")
        sys.exit(1)

    main(sys.argv[1])