import hmac, html, os, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOKEN = os.environ["OPS_TOKEN"]
REQ, LOG = "/trigger/request", "/trigger/last.log"

def page(msg=""):
    try:
        log = open(LOG).read()[-3000:]
    except OSError:
        log = "no runs yet"
    return f"""<!doctype html><meta name=viewport content="width=device-width">
<title>Pitwall ops</title><body style="font:16px system-ui;max-width:560px;margin:2rem auto;padding:0 1rem">
<h1>Pitwall ops</h1><p>{html.escape(msg)}</p>
<form method=post><input name=token type=password placeholder=token required>
<button formaction=/restart>Restart</button> <button formaction=/update>Pull + rebuild</button></form>
<h2>Last runs</h2><pre style="white-space:pre-wrap">{html.escape(log)}</pre>"""

class H(BaseHTTPRequestHandler):
    def send(self, code, body):
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode())

    def do_GET(self):
        self.send(200, page())

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        form = urllib.parse.parse_qs(self.rfile.read(n).decode())
        if not hmac.compare_digest(form.get("token", [""])[0], TOKEN):
            return self.send(403, page("Wrong token."))
        action = self.path.strip("/")
        if action not in ("restart", "update"):
            return self.send(404, page("Unknown action."))
        with open(REQ, "w") as f:
            f.write(action)
        self.send(200, page(f"Queued: {action}. Refresh in ~30 s to see the log."))

ThreadingHTTPServer(("0.0.0.0", 8099), H).serve_forever()
