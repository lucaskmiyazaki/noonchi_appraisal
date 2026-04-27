import json
import re
import sys
from pathlib import Path

def merge_transcript_segments(segments):
    merged = []
    sentence_end = re.compile(r'[.!?…]$')
    buffer = None

    for seg in segments:
        text = seg['text'].strip()
        if not text:
            continue
        if buffer is None:
            buffer = dict(seg)
        else:
            # If previous text does not end with sentence-ending punctuation, merge
            if not sentence_end.search(buffer['text']):
                buffer['text'] += ' ' + text
                buffer['end'] = seg['end']
            else:
                merged.append(buffer)
                buffer = dict(seg)
    if buffer:
        merged.append(buffer)
    # Reassign IDs
    for idx, seg in enumerate(merged, 1):
        seg['id'] = idx
    return merged

def main(input_path, output_path=None):
    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # If the file is a list, wrap it in a made-up header
    if isinstance(data, list):
        # Use the filename stem as sessionName
        import os
        session_id = os.path.splitext(os.path.basename(input_path))[0]
        data = {
            "id": session_id,
            "audioUrl": f"/uploads/{session_id}.wav",
            "audioFilename": f"{session_id}.wav",
            "originalName": f"{session_id}.wav",
            "sessionName": session_id,
            "safeSessionName": session_id,
            "uploadedAt": "2026-04-25T00:00:00.000000+00:00",
            "transcript": data
        }

    segments = data.get('transcript') or data
    merged = merge_transcript_segments(segments)
    data['transcript'] = merged

    target_path = output_path or input_path
    with open(target_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Merged transcript saved to {target_path}")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python transcript_analysis.py <input.json> [output.json]')
        sys.exit(1)
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
