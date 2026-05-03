FROM python:3.10-slim

# System dependencies: ffmpeg for audio, libsndfile1 for soundfile,
# libgomp1 for PyTorch/librosa parallelism, git for some pip installs
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    libgomp1 \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Upgrade pip first — old pip can't handle typing_extensions metadata quirks
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Install torch with CUDA 13.0 support first (must precede requirements.txt
# so pip sees torch==2.11.0+cu130 already satisfied and skips reinstall)
RUN pip install --no-cache-dir \
    torch==2.11.0 torchaudio==2.11.0 torchvision==0.26.0 \
    --index-url https://download.pytorch.org/whl/cu130

# Install remaining Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# pyannote packages: installed with --no-deps to bypass the numpy>=2.0
# metadata constraint (conflicts with facenet-pytorch<2.0.0 requirement).
# The packages work fine at runtime with numpy 1.26.4 — same as the host.
RUN pip install --no-cache-dir --no-deps \
    pyannote-core==6.0.1 \
    pyannote-database==6.1.1 \
    pyannote-metrics==4.0.0 \
    pyannote-pipeline==4.0.0 \
    "pyannote.audio==3.1.1" \
    pyannoteai-sdk==0.4.0

# Copy application code (data/, models/, logs/ are excluded via .dockerignore
# and mounted as volumes at runtime)
COPY . .

EXPOSE 5001 5002 5007
