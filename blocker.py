from constants import PAD_HIGH_AROUSAL_THRESHOLD


class Blocker:
    def __init__(self, text, responsible_agents=None, actionable=None, question=None):
        self.text = text
        self.responsible_agents = responsible_agents if responsible_agents else []
        self.responsible_agent = self.responsible_agents[0] if self.responsible_agents else None
        self.actionable = actionable
        self.question = question
        self.arousal_threshold = PAD_HIGH_AROUSAL_THRESHOLD

    def set_responsible(self, agent):
        self.responsible_agents = [agent]
        self.responsible_agent = agent

    def add_responsible_agent(self, agent):
        if agent not in self.responsible_agents:
            self.responsible_agents.append(agent)
            if self.responsible_agent is None:
                self.responsible_agent = agent

    def set_actionable(self, actionable):
        self.actionable = actionable

    def set_question(self, question):
        self.question = question

    def calculate_arousal_threshold(self, blocked_goal):
        self.arousal_threshold = PAD_HIGH_AROUSAL_THRESHOLD

    def __repr__(self):
        if not self.responsible_agents:
            agents_text = "None"
        else:
            agents_text = ", ".join(
                getattr(agent, "name", "") or getattr(agent, "role", "agent")
                for agent in self.responsible_agents
            )

        return (
            f"Blocker(text='{self.text}', "
            f"responsible_agents=[{agents_text}], "
            f"actionable={self.actionable}, "
            f"question={self.question}, "
            f"arousal_threshold={self.arousal_threshold})"
        )