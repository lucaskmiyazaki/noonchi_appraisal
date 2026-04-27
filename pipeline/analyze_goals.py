import sys
import json
from pathlib import Path
from dotenv import load_dotenv

from pipeline import goal_analysis, evaluation_analysis


def reset_goal_fields(transcript):
    for seg in transcript:
        seg["rephrased_goal"] = ""
        seg["goal_clarity"] = "no goal"
        seg["is_goal_status"] = ""


def main(json_path):
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    transcript = data.get("transcript", data)

    print("Resetting goal fields...")
    reset_goal_fields(transcript)
    Path(json_path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n--- Goal analysis (desire) ---")
    goal_indices, goal_sentences = goal_analysis.extract_goal_sentences(transcript)
    if goal_sentences:
        goal_results = goal_analysis.classify_goals(goal_sentences)
        if len(goal_results) == len(goal_sentences):
            goal_analysis.annotate_transcript(transcript, goal_indices, goal_results)
        else:
            print(f"Mismatch: expected {len(goal_sentences)} results, got {len(goal_results)}")
    else:
        print("No desire sentences found.")

    print("\n--- Evaluation analysis (positive/negative evaluation) ---")
    eval_indices, eval_sentences = evaluation_analysis.extract_evaluation_sentences(transcript)
    if eval_sentences:
        eval_results = evaluation_analysis.classify_evaluation_goals(eval_sentences)
        if len(eval_results) == len(eval_sentences):
            evaluation_analysis.annotate_transcript(transcript, eval_indices, eval_results)
            for sentence, result in zip(eval_sentences, eval_results):
                rephrased_goal = result.get("rephrased_goal", "")
                clarity = result.get("unclear_reason", "")
                goal_str = f'"{rephrased_goal}"' if rephrased_goal else "(none)"
                print(f"  [{clarity}] {goal_str}  ←  {sentence}")
        else:
            print(f"Mismatch: expected {len(eval_sentences)} results, got {len(eval_results)}")
    else:
        print("No evaluation sentences found.")

    Path(json_path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nDone. Annotated {json_path}.")


def run(json_path, log=print):
    main(str(json_path))
    log(f"Goal analysis done: {Path(json_path).name}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python analyze_goals.py <transcript.json>")
        sys.exit(1)
    main(sys.argv[1])
