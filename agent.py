from emotion import Emotion
from constants import (
    ROLE_WEARER,
    ROLE_PARTICIPANTS,
    ROLE_EXTERNAL,
    ROLES,
    normalize_role,
)


class Agent:
    def __init__(self, role=ROLE_EXTERNAL, emotion=None, goals=None):
        role = normalize_role(role, default=ROLE_EXTERNAL)
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
        role = normalize_role(role)
        if role not in ROLES:
            raise ValueError(f"Invalid role: {role}")
        self.role = role

    def is_wearer(self):
        return self.role == ROLE_WEARER

    def is_listener(self):
        return self.role == ROLE_PARTICIPANTS

    def is_passive(self):
        return self.role == ROLE_EXTERNAL

    def __repr__(self):
        return f"{self.role.capitalize()} | {self.emotion} | Goals: {self.goals}"