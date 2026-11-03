import copy
import json
import threading
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import numpy as np
from game import Embeddings, Mystery, TARGETS, EPS
from server import make_server


class RulesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.e = Embeddings()

    def game(self, players=2):
        return Mystery(self.e, players, target='stripes', seed=42)

    def test_failed_words_leave_no_trace_or_target_information(self):
        g = self.game()
        before = copy.deepcopy(g.state())
        origin = g.players[0]['launch']
        cosines = self.e.vectors @ self.e.vectors[self.e.index[origin]]
        failures = np.flatnonzero(cosines < g.threshold(origin)-.01)
        far = int(failures[np.argmin(g.sim[failures])])
        close = int(failures[np.argmax(g.sim[failures])])
        first = g.submit(self.e.words[far])
        second = g.submit(self.e.words[close])
        self.assertEqual(first,second)
        self.assertEqual(set(first), {'success','message'})
        self.assertEqual(before,g.state())
        self.assertEqual(g.debug()['history'],[])
        public = json.dumps(g.state())
        self.assertNotIn('stripes',public)
        self.assertNotIn('threshold',public)

    def test_threshold_is_fixed_and_backward_movement_is_valid(self):
        g = self.game()
        origin = g.players[0]['launch']
        legal = []
        for word in self.e.words:
            if word!=origin and self.e.cosine(origin,word)+EPS>=g.threshold(origin):
                legal.append(word)
        backward = next(w for w in legal if g.proximity(w)<g.proximity(origin)-.02)
        required = g.threshold(origin)
        event = g.submit(backward)
        self.assertTrue(event['success'])
        self.assertEqual(g.history[-1]['required'],required)
        self.assertLess(g.history[-1]['gain'],0)
        self.assertEqual(g.active,1)
        self.assertEqual(g.state()['words'],1)
        self.assertIn(origin,g.players[0]['words'])
        self.assertIn(backward,g.players[0]['words'])

    def test_launch_ownership_and_revisit(self):
        g = self.game()
        origin = g.players[0]['launch']
        with self.assertRaises(ValueError):
            g.select(g.players[1]['launch'])
        g.submit(g.diagnostics['verified_routes'][0][1])
        g.submit(g.diagnostics['verified_routes'][1][1])
        self.assertEqual(g.active,0)
        g.select(origin)
        self.assertEqual(g.players[0]['launch'],origin)
        self.assertEqual(g.state()['words'],2)
        with self.assertRaises(ValueError):
            g.submit(origin)

    def test_suspects_are_an_unscored_workspace(self):
        g=self.game()
        g.suspect('add','stripes')
        g.suspect('add','this is not a dictionary word')
        self.assertEqual(g.active,0)
        self.assertEqual(g.state()['words'],0)
        self.assertFalse(g.won)
        self.assertEqual(set(g.state()['suspects'][0]),{'word','favourite','eliminated'})
        g.suspect('favourite','stripes'); g.suspect('eliminated','stripes')
        self.assertTrue(g.suspects[0]['favourite'])
        self.assertTrue(g.suspects[0]['eliminated'])
        g.suspect('remove','stripes')
        self.assertEqual(len(g.suspects),1)

    def test_all_targets_have_balanced_verified_starts_for_two_and_three(self):
        for target in TARGETS:
            for count in (2,3):
                with self.subTest(target=target,players=count):
                    g=Mystery(self.e,count,target=target,seed=42)
                    rows=g.diagnostics['starts']
                    self.assertLessEqual(max(r['proximity'] for r in rows)-min(r['proximity'] for r in rows),.025+EPS)
                    self.assertLessEqual(max(r['connections'] for r in rows)/min(r['connections'] for r in rows),1.8+EPS)
                    self.assertLessEqual(max(r['forward_options'] for r in rows)/min(r['forward_options'] for r in rows),2.+EPS)
                    self.assertTrue(all(p['cosine']<=.24+EPS for p in g.diagnostics['pairwise']))
                    for route in g.diagnostics['verified_routes']:
                        for a,b in zip(route,route[1:]):
                            self.assertGreaterEqual(self.e.cosine(a,b)+EPS,g.threshold(a))
                        self.assertGreaterEqual(g.proximity(route[-1])+EPS,g.finish)
                    # Play the actual certified paths, alternating all players.
                    paths=[iter(r[1:]) for r in g.diagnostics['verified_routes']]
                    for _ in range(20):
                        if g.won:break
                        self.assertTrue(g.submit(next(paths[g.active]))['success'])
                    self.assertTrue(g.won)
                    result=g.state()
                    self.assertEqual(result['words'],len(g.history))
                    self.assertEqual(result['target'],target)
                    self.assertEqual(result['awards'][-1]['title'],'Finisher')

    def test_sparse_and_dense_targets_have_tight_finish_zones(self):
        for target in ['violin','lantern','stripes']:
            g=Mystery(self.e,target=target,seed=42)
            self.assertGreaterEqual(g.finish,.88)
            self.assertGreaterEqual(g.proximity(target)+EPS,g.finish)
            self.assertLessEqual(len(g.diagnostics['finish_neighbours']),1)
        g=Mystery(self.e,target='violin',seed=42)
        self.assertLess(g.proximity('cello'),g.finish)
        self.assertLess(g.proximity('piano'),g.finish)

    def test_reproducibility_and_invalid_setups(self):
        self.assertEqual(self.game().state(),self.game().state())
        for options in [dict(players=4),dict(players=2.5),dict(target='notawordxyz'),dict(starts=['tiger','tiger']),dict(starts=['tiger','stripes'])]:
            with self.assertRaises(ValueError):Mystery(self.e,target=options.pop('target','stripes'),**options)


class APITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=make_server(0)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
        cls.base=f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join()

    def post(self,action,body,origin=None):
        headers={'Content-Type':'application/json'}
        if origin:headers['Origin']=origin
        request=Request(self.base+'/api/'+action,data=json.dumps(body).encode(),headers=headers)
        with urlopen(request) as response:return json.load(response)

    def test_http_solve_and_hidden_normal_payload(self):
        r=self.post('new',dict(players=3,target='stripes',seed=42))
        token=r['token']
        self.assertNotIn('target',r['state'])
        self.assertEqual(self.post('state',dict(token=token))['state'],r['state'])
        debug=self.post('debug',dict(token=token))
        routes=[iter(r[1:]) for r in debug['diagnostics']['verified_routes']]
        state=r['state']
        while not state['won']:
            response=self.post('submit',dict(token=token,word=next(routes[state['active']])))
            self.assertTrue(response['event']['success'])
            state=response['state']
        self.assertEqual(state['target'],'stripes')
        self.assertGreater(state['words'],0)

    def test_invalid_sessions_origins_and_json(self):
        for action,body,origin,expected in [('submit',dict(token='bad',word='tiger'),None,410),('new',dict(players=2),'https://example.com',403),('new',[],None,400)]:
            with self.assertRaises(HTTPError) as context:self.post(action,body,origin)
            self.assertEqual(context.exception.code,expected)
            context.exception.close()


if __name__=='__main__':unittest.main()
