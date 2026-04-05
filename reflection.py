from constants import GOAL_STATUS_SUCCESS, GOAL_STATUS_FAIL


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
    def __init__(self, tree_id=None, start_node=None, nodes=None):
        self.tree_id = tree_id
        self.start_node = start_node
        self.nodes = nodes if nodes else {}

    def to_dict(self):
        return {
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

    def build_from_incoherent_goal(self, goal, speaker=None):
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
                "build_from_incoherent_goal currently supports successful or failed goals."
            )

        goal_text = goal.text

        if goal.status == GOAL_STATUS_SUCCESS:
            observation = ReflectionNode(
                id="observation",
                text=(
                    f'The goal "{goal_text}" was successful, '
                    f'but your tone may not have fully reflected that.'
                ),
                options=[
                    {"label": "Continue", "next": "reflection_question"}
                ],
                node_type="message",
            )

            reflection_question = ReflectionNode(
                id="reflection_question",
                text=(
                    "Are there any underlying concerns or dissatisfaction, "
                    "or is it possible that your tone simply did not show how you felt "
                    "about the outcome?"
                ),
                options=[
                    {
                        "label": "There are underlying concerns or dissatisfaction",
                        "value": "a",
                        "next": "make_explicit",
                    },
                    {
                        "label": "My tone just did not show how I felt",
                        "value": "b",
                        "next": "happy_tone_examples",
                    },
                ],
                node_type="question",
            )

            make_explicit = ReflectionNode(
                id="make_explicit",
                text=(
                    "If something still feels off, it might help to make it explicit "
                    "so others understand your perspective."
                ),
                options=[],
                node_type="message",
            )

            happy_tone_examples = ReflectionNode(
                id="happy_tone_examples",
                text=(
                    f"This is your voice tone: {self._voice_tone_text(speaker)}. "
                    "These are some examples of happy voice tone using the same phrase."
                ),
                options=[],
                node_type="message",
            )

            self.tree_id = "positive_outcome_negative_tone_speaker"
            self.start_node = "observation"
            self.nodes = {
                "observation": observation,
                "reflection_question": reflection_question,
                "make_explicit": make_explicit,
                "happy_tone_examples": happy_tone_examples,
            }
            return self

        # Negative outcome + positive tone (incoherent): branch by responsibility.
        blocker = goal.get_most_critical_blocker() if hasattr(goal, "get_most_critical_blocker") else None
        if blocker is None:
            blockers = getattr(goal, "blockers", []) or []
            blocker = blockers[0] if blockers else None

        blocker_text = getattr(blocker, "text", "this blocker")

        responsible_agent = None
        if blocker is not None:
            responsible_agents = getattr(blocker, "responsible_agents", []) or []
            if responsible_agents:
                responsible_agent = responsible_agents[0]
            else:
                responsible_agent = getattr(blocker, "responsible_agent", None)

        speaker_is_responsible = speaker is not None and responsible_agent is not None and speaker is responsible_agent
        tone_text = self._voice_tone_text(speaker)
        responsible_label = self._agent_label(responsible_agent)

        observation = ReflectionNode(
            id="observation",
            text=(
                f'The goal "{goal_text}" was not successful, '
                f'but your tone may not have fully reflected that.'
            ),
            options=[
                {"label": "Continue", "next": "sarcasm_question"}
            ],
            node_type="message",
        )

        sarcasm_question = ReflectionNode(
            id="sarcasm_question",
            text="Are you being sarcastic?",
            options=[
                {"label": "Yes", "value": "a", "next": "tone_interpretation"},
                {"label": "No", "value": "b", "next": "responsibility_question"},
            ],
            node_type="question",
        )

        tone_interpretation = ReflectionNode(
            id="tone_interpretation",
            text=(
                "People interpret tone differently. Some may understand the intended "
                "meaning, while others may take it more literally or feel unsure about "
                "your intent."
            ),
            options=[
                {"label": "Continue", "next": "responsibility_question"}
            ],
            node_type="message",
        )

        if blocker is None or responsible_agent is None:
            responsibility_question = ReflectionNode(
                id="responsibility_question",
                text=(
                    "Do you think you should have expressed a negative feeling "
                    "instead of showing signs of joy?"
                ),
                options=[
                    {"label": "Yes", "value": "c", "next": "negative_feeling_tone_examples"},
                    {"label": "No", "value": "no", "next": "negative_feeling_tone_examples"},
                ],
                node_type="question",
            )

            negative_feeling_tone_examples = ReflectionNode(
                id="negative_feeling_tone_examples",
                text=(
                    f"This is your voice tone: {tone_text}. "
                    "These are some examples of negative-feeling voice tone using the same phrase on AI voice tone."
                ),
                options=[],
                node_type="message",
            )

            self.tree_id = "negative_outcome_positive_tone_speaker_missing_responsibility"
            self.start_node = "observation"
            self.nodes = {
                "observation": observation,
                "sarcasm_question": sarcasm_question,
                "tone_interpretation": tone_interpretation,
                "responsibility_question": responsibility_question,
                "negative_feeling_tone_examples": negative_feeling_tone_examples,
            }
            return self

        if speaker_is_responsible:
            responsibility_question = ReflectionNode(
                id="responsibility_question",
                text=(
                    f'During the meeting, it was mentioned that "{blocker_text}". '
                    "Do you think you should have expressed regret in this situation to show accountability of your mistake?"
                ),
                options=[
                    {"label": "Yes", "value": "c", "next": "regret_tone_examples"},
                    {"label": "No", "value": "no", "next": "regret_tone_examples"},
                ],
                node_type="question",
            )

            regret_tone_examples = ReflectionNode(
                id="regret_tone_examples",
                text=(
                    f"This is your voice tone: {tone_text}. "
                    "These are some examples of regret voice tone using the same phrase on AI voice tone."
                ),
                options=[],
                node_type="message",
            )

            self.tree_id = "negative_outcome_positive_tone_speaker_self_responsible"
            self.start_node = "observation"
            self.nodes = {
                "observation": observation,
                "sarcasm_question": sarcasm_question,
                "tone_interpretation": tone_interpretation,
                "responsibility_question": responsibility_question,
                "regret_tone_examples": regret_tone_examples,
            }
            return self

        responsibility_question = ReflectionNode(
            id="responsibility_question",
            text=(
                f'During the meeting, it was mentioned that "{blocker_text}". '
                f'Do you think "{responsible_label}" should change/improve?'
            ),
            options=[
                {"label": "Yes", "value": "c", "next": "urgency_question"},
                {"label": "No", "value": "no", "next": "urgency_question"},
            ],
            node_type="question",
        )

        urgency_question = ReflectionNode(
            id="urgency_question",
            text="Do you think you could have been tougher to express urgency for change/improvement?",
            options=[
                {"label": "Yes", "value": "d", "next": "tough_tone_examples"},
                {"label": "No", "value": "no", "next": "tough_tone_examples"},
            ],
            node_type="question",
        )

        tough_tone_examples = ReflectionNode(
            id="tough_tone_examples",
            text=(
                f"This is your voice tone: {tone_text} when talking about {blocker_text}. "
                "These are some examples of tough voice tone using the same phrase on AI voice tone."
            ),
            options=[],
            node_type="message",
        )

        self.tree_id = "negative_outcome_positive_tone_speaker_other_responsible"
        self.start_node = "observation"
        self.nodes = {
            "observation": observation,
            "sarcasm_question": sarcasm_question,
            "tone_interpretation": tone_interpretation,
            "responsibility_question": responsibility_question,
            "urgency_question": urgency_question,
            "tough_tone_examples": tough_tone_examples,
        }

        return self