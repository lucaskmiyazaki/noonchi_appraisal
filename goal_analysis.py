import sys
import json

def main(json_path):
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    transcript = data.get('transcript', data)
    desires = []
    negative_evaluations = []
    for seg in transcript:
        label = seg.get('intent_label')
        if label == 'desire':
            desires.append(seg['text'])
        elif label == 'negative evaluation':
            negative_evaluations.append(seg['text'])
    print('Desires:')
    for d in desires:
        print('-', d)
    print('\nNegative Evaluations:')
    for n in negative_evaluations:
        print('-', n)

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python goal_analysis.py <transcript.json>')
        sys.exit(1)
    main(sys.argv[1])
