"""Mystery-specific rules. All target-bearing data stays behind the local API."""
from collections import deque
import math
import random
import json
import numpy as np

from vendor.word_golf import Embeddings, DATA

EPS = 1e-7
TARGETS = 'stripes lantern orchard velvet compass thunder glacier ribbon honey mirror feather anchor meadow pottery cactus violin coral bakery cinnamon umbrella puzzle marble bicycle circus blanket pepper castle jungle magnet waterfall'.split()
NAMES = ['Indigo', 'Amber', 'Rose']


def requirement(e, origin, proximity):
    """Golf's .095–.215 range and .035 hub ceiling, now launch-only.

    Remaining target distance replaces the proposed shot's forward distance.
    Only the launch hub is used: proposed-word hubs would leak information
    through a variable threshold and defeat the fixed-per-launch requirement.
    """
    remaining = min(1., max(0., (1. - proximity) / .9))
    return .095 + .12 * remaining + .035 * e.hub(origin) * remaining**2


def visual(proximity):
    # Word Golf mapFraction's .55 power curve; one shared fixed axis for everyone.
    # Negative cosines remain visibly distinct rather than clipping at zero.
    return max(0., min(1., ((proximity + 1.) / 2.)**.55))


class Mystery:
    def __init__(self, e, players=2, target=None, starts=None, seed=None):
        if type(players) is not int or players not in (2, 3):
            raise ValueError('Choose two or three players.')
        self.e, self.rng = e, random.Random(seed)
        self.target = str(target or self.rng.choice(TARGETS)).strip().lower()
        if self.target not in e.index:
            raise ValueError('The mystery must be in the supported vocabulary.')
        self.sim = np.clip(np.asarray(e.vectors @ e.vectors[e.index[self.target]]), -1, 1)
        neighbours = np.sort(np.delete(self.sim, e.index[self.target]))[::-1]
        # Extremely close equivalents only; a cello must not finish VIOLIN.
        # Density tightens the zone to at most one nonliteral neighbour, apart
        # from ties above the .97 ceiling. Sparse targets need the exact word.
        self.finish = float(max(.88, min(.97, neighbours[1] + .005)))
        self.diagnostics = {}
        if starts is None:
            starts = self.select_starts(players)
        if not isinstance(starts, list) or len(starts) != players:
            raise ValueError('Supply one different starting word per player.')
        starts = [str(w).strip().lower() for w in starts]
        if len(set(starts)) != players or any(w not in e.index for w in starts):
            raise ValueError('Starting words must be different supported words.')
        if any(self.sim[e.index[w]] + EPS >= self.finish for w in starts):
            raise ValueError('A starting word is already in the finishing zone.')
        self.players = [dict(name=NAMES[i], words=[w], launch=w) for i, w in enumerate(starts)]
        self.active, self.history, self.won, self.suspects = 0, [], False, []
        self.diagnostics.update(self.start_diagnostics(starts))

    def proximity(self, word):
        return float(self.sim[self.e.index[word]])

    def threshold(self, word):
        return requirement(self.e, word, self.proximity(word))

    def select_starts(self, count):
        e = self.e
        # Common vocabulary prefix, not the long tail of the dictionary.
        nouns = json.loads((DATA/'start-vocabulary.json').read_text())
        pool = [e.index[w] for w in nouns
                if .10 <= self.sim[e.index[w]] <= .19]
        self.rng.shuffle(pool)
        candidates = pool[:120]
        if len(candidates) < count:
            raise ValueError('This target has too few starting positions; try another.')
        vectors = np.asarray(e.vectors[candidates])
        contact = vectors @ e.vectors.T
        thresholds = np.array([requirement(e, e.words[i], float(self.sim[i])) for i in candidates])
        legal = contact + EPS >= thresholds[:, None]
        degrees = legal.sum(axis=1)
        progress = (legal & (self.sim[None, :] > self.sim[candidates, None] + .05)).sum(axis=1)
        finishing = np.flatnonzero(self.sim + EPS >= self.finish)
        immediate = legal[:, finishing].any(axis=1)
        # A bounded, exact replayable path witness through 800 close words.
        # This certifies reachability, not a global shortest-path claim.
        near = np.argsort(self.sim)[-800:]
        nodes = np.unique(np.concatenate((near, candidates)))
        node_vectors = np.asarray(e.vectors[nodes])
        edge = node_vectors @ node_vectors.T
        limits = np.array([requirement(e, e.words[i], float(self.sim[i])) for i in nodes])
        edge = edge + EPS >= limits[:, None]
        steps = np.full(len(nodes), 999, dtype=int)
        next_node = {}
        queue = deque(np.flatnonzero(self.sim[nodes] + EPS >= self.finish).tolist())
        for j in queue:
            steps[j] = 0
        while queue:
            j = queue.popleft()
            for k in np.flatnonzero(edge[:, j] & (steps == 999)):
                steps[k] = steps[j] + 1
                next_node[int(k)] = j
                queue.append(int(k))
        lookup = {int(n): j for j, n in enumerate(nodes)}
        eligible = [j for j, n in enumerate(candidates)
                    if not immediate[j] and degrees[j] >= 30 and progress[j] >= 12
                    and steps[lookup[n]] < 999]
        pair_cos = vectors @ vectors.T
        best = None
        for _ in range(1800):
            if len(eligible) < count:
                break
            pick = self.rng.sample(eligible, count)
            sims = self.sim[np.array(candidates)[pick]]
            separation = max(float(pair_cos[a, b]) for a in pick for b in pick if a != b)
            degree_ratio = max(degrees[pick]) / min(degrees[pick])
            progress_ratio = max(progress[pick]) / min(progress[pick])
            hubs = [e.hub(e.words[candidates[j]]) for j in pick]
            if np.ptp(sims) > .025 or separation > .24 or degree_ratio > 1.8 or progress_ratio > 2.:
                continue
            cost = 8 * np.ptp(sims) + separation + .15 * math.log(degree_ratio) + .15 * math.log(progress_ratio) + .1 * (max(hubs)-min(hubs))
            if best is None or cost < best[0]:
                best = (cost, pick)
        if best is None:
            raise ValueError('No balanced, reachable starts found. Try another mystery or two players.')
        result = [e.words[candidates[j]] for j in best[1]]
        witnesses = []
        for word in result:
            j = lookup[e.index[word]]
            route = [word]
            while j in next_node:
                j = next_node[j]
                route.append(e.words[int(nodes[j])])
            witnesses.append(route)
        self.diagnostics['verified_routes'] = witnesses
        self.diagnostics['selection'] = 'Common-word shell; equal proximity, diverse directions, comparable legal degree and forward options; bounded graph reachability.'
        return result

    def start_diagnostics(self, starts):
        rows = []
        for word in starts:
            links = self.e.vectors @ self.e.vectors[self.e.index[word]]
            legal = links + EPS >= self.threshold(word)
            rows.append(dict(word=word, proximity=self.proximity(word), required=self.threshold(word),
                             hub=self.e.hub(word), connections=int(legal.sum()),
                             forward_options=int((legal & (self.sim > self.proximity(word)+.05)).sum())))
        return dict(starts=rows, pairwise=[dict(a=a, b=b, cosine=self.e.cosine(a,b))
                    for i,a in enumerate(starts) for b in starts[i+1:]],
                    finish_similarity=self.finish, finish_neighbours=[self.e.words[i] for i in np.flatnonzero(self.sim+EPS>=self.finish) if self.e.words[i] != self.target])

    def select(self, word):
        if self.won:
            raise ValueError('This mystery is solved.')
        if word not in self.players[self.active]['words']:
            raise ValueError('Select one of the active player’s discovered words.')
        self.players[self.active]['launch'] = word

    def submit(self, word):
        if self.won:
            raise ValueError('This mystery is solved. Start a new one.')
        word = str(word).strip().lower()
        player = self.players[self.active]
        if word not in self.e.index:
            raise ValueError('That word is outside the supported vocabulary. Try another.')
        if word in player['words']:
            raise ValueError('You already have that word. Select it as a launch point instead.')
        origin = player['launch']
        connection = self.e.cosine(origin, word)
        required = self.threshold(origin)
        if connection + EPS < required:
            # Deliberately no proposed word, proximity, direction or metric.
            # Failed attempts are not retained in game state or diagnostics.
            return dict(success=False, message='Connection too weak. Try another word; it’s still your turn.')
        proximity = self.proximity(word)
        gain = proximity - self.proximity(origin)
        # A modest provisional accolade, not Golf's multi-leg route score.
        # Reward useful progress through a less obvious legal link; suppress hubs.
        clever = max(0., gain) * max(0., 1.-connection) * (1.-.5*max(self.e.hub(origin),self.e.hub(word)))
        event = dict(player=self.active, origin=origin, word=word, proximity=proximity,
                     connection=connection, required=required, gain=gain, clever=clever)
        self.history.append(event)
        player['words'].append(word)
        player['launch'] = word
        self.won = proximity + EPS >= self.finish
        if not self.won:
            self.active = (self.active + 1) % len(self.players)
        return dict(success=True, word=word, won=self.won)

    def suspect(self, action, word):
        word = str(word).strip().lower()
        if not word or len(word)>40 or not all(c.isalpha() or c in ' -' for c in word):
            raise ValueError('Write a short word or phrase for the board.')
        item = next((s for s in self.suspects if s['word']==word), None)
        if action == 'add':
            if item is None:
                if len(self.suspects)>=50:
                    raise ValueError('The board is full. Remove a suspect first.')
                self.suspects.append(dict(word=word, favourite=False, eliminated=False))
        elif item is not None and action == 'remove':
            self.suspects.remove(item)
        elif item is not None and action in ('favourite','eliminated'):
            item[action] = not item[action]
        else:
            raise ValueError('Unknown board action.')

    def state(self):
        state = dict(players=[dict(name=p['name'], launch=p['launch'], words=[dict(word=w, position=visual(self.proximity(w))) for w in p['words']]) for p in self.players],
                     active=self.active, words=len(self.history), won=self.won,
                     suspects=self.suspects,
                     history=[dict(player=h['player'],origin=h['origin'],word=h['word']) for h in self.history])
        if self.won:
            awards = []
            for title, field in [('Most Clever','clever'),('One Hit Wonder','gain')]:
                best = max(self.history, key=lambda h:h[field])
                if best[field]>EPS:
                    awards.append(dict(title=title, player=best['player'], word=best['word'], origin=best['origin']))
            awards.append(dict(title='Finisher', player=self.history[-1]['player'], word=self.history[-1]['word'], origin=self.history[-1]['origin']))
            state.update(target=self.target, awards=awards)
        return state

    def debug(self):
        return dict(target=self.target, diagnostics=self.diagnostics,
                    launches=[dict(player=p['name'],word=w,proximity=self.proximity(w),required=self.threshold(w),hub=self.e.hub(w)) for p in self.players for w in p['words']],
                    history=self.history, scoring='Provisional Most Clever = positive cosine gain × (1 − connection) × (1 − .5 × max endpoint hub). One Hit Wonder = largest positive cosine gain.')
