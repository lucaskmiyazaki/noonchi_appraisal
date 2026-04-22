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


class Actionable:
    def __init__(self, owner=None, target=None, text=""):
        self.owner = owner    # Agent responsible for action
        self.target = target  # Agent affected (optional)
        self.text = text      # action description

    def set_owner(self, agent):
        self.owner = agent

    def set_target(self, agent):
        self.target = agent

    def set_text(self, text):
        self.text = text

    def __repr__(self):
        owner = _agent_label(self.owner)
        target = _agent_label(self.target)
        return f"Actionable(owner={owner}, target={target}, text='{self.text}')"