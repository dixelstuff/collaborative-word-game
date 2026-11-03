"""A loopback-only local prototype, no accounts, remote APIs or multiplayer server."""
import os
# Small matrix batches are much faster without a thread pool on every operation.
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
os.environ.setdefault('VECLIB_MAXIMUM_THREADS', '1')
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import argparse
import json
import secrets
import threading
from game import Embeddings, Mystery

ROOT = Path(__file__).parent


def make_server(port=8001):
    embeddings = Embeddings()
    sessions, lock = {}, threading.Lock()

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(ROOT/'static'), **kwargs)

        def reply(self, body, status=200):
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == '/api/config':
                return self.reply(dict(vocabulary=len(embeddings.words), model='Word Golf · GloVe 6B · 300d'))
            if self.path.startswith('/api/'):
                return self.reply(dict(error='Use POST for game actions.'), 405)
            return super().do_GET()

        def do_POST(self):
            # Refuse cross-origin writes to this local application.
            origin = self.headers.get('Origin')
            if origin and origin != 'http://'+self.headers.get('Host',''):
                return self.reply(dict(error='Cross-origin request refused.'), 403)
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 12000:
                    raise ValueError('Invalid request size.')
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict):
                    raise ValueError('Expected a JSON object.')
                with lock:
                    if self.path == '/api/new':
                        options = {k:body[k] for k in ('players','target','starts','seed') if k in body}
                        # Retry automatic mysteries, but preserve explicit overrides.
                        for attempt in range(8):
                            try:
                                game = Mystery(embeddings, **options)
                                break
                            except ValueError:
                                if options.get('target') or options.get('starts') or options.get('seed') is not None or attempt==7:
                                    raise
                        token = secrets.token_urlsafe(24)
                        if len(sessions)>=100:
                            sessions.pop(next(iter(sessions)))
                        sessions[token] = game
                        return self.reply(dict(token=token,state=game.state()))
                    game = sessions.get(body.get('token'))
                    if game is None:
                        return self.reply(dict(error='Session expired. Start a new mystery.'), 410)
                    event = None
                    if self.path == '/api/submit':
                        event = game.submit(body.get('word',''))
                    elif self.path == '/api/select':
                        game.select(body.get('word'))
                    elif self.path == '/api/suspect':
                        game.suspect(body.get('action'),body.get('word',''))
                    elif self.path == '/api/debug':
                        return self.reply(game.debug())
                    elif self.path == '/api/state':
                        return self.reply(dict(state=game.state()))
                    else:
                        return self.reply(dict(error='Unknown endpoint.'),404)
                    return self.reply(dict(state=game.state(),event=event))
            except (ValueError, TypeError, KeyError, OverflowError) as error:
                self.reply(dict(error=str(error)),400)

    return ThreadingHTTPServer(('127.0.0.1',port),Handler)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8001)
    args = parser.parse_args()
    server = make_server(args.port)
    print(f'COMMON GROUND → http://localhost:{args.port}', flush=True)
    server.serve_forever()
