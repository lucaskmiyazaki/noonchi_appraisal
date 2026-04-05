from constants import (
    GOAL_STATUS_ON_GOING,
    GOAL_STATUSES,
)


class Goal:
    def __init__(self, text, status=GOAL_STATUS_ON_GOING, blockers=None):
        self.text = text
        self.status = status if status in GOAL_STATUSES else GOAL_STATUS_ON_GOING
        self.blockers = blockers if blockers else []

        self.lower_arousal_threshold = 0.2
        self.upper_arousal_threshold = 0.8
        self.calculate_arousal_threshold()

    def calculate_arousal_threshold(self):
        """
        For now: sets fixed lower/upper thresholds
        Later: can depend on goal importance, urgency, etc.
        """
        self.lower_arousal_threshold = 0.2
        self.upper_arousal_threshold = 0.8

    def update_status(self, status):
        if status in GOAL_STATUSES:
            self.status = status
        else:
            raise ValueError(f"Invalid goal status: {status}")

    def add_blocker(self, blocker):
        blocker.calculate_arousal_threshold(self.text)
        self.blockers.append(blocker)

    def get_most_critical_blocker(self):
        if not self.blockers:
            return None
        return max(self.blockers, key=lambda b: b.arousal_threshold)

    def __repr__(self):
        return (
            f"Goal(text='{self.text}', "
            f"status={self.status}, "
            f"lower_arousal_threshold={self.lower_arousal_threshold}, "
            f"upper_arousal_threshold={self.upper_arousal_threshold}, "
            f"blockers={self.blockers})"
        )