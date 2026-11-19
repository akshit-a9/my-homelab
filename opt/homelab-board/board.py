#!/usr/bin/env python3
# Homelab status board: serves the design named in ./theme (board-<name>.html: a320, md80, retro, classic),
# and a JSON feed of live stats at /api on port 8088
import base64, calendar, glob, json, os, re, sqlite3, subprocess, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8088
IFACE = "enp6s0f1"
HERE = os.path.dirname(os.path.abspath(__file__))
DISKS = [("NAS", "2 TB EXPANSION", "/srv/media"), ("BACKUP", "1 TB HDD", "/srv/backup"), ("SYSTEM", "INTERNAL SSD", "/")]
SERVICES = [
    ("Pitwall", "pitwall-pitwall-1"),
    ("Immich", "immich_server"),
    ("Jellyfin", "jellyfin-jellyfin-1"),
    ("AdGuard", "adguard"),
    ("Uptime Kuma", "uptime-kuma"),
    ("Syncthing", "syncthing"),
    ("Speedtest", "speedtest"),
    ("Dockge", "dockge"),
]
PRINTER = "Epson-L4160"
BACKUP_FILE = "/home/akshit/last-backup.txt"
BACKUP_MAX_HOURS = 25
SPEEDTEST_DB = "/opt/speedtest/config/database.sqlite"
SECRETS = os.path.join(HERE, "secrets.json")   # optional: API keys for extra service data

live = {"cpu": 0.0, "rx": 0.0, "tx": 0.0}
extras = {}   # label -> short text, refreshed every 2 minutes

def read(path, default=""):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return default

# ---------- live sampling ----------
def cpu_times():
    v = [int(x) for x in read("/proc/stat").splitlines()[0].split()[1:]]
    return v[3] + v[4], sum(v)

def net_bytes():
    for line in read("/proc/net/dev").splitlines():
        name, _, rest = line.partition(":")
        if name.strip() == IFACE:
            d = rest.split()
            return int(d[0]), int(d[8])
    return 0, 0

def sampler():
    idle0, tot0 = cpu_times()
    rx0, tx0 = net_bytes()
    t0 = time.time()
    while True:
        time.sleep(2)
        idle1, tot1 = cpu_times()
        rx1, tx1 = net_bytes()
        t1 = time.time()
        dt, dtot = t1 - t0, tot1 - tot0
        live["cpu"] = 100.0 * (1 - (idle1 - idle0) / dtot) if dtot else 0.0
        live["rx"] = (rx1 - rx0) * 8 / dt
        live["tx"] = (tx1 - tx0) * 8 / dt
        idle0, tot0, rx0, tx0, t0 = idle1, tot1, rx1, tx1, t1

# ---------- system ----------
def temperature():
    for z in glob.glob("/sys/class/thermal/thermal_zone*"):
        if read(z + "/type") == "x86_pkg_temp":
            return int(read(z + "/temp", "0")) / 1000
    return None

def memory():
    info = {}
    for line in read("/proc/meminfo").splitlines():
        k, v = line.split(":", 1)
        info[k] = int(v.split()[0]) * 1024
    return info["MemTotal"] - info["MemAvailable"], info["MemTotal"]

def disks():
    out = []
    for label, sub, path in DISKS:
        if path != "/" and not os.path.ismount(path):
            out.append({"label": label, "sub": sub, "mounted": False})
            continue
        s = os.statvfs(path)
        total = s.f_blocks * s.f_frsize
        out.append({"label": label, "sub": sub, "mounted": True,
                    "used": total - s.f_bfree * s.f_frsize, "total": total})
    return out

def short_uptime(status):
    # "Up 3 hours (healthy)" -> "3H"
    m = re.match(r"Up (About an? |Less than a )?(\d+)?\s*(second|minute|hour|day|week|month)", status)
    if not m:
        return ""
    n = m.group(2) or "1"
    return n + {"second": "S", "minute": "M", "hour": "H", "day": "D", "week": "W", "month": "MO"}[m.group(3)]

def containers():
    try:
        r = subprocess.run(["docker", "ps", "-a", "--format", "{{.Names}}\t{{.State}}\t{{.Status}}"],
                           capture_output=True, text=True, timeout=10)
    except Exception:
        return {}
    res = {}
    for line in r.stdout.splitlines():
        name, state, status = line.split("\t")
        if "(unhealthy)" in status:
            health = "unhealthy"
        elif "health: starting" in status:
            health = "starting"
        else:
            health = "ok"
        res[name] = {"state": state, "health": health, "up": short_uptime(status)}
    return res

def tailscale():
    try:
        r = subprocess.run(["tailscale", "status", "--json"], capture_output=True, text=True, timeout=10)
        j = json.loads(r.stdout)
        ips = j.get("Self", {}).get("TailscaleIPs") or [""]
        return {"online": j.get("BackendState") == "Running", "ip": ips[0]}
    except Exception:
        return {"online": False, "ip": ""}

def battery():
    for b in glob.glob("/sys/class/power_supply/BAT*"):
        return {"pct": int(read(b + "/capacity", "0")), "status": read(b + "/status")}
    return None

def printer():
    # Epson's USB vendor id is 04b8; it vanishes when the printer is switched off
    usb = any(read(d + "/idVendor") == "04b8" for d in glob.glob("/sys/bus/usb/devices/*"))
    try:
        out = subprocess.run(["lpstat", "-p", PRINTER], capture_output=True, text=True, timeout=5).stdout
        q = subprocess.run(["lpstat", "-o", PRINTER], capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return {"state": "unknown", "usb": usb, "jobs": 0}
    if "disabled" in out:
        state = "stopped"
    elif "now printing" in out:
        state = "printing"
    elif "idle" in out:
        state = "idle"
    else:
        state = "unknown"
    return {"state": state, "usb": usb, "jobs": len([l for l in q.splitlines() if l.strip()])}

def backup():
    text = read(BACKUP_FILE, "")
    ts = None
    try:
        ts = time.mktime(time.strptime(text, "%Y-%m-%d %H:%M:%S"))
    except ValueError:
        try:
            ts = os.path.getmtime(BACKUP_FILE)
        except OSError:
            pass
    if ts is None:
        return {"text": "never", "age_h": None, "ok": False}
    age = (time.time() - ts) / 3600
    return {"text": text, "age_h": age, "ok": age <= BACKUP_MAX_HOURS}

# ---------- slow extras (every 2 minutes) ----------
def speedtest():
    try:
        db = sqlite3.connect("file:%s?mode=ro" % SPEEDTEST_DB, uri=True, timeout=3)
        row = db.execute("SELECT ping, download, upload, created_at FROM results "
                         "WHERE status = 'completed' ORDER BY id DESC LIMIT 1").fetchone()
        db.close()
    except Exception:
        return None
    if not row or row[1] is None:
        return None
    ping, down, up, created = row
    try:   # Speedtest Tracker stores UTC
        age = (time.time() - calendar.timegm(time.strptime(created[:19], "%Y-%m-%d %H:%M:%S"))) / 3600
    except Exception:
        age = None
    # download/upload are stored in bytes per second
    return {"down": down * 8 / 1e6, "up": (up or 0) * 8 / 1e6, "ping": ping, "age_h": age}

def get_json(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read().decode())

def refresh_extras():
    while True:
        new = {}
        st = speedtest()
        if st:
            new["Speedtest"] = "%.0f&darr; %.0f&uarr; MBPS" % (st["down"], st["up"])
            new["_speedtest"] = st
        try:
            sec = json.loads(read(SECRETS, "{}"))
        except ValueError:
            sec = {}
        if sec.get("immich_api_key"):
            try:
                j = get_json("http://127.0.0.1:2283/api/server/statistics", {"x-api-key": sec["immich_api_key"]})
                new["Immich"] = "{:,} PHOTOS".format(j.get("photos", 0))
            except Exception:
                pass
        if sec.get("adguard_user"):
            try:
                auth = base64.b64encode(("%s:%s" % (sec["adguard_user"], sec.get("adguard_pass", ""))).encode()).decode()
                j = get_json("http://127.0.0.1:3080/control/stats", {"Authorization": "Basic " + auth})
                q = j.get("num_dns_queries") or 0
                b = j.get("num_blocked_filtering") or 0
                new["AdGuard"] = "%d%% BLOCKED" % (100 * b / q) if q else "0 QUERIES"
            except Exception:
                pass
        if sec.get("jellyfin_api_key"):
            try:
                j = get_json("http://127.0.0.1:8096/Items/Counts", {"Authorization": "MediaBrowser Token=\"%s\"" % sec["jellyfin_api_key"]})
                new["Jellyfin"] = "%d FILMS &middot; %d SHOWS" % (j.get("MovieCount", 0), j.get("SeriesCount", 0))
            except Exception:
                pass
        extras.clear()
        extras.update(new)
        time.sleep(120)

# ---------- snapshot ----------
def snapshot():
    ctr = containers()
    used, total = memory()
    services, cautions, advisories = [], [], []
    for label, name in SERVICES:
        c = ctr.get(name)
        if c is None or c["state"] != "running" or c["health"] == "unhealthy":
            st = "down"
            cautions.append(label.upper() + " FAIL")
        elif c["health"] == "starting":
            st = "starting"
        else:
            st = "up"
        services.append({"label": label, "status": st, "up": c["up"] if c else "",
                         "info": extras.get(label, "")})
    dk = disks()
    for d in dk:
        if not d["mounted"]:
            cautions.append(d["label"] + " DRIVE NOT MOUNTED")
        elif 100.0 * d["used"] / d["total"] >= 90:
            cautions.append(d["label"] + " DRIVE ALMOST FULL")
    ts = tailscale()
    if not ts["online"]:
        cautions.append("TAILSCALE OFFLINE")
    pr = printer()
    if pr["state"] == "stopped":
        cautions.append("PRINTER STOPPED")
    bk = backup()
    if not bk["ok"]:
        cautions.append("BACKUP OVERDUE")
    tp = temperature()
    if tp is not None and tp >= 85:
        cautions.append("CPU TEMP HIGH")
    bat = battery()
    if bat and bat["status"] == "Discharging":
        advisories.append("ON BATTERY %d%%" % bat["pct"])
    return {
        "time": time.time(),
        "uptime": float(read("/proc/uptime", "0 0").split()[0]),
        "cpu": live["cpu"], "temp": tp, "load": os.getloadavg()[0],
        "mem_used": used, "mem_total": total, "disks": dk,
        "rx": live["rx"], "tx": live["tx"],
        "tailscale": ts, "battery": bat, "printer": pr,
        "backup": bk, "last_backup": bk["text"] or "never",
        "speedtest": extras.get("_speedtest"),
        "containers_running": sum(1 for c in ctr.values() if c["state"] == "running"),
        "containers_total": len(ctr),
        "services": services,
        "cautions": cautions, "advisories": advisories,
        "issues": cautions,   # used by the classic page
        "theme": theme(),     # pages reload themselves when this changes
    }

THEME_FILE = os.path.join(HERE, "theme")

def theme():
    name = read(THEME_FILE, "retro")
    if re.match(r"^[a-z0-9-]+$", name) and os.path.exists(os.path.join(HERE, "board-%s.html" % name)):
        return name
    return "retro"

def page_file():
    name = theme()
    return "board-%s.html" % name if os.path.exists(os.path.join(HERE, "board-%s.html" % name)) else "board.html"

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, body, ctype):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/api"):
            self.send(json.dumps(snapshot()).encode(), "application/json")
            return
        if self.path.startswith("/fonts/"):
            fn = os.path.basename(self.path.split("?")[0])
            fp = os.path.join(HERE, "fonts", fn)
            if re.match(r"^[A-Za-z0-9_.-]+\.(ttf|otf|woff2?)$", fn) and os.path.exists(fp):
                with open(fp, "rb") as f:
                    self.send_response(200)
                    self.send_header("Content-Type", "font/" + fn.rsplit(".", 1)[1])
                    self.send_header("Cache-Control", "max-age=31536000")
                    self.end_headers()
                    self.wfile.write(f.read())
            else:
                self.send_error(404)
            return
        # The design shown is whatever the "theme" file names (a320, md80, retro, classic).
        # Switch with:  echo md80 > /opt/homelab-board/theme   (the tablet reloads by itself)
        with open(os.path.join(HERE, page_file()), "rb") as f:
            self.send(f.read(), "text/html; charset=utf-8")

threading.Thread(target=sampler, daemon=True).start()
threading.Thread(target=refresh_extras, daemon=True).start()
ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
