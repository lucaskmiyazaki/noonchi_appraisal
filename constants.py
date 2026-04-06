# emotion_constants.py

DEFAULT_PAD = (0, 0, 0)

NAME_TO_PAD = {
    "excited":      (1, 1, 1),
    "surprised":    (1, 1, 0),
    "enjoyment":    (1, 0, 1),
    "relaxed":      (1, 0, 0),
    "angry":        (-1, 1, 1),
    "anxious":      (-1, 1, 0),
    "disappointed": (-1, 0, 1),
    "sad":          (-1, 0, 0),
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