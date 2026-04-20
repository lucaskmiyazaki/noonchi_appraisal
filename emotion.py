from constants import (
    DEFAULT_PAD,
    NAME_TO_PAD,
    PAD_NEUTRAL_MAX,
    PAD_NEUTRAL_MIN,
)

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
            NAME_TO_PAD.get(self.name, DEFAULT_PAD)

    @staticmethod
    def _classify_axis(value):
        if value < PAD_NEUTRAL_MIN:
            return "low"
        if value > PAD_NEUTRAL_MAX:
            return "high"
        return "neutral"

    def _name_from_pad(self):
        v, a, d = self.valence, self.arousal, self.dominance
        v_state = self._classify_axis(v)
        a_state = self._classify_axis(a)
        d_state = self._classify_axis(d)

        if "neutral" in {v_state, a_state, d_state}:
            self.name = "unknown"
            return

        if v_state == "high":
            if a_state == "high":
                self.name = "excited" if d_state == "high" else "surprised"
            else:
                self.name = "enjoyment" if d_state == "high" else "relaxed"
        else:
            if a_state == "high":
                self.name = "angry" if d_state == "high" else "anxious"
            else:
                self.name = "disappointed" if d_state == "high" else "sad"

    def __repr__(self):
        return f"{self.name} (V={self.valence:.2f}, A={self.arousal:.2f}, D={self.dominance:.2f})"
    
