from emotion import Emotion
from agent import Agent
from goal import Goal
from blocker import Blocker


def print_tone_result(agent):
    result = agent.is_tone_coherent()
    print("Tone coherent:", result)


def print_intensity_result(agent):
    is_coherent, goals, blockers = agent.is_intensity_coherent()
    print("Intensity coherent:", is_coherent)
    print("Related goals:", goals)
    print("Related blockers:", blockers)


# -------------------------
# TEST 1: coherent case
# -------------------------
emotion1 = Emotion(valence=-0.6, arousal=0.5, dominance=0.6)
agent1 = Agent(is_speaker=True, emotion=emotion1)

goal1 = Goal(text="Deliver project", status="failed")
blocker1 = Blocker(text="Client requirements unclear")
goal1.add_blocker(blocker1)

agent1.add_goal(goal1)

print("=== TEST 1: coherent case ===")
print(agent1)
print_tone_result(agent1)
print_intensity_result(agent1)
print()


# -------------------------
# TEST 2: tone incoherent
# failed goal + positive valence
# -------------------------
emotion2 = Emotion(valence=0.7, arousal=0.5, dominance=0.6)
agent2 = Agent(is_speaker=True, emotion=emotion2)

goal2 = Goal(text="Finish presentation", status="failed")
blocker2 = Blocker(text="Slides were incomplete")
goal2.add_blocker(blocker2)

agent2.add_goal(goal2)

print("=== TEST 2: tone incoherent ===")
print(agent2)
print_tone_result(agent2)
print_intensity_result(agent2)
print()


# -------------------------
# TEST 3: intensity incoherent (under threshold)
# arousal below goal lower threshold
# -------------------------
emotion3 = Emotion(valence=-0.5, arousal=0.2, dominance=0.4)
agent3 = Agent(is_speaker=False, emotion=emotion3)

goal3 = Goal(text="Prepare for client meeting", status="on_going")
blocker3 = Blocker(text="Not enough preparation time")
goal3.add_blocker(blocker3)

agent3.add_goal(goal3)

print("=== TEST 3: intensity incoherent (under) ===")
print(agent3)
print_tone_result(agent3)
print_intensity_result(agent3)
print()


# -------------------------
# TEST 4: intensity incoherent (over threshold)
# arousal above blocker threshold
# -------------------------
emotion4 = Emotion(valence=-0.5, arousal=0.9, dominance=0.7)
agent4 = Agent(is_speaker=True, emotion=emotion4)

goal4 = Goal(text="Send follow-up email", status="on_going")
blocker4 = Blocker(text="Waiting for one missing detail")
goal4.add_blocker(blocker4)

agent4.add_goal(goal4)

print("=== TEST 4: intensity incoherent (over) ===")
print(agent4)
print_tone_result(agent4)
print_intensity_result(agent4)
print()