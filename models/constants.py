# emotion_constants.py

PAD_NEUTRAL_MIN = 0.35
PAD_NEUTRAL_MAX = 0.65
PAD_LOW_DEFAULT = 0.25
PAD_HIGH_DEFAULT = 0.75
PAD_DEFAULT = 0.5

PAD_LOW_AROUSAL_THRESHOLD = 0.15
PAD_HIGH_AROUSAL_THRESHOLD = 0.85

DEFAULT_PAD = (PAD_DEFAULT, PAD_DEFAULT, PAD_DEFAULT)

EXCITED = "excited"
SURPRISED = "surprised"
ENJOYMENT = "enjoyment"
RELAXED = "relaxed"
ANGRY = "angry"
ANXIOUS = "anxious"
DISAPPOINTED = "disappointed"
SAD = "sad"

NAME_TO_PAD = {
    EXCITED:      (PAD_HIGH_DEFAULT, PAD_HIGH_DEFAULT, PAD_HIGH_DEFAULT),
    SURPRISED:    (PAD_HIGH_DEFAULT, PAD_HIGH_DEFAULT, PAD_LOW_DEFAULT),
    ENJOYMENT:    (PAD_HIGH_DEFAULT, PAD_LOW_DEFAULT, PAD_HIGH_DEFAULT),
    RELAXED:      (PAD_HIGH_DEFAULT, PAD_LOW_DEFAULT, PAD_LOW_DEFAULT),
    ANGRY:        (PAD_LOW_DEFAULT, PAD_HIGH_DEFAULT, PAD_HIGH_DEFAULT),
    ANXIOUS:      (PAD_LOW_DEFAULT, PAD_HIGH_DEFAULT, PAD_LOW_DEFAULT),
    DISAPPOINTED: (PAD_LOW_DEFAULT, PAD_LOW_DEFAULT, PAD_HIGH_DEFAULT),
    SAD:          (PAD_LOW_DEFAULT, PAD_LOW_DEFAULT, PAD_LOW_DEFAULT),
}

POSITIVE_CATEGORY = "positive"
NEGATIVE_DOMINANT_CATEGORY = "negative_dominant"
NEGATIVE_SUBMISSIVE_CATEGORY = "negative_submissive"

UNIFIED_TAGS_BY_CATEGORY = {
    POSITIVE_CATEGORY: [
        "laughing",
        "excited and energetic",
        "calm and pleased",
    ],
    NEGATIVE_DOMINANT_CATEGORY: [
        "angry and explosive",
        "disapointed and forgiving",
        "scolding and firm",
    ],
    NEGATIVE_SUBMISSIVE_CATEGORY: [
        "sobbing and depressed",
        "sad and regretful",
        "withdrawn and isolated",
    ],
}

POSITIVE_EMOTIONS = {
    EXCITED,
    SURPRISED,
    ENJOYMENT,
    RELAXED,
}

NEGATIVE_DOMINANT_EMOTIONS = {
    ANGRY,
    DISAPPOINTED,
}

NEGATIVE_SUBMISSIVE_EMOTIONS = {
    ANXIOUS,
    SAD,
}

EMOTION_CATEGORY_BY_EMOTION = {
    **{emotion: POSITIVE_CATEGORY for emotion in POSITIVE_EMOTIONS},
    **{emotion: NEGATIVE_DOMINANT_CATEGORY for emotion in NEGATIVE_DOMINANT_EMOTIONS},
    **{emotion: NEGATIVE_SUBMISSIVE_CATEGORY for emotion in NEGATIVE_SUBMISSIVE_EMOTIONS},
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