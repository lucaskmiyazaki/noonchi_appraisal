from pathlib import Path
from dotenv import load_dotenv

from pipeline import transcript_analysis, emotion_analysis, intent_analysis, analyze_goals, build_intent_diagram


def run_pipeline(json_path, log=print, wearer="wearer", participants=None):
    """Run the full analysis pipeline, calling log(message) after each step."""
    load_dotenv()
    path = Path(json_path)
    record_id = path.stem

    log("[1/5] Merging transcript segments...")
    transcript_analysis.run(path, log=log)

    log("[2/5] Running emotion analysis...")
    emotion_analysis.run(record_id, log=log)

    log("[3/5] Running intent analysis...")
    intent_analysis.run(record_id, log=log)

    log("[4/5] Analyzing goals...")
    analyze_goals.run(path, log=log)

    log("[5/5] Building intent diagram...")
    build_intent_diagram.run(path, wearer=wearer, participants=participants or [], log=log)

    log("Pipeline complete.")
