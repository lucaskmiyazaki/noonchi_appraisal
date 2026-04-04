class Question:
    def __init__(self, speaker=None, target=None, text=""):
        self.speaker = speaker  # Agent asking
        self.target = target    # Agent receiving
        self.text = text        # question content

    def set_speaker(self, agent):
        self.speaker = agent

    def set_target(self, agent):
        self.target = agent

    def set_text(self, text):
        self.text = text

    def __repr__(self):
        speaker = (
            "None" if self.speaker is None
            else ("Speaker" if self.speaker.is_speaker else "Listener")
        )
        target = (
            "None" if self.target is None
            else ("Speaker" if self.target.is_speaker else "Listener")
        )
        return f"Question(from={speaker}, to={target}, text='{self.text}')"