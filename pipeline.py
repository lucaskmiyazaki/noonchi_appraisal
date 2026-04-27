import sys
import os
from pathlib import Path
from dotenv import load_dotenv

from pipeline import transcript_analysis, emotion_analysis, intent_analysis, analyze_goals, build_intent_diagram


STEPS = [
    ("Merging transcript",       "transcript"),
    ("Running emotion analysis", "emotion"),
    ("Running intent analysis",  "intent"),
    ("Analyzing goals",          "goals"),
    ("Building intent diagram",  "diagram"),
]


def run_pipeline(json_path, log=print, wearer="wearer", participants=None):
    """Run the full pipeline. Calls log(message) after each step."""
    load_dotenv()
    path = Path(json_path)
    record_id = path.stem
    data_path = path

    log(f"[1/5] Merging transcript segments...")
    transcript_analysis.run(data_path, log=log)

    log(f"[2/5] Running emotion analysis...")
    emotion_analysis.run(record_id, log=log)

    log(f"[3/5] Running intent analysis...")
    intent_analysis.run(record_id, log=log)

    log(f"[4/5] Analyzing goals...")
    analyze_goals.run(data_path, log=log)

    log(f"[5/5] Building intent diagram...")
    build_intent_diagram.run(data_path, wearer=wearer, participants=participants or [], log=log)

    log("Pipeline complete.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python pipeline.py <transcript.json>")
        sys.exit(1)
    run_pipeline(sys.argv[1])

