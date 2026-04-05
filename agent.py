from emotion import Emotion
from constants import (
    GOAL_STATUS_SUCCESS,
    GOAL_STATUS_FAIL,
    ROLE_SPEAKER,
    ROLE_LISTENER,
    ROLE_PASSIVE,
    ROLES,
)


class Agent:
    def __init__(self, role=ROLE_PASSIVE, emotion=None, goals=None):
        if role not in ROLES:
            raise ValueError(f"Invalid role: {role}")

        self.role = role
        self.emotion = emotion if emotion else Emotion()
        self.goals = goals if goals else []

    def update_emotion(self, **kwargs):
        """Update emotion (name or PAD values)."""
        self.emotion.update(**kwargs)

    def add_goal(self, goal):
        self.goals.append(goal)

    def set_role(self, role: str):
        if role not in ROLES:
            raise ValueError(f"Invalid role: {role}")
        self.role = role

    def is_speaker(self):
        return self.role == ROLE_SPEAKER

    def is_listener(self):
        return self.role == ROLE_LISTENER

    def is_passive(self):
        return self.role == ROLE_PASSIVE

    def is_tone_coherent(self):
        """
        Checks whether emotional valence matches goal outcome.

        Rules:
        - success -> expected positive valence
        - fail -> expected negative valence
        - on_going -> ignored
        """
        incoherent_goals = []

        for goal in self.goals:
            if goal.status == GOAL_STATUS_SUCCESS and self.emotion.valence < 0:
                incoherent_goals.append(goal)

            elif goal.status == GOAL_STATUS_FAIL and self.emotion.valence > 0:
                incoherent_goals.append(goal)

        is_coherent = len(incoherent_goals) == 0
        return is_coherent, incoherent_goals

    def is_intensity_coherent(self):
        issues = self.detect_wrong_voice_intensity()
        incoherent_goals = [issue["goal"] for issue in issues]
        incoherent_blockers = [issue["blocker"] for issue in issues if issue["blocker"] is not None]
        is_coherent = len(issues) == 0
        return is_coherent, incoherent_goals, incoherent_blockers

    def detect_wrong_voice_intensity(self):
        """
        Detects voice intensity mismatches per goal.

        Upper bound rule:
        use min(most_critical_blocker.arousal_threshold, goal.upper_arousal_threshold)
        when blocker exists, otherwise goal.upper_arousal_threshold.

        Returns a list of issue dicts with kind in:
        - low_context
        - high_blocker_blame
        - high_context
        """
        arousal = self.emotion.arousal
        issues = []

        for goal in self.goals:
            lower_threshold = getattr(goal, "lower_arousal_threshold", 0.2)
            goal_upper_threshold = getattr(goal, "upper_arousal_threshold", 0.8)

            blocker = goal.get_most_critical_blocker() if hasattr(goal, "get_most_critical_blocker") else None
            blocker_threshold = getattr(blocker, "arousal_threshold", None) if blocker is not None else None

            effective_upper_threshold = (
                min(goal_upper_threshold, blocker_threshold)
                if blocker_threshold is not None
                else goal_upper_threshold
            )

            if arousal < lower_threshold:
                issues.append({
                    "kind": "low_context",
                    "goal": goal,
                    "blocker": blocker,
                    "arousal": arousal,
                    "lower_threshold": lower_threshold,
                    "goal_upper_threshold": goal_upper_threshold,
                    "effective_upper_threshold": effective_upper_threshold,
                    "blocker_threshold": blocker_threshold,
                })
                continue

            if arousal > effective_upper_threshold:
                blocker_responsible_agent = getattr(blocker, "responsible_agent", None) if blocker is not None else None
                is_other_blame = blocker is not None and blocker_responsible_agent is not None and blocker_responsible_agent is not self

                kind = "high_blocker_blame" if is_other_blame and blocker_threshold is not None and blocker_threshold <= goal_upper_threshold else "high_context"

                issues.append({
                    "kind": kind,
                    "goal": goal,
                    "blocker": blocker,
                    "arousal": arousal,
                    "lower_threshold": lower_threshold,
                    "goal_upper_threshold": goal_upper_threshold,
                    "effective_upper_threshold": effective_upper_threshold,
                    "blocker_threshold": blocker_threshold,
                })

        return issues

    def __repr__(self):
        return f"{self.role.capitalize()} | {self.emotion} | Goals: {self.goals}"