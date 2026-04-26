import sys
import subprocess
import os
from tqdm import tqdm

def run_with_progress(cmd, desc):
    print(f"\n{desc}")
    with tqdm(total=1, desc=desc, bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt}') as pbar:
        result = subprocess.run(cmd, shell=True)
        pbar.update(1)
    return result.returncode

def main(transcript_path):
    base = os.path.splitext(os.path.basename(transcript_path))[0]
    # Step 1: transcript_analysis
    run_with_progress(f"python3 transcript_analysis.py {transcript_path}", "Merging transcript segments")
    # Step 2: emotion_analysis
    run_with_progress(f"python3 emotion_analysis.py --record-id {base}", "Running emotion analysis")
    # Step 3: intent_analysis
    run_with_progress(f"python3 intent_analysis.py --record-id {base}", "Running intent analysis")
    # Step 4: goal_analysis
    run_with_progress(f"python3 goal_analysis.py data/{base}.json", "Extracting goals and negative evaluations")
    print("\nAll analyses complete.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python pipeline.py <transcript.json>")
        sys.exit(1)
    main(sys.argv[1])
