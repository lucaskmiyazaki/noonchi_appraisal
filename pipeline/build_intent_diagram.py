import csv
import sys
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR.parent / "data"
DB_PATH = DATA_DIR / "db.csv"

FIELDNAMES = [
    "wearer_agent",
    "session_name",
    "reflection_tree_file",
    "startms",
    "endms",
    "practice",
    "audio_filename",
    "intent_filename",
]


def _add_to_db(session_name, intent_file):
    rows = []
    fieldnames = list(FIELDNAMES)
    if DB_PATH.exists():
        with DB_PATH.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            existing = list(reader.fieldnames or [])
            for name in existing:
                if name not in fieldnames:
                    fieldnames.append(name)
            for row in reader:
                rows.append({field: row.get(field, "") for field in fieldnames})

    # Remove any existing row for this intent file
    rows = [r for r in rows if r.get("intent_filename", "") != intent_file]

    rows.append({
        "wearer_agent": "",
        "session_name": session_name,
        "reflection_tree_file": "",
        "startms": "",
        "endms": "",
        "practice": "null",
        "audio_filename": "",
        "intent_filename": intent_file,
    })

    with DB_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def _resolve_role(speaker, wearer, participants):
    """Return (role, name) for a segment's speaker."""
    if not speaker:
        return "wearer", wearer
    if speaker == wearer:
        return "wearer", speaker
    if speaker in (participants or []):
        return "participants", speaker
    return "external", speaker


def build_intent_diagram(json_path, wearer="wearer", participants=None):
    participants = participants or []
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    transcript = data.get("transcript", data)

    diagrams = []
    last_goal_node = None
    seen_clear_goal = False

    for seg in transcript:
        # --- Agent node ---
        speaker = seg.get("speaker") or None
        role, name = _resolve_role(speaker, wearer, participants)
        agent_node = {
            "id": "agent-1",
            "type": "agent",
            "title": "Agent",
            "badge": role,
            "x": 80.0,
            "y": 180.0,
            "data": {
                "name": name,
                "role": role,
                "valence": seg.get("valence", 0.5),
                "arousal": seg.get("arousal", 0.5),
                "dominance": seg.get("dominance", 0.5),
            },
        }

        # --- Goal node ---
        label = seg.get("intent_label")
        clarity = seg.get("goal_clarity", "no goal")

        # A segment "has a goal" if it's a desire that is clear,
        # or if it's unclear and no clear goal has been seen yet (first unclear).
        has_goal = (
            label == "desire"
            and clarity in ("clear", "unclear")
            and (clarity == "clear" or not seen_clear_goal)
        )

        if has_goal:
            if clarity == "clear":
                seen_clear_goal = True
            goal_node = {
                "id": "goal-1",
                "type": "goal",
                "title": "Goal",
                "badge": "goal",
                "x": 320.0,
                "y": 200.0,
                "data": {
                    "text": seg.get("rephrased_goal") or seg.get("text", ""),
                    "status": "",
                    "is_clear": clarity == "clear",
                },
            }
            last_goal_node = goal_node
        else:
            # Inherit the last known goal (may be None if no goal seen yet)
            goal_node = last_goal_node

        nodes = [agent_node]
        edges = []
        if goal_node:
            nodes.append(goal_node)
            edges.append({
                "fromId": "agent-1",
                "toId": "goal-1",
                "fromSide": "right",
                "toSide": "left",
                "label": "",
            })

        diagrams.append({
            "nodes": nodes,
            "edges": edges,
            "startms": seg.get("start") * 1000 if seg.get("start") is not None else None,
            "endms": seg.get("end") * 1000 if seg.get("end") is not None else None,
        })

    # Compose intent structure
    intent = {"diagrams": diagrams}
    if isinstance(data, dict):
        for k in ("sessionName",):
            if k in data:
                intent[k] = data[k]

    intent_path = Path(json_path).with_suffix(".intent.json")
    intent_path.write_text(json.dumps(intent, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote intent file: {intent_path}")

    _add_to_db(intent.get("sessionName", ""), intent_path.name)
    print(f"Added {intent_path.name} to db.csv")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Build intent diagram JSON from annotated transcript.")
    parser.add_argument("json_path", help="Path to transcript JSON file.")
    parser.add_argument("--wearer", default="wearer", help="Name/ID of the wearer speaker.")
    parser.add_argument("--participants", nargs="*", default=[], help="Names/IDs of participant speakers.")
    args = parser.parse_args()
    build_intent_diagram(args.json_path, wearer=args.wearer, participants=args.participants)


def run(json_path, wearer="wearer", participants=None, log=print):
    build_intent_diagram(str(json_path), wearer=wearer, participants=participants or [])
    log(f"Intent diagram built: {Path(json_path).name}")
