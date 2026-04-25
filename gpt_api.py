from dotenv import load_dotenv
import os
import json
import re
from openai import OpenAI

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

LABELS = [
    "request", "question", "desire", "apology", "state",
    "positive evaluation", "negative evaluation",
    "informing", "greeting", "None"
]

transcript = """
Alright, let's go. So, all of us are here because we received a complaint between, I'm guessing you're the manager, and the employee. And we'd like to discuss what happened, collect more evidence, and maybe come to a resolution together, and maybe make action next steps.

So, just because you gave the complaint to us, and we do appreciate you being transparent about it, I know this could be a hard thing for you to do, but if you could give us more information. And it's completely confidential. It's happening in front of four of us only.
"""

def split_sentences(text):
    text = re.sub(r"\s+", " ", text.strip())
    return re.split(r"(?<=[.!?])\s+", text)

sentences = split_sentences(transcript)

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

response = client.responses.create(
    model="gpt-4.1-mini",
    input=[
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": json.dumps({
                "sentence_count": len(sentences),
                "sentences": sentences
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
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": LABELS
                        }
                    }
                },
                "required": ["labels"]
            },
            "strict": True
        }
    }
)

data = json.loads(response.output_text)
labels = data["labels"]

if len(labels) != len(sentences):
    raise ValueError(
        f"Mismatch: expected {len(sentences)} labels, got {len(labels)}"
    )

# print nicely
for i, (s, l) in enumerate(zip(sentences, labels)):
    print(f"{i}. [{l}] {s}")