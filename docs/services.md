# Services

[← back to README](../README.md)

## Ports

| Service | Config | Port | Notes |
|---|---|---|---|
| Immich | [`opt/immich`](../opt/immich) | 2283 | `IMMICH_VERSION=v3`, uploads in `/srv/media/03_Critical/immich`. Machine learning is switched off in settings until a RAM upgrade. **Read the release notes before updating.** |
| Jellyfin | [`opt/jellyfin`](../opt/jellyfin) | 8096 | Intel iGPU through `/dev/dri` (`RENDER_GID` in `.env`). Media mounted read-only. |
| AdGuard Home | [`opt/adguard`](../opt/adguard) | DNS 53, UI 3080 | Host network |
| Syncthing | [`opt/syncthing`](../opt/syncthing) | 8384 (UI), 22000 tcp/udp, 21027 udp | `/srv/media` mounted at `/media` |
| Uptime Kuma | [`opt/uptime-kuma`](../opt/uptime-kuma) | 3001 | |
| Dockge | [`opt/dockge`](../opt/dockge) | 5001 | Manages every stack under `/opt` |
| Speedtest Tracker | [`opt/speedtest`](../opt/speedtest) | 8765 | |
| Pitwall | [`opt/pitwall`](../opt/pitwall) | 8020 (app), 8099 (ops), 8030 (files) | Only on the F1 tailnet, through the `ts-pitwall` sidecar. `autoheal` restarts it when it's unhealthy. |
| Homelab board | [`opt/homelab-board`](../opt/homelab-board) | 8088 | Dashboard page plus JSON at `/api` |
| Samba | [`etc/samba/smb.conf`](../etc/samba/smb.conf) | 445 | Shares `nas` (read-write, `/srv/media`) and `backup` (read-only, `/srv/backup`). SMB3 only. `hosts allow` = localhost, Tailscale CGNAT, 192.168/16 |
| CUPS | [`etc/cups/`](../etc/cups) | 631 | Queue `Epson-L4160`, shared, allows 100.64.0.0/10 |
| Console status | `homelab-status.service` | tty1 | Status screen on the laptop's own display |

Updating: `docker compose pull && docker compose up -d` in the stack's folder, except Immich (read the release notes first).

## Dashboard (`homelab-board`)

[`board.py`](../opt/homelab-board/board.py) is a dependency-free Python server (systemd unit `homelab-board.service`). It samples CPU,
RAM, temperature, network and disks, checks each container's health with `docker inspect`, reads the Speedtest Tracker
database and the last-backup timestamp, and serves it all as JSON at `/api` together with the page.

- **Themes:** the name in [`opt/homelab-board/theme`](../opt/homelab-board/theme) picks `board-<name>.html`: `a320`
  (the Airbus-style one in the screenshots), `md80`, `retro` or `classic`. Open pages notice the change and reload.
- **Fonts:** B612 / B612 Mono (the font family designed for cockpit displays). They're not in this repo, so download them from Google Fonts into `fonts/`.
- **Extra counters** (Immich photos, Jellyfin items, AdGuard % blocked): copy
  [`secrets.example.json`](../opt/homelab-board/secrets.example.json) to `secrets.json` (mode 600) and fill it in.
- **Cautions and warnings:** each of these turns on MASTER CAUT with its own message: a container down, a drive not
  mounted or almost full, Tailscale offline, the printer stopped, a backup older than 25 h, or a high CPU temperature.
  When the page loses contact with the server, MASTER WARN flashes ("COMM HOMELAB LOST"). Tap a light to acknowledge it.

## Console status screen (tty1)

[`homelab-status`](../usr/local/bin/homelab-status) replaces the login prompt on the laptop's own screen. The screen stays
off. Pressing any key shows uptime, temperature, battery, Tailscale IP, disk usage, last backup and key containers for 60 s.
There's also a note asking whoever is at home to keep it plugged in.

## Pitwall ops

[`opt/pitwall/ops/app.py`](../opt/pitwall/ops/app.py) is a small page on :8099, protected by `OPS_TOKEN`, inside the sidecar's
network. Friends can trigger a restart or update without any access to the host:

1. The page writes `restart` or `update` to `/opt/pitwall/trigger/request`.
2. On the host, `pitwall-ops.path` watches that file and starts `pitwall-ops.service`.
3. That runs [`opt/pitwall/ops.sh`](../opt/pitwall/ops.sh), which restarts the container or does `git pull` and a rebuild.

The container never gets the Docker socket.

## Printer

The `Epson-L4160` queue runs over USB with the `printer-driver-escpr` driver and is shared. To keep it working:
- `ipp-usb` is **masked**: it grabbed the printer's USB interface and left jobs stuck.
- `cups-browsed` is **disabled**: it created duplicate queues.

To add it on a Mac (duplex works):
```
lpadmin -p Epson_L4160_homelab -E -v ipp://homelab:631/printers/Epson-L4160 -m everywhere
```

## Scheduled jobs

| Who | When | What |
|---|---|---|
| root | every 2 min | [`remount-media`](../usr/local/bin/remount-media): recover the 2 TB after a USB drop |
| root | 03:00 | [`backup-opt`](../usr/local/bin/backup-opt): archive `/opt` and system config to `03_Critical/homelab-config/homelab-<Day>.tar.gz` (rotates by weekday name, so 7 are kept) |
| akshit | 03:30 | [`local-backup`](../usr/local/bin/local-backup): restic snapshots, see [backups.md](backups.md) |
| akshit | 04:15 | `git pull` + [`sync.sh --push`](../sync.sh): refresh this repo, see [sync.md](sync.md) |
| akshit | every 5 min | healthchecks.io ping, only when both drives are mounted (URL redacted in this repo) |

The live crontabs are in [`crontabs/`](../crontabs).
