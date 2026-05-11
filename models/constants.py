# emotion_constants.py

PAD_NEUTRAL_MIN = 0.35
PAD_NEUTRAL_MAX = 0.65
PAD_LOW_DEFAULT = 0.25
PAD_HIGH_DEFAULT = 0.75
PAD_DEFAULT = 0.5

PAD_LOW_AROUSAL_THRESHOLD = 0.20
PAD_HIGH_AROUSAL_THRESHOLD = 0.75

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
NEGATIVE_CATEGORY = "negative"

UNIFIED_TAGS_BY_CATEGORY = {
    POSITIVE_CATEGORY: [
        "laughing",
        "excited and energetic",
        "calm and pleased",
    ],
    NEGATIVE_CATEGORY: [
        "sobbing and depressed",
        "concerned and firm",
        "regret and sad",
    ],
}
#NEGATIVE_CATEGORY: [
#        "angry and explosive",
#        "firm and calm",
#        "concerned and anxious",
#    ],

SUGGESTIONS_BY_CATEGORY = {
    POSITIVE_CATEGORY: [
        "Try expressing this with warmth and enthusiasm to reinforce the positive message.",
        "Consider using an uplifting tone so the listener feels acknowledged and motivated.",
        "You could make your encouragement more explicit and energetic to increase impact.",
    ],
    NEGATIVE_CATEGORY: [
        "Expressing a sad tone might show how deeply this situation is affecting you.",
        "Expressing a concerned voice tone might help show seriousness and genuine worry.",
        "Expressing a regretful voice tone might help communicate reflection and accountability.",
    ],
}
#NEGATIVE_CATEGORY: [
#        "Expressing an angry voice tone might make your message sound stronger, but stay controlled so it does not come across as too aggressive.",
#        "Expressing a firm voice tone might make your message sound confident and clear.",
#        "Expressing a concerned voice tone might help show seriousness and care, but avoid sounding overly anxious or unsure.",
#    ],

OPPOSITE_CATEGORY = {
    POSITIVE_CATEGORY: NEGATIVE_CATEGORY,
    NEGATIVE_CATEGORY: POSITIVE_CATEGORY,
}

POSITIVE_EMOTIONS = {
    EXCITED,
    SURPRISED,
    ENJOYMENT,
    RELAXED,
}

NEGATIVE_EMOTIONS = {
    ANGRY,
    DISAPPOINTED,
    ANXIOUS,
    SAD,
}

EMOTION_CATEGORY_BY_EMOTION = {
    **{emotion: POSITIVE_CATEGORY for emotion in POSITIVE_EMOTIONS},
    **{emotion: NEGATIVE_CATEGORY for emotion in NEGATIVE_EMOTIONS},
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


def classify_emotion_from_vad(valence: float, arousal: float, dominance: float) -> str:
    """Return the emotion name whose PAD prototype is nearest to the given values."""
    best_emotion = SAD
    best_dist = float("inf")
    for emotion, (pv, pa, pd) in NAME_TO_PAD.items():
        dist = ((valence - pv) ** 2 + (arousal - pa) ** 2 + (dominance - pd) ** 2) ** 0.5
        if dist < best_dist:
            best_dist = dist
            best_emotion = emotion
    return best_emotion