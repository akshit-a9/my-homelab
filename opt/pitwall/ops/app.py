import hmac, html, os, re, time, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOKEN = os.environ["OPS_TOKEN"]
T = "/trigger"
REQ, HIST, RUNS = T + "/request", T + "/history.tsv", T + "/runs/"
BRANCHES, CURRENT = T + "/branches.txt", T + "/current.txt"
NAME_OK = re.compile(r"^[A-Za-z0-9._/-]{1,100}$")
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
LABEL = {"restart": "Restart", "update": "Pull + rebuild", "refresh": "Refresh branches", "switch": "Switch branch"}

def read(path, default=""):
    try:
        with open(path, errors="replace") as f:
            return f.read()
    except OSError:
        return default

def branches():
    return [b.strip() for b in read(BRANCHES).splitlines() if NAME_OK.match(b.strip())]

def tail_log(name, n=40):
    if not re.match(r"^[0-9-]+\.log$", name):
        return ""
    text = ANSI.sub("", read(RUNS + name)).replace("\r", "\n")
    lines = [l for l in text.splitlines() if l.strip()]
    return "\n".join(lines[-n:]) or "(no output)"

def dur(s):
    s = int(s)
    return "%dm %02ds" % (s // 60, s % 60) if s >= 60 else "%ds" % s

def history(limit=15):
    rows = []
    for line in reversed(read(HIST).splitlines()[-limit:]):
        p = line.split("\t")
        if len(p) != 7:
            continue
        start, action, arg, rc, secs, running, log = p
        what = LABEL.get(action, action)
        if action == "switch":
            what += " &rarr; <code>%s</code>" % html.escape(arg)
        elif arg == "after-race":
            what += " <small>(automatic, after a race)</small>"
        ok = rc == "0"
        rows.append(
            '<details><summary><span class=t>%s</span> %s <b class=%s>%s</b> <span class=d>%s</span></summary>'
            '<div class=run>Now running: <code>%s</code></div><pre>%s</pre></details>'
            % (time.strftime("%d %b %H:%M", time.gmtime(int(start) + 19800)), what,
               "ok" if ok else "bad", "&#10003; OK" if ok else "&#10007; Failed (exit %s)" % html.escape(rc),
               dur(secs), html.escape(running), html.escape(tail_log(log))))
    return "".join(rows) or "<p>No runs yet.</p>"

def page(msg=""):
    cur = read(CURRENT, "unknown (press Refresh branches)").strip()
    pending = read(REQ).strip()
    opts = "".join('<option%s>%s</option>' % (" selected" if cur.startswith(b + " ") else "", html.escape(b)) for b in branches())
    return f"""<!doctype html><meta name=viewport content="width=device-width">
<title>Pitwall ops</title>
<style>body{{font:16px system-ui;max-width:640px;margin:2rem auto;padding:0 1rem}}
details{{border-bottom:1px solid #ddd;padding:.5rem 0}}summary{{cursor:pointer}}
.t{{color:#666;font-variant-numeric:tabular-nums}}.d{{color:#666;font-size:.9em}}
.ok{{color:#1a7f37}}.bad{{color:#cf222e}}.run{{margin:.5rem 0;color:#444}}
pre{{background:#f6f8fa;padding:.6rem;overflow-x:auto;font-size:12px;white-space:pre-wrap}}
.msg{{background:#fff8c5;padding:.5rem}}</style>
<h1>Pitwall ops</h1>{'<p class=msg>' + html.escape(msg) + '</p>' if msg else ''}
<p><b>Running:</b> <code>{html.escape(cur)}</code></p>
{'<p class=msg>Waiting to run: ' + html.escape(pending) + ' (reload in a few seconds)</p>' if pending else ''}
<form method=post>
<input name=token type=password placeholder=token required><br><br>
<button formaction=/restart>Restart</button>
<button formaction=/update>Pull + rebuild</button>
<button formaction=/refresh>Refresh branches</button><br><br>
<select name=branch>{opts or "<option value=''>(no list yet: Refresh branches)</option>"}</select>
<button formaction=/switch>Switch to branch + rebuild</button>
</form>
<h2>Recent runs</h2><p class=d>Tap a run to see its output.</p>{history()}"""

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
        if action in ("restart", "update", "refresh"):
            req = action
        elif action == "switch":
            b = form.get("branch", [""])[0].strip()
            if b not in branches():
                return self.send(400, page("Pick a branch from the list (press Refresh branches first)."))
            req = "switch " + b
        else:
            return self.send(404, page("Unknown action."))
        with open(REQ, "w") as f:
            f.write(req)
        self.send(200, page("Queued: %s. Reload in ~30 s to see the result." % req))

ThreadingHTTPServer(("0.0.0.0", 8099), H).serve_forever()
