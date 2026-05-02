import sys
from pathlib import Path

from data_store import read_json, upsert_intent_reflection_row, write_data_json_file


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
    data = read_json(Path(json_path))
    transcript = data.get("transcript", data)

    diagrams = []
    last_goal_node = None

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

        # Map pipeline is_goal_status values to model constant values.
        _STATUS_MAP = {"ongoing": "on_going", "success": "success", "failed": "fail"}
        goal_status = _STATUS_MAP.get(seg.get("is_goal_status", ""), "")

        # Any segment with a clear or unclear goal gets its own goal node and propagates it.
        has_goal = clarity in ("clear", "unclear")

        if has_goal:
            goal_node = {
                "id": "goal-1",
                "type": "goal",
                "title": "Goal",
                "badge": "goal",
                "x": 320.0,
                "y": 200.0,
                "data": {
                    "text": seg.get("rephrased_goal") or seg.get("text", ""),
                    "status": goal_status,
                    "is_clear": clarity == "clear",
                    "is_own_goal": True,
                },
            }
            last_goal_node = goal_node
        else:
            # Inherit the last known goal but mark it as not owned by this segment.
            if last_goal_node is not None:
                goal_node = {
                    **last_goal_node,
                    "data": {**last_goal_node["data"], "is_own_goal": False, "status": goal_status or last_goal_node["data"].get("status", "")},
                }
            else:
                goal_node = None

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

    intent_filename = f"{Path(json_path).stem}.intent.json"
    intent_path = write_data_json_file(intent_filename, intent, ensure_ascii=False)
    print(f"Wrote intent file: {intent_path}")

    upsert_intent_reflection_row(intent.get("sessionName", ""), intent_filename)
    print(f"Added {intent_filename} to intents.csv")


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
