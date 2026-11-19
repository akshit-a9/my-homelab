# Homelab: what you're working on
Old Acer Predator Helios 300 (i5-8300H, 8 GB RAM, dead Nvidia GPU removed at boot) running
Ubuntu Server 26.04.1 LTS at Akshit's parents' home in <hometown>. Akshit is usually away (<city>).

## Network
- Home LAN 192.168.29.0/24 (Jio router 192.168.29.1). Homelab = 192.168.29.69 (DHCP reservation).
- Tailscale (Akshit's own tailnet): host `homelab`, 100.112.130.103, offers exit node, Tailscale SSH.
- Pitwall runs in a sidecar on a SEPARATE shared F1 tailnet (100.67.124.99). Never connect the two.

## Storage
- 128 GB SSD: OS, Docker, /opt (all stacks).
- 2 TB USB exFAT (label Expansion) at /srv/media: 02_Sync, 03_Critical, 04_Jellyfin,
  05_Event_Photos, 06_Videos_Cloud (already in the cloud), 07_Videos_Local (backed up nightly), 99_Temp_Files. Drive letters change between boots; use labels/UUIDs.
- 1 TB internal ext4 (Seagate FireCuda, label backup, UUID c6f0e7a7-…) at /srv/backup, fitted 14 Nov 2026.
  Holds a restic repository at /srv/backup/restic (password file ~/.restic-pass): versioned snapshots of
  02_Sync, 03_Critical (everyone's Immich photos; thumbs/encoded-video excluded), 05_Event_Photos, 07_Videos_Local.
  06_Videos_Cloud, 04_Jellyfin and 99_Temp_Files are deliberately NOT backed up locally.
- The old 500 GB backup drive is out of the laptop and kept offline (future enclosure / offline copy).

## Stacks (/opt/<name>, docker compose)
immich :2283 (IMMICH_VERSION=v3, UPLOAD_LOCATION=/srv/media/03_Critical/immich; ML switched off in settings until
  the RAM upgrade) | jellyfin :8096 (media at /srv/media/04_Jellyfin)
pitwall (ts sidecar + pitwall :8020 + ops :8099 + files :8030 + autoheal) | adguard (host network, DNS :53, UI :3080)
uptime-kuma :3001 | dockge :5001 | syncthing :8384 | speedtest :8765
Host services: smbd (shares nas, backup), homelab-status (tty1), pitwall-ops.path.
- cups: queue Epson-L4160 over USB with the escpr driver, shared; ipp-usb is MASKED (it grabbed the printer's USB
  and left jobs stuck), cups-browsed disabled (it created duplicate queues), cupsd.conf allows 100.64.0.0/10.
  Macs add it with: lpadmin -p Epson_L4160_homelab -E -v ipp://homelab:631/printers/Epson-L4160 -m everywhere (duplex works).
- homelab-board :8088 (/opt/homelab-board, Python): JSON feed at /api and the tablet dashboard. The design shown is
  named in /opt/homelab-board/theme (retro | a320 | md80 | classic = board-<name>.html); pages reload themselves when
  it changes. B612 fonts in fonts/. Optional secrets.json holds Immich/Jellyfin API keys and the AdGuard login.

## Scheduled jobs
- akshit crontab: 03:30 /usr/local/bin/local-backup (restic backup, then forget --keep-daily 14 --keep-weekly 8
  --keep-monthly 12; Sundays also prune + check --read-data-subset 5%; writes ~/last-backup.txt only on success,
  log in ~/backup.log); */5 healthchecks ping (only if both drives mounted).
- root crontab: */2 remount-media (recovers the 2 TB after USB drops); 03:00 backup-opt (archive of /opt + system config into 03_Critical/homelab-config).

## Rules
- Ask before anything destructive: deleting files under /srv, formatting, changing /etc/fstab, rebooting.
- Never delete from /srv/backup or 03_Critical without explicit confirmation. Never run restic forget/prune with a
  different policy, or remove snapshots, without asking. Read-only restic commands (snapshots, ls, check, diff) are fine.
- Never print, copy or commit ~/.restic-pass, /opt/homelab-board/secrets.json, .env files or ts-state.
- Read Immich release notes before updating Immich. Other stacks: pull + up -d is fine.
- Run long jobs (first backups, big copies, upgrades that restart Tailscale) inside tmux: SSH runs over Tailscale.
- Never add ports, SSH, exit node or routes to the Pitwall Tailscale sidecar.
- Don't loosen Samba `hosts allow` or expose anything to the public internet.
- Prefer read-only checks first; explain what you'll change before changing it.
