from __future__ import annotations

from flask import Flask, jsonify, request, render_template
from flask_cors import CORS

from emotion import Emotion
from agent import Agent
from goal import Goal
from blocker import Blocker
from actionable import Actionable
from question import Question
from constants import GOAL_STATUS_ON_GOING, GOAL_STATUS_SUCCESS
from reflection import ReflectionTree

app = Flask(__name__)
CORS(app)


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

    # Find speaker and evaluate tone coherence against attached goals.
    speaker_id = None
    speaker_agent = None
    for agent_id, agent in built["agents"].items():
        if getattr(agent, "role", "") == "speaker":
            speaker_id = agent_id
            speaker_agent = agent
            break

    tone_check = {
        "speaker_agent_id": speaker_id,
        "speaker_found": speaker_agent is not None,
        "is_tone_coherent": None,
        "incoherent_goals": [],
    }
    reflection_tree = None

    if speaker_agent is not None:
        is_coherent, incoherent_goals = speaker_agent.is_tone_coherent()
        tone_check["is_tone_coherent"] = is_coherent
        tone_check["incoherent_goals"] = [
            {
                "text": goal.text,
                "status": goal.status,
            }
            for goal in incoherent_goals
        ]

        if not is_coherent and incoherent_goals:
            # Current reflection builder supports successful-goal mismatch.
            successful_incoherent = [
                g for g in incoherent_goals if g.status == GOAL_STATUS_SUCCESS
            ]
            goal_for_reflection = successful_incoherent[0] if successful_incoherent else None

            if goal_for_reflection is not None:
                reflection_tree = ReflectionTree().build_from_incoherent_goal(
                    goal_for_reflection
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

    return jsonify({
        "message": "ok",
        "agents": {k: repr(v) for k, v in built["agents"].items()},
        "goals": {k: repr(v) for k, v in built["goals"].items()},
        "blockers": {k: repr(v) for k, v in built["blockers"].items()},
        "actionables": {k: repr(v) for k, v in built["actionables"].items()},
        "questions": {k: repr(v) for k, v in built["questions"].items()},
        "tone_check": tone_check,
        "reflection_tree": reflection_tree,
    })


if __name__ == "__main__":
    app.run(debug=True, port=5001)