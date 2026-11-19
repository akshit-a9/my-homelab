# Rebuilding the server from scratch

[← back to README](../README.md)

Review every file before copying it into place. Paths in this repo match their paths on the server.

1. **OS and packages.** Install Ubuntu Server 26.04 LTS on the SSD, with user `akshit`. Then install Docker CE (or `docker.io`) with the compose
   plugin, plus `tailscale samba cups printer-driver-escpr restic exfatprogs smartmontools lm-sensors tmux git`.
2. **Host config:**
   - `etc/udev/rules.d/*`, `etc/systemd/logind.conf.d/*`, `etc/systemd/resolved.conf.d/*` → the same paths.
   - `etc/default/grub` → `/etc/default/grub`, then `sudo update-grub`.
   - Mask the units listed in `etc/systemd/system/MASKED` (`sudo systemctl mask …`) and run `sudo systemctl disable --now cups-browsed`.
   - Add the two data-disk lines from `etc/fstab` (check the UUIDs with `blkid`), then `sudo mkdir -p /srv/media /srv/backup && sudo mount -a`.
3. **Network.** Run `sudo tailscale up --ssh --advertise-exit-node` and approve it in the admin console. Give the server a DHCP reservation
   on the router (.69), and set it as the LAN's DNS server once AdGuard is up.
4. **Scripts and units.** Copy `usr/local/bin/*` → `/usr/local/bin/` (mode 755) and `etc/systemd/system/*.service|*.path` →
   `/etc/systemd/system/`. Then run `sudo systemctl daemon-reload && sudo systemctl enable --now homelab-board homelab-status pitwall-ops.path`.
5. **Samba and CUPS.** Copy `etc/samba/smb.conf` into place, then `sudo smbpasswd -a akshit`. Copy `etc/cups/cupsd.conf`, `printers.conf` and `ppd/`
   into place, put the printer's real serial number back in `printers.conf` (or re-add the queue in the CUPS UI), then restart cups.
6. **Stacks.** Copy each `opt/<name>` to `/opt/<name>`. Create `.env` from `.env.example` (and `secrets.json` from
   `secrets.example.json`) with real values, then run `docker compose up -d` in each.
   - Pitwall: clone its source into `/opt/pitwall/src` and use a fresh auth key from the F1 tailnet.
   - Dashboard: download the B612 fonts into `/opt/homelab-board/fonts/`.
   - App data (AdGuard, Syncthing, Uptime Kuma, Jellyfin, Immich DB) comes back from the setup archives in
     `03_Critical/homelab-config/`, or from restic.
7. **Crontabs.** Install `crontabs/akshit` with `crontab -e`, putting the real healthchecks URL back in, and `crontabs/root` with `sudo crontab -e`.
8. **Backups.** Put the restic password in `~/.restic-pass` (mode 600) and check it with `restic snapshots`.
9. **This repo.** Clone it to `~/work/my-homelab`, run `gh auth login` and `gh auth setup-git` so the nightly sync can push, and create
   `.sync-redact` (see [sync.md](sync.md)).

Any host name in this repo that shows as `HOME` or `<hometown>` was masked by `sync.sh`. Put your own value back.
