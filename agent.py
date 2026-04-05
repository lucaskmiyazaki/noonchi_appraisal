from emotion import Emotion
from constants import (
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

    def __repr__(self):
        return f"{self.role.capitalize()} | {self.emotion} | Goals: {self.goals}"