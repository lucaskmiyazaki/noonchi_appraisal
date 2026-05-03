# Codesign2

A meeting analysis platform that records audio, transcribes speech, runs emotion/intent analysis, and surfaces reflections and coaching nudges through a web UI. A wearable Bangle.js smartwatch receives real-time tip notifications over BLE.

---

## Architecture

| Service | Port | Description |
|---|---|---|
| `nginx` | 5000 | Reverse proxy — public entry point |
| `processing_server` | 5002 | Audio upload, transcription (Whisper), pipeline execution, reflection generation, voice synthesis |
| `ui_server` | 5001 | User-facing pages: analysis, journaling, practice, nudges |
| `bangle_server` | 5007 | BLE bridge — sends tips to Bangle.js smartwatch |

The analysis pipeline runs in five steps:
1. Merge transcript segments
2. Emotion analysis (PAD model — valence, arousal, dominance)
3. Intent classification (OpenAI GPT)
4. Goal analysis
5. Build intent diagram

---

## Prerequisites

- Docker + Docker Compose
- `ngrok` (for prod)
- OpenAI API key + ElevenLabs API key

---

## Setup

Copy and fill in the environment file:

```bash
cp .env.example .env   # or edit .env directly
```

Required variables in `.env`:

```
OPENAI_API_KEY=...
ELEVENLABS_API_KEY=...
DEBUG=true
```

---

## Running

### Development (local, `DEBUG=true`, logs stream to terminal)

```bash
./dev.sh
```

Starts all containers in the foreground. Access at **http://localhost:5000**.

### Production (detached, `DEBUG=false`, exposed via ngrok)

```bash
./prod.sh
```

Starts all containers in the background, then launches `ngrok http 5000`. Press Ctrl+C to stop ngrok — containers keep running.

Stop everything:

```bash
sudo docker compose down
```

---