from __future__ import annotations

from flask import Flask, jsonify, request, render_template
from flask_cors import CORS

from emotion import Emotion
from agent import Agent
from goal import Goal
from blocker import Blocker
from constants import GOAL_STATUS_ON_GOING

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

    # LINK AGENT -> GOAL
    for agent_id, agent in agents.items():
        for child_id in outgoing.get(agent_id, []):
            if child_id in goals:
                agent.add_goal(goals[child_id])

    # LINK GOAL -> BLOCKER
    for goal_id, goal in goals.items():
        for child_id in outgoing.get(goal_id, []):
            if child_id in blockers:
                goal.add_blocker(blockers[child_id])

    # LINK BLOCKER -> AGENT
    for blocker_id, blocker in blockers.items():
        responsible_agents = []

        for child_id in outgoing.get(blocker_id, []):
            if child_id in agents:
                responsible_agents.append(agents[child_id])

        blocker.responsible_agents = responsible_agents
        blocker.responsible_agent = responsible_agents[0] if responsible_agents else None

    # ROOT AGENTS
    root_agents = []
    for agent_id, agent in agents.items():
        parents = incoming.get(agent_id, [])
        has_blocker_parent = any(pid in blockers for pid in parents)

        if not has_blocker_parent:
            root_agents.append(agent)

    return {
        "agents": agents,
        "goals": goals,
        "blockers": blockers,
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

    print("\n=== GRAPH CREATED ===")
    for k, v in built["agents"].items():
        print(k, v)
    for k, v in built["goals"].items():
        print(k, v)
    for k, v in built["blockers"].items():
        print(k, v)

    return jsonify({
        "message": "ok",
        "agents": {k: repr(v) for k, v in built["agents"].items()},
        "goals": {k: repr(v) for k, v in built["goals"].items()},
        "blockers": {k: repr(v) for k, v in built["blockers"].items()},
    })


if __name__ == "__main__":
    app.run(debug=True, port=5001)