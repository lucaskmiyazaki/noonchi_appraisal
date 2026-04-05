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
        tone_text = self._voice_tone_text(speaker)
        positive_reframe = f"We had to {goal_text}, but {blocker_text} and that is fine (positive tone)."

        if responsible_agent is None:
            observation = ReflectionNode(
                id="observation",
                text=(
                    "Your voice tone suggests that someone needs to improve. "
                    "However, it might not be clear who your feedback was directed to."
                ),
                options=[{"label": "Continue", "next": "target_question"}],
                node_type="message",
            )

            target_question = ReflectionNode(
                id="target_question",
                text="Who do you think needs improvement?",
                options=[
                    {"label": "Nobody in the room", "value": "a", "next": "frustration_context_question"},
                    {"label": "Someone in the room", "value": "b", "next": "context_question"},
                ],
                node_type="question",
            )

            frustration_context_question = ReflectionNode(
                id="frustration_context_question",
                text="Do you think the context is appropriate to demonstrate frustration?",
                options=[
                    {"label": "Yes", "value": "yes", "next": "clarity_tips"},
                    {"label": "No", "value": "no", "next": "tone_reframe"},
                ],
                node_type="question",
            )

            clarity_tips = ReflectionNode(
                id="clarity_tips",
                text=(
                    "You might want to be more clear about what you are mad about."
                    "Tips: name the exact issue, describe impact, state who is responsible (if anyone), and what are the actionable steps to avoid future mistakes."
                ),
                options=[],
                node_type="message",
            )

            tone_reframe = ReflectionNode(
                id="tone_reframe",
                text=(
                    "You might want to change voice tone. "
                    f"This is your tone: {tone_text}. "
                    f"This is a more positive tone: \"{positive_reframe}\""
                ),
                options=[],
                node_type="message",
            )

            context_question = ReflectionNode(
                id="context_question",
                text="Is the context right to provide feedback?",
                options=[
                    {"label": "Yes", "value": "c", "next": "clarity_tips"},
                    {"label": "No", "value": "a", "next": "tone_reframe"},
                ],
                node_type="question",
            )

            self.tree_id = "unclear_feedback_unknown_target"
            self.start_node = "observation"
            self.nodes = {
                "observation": observation,
                "target_question": target_question,
                "frustration_context_question": frustration_context_question,
                "clarity_tips": clarity_tips,
                "tone_reframe": tone_reframe,
                "context_question": context_question,
            }
            return self

        observation = ReflectionNode(
            id="observation",
            text=(
                f"Your voice tone suggests that {responsible_label} needs to improve. "
                "However, it might not be clear what the points of improvement are."
            ),
            options=[{"label": "Continue", "next": "context_question"}],
            node_type="message",
        )

        context_question = ReflectionNode(
            id="context_question",
            text=(
                f"Do you think {responsible_label} needs to improve? "
                "Is the context right to provide feedback?"
            ),
            options=[
                {"label": "Yes", "value": "a", "next": "actionable_guidance"},
                {"label": "No", "value": "b", "next": "tone_reframe"},
            ],
            node_type="question",
        )

        actionable_guidance = ReflectionNode(
            id="actionable_guidance",
            text=f"Provide clear actionable steps and conditions for addressing {blocker_text}.",
            options=[{"label": "Continue", "next": "tone_reframe"}],
            node_type="message",
        )

        tone_reframe = ReflectionNode(
            id="tone_reframe",
            text=(
                "If you don't want to express change, you might want to use a different tone. "
                f"This is your tone: {tone_text}. "
                f"This is more positive tone: \"{positive_reframe}\""
            ),
            options=[],
            node_type="message",
        )

        self.tree_id = "unclear_feedback_known_target"
        self.start_node = "observation"
        self.nodes = {
            "observation": observation,
            "context_question": context_question,
            "actionable_guidance": actionable_guidance,
            "tone_reframe": tone_reframe,
        }
        return self

    def build_from_unclear_concerns_issue(self, issue, speaker=None, blockers_without_actionables=None):
        """
        Builds reflection tree for unclear concerns when speaker sounds concerned.

        Branches:
        - concerns unclear
        - concerns clear but no actionables
        """
        goal = issue.get("goal")
        goal_text = getattr(goal, "text", "this goal")
        tone_text = self._voice_tone_text(speaker)

        blockers_without_actionables = blockers_without_actionables or []
        blocker_labels = [getattr(b, "text", "") for b in blockers_without_actionables if getattr(b, "text", "")]
        blockers_text = ", ".join(blocker_labels) if blocker_labels else "some risks"

        confident_tone_example = f"I am confident that we are going to {goal_text}."

        if blocker_labels:
            observation = ReflectionNode(
                id="observation",
                text=(
                    f"Your voice tone suggests you are concerned about {blockers_text} "
                    f"as it may hinder {goal_text}."
                ),
                options=[{"label": "Continue", "next": "importance_question"}],
                node_type="message",
            )

            importance_question = ReflectionNode(
                id="importance_question",
                text="Is it important to point out these risks to people at the meeting?",
                options=[
                    {"label": "Yes", "value": "a", "next": "tone_reframe"},
                    {"label": "No", "value": "b", "next": "tone_reframe"},
                ],
                node_type="question",
            )

            tone_reframe = ReflectionNode(
                id="tone_reframe",
                text=(
                    f"You might want to change your voice tone. This is your tone: {tone_text}. "
                    f"This is a more confident tone: {confident_tone_example}"
                ),
                options=[{"label": "Continue", "next": "actionables_question"}],
                node_type="message",
            )

            actionables_question = ReflectionNode(
                id="actionables_question",
                text="What are the actionable steps that should be taken to mitigate these concerns? And who should act?",
                options=[],
                node_type="question",
            )

            self.tree_id = "unclear_concerns_clear_risks_no_actionables"
            self.start_node = "observation"
            self.nodes = {
                "observation": observation,
                "importance_question": importance_question,
                "tone_reframe": tone_reframe,
                "actionables_question": actionables_question,
            }
            return self

        observation = ReflectionNode(
            id="observation",
            text=(
                "Your voice tone suggests there are points of risk that should be addressed. "
                "However, these points are not clear."
            ),
            options=[{"label": "Continue", "next": "risks_question"}],
            node_type="message",
        )

        risks_question = ReflectionNode(
            id="risks_question",
            text="What are the points of risks that should be mitigated?",
            options=[
                {"label": "No concerns", "value": "a", "next": "tone_reframe"},
                {"label": "Some concerns", "value": "b", "next": "tone_reframe"},
            ],
            node_type="question",
        )

        tone_reframe = ReflectionNode(
            id="tone_reframe",
            text=(
                "You might want to change your voice tone. "
                f"This is an example of a more confident tone: {confident_tone_example}"
            ),
            options=[{"label": "Continue", "next": "actionables_question"}],
            node_type="message",
        )

        actionables_question = ReflectionNode(
            id="actionables_question",
            text="What are the actionable steps that should be taken to mitigate these concerns? And who should act?",
            options=[],
            node_type="question",
        )

        self.tree_id = "unclear_concerns_unclear_risks"
        self.start_node = "observation"
        self.nodes = {
            "observation": observation,
            "risks_question": risks_question,
            "tone_reframe": tone_reframe,
            "actionables_question": actionables_question,
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
        goal_upper_threshold = issue.get("goal_upper_threshold", 0.8)
        effective_upper_threshold = issue.get("effective_upper_threshold", goal_upper_threshold)

        goal_text = getattr(goal, "text", "this goal")
        blocker_text = getattr(blocker, "text", "(no blocker)") if blocker is not None else "(no blocker)"

        if kind == "high_blocker_blame":
            responsible_agent = getattr(blocker, "responsible_agent", None) if blocker is not None else None
            responsible_label = self._agent_label(responsible_agent, fallback="this person")

            observation = ReflectionNode(
                id="observation",
                text="Your voice might be too elevated.",
                options=[{"label": "Continue", "next": "feedback_question"}],
                node_type="message",
            )

            feedback_question = ReflectionNode(
                id="feedback_question",
                text=(
                    f'Are you angry with "{responsible_label}" for "{blocker_text}" and do you want/need to provide '
                    f'feedback so "{responsible_label}" improves?'
                ),
                options=[
                    {"label": "Yes", "value": "a", "next": "proportionality_question"},
                    {"label": "No", "value": "no", "next": "proportionality_question"},
                ],
                node_type="question",
            )

            proportionality_question = ReflectionNode(
                id="proportionality_question",
                text=(
                    f"Is your voice intensity {arousal:.2f} proportional to the context? "
                    f"Upper threshold={effective_upper_threshold:.2f} (goal upper={goal_upper_threshold:.2f}) "
                    f"for goal \"{goal_text}\" and blocker \"{blocker_text}\"."
                ),
                options=[],
                node_type="question",
            )

            self.tree_id = "intensity_high_blocker_blame"
            self.start_node = "observation"
            self.nodes = {
                "observation": observation,
                "feedback_question": feedback_question,
                "proportionality_question": proportionality_question,
            }
            return self

        if kind == "high_context":
            observation = ReflectionNode(
                id="observation",
                text="Your voice might be too elevated.",
                options=[{"label": "Continue", "next": "context_question"}],
                node_type="message",
            )

            context_question = ReflectionNode(
                id="context_question",
                text=(
                    f"Is your voice intensity {arousal:.2f} appropriate for this context? "
                    f"Upper threshold={effective_upper_threshold:.2f} (goal upper={goal_upper_threshold:.2f}) "
                    f"for goal \"{goal_text}\" and blocker \"{blocker_text}\"."
                ),
                options=[],
                node_type="question",
            )

            self.tree_id = "intensity_high_context"
            self.start_node = "observation"
            self.nodes = {
                "observation": observation,
                "context_question": context_question,
            }
            return self

        # low_context
        observation = ReflectionNode(
            id="observation",
            text="Your voice might be too low energy.",
            options=[{"label": "Continue", "next": "context_question"}],
            node_type="message",
        )

        context_question = ReflectionNode(
            id="context_question",
            text=(
                f"Is your voice intensity {arousal:.2f} appropriate for this context? "
                f"Lower threshold={lower_threshold:.2f} for goal \"{goal_text}\" and blocker \"{blocker_text}\"."
            ),
            options=[],
            node_type="question",
        )

        self.tree_id = "intensity_low_context"
        self.start_node = "observation"
        self.nodes = {
            "observation": observation,
            "context_question": context_question,
        }
        return self

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