from constants import (
    GOAL_STATUS_FAIL,
    GOAL_STATUS_SUCCESS,
    PAD_DEFAULT,
    PAD_HIGH_AROUSAL_THRESHOLD,
    PAD_LOW_AROUSAL_THRESHOLD,
    PAD_NEUTRAL_MAX,
    PAD_NEUTRAL_MIN,
)


def find_speaker(agents):
    for agent_id, agent in agents.items():
        if getattr(agent, "role", "") == "speaker":
            return agent_id, agent
    return None, None


def get_speaker_goals(speaker_agent):
    return list(getattr(speaker_agent, "goals", []))


def get_speaker_blockers(speaker_agent):
    blockers = []

    for goal in get_speaker_goals(speaker_agent):
        blockers.extend(getattr(goal, "blockers", []))

    return blockers


def detect_tone_incoherence(speaker_agent):
    emotion = getattr(speaker_agent, "emotion", None)
    if emotion is None:
        return None

    incoherent_goals = []

    for goal in get_speaker_goals(speaker_agent):
        if goal.status == GOAL_STATUS_SUCCESS and emotion.valence < PAD_NEUTRAL_MIN:
            incoherent_goals.append(goal)
        elif goal.status == GOAL_STATUS_FAIL and emotion.valence > PAD_NEUTRAL_MAX:
            incoherent_goals.append(goal)

    if not incoherent_goals:
        return None

    return {
        "kind": "tone_incoherence",
        "goal": incoherent_goals[0],
        "incoherent_goals": incoherent_goals,
    }


def detect_intensity_incoherence(speaker_agent):
    emotion = getattr(speaker_agent, "emotion", None)
    if emotion is None:
        return None

    arousal = emotion.arousal
    issues = []

    for goal in get_speaker_goals(speaker_agent):
        lower_threshold = getattr(goal, "lower_arousal_threshold", PAD_LOW_AROUSAL_THRESHOLD)
        goal_upper_threshold = getattr(goal, "upper_arousal_threshold", PAD_HIGH_AROUSAL_THRESHOLD)

        blocker = goal.get_most_critical_blocker() if hasattr(goal, "get_most_critical_blocker") else None
        blocker_threshold = getattr(blocker, "arousal_threshold", None) if blocker is not None else None

        effective_upper_threshold = (
            min(goal_upper_threshold, blocker_threshold)
            if blocker_threshold is not None
            else goal_upper_threshold
        )

        if arousal < lower_threshold:
            issues.append({
                "kind": "low_context",
                "goal": goal,
                "blocker": blocker,
                "arousal": arousal,
                "lower_threshold": lower_threshold,
                "goal_upper_threshold": goal_upper_threshold,
                "effective_upper_threshold": effective_upper_threshold,
                "blocker_threshold": blocker_threshold,
            })
            continue

        if arousal > effective_upper_threshold:
            blocker_responsible_agent = getattr(blocker, "responsible_agent", None) if blocker is not None else None
            is_other_blame = (
                blocker is not None
                and blocker_responsible_agent is not None
                and blocker_responsible_agent is not speaker_agent
            )

            kind = (
                "high_blocker_blame"
                if is_other_blame and blocker_threshold is not None and blocker_threshold <= goal_upper_threshold
                else "high_context"
            )

            issues.append({
                "kind": kind,
                "goal": goal,
                "blocker": blocker,
                "arousal": arousal,
                "lower_threshold": lower_threshold,
                "goal_upper_threshold": goal_upper_threshold,
                "effective_upper_threshold": effective_upper_threshold,
                "blocker_threshold": blocker_threshold,
            })

    if not issues:
        return None

    return {
        "kind": "intensity_incoherence",
        "issue": issues[0],
        "issues": issues,
    }


def blocker_has_actionable(blocker):
    single = getattr(blocker, "actionable", None)
    plural = getattr(blocker, "actionables", None)
    has_single = single is not None
    has_plural = isinstance(plural, list) and len(plural) > 0
    return has_single or has_plural


def goal_has_actionable(goal):
    single = getattr(goal, "actionable", None)
    plural = getattr(goal, "actionables", None)
    has_single = single is not None
    has_plural = isinstance(plural, list) and len(plural) > 0
    return has_single or has_plural


def blocker_has_responsible_agent(blocker):
    responsible_agent = getattr(blocker, "responsible_agent", None)
    responsible_agents = getattr(blocker, "responsible_agents", None)
    has_primary = responsible_agent is not None
    has_plural = isinstance(responsible_agents, list) and len(responsible_agents) > 0
    return has_primary or has_plural


def blocker_is_clear_for_concern(blocker):
    blocker_text = getattr(blocker, "text", "")
    has_text = isinstance(blocker_text, str) and bool(blocker_text.strip())
    return has_text and blocker_has_responsible_agent(blocker) and blocker_has_actionable(blocker)


def goal_has_clear_concern_context(goal):
    blockers = list(getattr(goal, "blockers", []))
    if goal_has_actionable(goal):
        return True
    return bool(blockers) and all(blocker_is_clear_for_concern(blocker) for blocker in blockers)


def find_first_unclear_concern_target(speaker_agent):
    for goal in get_speaker_goals(speaker_agent):
        if goal_has_actionable(goal):
            continue

        blockers = list(getattr(goal, "blockers", []))

        if not blockers:
            return goal, None

        for blocker in blockers:
            if not blocker_is_clear_for_concern(blocker):
                return goal, blocker

    return None, None


def summarize_blockers_actionables(blockers):
    blockers_list = list(blockers)
    all_blockers_have_actionable = bool(blockers_list) and all(
        blocker_has_actionable(blocker)
        for blocker in blockers_list
    )
    blockers_without_actionables = [
        blocker for blocker in blockers_list
        if not blocker_has_actionable(blocker)
    ]
    return all_blockers_have_actionable, blockers_without_actionables


def find_goal_for_blocker(speaker_agent, blocker):
    for goal in get_speaker_goals(speaker_agent):
        if blocker is None or blocker in getattr(goal, "blockers", []):
            return goal
    return None


def get_primary_goal_and_blocker(speaker_agent):
    goals = get_speaker_goals(speaker_agent)
    if not goals:
        return None, None

    primary_goal = goals[0]
    primary_blocker = (
        primary_goal.get_most_critical_blocker()
        if hasattr(primary_goal, "get_most_critical_blocker")
        else None
    )
    return primary_goal, primary_blocker


def detect_unclear_feedback(speaker_agent):
    looks_angry, _ = classify_emotional_profile(speaker_agent)
    if not looks_angry:
        return None

    goals = get_speaker_goals(speaker_agent)
    if not goals:
        return {
            "kind": "unclear_feedback",
            "goal": None,
            "blocker": None,
        }

    blockers_list = get_speaker_blockers(speaker_agent)
    if not blockers_list:
        goal, blocker = get_primary_goal_and_blocker(speaker_agent)
        return {
            "kind": "unclear_feedback",
            "goal": goal,
            "blocker": blocker,
        }

    _, blockers_without_actionables = summarize_blockers_actionables(blockers_list)

    if not blockers_without_actionables:
        return None

    blocker = blockers_without_actionables[0]
    goal = find_goal_for_blocker(speaker_agent, blocker)

    return {
        "kind": "unclear_feedback",
        "goal": goal,
        "blocker": blocker,
    }


def detect_unclear_concern(speaker_agent):
    _, looks_concerned = classify_emotional_profile(speaker_agent)
    if not looks_concerned:
        return None

    goals = get_speaker_goals(speaker_agent)
    if not goals:
        return {
            "kind": "unclear_concern",
            "goal": None,
            "blocker": None,
            "blockers_without_actionables": [],
        }

    if all(goal_has_clear_concern_context(goal) for goal in goals):
        return None

    blockers_list = get_speaker_blockers(speaker_agent)
    _, blockers_without_actionables = summarize_blockers_actionables(blockers_list)
    goal, blocker = find_first_unclear_concern_target(speaker_agent)

    if goal is None and blockers_without_actionables:
        blocker = blockers_without_actionables[0]
        goal = find_goal_for_blocker(speaker_agent, blocker)

    if goal is None:
        goal, blocker = get_primary_goal_and_blocker(speaker_agent)

    if goal is None:
        return None

    return {
        "kind": "unclear_concern",
        "goal": goal,
        "blocker": blocker,
        "blockers_without_actionables": blockers_without_actionables,
    }


def summarize_rule_issue(issue):
    if issue is None:
        return None

    return {
        "kind": issue.get("kind"),
        "goal": getattr(issue.get("goal"), "text", ""),
        "blocker": getattr(issue.get("blocker"), "text", "") if issue.get("blocker") is not None else None,
    }


def summarize_tone_issue(tone_issue):
    if tone_issue is None:
        return True, []

    incoherent_goals = tone_issue.get("incoherent_goals", [])
    return False, [
        {
            "text": goal.text,
            "status": goal.status,
        }
        for goal in incoherent_goals
    ]


def summarize_intensity_issue(intensity_issue):
    if intensity_issue is None:
        return True, []

    return False, [
        {
            "kind": issue["kind"],
            "goal": getattr(issue.get("goal"), "text", ""),
            "blocker": getattr(issue.get("blocker"), "text", "") if issue.get("blocker") is not None else None,
            "arousal": issue.get("arousal"),
            "lower_threshold": issue.get("lower_threshold"),
            "goal_upper_threshold": issue.get("goal_upper_threshold"),
            "effective_upper_threshold": issue.get("effective_upper_threshold"),
            "blocker_threshold": issue.get("blocker_threshold"),
        }
        for issue in intensity_issue.get("issues", [])
    ]


def classify_emotional_profile(speaker_agent):
    emotion = getattr(speaker_agent, "emotion", None)
    if emotion is None:
        return False, False

    valence = getattr(emotion, "valence", PAD_DEFAULT)
    dominance = getattr(emotion, "dominance", PAD_DEFAULT)

    negative_valence = valence < PAD_NEUTRAL_MIN
    looks_angry = negative_valence and dominance > PAD_NEUTRAL_MAX
    looks_concerned = negative_valence and dominance < PAD_NEUTRAL_MIN
    return looks_angry, looks_concerned
