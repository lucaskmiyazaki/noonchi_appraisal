import sys
import json
from pathlib import Path

def build_intent_diagram(json_path):
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    transcript = data.get("transcript", data)
    # Find all goal segments
    indices = []
    for i, seg in enumerate(transcript):
        label = seg.get("intent_label")
        text = seg.get("text", "").strip()
        if label == "desire" and text:
            indices.append(i)
    # Collect goal segments with clarity
    goal_segments = []
    for idx in indices:
        seg = transcript[idx]
        clarity = seg.get("goal_clarity", "no goal")
        goal_segments.append({
            "idx": idx,
            "seg": seg,
            "clarity": clarity
        })

    diagrams = []
    agent_id = "agent-1"
    agent_node = {
        "id": agent_id,
        "type": "agent",
        "title": "Agent",
        "badge": "wearer",
        "x": 80.0,
        "y": 180.0,
        "data": {
            "name": "wearer",
            "role": "wearer",
            "valence": 0.5,
            "arousal": 0.5,
            "dominance": 0.5
        }
    }

    # Build diagrams: one for each goal segment
    for i, g in enumerate(goal_segments):
        clarity = g["clarity"]
        seg = g["seg"]
        idx = g["idx"]
        # Only add unclear if no clear before
        if clarity == "clear" or (clarity == "unclear" and not any(
            gs["clarity"] == "clear" for gs in goal_segments[:i])):
            # Set startms and endms for this diagram
            startms = seg.get("start", None)
            if i + 1 < len(goal_segments):
                endms = transcript[goal_segments[i + 1]["idx"]].get("start", None)
            else:
                endms = transcript[-1].get("end", None) if transcript else None
            # Place goal node with x/y
            goal_node = {
                "id": f"goal-{idx}",
                "type": "goal",
                "title": "Goal",
                "badge": "goal",
                "x": 320.0,
                "y": 200.0,
                "data": {
                    "text": seg.get("rephrased_goal") or seg.get("text", ""),
                    "status": clarity,
                    "is_clear": clarity == "clear"
                }
            }
            edge = {
                "fromId": agent_id,
                "toId": goal_node["id"],
                "fromSide": "right",
                "toSide": "left",
                "label": ""
            }
            diagrams.append({
                "nodes": [agent_node, goal_node],
                "edges": [edge],
                "startms": startms,
                "endms": endms
            })

    # Compose new intent structure
    intent = {"diagrams": diagrams}
    if isinstance(data, dict):
        for k in ("sessionName",):
            if k in data:
                intent[k] = data[k]
    intent_path = str(Path(json_path).with_suffix(".intent.json"))
    Path(intent_path).write_text(json.dumps(intent, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote intent file: {intent_path}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python build_intent_diagram.py <transcript.json>")
        sys.exit(1)
    build_intent_diagram(sys.argv[1])
