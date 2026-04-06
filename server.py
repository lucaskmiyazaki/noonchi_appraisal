from __future__ import annotations

import json
from urllib import error as url_error
from urllib import request as url_request

from flask import Flask, jsonify, request, render_template
from flask_cors import CORS

from emotion import Emotion
from agent import Agent
from goal import Goal
from blocker import Blocker
from actionable import Actionable
from question import Question
from constants import GOAL_STATUS_ON_GOING
from reflection import ReflectionTree
from business_rules import (
    find_speaker,
    detect_tone_incoherence,
    detect_intensity_incoherence,
    detect_unclear_feedback,
    detect_unclear_concern,
    summarize_rule_issue,
    summarize_tone_issue,
    summarize_intensity_issue,
)

app = Flask(__name__)
CORS(app)


def post_tip_to_bangle(message):
    if not message:
        return

    payload = json.dumps({"tip": message}).encode("utf-8")
    req = url_request.Request(
        "http://127.0.0.1:5007/tips",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with url_request.urlopen(req, timeout=2.0) as response:
            response.read()
    except (url_error.URLError, TimeoutError) as exc:
        print(f"Failed to send tip to bangle.js: {exc}")


@app.get("/")
def index():
    return render_template("index.html")


def build_adjacency(edges):
    outgoing = {}
    incoming = {}

    for edge in edges:
        from_id = edge.get("fromId")
        to_id = edge.get("toId")

        if not from_id or not to_id:
            continue

        outgoing.setdefault(from_id, []).append(to_id)
        incoming.setdefault(to_id, []).append(from_id)

    return outgoing, incoming


def build_objects_from_graph(payload):
    nodes = payload.get("nodes", [])
    edges = payload.get("edges", [])

    outgoing, incoming = build_adjacency(edges)

    agents = {}
    goals = {}
    blockers = {}
    actionables = {}
    questions = {}

    # CREATE OBJECTS
    for node in nodes:
        node_id = node.get("id")
        node_type = node.get("type")
        data = node.get("data", {})

        if node_type == "agent":
            emotion = Emotion(
                valence=float(data.get("valence", 0.0)),
                arousal=float(data.get("arousal", 0.0)),
                dominance=float(data.get("dominance", 0.0)),
            )

            role = data.get("role", "listener")

            agent = Agent(emotion=emotion)
            agent.role = role
            agent.name = data.get("name", "")
            agent.is_speaker = role == "speaker"

            agents[node_id] = agent

        elif node_type == "goal":
            goals[node_id] = Goal(
                text=data.get("text", ""),
                status=data.get("status", GOAL_STATUS_ON_GOING),
            )

        elif node_type == "blocker":
            blockers[node_id] = Blocker(
                text=data.get("text", "")
            )

        elif node_type == "followup":
            mode = data.get("mode", "actionable")
            text = data.get("text", "")

            if mode == "question":
                questions[node_id] = Question(text=text)
            else:
                actionables[node_id] = Actionable(text=text)

    # LINK AGENT -> GOAL
    for agent_id, agent in agents.items():
        for child_id in outgoing.get(agent_id, []):
            if child_id in goals:
                agent.add_goal(goals[child_id])

    # LINK GOAL -> BLOCKER / FOLLOWUP
    for goal_id, goal in goals.items():
        for child_id in outgoing.get(goal_id, []):
            if child_id in blockers:
                goal.add_blocker(blockers[child_id])

            if child_id in actionables:
                if not hasattr(goal, "actionables"):
                    goal.actionables = []
                goal.actionables.append(actionables[child_id])

            if child_id in questions:
                if not hasattr(goal, "questions"):
                    goal.questions = []
                goal.questions.append(questions[child_id])

    # LINK BLOCKER -> AGENT / FOLLOWUP
    for blocker_id, blocker in blockers.items():
        responsible_agents = []

        for child_id in outgoing.get(blocker_id, []):
            if child_id in agents:
                responsible_agents.append(agents[child_id])

            if child_id in actionables:
                if not hasattr(blocker, "actionables"):
                    blocker.actionables = []
                blocker.actionables.append(actionables[child_id])

            if child_id in questions:
                if not hasattr(blocker, "questions"):
                    blocker.questions = []
                blocker.questions.append(questions[child_id])

        blocker.responsible_agents = responsible_agents
        blocker.responsible_agent = responsible_agents[0] if responsible_agents else None

    # LINK DIRECTIONAL SEMANTICS FOR FOLLOWUPS

    # agent -> actionable  => owner
    # actionable -> agent  => target
    for actionable_id, actionable in actionables.items():
        owners = []
        targets = []

        for parent_id in incoming.get(actionable_id, []):
            if parent_id in agents:
                owners.append(agents[parent_id])

        for child_id in outgoing.get(actionable_id, []):
            if child_id in agents:
                targets.append(agents[child_id])

        actionable.owners = owners
        actionable.owner = owners[0] if owners else None
        actionable.targets = targets
        actionable.target = targets[0] if targets else None

    # agent -> question  => speaker
    # question -> agent  => target
    for question_id, question in questions.items():
        speakers = []
        targets = []

        for parent_id in incoming.get(question_id, []):
            if parent_id in agents:
                speakers.append(agents[parent_id])

        for child_id in outgoing.get(question_id, []):
            if child_id in agents:
                targets.append(agents[child_id])

        question.speakers = speakers
        question.speaker = speakers[0] if speakers else None
        question.targets = targets
        question.target = targets[0] if targets else None

    # ROOT AGENTS
    root_agents = []
    for agent_id, agent in agents.items():
        parents = incoming.get(agent_id, [])

        has_blocker_parent = any(pid in blockers for pid in parents)
        has_actionable_parent = any(pid in actionables for pid in parents)
        has_question_parent = any(pid in questions for pid in parents)

        if not has_blocker_parent and not has_actionable_parent and not has_question_parent:
            root_agents.append(agent)

    return {
        "agents": agents,
        "goals": goals,
        "blockers": blockers,
        "actionables": actionables,
        "questions": questions,
        "root_agents": root_agents,
    }


@app.post("/play_graph")
def play_graph():
    payload = request.get_json() or {}

    nodes = payload.get("nodes")
    edges = payload.get("edges")

    if not isinstance(nodes, list) or not isinstance(edges, list):
        return jsonify({"error": "nodes and edges must be lists"}), 400

    built = build_objects_from_graph(payload)

    # Find speaker and evaluate tone/intensity coherence via business rules.
    speaker_id, speaker_agent = find_speaker(built["agents"])

    tone_check = {
        "speaker_agent_id": speaker_id,
        "speaker_found": speaker_agent is not None,
        "is_tone_coherent": None,
        "incoherent_goals": [],
    }
    unclear_feedback_check = {
        "speaker_agent_id": speaker_id,
        "speaker_found": speaker_agent is not None,
        "has_unclear_feedback": None,
        "issue": None,
    }
    unclear_concerns_check = {
        "speaker_agent_id": speaker_id,
        "speaker_found": speaker_agent is not None,
        "has_unclear_concerns": None,
        "issue": None,
    }
    intensity_check = {
        "speaker_agent_id": speaker_id,
        "speaker_found": speaker_agent is not None,
        "is_intensity_coherent": None,
        "issues": [],
    }
    reflection_tree = None

    if speaker_agent is not None:
        unclear_feedback_issue = detect_unclear_feedback(speaker_agent)
        unclear_concern_issue = detect_unclear_concern(speaker_agent)
        tone_issue = detect_tone_incoherence(speaker_agent)
        intensity_issue = detect_intensity_incoherence(speaker_agent)

        unclear_feedback_check["has_unclear_feedback"] = unclear_feedback_issue is not None
        unclear_feedback_check["issue"] = summarize_rule_issue(unclear_feedback_issue)

        unclear_concerns_check["has_unclear_concerns"] = unclear_concern_issue is not None
        unclear_concerns_check["issue"] = summarize_rule_issue(unclear_concern_issue)

        tone_check["is_tone_coherent"], tone_check["incoherent_goals"] = summarize_tone_issue(tone_issue)

        intensity_check["is_intensity_coherent"], intensity_check["issues"] = summarize_intensity_issue(intensity_issue)

        if reflection_tree is None and tone_issue is not None:
            reflection_tree = ReflectionTree().build_from_incoherent_goal(
                tone_issue["goal"],
                speaker=speaker_agent,
            ).to_dict()

        if reflection_tree is None and unclear_feedback_issue is not None:
            reflection_tree = ReflectionTree().build_from_unclear_feedback_issue(
                unclear_feedback_issue,
                speaker=speaker_agent,
            ).to_dict()

        if reflection_tree is None and unclear_concern_issue is not None:
            reflection_tree = ReflectionTree().build_from_unclear_concerns_issue(
                unclear_concern_issue,
                speaker=speaker_agent,
                blockers_without_actionables=unclear_concern_issue.get("blockers_without_actionables"),
            ).to_dict()

        if reflection_tree is None and intensity_issue is not None:
            reflection_tree = ReflectionTree().build_from_incoherent_intensity_issue(
                intensity_issue["issue"],
                speaker=speaker_agent,
            ).to_dict()

    print("\n=== GRAPH CREATED ===")
    for k, v in built["agents"].items():
        print(k, v)
    for k, v in built["goals"].items():
        print(k, v)
    for k, v in built["blockers"].items():
        print(k, v)
    for k, v in built["actionables"].items():
        print(k, v)
    for k, v in built["questions"].items():
        print(k, v)

    if reflection_tree:
        start_node_id = reflection_tree.get("start_node")
        first_node = reflection_tree.get("nodes", {}).get(start_node_id, {}) if start_node_id else {}
        first_message = first_node.get("text")

        if first_message:
            post_tip_to_bangle(first_message)

    return jsonify({
        "message": "ok",
        "agents": {k: repr(v) for k, v in built["agents"].items()},
        "goals": {k: repr(v) for k, v in built["goals"].items()},
        "blockers": {k: repr(v) for k, v in built["blockers"].items()},
        "actionables": {k: repr(v) for k, v in built["actionables"].items()},
        "questions": {k: repr(v) for k, v in built["questions"].items()},
        "unclear_feedback_check": unclear_feedback_check,
        "unclear_concerns_check": unclear_concerns_check,
        "tone_check": tone_check,
        "intensity_check": intensity_check,
        "reflection_tree": reflection_tree,
    })


if __name__ == "__main__":
    app.run(debug=True, port=5001)