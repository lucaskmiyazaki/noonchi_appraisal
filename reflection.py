from actionable import Actionable
from agent import Agent
from blocker import Blocker
from constants import GOAL_STATUS_ON_GOING
from constants import GOAL_STATUS_SUCCESS, GOAL_STATUS_FAIL
from emotion import Emotion
from goal import Goal
from question import Question


class ReflectionNode:
    def __init__(self, id, text, options=None, node_type="question"):
        self.id = id
        self.text = text
        self.node_type = node_type
        self.options = options if options else []

    def to_dict(self):
        return {
            "id": self.id,
            "type": self.node_type,
            "text": self.text,
            "options": self.options,
        }


class ReflectionTree:
    def __init__(self, tree_id=None, start_node=None, nodes=None, reflection_type=None):
        self.tree_id = tree_id
        self.start_node = start_node
        self.nodes = nodes if nodes else {}
        self.reflection_type = reflection_type

    def to_dict(self):
        return {
            "type": self.reflection_type,
            "tree_id": self.tree_id,
            "start_node": self.start_node,
            "nodes": {
                node_id: node.to_dict()
                for node_id, node in self.nodes.items()
            },
        }

    def _voice_tone_text(self, speaker):
        if speaker is None or not getattr(speaker, "emotion", None):
            return "unknown"

        emotion = speaker.emotion
        return (
            f"{emotion.name} "
            f"(V={emotion.valence:.2f}, A={emotion.arousal:.2f}, D={emotion.dominance:.2f})"
        )

    def _agent_label(self, agent, fallback="the responsible agent"):
        if agent is None:
            return fallback
        name = getattr(agent, "name", "")
        if isinstance(name, str) and name.strip():
            return name.strip()
        role = getattr(agent, "role", "")
        if isinstance(role, str) and role.strip():
            return role.strip()
        return fallback

    def build_adjacency(self, edges):
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

    def build_objects_from_graph(self, payload):
        nodes = payload.get("nodes", [])
        edges = payload.get("edges", [])

        outgoing, incoming = self.build_adjacency(edges)

        agents = {}
        goals = {}
        blockers = {}
        actionables = {}
        questions = {}

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
                blockers[node_id] = Blocker(text=data.get("text", ""))

            elif node_type == "followup":
                mode = data.get("mode", "actionable")
                text = data.get("text", "")

                if mode == "question":
                    questions[node_id] = Question(text=text)
                else:
                    actionables[node_id] = Actionable(text=text)

        for agent_id, agent in agents.items():
            for child_id in outgoing.get(agent_id, []):
                if child_id in goals:
                    agent.add_goal(goals[child_id])

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

    def build_from_unclear_feedback_issue(self, issue, speaker=None):
        """
        Builds reflection tree for unclear feedback when speaker sounds angry.

        Branches:
        - responsible agent unclear
        - responsible agent known but improvement points are unclear
        """
        goal = issue.get("goal")
        blocker = issue.get("blocker")
        goal_text = getattr(goal, "text", "this goal")
        blocker_text = getattr(blocker, "text", "this blocker") if blocker is not None else "this blocker"

        responsible_agent = getattr(blocker, "responsible_agent", None) if blocker is not None else None
        responsible_label = self._agent_label(responsible_agent, fallback="someone in the room")

        if responsible_agent is None:
            observation = ReflectionNode(
                id="observation",
                text="You sounded upset.",
                options=[{"label": "Continue", "next": "feedback_question"}],
                node_type="audio",
            )

            feedback_question = ReflectionNode(
                id="feedback_question",
                text="But it is not clear what is causing it. Were you trying to share any feedback?",
                options=[
                    {"label": "Yes", "value": "yes", "next": "actionable_journal"},
                    {"label": "No", "value": "no", "next": "clarity_question"},
                ],
                node_type="question",
            )

            actionable_journal = ReflectionNode(
                id="actionable_journal",
                text=(
                    "When providing feedback, suggesting clear and specific points of improvement can make your message more constructive and actionable. "
                    "What do you think those points might be?"
                ),
                options=[],
                node_type="journaling",
            )

            clarity_question = ReflectionNode(
                id="clarity_question",
                text="Do you think you would have been more clear if you had not expressed anger?",
                options=[
                    {"label": "Yes", "value": "yes", "next": "practice_question"},
                    {"label": "No", "value": "no", "next": "why_question"},
                ],
                node_type="question",
            )

            practice_question = ReflectionNode(
                id="practice_question",
                text="Would you lie to practice your tone?",
                options=[],
                node_type="practice",
            )

            why_question = ReflectionNode(
                id="why_question",
                text="Why?",
                options=[],
                node_type="journaling",
            )

            self.tree_id = "unclear_feedback_unknown_target"
            self.reflection_type = "unclear feedback"
            self.start_node = "observation"
            self.nodes = {
                "observation": observation,
                "feedback_question": feedback_question,
                "actionable_journal": actionable_journal,
                "clarity_question": clarity_question,
                "practice_question": practice_question,
                "why_question": why_question,
            }
            return self

        observation = ReflectionNode(
            id="observation",
            text=(
                f"You sounded upset with {responsible_label}."
            ),
            options=[{"label": "Continue", "next": "feedback_question"}],
            node_type="audio",
        )

        feedback_question = ReflectionNode(
            id="feedback_question",
            text=(
                "Were you trying to share any feedback with them?"
            ),
            options=[
                {"label": "Yes", "value": "yes", "next": "timing_question"},
                {"label": "No", "value": "no", "next": "clarity_question"},
            ],
            node_type="question",
        )

        timing_question = ReflectionNode(
            id="timing_question",
            text="Was that a good moment to provide feedback?",
            options=[
                {"label": "Yes", "value": "yes", "next": "actionable_journal"},
                {"label": "No", "value": "no", "next": "clarity_question"},
            ],
            node_type="question",
        )

        clarity_question = ReflectionNode(
            id="clarity_question",
            text=(
                "Do you think you have been more clear if you had not expressed anger?"
            ),
            options=[
                {"label": "Yes", "value": "yes", "next": "practice_question"},
                {"label": "No", "value": "no", "next": "why_question"},
            ],
            node_type="question",
        )

        actionable_journal = ReflectionNode(
            id="actionable_journal",
            text=(
                "When providing feedback, suggesting clear and specific points of improvement can make your message more constructive and actionable. "
                "What do you think those points might be?"
            ),
            options=[],
            node_type="journaling",
        )

        practice_question = ReflectionNode(
            id="practice_question",
            text="Would you like to practice your tone?",
            options=[],
            node_type="practice",
        )

        why_question = ReflectionNode(
            id="why_question",
            text="Why?",
            options=[],
            node_type="journaling",
        )

        self.tree_id = "unclear_feedback_known_target"
        self.reflection_type = "unclear feedback"
        self.start_node = "observation"
        self.nodes = {
            "observation": observation,
            "feedback_question": feedback_question,
            "timing_question": timing_question,
            "clarity_question": clarity_question,
            "actionable_journal": actionable_journal,
            "practice_question": practice_question,
            "why_question": why_question,
        }
        return self

    def build_from_unclear_concerns_issue(self, issue, speaker=None, blockers_without_actionables=None):
        """
        Builds reflection tree for unclear concerns when speaker sounds concerned.

        Branches:
        - concerns unclear
        - concerns clear but no actionables
        """
        observation = ReflectionNode(
            id="observation",
            text="Your voice suggests you are concerned.",
            options=[{"label": "Continue", "next": "timing_question"}],
            node_type="audio",
        )

        timing_question = ReflectionNode(
            id="timing_question",
            text="Was that a good moment to share your concerns?",
            options=[
                {"label": "Yes", "value": "yes", "next": "actionable_journal"},
                {"label": "No", "value": "no", "next": "clarity_question"},
            ],
            node_type="question",
        )

        actionable_journal = ReflectionNode(
            id="actionable_journal",
            text=(
                "When sharing concerns, pointing out specific points of risk and steps for mitigation can make message more constructive and actionable. "
                "What do you think those points might be?"
            ),
            options=[],
            node_type="journaling",
        )

        clarity_question = ReflectionNode(
            id="clarity_question",
            text="Do you think you would have been more clear if you had not expressed concern in your voice tone?",
            options=[
                {"label": "Yes", "value": "yes", "next": "practice_question"},
                {"label": "No", "value": "no", "next": "why_question"},
            ],
            node_type="question",
        )

        practice_question = ReflectionNode(
            id="practice_question",
            text="Would you like to practice your tone?",
            options=[],
            node_type="practice",
        )

        why_question = ReflectionNode(
            id="why_question",
            text="Why?",
            options=[],
            node_type="journaling",
        )

        self.tree_id = "unclear_concerns"
        self.reflection_type = "unclear concern"
        self.start_node = "observation"
        self.nodes = {
            "observation": observation,
            "timing_question": timing_question,
            "actionable_journal": actionable_journal,
            "clarity_question": clarity_question,
            "practice_question": practice_question,
            "why_question": why_question,
        }
        return self

    def build_from_incoherent_intensity_issue(self, issue, speaker=None):
        """
        Builds reflection tree for intensity mismatches.

        Expected issue keys:
        - kind: high_blocker_blame | high_context | low_context
        - goal
        - blocker
        - arousal
        - lower_threshold
        - goal_upper_threshold
        - effective_upper_threshold
        """
        kind = issue.get("kind", "high_context")
        goal = issue.get("goal")
        blocker = issue.get("blocker")
        arousal = issue.get("arousal", 0.0)
        lower_threshold = issue.get("lower_threshold", 0.2)
        goal_text = getattr(goal, "text", "this goal")
        blocker_text = getattr(blocker, "text", "(no blocker)") if blocker is not None else "(no blocker)"

        if kind in {"high_blocker_blame", "high_context"}:
            observation = ReflectionNode(
                id="observation",
                text="Noonchi detected some elevation in your voice",
                options=[{"label": "Continue", "next": "appropriateness_question"}],
                node_type="audio",
            )

            appropriateness_question = ReflectionNode(
                id="appropriateness_question",
                text="Do you think your tone of voice was appropriate for the situation?",
                options=[
                    {"label": "No", "value": "no", "next": "practice_question"},
                    {"label": "Yes", "value": "yes", "next": "why_question"},
                ],
                node_type="question",
            )

            why_question = ReflectionNode(
                id="why_question",
                text="Why?",
                options=[],
                node_type="journaling",
            )

            practice_question = ReflectionNode(
                id="practice_question",
                text="Would you like to practice your tone?",
                options=[],
                node_type="practice",
            )

            self.tree_id = "intensity_high_elevation"
            self.reflection_type = "incoherent intensity"
            self.start_node = "observation"
            self.nodes = {
                "observation": observation,
                "appropriateness_question": appropriateness_question,
                "why_question": why_question,
                "practice_question": practice_question,
            }
            return self

        # low_context
        observation = ReflectionNode(
            id="observation",
            text="Your voice might be too low energy.",
            options=[{"label": "Continue", "next": "appropriateness_question"}],
            node_type="audio",
        )

        appropriateness_question = ReflectionNode(
            id="appropriateness_question",
            text="Do you think your tone of voice was appropriate for the situation?",
            options=[
                {"label": "No", "value": "no", "next": "practice_question"},
                {"label": "Yes", "value": "yes", "next": "why_question"},
            ],
            node_type="question",
        )

        why_question = ReflectionNode(
            id="why_question",
            text="Why?",
            options=[],
            node_type="journaling",
        )

        practice_question = ReflectionNode(
            id="practice_question",
            text="Would you like to practice your tone?",
            options=[],
            node_type="practice",
        )

        self.tree_id = "intensity_low_context"
        self.reflection_type = "incoherent intensity"
        self.start_node = "observation"
        self.nodes = {
            "observation": observation,
            "appropriateness_question": appropriateness_question,
            "why_question": why_question,
            "practice_question": practice_question,
        }
        return self

    def build_from_incoherent_tone(self, goal, speaker=None):
        """
        Builds a reflection tree for:
        Positive outcome, negative tone, speaker

        Expected logic:
        Observation:
        The goal "<goal>" was successful, but your tone may not have fully reflected that.

        Reflection:
        Are there any underlying concerns or dissatisfaction (a),
        or is it possible that your tone simply did not show how you felt about the outcome (b)?

        a) If something still feels off, it might help to make it explicit
           so others understand your perspective.

        b) This is your voice tone. These are some examples of happy voice tone.
        """
        if goal.status not in {GOAL_STATUS_SUCCESS, GOAL_STATUS_FAIL}:
            raise ValueError(
                "build_from_incoherent_tone currently supports successful or failed goals."
            )

        goal_text = goal.text

        if goal.status == GOAL_STATUS_SUCCESS:
            observation = ReflectionNode(
                id="observation",
                text=(
                    f'You were talking about "{goal_text}". '
                    'It seems everything went well. '
                    'However, you sounded upset when talking about that.'
                ),
                options=[
                    {"label": "Continue", "next": "concerns_question"}
                ],
                node_type="audio",
            )

            concerns_question = ReflectionNode(
                id="concerns_question",
                text=(
                    "Do you have any underlying concerns or dissatisfaction?"
                ),
                options=[
                    {
                        "label": "Yes",
                        "value": "yes",
                        "next": "concerns_journal",
                    },
                    {
                        "label": "No",
                        "value": "no",
                        "next": "clarity_question",
                    },
                ],
                node_type="question",
            )

            concerns_journal = ReflectionNode(
                id="concerns_journal",
                text=(
                    "If something feels off, it might help to make it explicit. "
                    "Can you describe what your concerns are?"
                ),
                options=[],
                node_type="journaling",
            )

            clarity_question = ReflectionNode(
                id="clarity_question",
                text=(
                    "Do you think it would have been more clear if you had expressed joy instead?"
                ),
                options=[
                    {"label": "Yes", "value": "yes", "next": "practice_question"},
                    {"label": "No", "value": "no", "next": "why_question"},
                ],
                node_type="question",
            )

            practice_question = ReflectionNode(
                id="practice_question",
                text="Would you like to practice your tone?",
                options=[],
                node_type="practice",
            )

            why_question = ReflectionNode(
                id="why_question",
                text="Why?",
                options=[],
                node_type="journaling",
            )

            self.tree_id = "positive_outcome_negative_tone_speaker"
            self.reflection_type = "incoherent tone"
            self.start_node = "observation"
            self.nodes = {
                "observation": observation,
                "concerns_question": concerns_question,
                "concerns_journal": concerns_journal,
                "clarity_question": clarity_question,
                "practice_question": practice_question,
                "why_question": why_question,
            }
            return self

        observation = ReflectionNode(
            id="observation",
            text=(
                f'You were talking about "{goal_text}". '
                "It seems it did not go as planned. "
                "However, you sounded happy when talking about that."
            ),
            options=[
                {"label": "Continue", "next": "sarcasm_question"}
            ],
            node_type="audio",
        )

        sarcasm_question = ReflectionNode(
            id="sarcasm_question",
            text="Were you being sarcastic?",
            options=[
                {"label": "Yes", "value": "a", "next": "tone_interpretation"},
                {"label": "No", "value": "b", "next": "clarity_question"},
            ],
            node_type="question",
        )

        tone_interpretation = ReflectionNode(
            id="tone_interpretation",
            text=(
                "Humor is great, but keep in mind that neurodivergent people might interpret tones differently. "
                "Some may understand the intended meaning, while others may take it more literally or feel unsure about the intent."
            ),
            options=[],
            node_type="message",
        )

        clarity_question = ReflectionNode(
            id="clarity_question",
            text="Do you think it would have been more clear if you had not expressed joy?",
            options=[
                {"label": "Yes", "value": "yes", "next": "practice_question"},
                {"label": "No", "value": "no", "next": "why_question"},
            ],
            node_type="question",
        )

        why_question = ReflectionNode(
            id="why_question",
            text="Why?",
            options=[],
            node_type="journaling",
        )

        practice_question = ReflectionNode(
            id="practice_question",
            text="Would you like to practice your tone?",
            options=[],
            node_type="practice",
        )

        self.tree_id = "negative_outcome_incoherent_tone"
        self.reflection_type = "incoherent tone"
        self.start_node = "observation"
        self.nodes = {
            "observation": observation,
            "sarcasm_question": sarcasm_question,
            "tone_interpretation": tone_interpretation,
            "clarity_question": clarity_question,
            "why_question": why_question,
            "practice_question": practice_question,
        }

        return self