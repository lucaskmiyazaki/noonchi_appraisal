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
        owner = (
            "None" if self.owner is None
            else ("Speaker" if self.owner.is_speaker else "Listener")
        )
        target = (
            "None" if self.target is None
            else ("Speaker" if self.target.is_speaker else "Listener")
        )
        return f"Actionable(owner={owner}, target={target}, text='{self.text}')"