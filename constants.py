# emotion_constants.py

PAD_NEUTRAL_MIN = 0.35
PAD_NEUTRAL_MAX = 0.65
PAD_LOW_DEFAULT = 0.25
PAD_HIGH_DEFAULT = 0.75
PAD_DEFAULT = 0.5

PAD_LOW_AROUSAL_THRESHOLD = 0.15
PAD_HIGH_AROUSAL_THRESHOLD = 0.85

DEFAULT_PAD = (PAD_DEFAULT, PAD_DEFAULT, PAD_DEFAULT)

NAME_TO_PAD = {
    "excited":      (PAD_HIGH_DEFAULT, PAD_HIGH_DEFAULT, PAD_HIGH_DEFAULT),
    "surprised":    (PAD_HIGH_DEFAULT, PAD_HIGH_DEFAULT, PAD_LOW_DEFAULT),
    "enjoyment":    (PAD_HIGH_DEFAULT, PAD_LOW_DEFAULT, PAD_HIGH_DEFAULT),
    "relaxed":      (PAD_HIGH_DEFAULT, PAD_LOW_DEFAULT, PAD_LOW_DEFAULT),
    "angry":        (PAD_LOW_DEFAULT, PAD_HIGH_DEFAULT, PAD_HIGH_DEFAULT),
    "anxious":      (PAD_LOW_DEFAULT, PAD_HIGH_DEFAULT, PAD_LOW_DEFAULT),
    "disappointed": (PAD_LOW_DEFAULT, PAD_LOW_DEFAULT, PAD_HIGH_DEFAULT),
    "sad":          (PAD_LOW_DEFAULT, PAD_LOW_DEFAULT, PAD_LOW_DEFAULT),
}

GOAL_STATUS_ON_GOING = "on_going"
GOAL_STATUS_SUCCESS = "success"
GOAL_STATUS_FAIL = "fail"

GOAL_STATUSES = {
    GOAL_STATUS_ON_GOING,
    GOAL_STATUS_SUCCESS,
    GOAL_STATUS_FAIL,
}

ROLE_WEARER = "wearer"
ROLE_PARTICIPANTS = "participants"
ROLE_EXTERNAL = "external"

ROLES = {
    ROLE_WEARER,
    ROLE_PARTICIPANTS,
    ROLE_EXTERNAL,
}

LEGACY_ROLE_ALIASES = {
    "listener": ROLE_PARTICIPANTS,
    "passive": ROLE_EXTERNAL,
}


def normalize_role(role, default=ROLE_PARTICIPANTS):
    if role is None:
        return default

    normalized = str(role).strip().lower()
    if not normalized:
        return default

    return LEGACY_ROLE_ALIASES.get(normalized, normalized)