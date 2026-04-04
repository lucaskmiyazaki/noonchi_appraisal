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
        arousal = self.emotion.arousal
        incoherent_goals = []
        incoherent_blockers = []

        for goal in self.goals:
            # underreaction
            if arousal < goal.lower_arousal_threshold:
                incoherent_goals.append(goal)
                continue

            # overreaction
            most_critical_blocker = goal.get_most_critical_blocker()
            if most_critical_blocker is not None:
                if arousal > most_critical_blocker.arousal_threshold:
                    incoherent_goals.append(goal)
                    incoherent_blockers.append(most_critical_blocker)

        is_coherent = len(incoherent_goals) == 0
        return is_coherent, incoherent_goals, incoherent_blockers

    def __repr__(self):
        return f"{self.role.capitalize()} | {self.emotion} | Goals: {self.goals}"