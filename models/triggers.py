# Trigger definitions — single source of truth.
# Each entry is used by templates (via Jinja2 global) and can be imported
# by server-side logic (e.g. validation, API responses).
#
# Fields:
#   id          — snake_case identifier, also used as the SVG icon filename
#                 (templates/trigger_icons/<id>.svg)
#   label       — display name
#   desc        — short description shown on the card
#   card_bg     — CSS colour for the card background
#   card_icon   — CSS colour used as the icon accent / fallback circle fill

TRIGGERS = [
    {
        "id": "tone_difference",
        "label": "Tone Difference",
        "desc": "Your tone lands sharper or harsher than the context suggests.",
        "card_bg": "var(--trigger-tone-difference-bg)",
        "card_icon": "var(--trigger-tone-difference-icon)",
    },
    {
        "id": "elevation",
        "label": "Elevation",
        "desc": "Your emotional intensity rises enough to affect how your message lands.",
        "card_bg": "var(--trigger-elevation-bg)",
        "card_icon": "var(--trigger-elevation-icon)",
    },
    {
        "id": "unclear_intent",
        "label": "Unclear Intent",
        "desc": "Your reaction shows friction but your goal or next step is missing.",
        "card_bg": "var(--trigger-unclear-intent-bg)",
        "card_icon": "var(--trigger-unclear-intent-icon)",
    },
    {
        "id": "excellent_tone",
        "label": "Excellent Tone",
        "desc": "Your tone lands especially well — recognize and repeat it.",
        "card_bg": "var(--trigger-excellent-tone-bg)",
        "card_icon": "var(--trigger-excellent-tone-icon)",
    },
    {
        "id": "need_for_clarification",
        "label": "Need for Clarification",
        "desc": "A participant sounds concerned and it's unclear what needs clarifying.",
        "card_bg": "var(--trigger-clarification-bg)",
        "card_icon": "var(--trigger-clarification-icon)",
    },
]

