# Architecture

[← back to README](../README.md)

## Network

```
                 Internet
                    │
            Jio router 192.168.29.1 ── LAN 192.168.29.0/24 ── family devices (DNS → homelab)
                    │
        ┌───────────┴───────────────────────────────────────────────────────────┐
        │ homelab  192.168.29.69 (DHCP reservation)                              │
        │ Tailscale (own tailnet): homelab / 100.112.130.103, exit node, TS SSH  │
        │                                                                        │
        │  Docker stacks (/opt/<name>)            Host services                  │
        │  immich, jellyfin, adguard, syncthing,   smbd (nas, backup)            │
        │  uptime-kuma, dockge, speedtest,         cups (Epson L4160, USB)       │
        │  pitwall ─┐                              homelab-board :8088           │
        │           └─ ts sidecar ── shared F1     homelab-status (tty1)         │
        │              tailnet 100.67.124.99       pitwall-ops.path              │
        │                                                                        │
        │  128 GB SSD: OS, Docker, /opt                                          │
        │  2 TB USB exFAT "Expansion" → /srv/media                               │
        │  1 TB internal ext4 "backup" → /srv/backup (restic)                    │
        └────────────────────────────────────────────────────────────────────────┘
```

- **Home LAN**: the router gives the server a fixed address (.69) and hands it out as DNS, so AdGuard filters the whole house.
- **My tailnet**: how I reach everything remotely. The server advertises itself as an exit node and accepts Tailscale SSH.
  Nothing is port-forwarded on the router.
- **The F1 tailnet**: Pitwall runs behind a Tailscale sidecar container that joins a *separate*, shared tailnet, so friends
  can reach Pitwall and nothing else. The sidecar gets no ports, SSH, exit node or routes, and is never bridged to my tailnet.

## Disks

| Disk | Filesystem / label | Mount | Purpose |
|---|---|---|---|
| 128 GB SSD | ext4 | `/`, `/boot/efi` | OS, Docker, `/opt` (all stacks) |
| 2 TB USB (Seagate Expansion) | exFAT, UUID `046C-06F0` | `/srv/media` | Media and everyone's photos |
| 1 TB internal (Seagate FireCuda) | ext4, label `backup` | `/srv/backup` | restic repository only (fitted 14 Nov 2026) |
| 500 GB (old backup drive) | | offline | Set aside for a future offline/off-site copy |

Both data disks are mounted by UUID with `nofail` (see [`etc/fstab`](../etc/fstab)), so the server still boots if one is missing.

**The USB drive sometimes drops off the bus.** Two things deal with that:
- `usbcore.autosuspend=-1` on the kernel command line, so it happens less often.
- root's `*/2` cron job [`remount-media`](../usr/local/bin/remount-media): when the drive reappears, it runs `fsck.exfat`, remounts it,
  and recreates the containers that use it (Immich, Jellyfin, Syncthing).

### `/srv/media` layout

| Folder | Contents | Local backup? |
|---|---|---|
| `02_Sync` | Syncthing folders | ✅ restic |
| `03_Critical` | Immich library (`immich/`), nightly setup archives (`homelab-config/`) | ✅ restic (Immich thumbnails/encoded video excluded) |
| `04_Jellyfin` | Jellyfin media (read-only in the container) | ❌ can be downloaded again |
| `05_Event_Photos` | Event photo dumps | ✅ restic |
| `06_Videos_Cloud` | Videos that already have a cloud copy | ❌ on purpose |
| `07_Videos_Local` | Videos that exist only here | ✅ restic |
| `08_Photos_Unsorted` | Photos waiting to be sorted | ✅ restic, short 7-day window |
| `99_Temp_Files` | Scratch | ❌ |

## Host tweaks

| File | What it does |
|---|---|
| [`etc/udev/rules.d/00-remove-nvidia.rules`](../etc/udev/rules.d/00-remove-nvidia.rules) | Removes the dead Nvidia GPU (and its audio and USB controllers) from the PCI bus at boot |
| [`etc/default/grub`](../etc/default/grub) | `modprobe.blacklist=nouveau consoleblank=60 usbcore.autosuspend=-1` |
| [`etc/systemd/logind.conf.d/homelab.conf`](../etc/systemd/logind.conf.d/homelab.conf) | Ignores the lid switch, so it runs lid-closed |
| [`etc/systemd/resolved.conf.d/adguard.conf`](../etc/systemd/resolved.conf.d/adguard.conf) | Disables the systemd-resolved stub so AdGuard can use port 53 |
| [`etc/systemd/system/MASKED`](../etc/systemd/system/MASKED) | Units masked on the host: sleep/suspend/hibernate, `ipp-usb`, `getty@tty1` |
