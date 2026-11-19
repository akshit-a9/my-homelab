# Keeping this repo current

[← back to README](../README.md)

The server is the source of truth, and this repo is a cleaned-up copy of its config. Nobody edits the files under `opt/`,
`etc/`, `usr/`, `crontabs/` or `CLAUDE.md` here: `sync.sh` rebuilds them from scratch on every run. `README.md`, `docs/`
and `images/` are hand-written and never touched by the sync.

## The nightly job

On the server, in akshit's crontab:

```
15 4 * * * cd /home/akshit/work/my-homelab && git pull -q --ff-only && ./sync.sh --push >> /home/akshit/sync.log 2>&1
```

It runs at 04:15, after the 03:00 setup archive. It first pulls whatever I pushed from elsewhere (README edits, for example),
then syncs, commits as **`Sync from homelab YYYY-MM-DD`** (the date the archive was made), and pushes.
If nothing changed, it makes no commit. Pushing uses the `gh` credential helper (`gh auth setup-git`).

## What `sync.sh` does

1. Takes the newest `/srv/media/03_Critical/homelab-config/homelab-*.tar.gz` and warns if it's more than 2 days old.
2. Extracts an **allowlist** only: compose files, the dashboard, the Pitwall ops files, `/usr/local/bin`, and selected `/etc` files and crontabs.
3. Turns each `.env` into `.env.example`. Key names stay, and values become `<change-me>` unless the key is on a short
   list of harmless settings (`TZ`, `IMMICH_VERSION`, paths, and so on). New keys are hidden by default.
4. Turns `secrets.json` into `secrets.example.json` with the same keys and empty values.
5. Replaces every URL in the crontabs with `<HEALTHCHECKS_PING_URL>`, and masks the printer's USB serial number.
6. Records masked systemd units as a list (`etc/systemd/system/MASKED`), because they're symlinks.
7. Replaces private words listed in `.sync-redact` (see below).
8. **Safety net:** stops with an error, without committing, if it finds anything that looks like a Tailscale auth key, a healthchecks
   URL, a private key, a filled-in `"…key"`/`"…pass"` JSON value, a `.env`/`secrets.json`/`ts-state`/`*.pem`/`*.key`
   file, or a word from `.sync-redact`.
9. Stages only the managed paths, so a stray file in the clone never gets committed.

```bash
./sync.sh            # review mode: update the working tree and show the diff, without committing
./sync.sh --commit   # also commit
./sync.sh --push     # commit and push (the nightly job)
./sync.sh --push path/to/homelab-Mon.tar.gz   # use a specific archive
```

The log is `~/sync.log` on the server. A failed run leaves the repo uncommitted, and the next run starts clean.

## `.sync-redact`

This git-ignored file in the repo root lists words that must never be published, one `word=replacement` per line
(case-sensitive, `#` for comments):

```
MYTOWN=HOME
MyTown=<hometown>
```

They are matched as whole words and replaced in every synced file. The safety net then checks, ignoring case, that none of them is left anywhere in
the repo, including the hand-written docs.

## What is never in this repo

`.env` files, `secrets.json`, Tailscale `ts-state`, `~/.restic-pass`, the restic repository, keys and certificates
(including `/etc/cups/ssl`), the healthchecks ping URL, app data (AdGuard, Syncthing, Uptime Kuma, Dockge, Jellyfin,
Immich Postgres, Pitwall data, Speedtest config), the Pitwall source (it has its own repo), the dashboard fonts, and raw photos.
[`.gitignore`](../.gitignore) blocks these as a second layer of protection.

The photos in `images/` were re-encoded with all metadata (including GPS) removed, and identifying text was blurred.
