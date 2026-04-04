# emotion_constants.py

DEFAULT_PAD = (0.5, 0.5, 0.5)

NAME_TO_PAD = {
    "excited":      (0.7, 0.8, 0.7),
    "surprised":    (0.6, 0.8, 0.4),
    "enjoyment":    (0.7, 0.5, 0.7),
    "relaxed":      (0.6, 0.3, 0.4),
    "angry":        (-0.7, 0.8, 0.7),
    "anxious":      (-0.7, 0.8, 0.3),
    "disappointed": (-0.6, 0.3, 0.7),
    "sad":          (-0.6, 0.3, 0.3),
}

GOAL_STATUS_ON_GOING = "on_going"
GOAL_STATUS_SUCCESS = "success"
GOAL_STATUS_FAIL = "fail"

GOAL_STATUSES = {
    GOAL_STATUS_ON_GOING,
    GOAL_STATUS_SUCCESS,
    GOAL_STATUS_FAIL,
}

ROLE_SPEAKER = "speaker"
ROLE_LISTENER = "listener"
ROLE_PASSIVE = "passive"

ROLES = {
    ROLE_SPEAKER,
    ROLE_LISTENER,
    ROLE_PASSIVE,
}