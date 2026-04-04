from constants import NAME_TO_PAD, DEFAULT_PAD

class Emotion:

    def __init__(self, name=None, valence=None, arousal=None, dominance=None):
        self.valence = valence if valence is not None else 0.5
        self.arousal = arousal if arousal is not None else 0.5
        self.dominance = dominance if dominance is not None else 0.5
        self.name = name if name else "unknown"

        if name:
            self._pad_from_name()
        elif any(v is not None for v in [valence, arousal, dominance]):
            self._name_from_pad()

    def update(self, name=None, valence=None, arousal=None, dominance=None):
        if name:
            self.name = name
            self._pad_from_name()
        else:
            if valence is not None: self.valence = valence
            if arousal is not None: self.arousal = arousal
            if dominance is not None: self.dominance = dominance
            self._name_from_pad()

    def _pad_from_name(self):
        self.valence, self.arousal, self.dominance = \
            self.NAME_TO_PAD.get(self.name, (0.5, 0.5, 0.5))

    def _name_from_pad(self):
        # simple rule-based (faster + aligned with your model)
        v, a, d = self.valence, self.arousal, self.dominance

        if v > 0:
            if a > 0.5:
                self.name = "excited" if d > 0.5 else "surprised"
            else:
                self.name = "enjoyment" if d > 0.5 else "relaxed"
        else:
            if a > 0.5:
                self.name = "angry" if d > 0.5 else "anxious"
            else:
                self.name = "disappointed" if d > 0.5 else "sad"

    def __repr__(self):
        return f"{self.name} (V={self.valence:.2f}, A={self.arousal:.2f}, D={self.dominance:.2f})"
    
