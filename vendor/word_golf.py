"""Word Golf Embeddings, reused from dixelstuff/escape-velocity engine.py.
Snapshot: 3 November 2026. Only the model-data path is adjusted.
"""
from pathlib import Path
import json, hashlib
import numpy as np
DATA = Path(__file__).parent.parent/'data'

class Embeddings:
    def __init__(self, folder=DATA):
        self.words = json.loads((folder/'words.json').read_text())
        self.index = {w:i for i,w in enumerate(self.words)}
        self.vectors = np.load(folder/'vectors.npy', mmap_mode='r')
        self.hubs=None
    def hub(self,word):
        if self.hubs is None:
            model=Path(__file__).parent.parent/'static/model'
            metadata=json.loads((model/'hubs.json').read_text())
            data=(model/metadata['file']).read_bytes()
            if len(data)!=len(self.words) or hashlib.sha256(data).hexdigest()!=metadata['sha256']:
                raise ValueError('Invalid word breadth data; rebuild the browser model.')
            self.hubs=np.frombuffer(data,dtype='u1')
        return float(self.hubs[self.index[word]])/255
    def cosine(self, a, b):
        return float(np.clip(self.vectors[self.index[a]] @ self.vectors[self.index[b]], -1, 1))
