# Backups

[← back to README](../README.md)

Two layers, both on the server:

1. **03:00 setup archive**: [`backup-opt`](../usr/local/bin/backup-opt) (root) tars `/opt` (minus the Immich database
   files, Jellyfin cache and Pitwall data), system config and crontabs to
   `/srv/media/03_Critical/homelab-config/homelab-<Day>.tar.gz`. The name is the weekday, so it keeps a rolling week.
2. **03:30 restic**: [`local-backup`](../usr/local/bin/local-backup) (akshit) takes versioned snapshots of the 2 TB into a
   [restic](https://restic.net) repository on the internal 1 TB drive. Because the archives sit inside `03_Critical`,
   restic versions those too.

A healthchecks.io ping every 5 minutes (sent only when both drives are mounted) catches a dead server or a missing drive.

## What restic backs up

| Snapshot tag | Folders | Retention |
|---|---|---|
| `nightly` | `02_Sync`, `03_Critical`, `05_Event_Photos`, `07_Videos_Local` | 14 daily, 8 weekly, 12 monthly |
| `unsorted` | `08_Photos_Unsorted` | 7 daily, so a photo deleted while sorting is gone from the backup after a week |

Excluded: Immich `thumbs/` and `encoded-video/` (Immich can regenerate them), Syncthing `.stversions`, anything listed in
`~/.backup-exclude`, and the whole of `04_Jellyfin`, `06_Videos_Cloud` and `99_Temp_Files`.

On Sundays it also runs `restic prune` and `restic check --read-data-subset 5%`. Only when everything succeeds does it write
the time to `~/last-backup.txt`, which the dashboard reads. The log is `~/backup.log`.

The repository password is in `~/.restic-pass` on the server. **It is not in this repo.** Keep a copy in a password
manager too, because without it the repository can't be read.

**Gap:** there's no off-site or offline copy yet. A drive fire or theft at home would take both copies. The old 500 GB
drive is set aside for an offline copy.

## Restoring

```bash
export RESTIC_REPOSITORY=/srv/backup/restic RESTIC_PASSWORD_FILE=~/.restic-pass

restic snapshots                                   # list snapshots
restic ls latest /srv/media/02_Sync | less         # browse one
restic diff <old-id> <new-id>                      # what changed between two

# Restore one file or folder to a scratch location first, never straight over live data:
restic restore latest --target /srv/media/99_Temp_Files/restore \
  --include /srv/media/03_Critical/immich/library/<user>/2026/11

# Or mount the repository and browse it (needs fuse; run inside tmux):
mkdir -p /tmp/restic-mnt && restic mount /tmp/restic-mnt
```

Check the restored copy, then move it into place (`rsync -a --dry-run` first).

**Immich:** restart the stack after restoring files. Thumbnails and encoded videos weren't backed up, so regenerate them
from *Administration → Jobs*. A full library restore also needs a matching database: restore Immich's own DB dumps
(`03_Critical/immich/backups`) together with the files.

**From another machine:** plug in the 1 TB drive (ext4) and use the same `restic` commands with the password.
