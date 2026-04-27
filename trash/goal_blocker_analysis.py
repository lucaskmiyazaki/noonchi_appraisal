
import sys
import json
import os
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
import argparse

def extract_sentences(transcript):
    return [seg["text"] for seg in transcript]

def call_gpt_goal_api(sentences, client, prompt):
    input_obj = {
        "sentence_count": len(sentences),
        "sentences": [{"index": i, "sentence": s} for i, s in enumerate(sentences)]
    }
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(input_obj, ensure_ascii=False)}
        ],
        response_format={"type": "json_object"}
    )
    return json.loads(response.choices[0].message.content)

def annotate_transcript_with_goals(json_path):
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    transcript = data.get('transcript', data)
    sentences = extract_sentences(transcript)


    load_dotenv()
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    GPT_PROMPT = '''
You analyze meeting transcripts to extract the underlying goal of a discussed fact/event.

Important:

Do NOT return the goal of the meeting.
Return the goal of the event being discussed (what was supposed to happen).

Example:
“Improve intern communication because he gave a bad presentation”
→ Goal = give a good presentation
→ Status = fail

Input:
{
"sentence_count": N,
"sentences": [{"index": i, "sentence": "..."}]
}

Output (STRICT JSON):
{
"goals": [
{
"goal_indexes": [int],
"status": "success" | "fail" | "on going" | "unknown",
"blocker_indexes": [int]
}
]
}

Rules:

Use ONLY provided indexes (no text, no paraphrasing).
goal_indexes = where the goal is stated/implied.
blocker_indexes = what prevented or harmed the goal.
Infer status from the transcript.
Prefer minimal, precise indexes.
If no goal → {"goals": []}
'''
    gpt_result = call_gpt_goal_api(sentences, client, GPT_PROMPT)

    # Default all to 'none'
    for seg in transcript:
        seg['goal_blocker_label'] = 'none'

    for goal_obj in gpt_result.get('goals', []):
        for idx in goal_obj.get('goal_indexes', []):
            transcript[idx]['goal_blocker_label'] = 'goal'
        for idx in goal_obj.get('blocker_indexes', []):
            transcript[idx]['goal_blocker_label'] = 'blocker'

    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Annotated {json_path} with goal/blocker/none labels.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Annotate transcript with goal/blocker/none using GPT goal extraction.")
    parser.add_argument("json_path", help="Path to transcript JSON file.")
    args = parser.parse_args()
    annotate_transcript_with_goals(args.json_path)
