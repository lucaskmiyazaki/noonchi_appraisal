from constants import GOAL_STATUS_SUCCESS


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

    def build_from_incoherent_goal(self, goal):
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
        if goal.status != GOAL_STATUS_SUCCESS:
            raise ValueError(
                "build_from_incoherent_goal currently only supports successful goals."
            )

        goal_text = goal.text

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
                "This is your voice tone. These are some examples of happy voice tone "
                "using the same phrase."
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