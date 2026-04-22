def _agent_label(agent):
    if agent is None:
        return "None"

    name = getattr(agent, "name", "")
    if isinstance(name, str) and name.strip():
        return name.strip()

    role = getattr(agent, "role", "")
    if isinstance(role, str) and role.strip():
        return role.strip().capitalize()

    return "Agent"


class Question:
    def __init__(self, asker=None, target=None, text=""):
        self.asker = asker  # Agent asking
        self.target = target    # Agent receiving
        self.text = text        # question content

    def set_asker(self, agent):
        self.asker = agent

    def set_target(self, agent):
        self.target = agent

    def set_text(self, text):
        self.text = text

    def __repr__(self):
        asker = _agent_label(self.asker)
        target = _agent_label(self.target)
        return f"Question(from={asker}, to={target}, text='{self.text}')"