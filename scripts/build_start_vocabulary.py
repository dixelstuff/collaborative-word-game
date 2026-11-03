"""Reproduce concrete noun candidates from Word Golf's retained WordNet archive.

Usage: python scripts/build_start_vocabulary.py /path/to/wordnet.zip
Runtime play needs only the generated JSON, not WordNet or NLTK.
"""
from pathlib import Path
import json
import sys
import zipfile

root = Path(__file__).resolve().parent.parent
with zipfile.ZipFile(sys.argv[1]) as archive:
    nouns = set()
    for line in archive.read('wordnet/data.noun').decode().splitlines():
        if not line or not line[0].isdigit():
            continue
        fields = line.split()
        # Animal, artifact, body, food, location, natural object, plant, substance.
        if int(fields[1]) not in {5, 6, 8, 13, 15, 17, 20, 27}:
            continue
        for i in range(int(fields[3], 16)):
            word = fields[4+i*2]
            if word.isalpha() and word.islower():
                nouns.add(word)
words = json.loads((root/'data/words.json').read_text())[:12000]
starts = [w for w in words if w in nouns and 4 <= len(w) <= 11]
(root/'data/start-vocabulary.json').write_text(json.dumps(starts))
print(f'{len(starts)} concrete noun candidates')
