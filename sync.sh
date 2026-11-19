#!/bin/bash
# Refresh this repo from the newest homelab setup archive (written nightly at 03:00 by backup-opt).
# Copies an allowlist of config files only, redacts secrets and private words, regenerates the
# *.example files, then shows what changed.
#
#   ./sync.sh                      # review mode: update the working tree, show the diff, commit nothing
#   ./sync.sh --commit             # also commit, as "Sync from homelab YYYY-MM-DD"
#   ./sync.sh --push               # commit and push (what the daily cron job runs)
#   ./sync.sh [--commit|--push] path/to/archive.tar.gz
#
# Private words: put "word=replacement" lines in .sync-redact (git-ignored, one per line, case-sensitive),
# e.g. "MyTown=<hometown>". They are replaced in every synced file, and the sync fails if one survives.
set -euo pipefail

COMMIT=0 PUSH=0 ARCHIVE=
for a in "$@"; do
  case $a in
    --commit) COMMIT=1 ;;
    --push)   COMMIT=1 PUSH=1 ;;
    -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
    -*) echo "unknown option: $a" >&2; exit 1 ;;
    *)  ARCHIVE=$a ;;
  esac
done

REPO=$(cd "$(dirname "$0")" && pwd)
MANAGED=(opt etc usr crontabs CLAUDE.md)      # everything this script writes; nothing else is committed
REDACT_FILE=$REPO/.sync-redact
ARCHIVE_DIR=/srv/media/03_Critical/homelab-config
ARCHIVE=${ARCHIVE:-$(ls -t "$ARCHIVE_DIR"/homelab-*.tar.gz 2>/dev/null | head -n1)}
[ -f "$ARCHIVE" ] || { echo "no archive found (looked in $ARCHIVE_DIR)" >&2; exit 1; }
ARCHIVE_DAY=$(date -r "$ARCHIVE" +%F)
echo "== $(date '+%F %T') sync from $ARCHIVE ($(date -r "$ARCHIVE" '+%F %T'))"
if [ $(( $(date +%s) - $(date -r "$ARCHIVE" +%s) )) -gt 172800 ]; then
  echo "!! Newest archive is more than 2 days old: is backup-opt still running?" >&2
fi

cd "$REPO"
exec 9>"$REPO/.git/sync.lock"
flock -n 9 || { echo "another sync is running" >&2; exit 1; }
if [ "$COMMIT" = 1 ] && ! git diff --cached --quiet; then
  echo "!! Something is already staged in $REPO; not committing on top of it." >&2
  exit 3
fi

TMP=$(mktemp -d)
chmod 700 "$TMP"
trap 'rm -rf "$TMP"' EXIT

# Extract only what we need. .env and secrets.json are pulled into the private temp dir solely to
# read their key names; their values never reach the repo.
tar -xzf "$ARCHIVE" -C "$TMP" --wildcards --no-wildcards-match-slash --warning=no-unknown-keyword \
  'opt/*/compose.yml' 'opt/*/compose.override.yml' 'opt/*/docker-compose.yml' \
  'opt/*/.env' \
  'opt/pitwall/ops.sh' 'opt/pitwall/ops/*' \
  'opt/homelab-board/board.py' 'opt/homelab-board/board-*.html' 'opt/homelab-board/theme' \
  'opt/homelab-board/secrets.json' \
  'usr/local/bin/*' \
  'etc/fstab' 'etc/samba/smb.conf' 'etc/default/grub' \
  'etc/systemd/system/*' 'etc/systemd/logind.conf.d/*' 'etc/systemd/resolved.conf.d/*' \
  'etc/udev/rules.d/*' \
  'etc/cups/cupsd.conf' 'etc/cups/printers.conf' 'etc/cups/ppd/*' \
  'var/spool/cron/crontabs/*' 2>/dev/null || true
S=$TMP
[ -d "$S/opt" ] && [ -d "$S/etc" ] || { echo "archive looks empty or unreadable; leaving the repo alone" >&2; exit 1; }

# Rebuild the managed trees from scratch so files removed on the server disappear here too.
rm -rf "$REPO/opt" "$REPO/etc" "$REPO/usr" "$REPO/crontabs"

put() {  # put <path relative to archive root> [dest relative to repo]
  local src="$S/$1" dst="$REPO/${2:-$1}"
  [ -f "$src" ] && [ ! -L "$src" ] || return 0
  mkdir -p "$(dirname "$dst")"
  cp -p "$src" "$dst"
}

# --- /opt: compose files, Pitwall ops, tablet board -----------------------------------------
for f in "$S"/opt/*/compose.yml "$S"/opt/*/compose.override.yml "$S"/opt/*/docker-compose.yml; do
  [ -e "$f" ] && put "${f#"$S"/}"
done
put opt/pitwall/ops.sh
for f in "$S"/opt/pitwall/ops/*; do [ -e "$f" ] && put "${f#"$S"/}"; done
put opt/homelab-board/board.py
put opt/homelab-board/theme
for f in "$S"/opt/homelab-board/board-*.html; do [ -e "$f" ] && put "${f#"$S"/}"; done

# .env -> .env.example: keep only the comments and key names. Values from the known-harmless
# list below are kept; everything else becomes a placeholder, including keys added later.
KEEP_VALUES='^(UPLOAD_LOCATION|DB_DATA_LOCATION|TZ|IMMICH_VERSION|DB_USERNAME|DB_DATABASE_NAME|RENDER_GID)$'
for f in "$S"/opt/*/.env; do
  [ -e "$f" ] || continue
  out="$REPO/${f#"$S"/}.example"
  mkdir -p "$(dirname "$out")"
  while IFS= read -r line || [ -n "$line" ]; do
    if [[ $line =~ ^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)= ]]; then
      k=${BASH_REMATCH[1]}
      if [[ $k =~ $KEEP_VALUES ]]; then printf '%s\n' "$line"; else printf '%s=<change-me>\n' "$k"; fi
    else
      printf '%s\n' "$line"
    fi
  done < "$f" > "$out"
done

# secrets.json -> secrets.example.json: same keys, empty values.
if [ -f "$S/opt/homelab-board/secrets.json" ]; then
  python3 -I -c 'import json,sys; d=json.load(open(sys.argv[1])); json.dump({k:"" for k in d}, open(sys.argv[2],"w"), indent=2); open(sys.argv[2],"a").write("\n")' \
    "$S/opt/homelab-board/secrets.json" "$REPO/opt/homelab-board/secrets.example.json"
fi

# --- host scripts and system config ------------------------------------------------------
for f in "$S"/usr/local/bin/*; do [ -e "$f" ] && put "${f#"$S"/}"; done
for p in etc/fstab etc/samba/smb.conf etc/default/grub etc/cups/cupsd.conf etc/cups/printers.conf; do put "$p"; done
[ -f "$REPO/etc/cups/printers.conf" ] &&   # the printer's USB serial number: not needed, CUPS re-detects it
  sed -i -E 's/([?&]serial=)[^&[:space:]]+/\1<printer-serial>/' "$REPO/etc/cups/printers.conf"
for f in "$S"/etc/cups/ppd/*.ppd; do [ -e "$f" ] && put "${f#"$S"/}"; done
for f in "$S"/etc/systemd/logind.conf.d/* "$S"/etc/systemd/resolved.conf.d/*; do [ -e "$f" ] && put "${f#"$S"/}"; done
for f in "$S"/etc/udev/rules.d/*; do
  [ -e "$f" ] || continue
  case $(basename "$f") in 70-snap.*) continue ;; esac   # generated by snapd
  put "${f#"$S"/}"
done

# systemd: our own units (plain files, not snap-generated) and drop-ins (*.d/*.conf).
for f in "$S"/etc/systemd/system/*; do
  b=$(basename "$f")
  [ -f "$f" ] && [ ! -L "$f" ] || continue
  case $b in snap-*|snap.*) continue ;; esac
  put "${f#"$S"/}"
done
for f in "$S"/etc/systemd/system/*.d/*.conf; do [ -e "$f" ] && put "${f#"$S"/}"; done
# Masked units are symlinks to /dev/null; record them as a list instead.
masked=$(find "$S/etc/systemd/system" -maxdepth 1 -type l -lname /dev/null -printf '%f\n' | sort)
if [ -n "$masked" ]; then
  { echo "# Units masked on the homelab (symlinked to /dev/null). Re-create with: sudo systemctl mask <unit>"
    echo "$masked"; } > "$REPO/etc/systemd/system/MASKED"
fi

# --- crontabs: every URL becomes a placeholder (hides the healthchecks ping UUID) ------------
for f in "$S"/var/spool/cron/crontabs/*; do
  [ -e "$f" ] || continue
  mkdir -p "$REPO/crontabs"
  sed -E 's#https?://[^[:space:]"'\'']+#<HEALTHCHECKS_PING_URL>#g' "$f" > "$REPO/crontabs/$(basename "$f")"
done

# --- CLAUDE.md from the admin workspace, if present ---------------------------------------
[ -f "$HOME/work/homelab-admin/CLAUDE.md" ] && cp "$HOME/work/homelab-admin/CLAUDE.md" "$REPO/CLAUDE.md"

# --- private words from .sync-redact ------------------------------------------------------
if [ -f "$REDACT_FILE" ]; then
  python3 -I - "$REDACT_FILE" "${MANAGED[@]}" <<'PY'
import os, re, sys
pairs = []
for line in open(sys.argv[1], encoding="utf-8"):
    line = line.rstrip("\r\n")
    if line.strip() and not line.lstrip().startswith("#") and "=" in line:
        old, new = line.split("=", 1)
        if old:
            pairs.append((old, new))
pairs.sort(key=lambda p: -len(p[0]))          # longest first, so "Foo Bar" wins over "Foo"
# Whole words only, so a short entry like "Ann" doesn't also rewrite "Anne".
pairs = [(re.compile(r"(?<![A-Za-z0-9])" + re.escape(old) + r"(?![A-Za-z0-9])"), new) for old, new in pairs]

def walk(paths):
    for p in paths:
        if os.path.isfile(p):
            yield p
        for root, _, names in os.walk(p):
            for n in names:
                yield os.path.join(root, n)

for f in walk(sys.argv[2:]):
    try:
        with open(f, encoding="utf-8", newline="") as h:
            text = h.read()
    except (UnicodeDecodeError, OSError):
        continue                                 # binary or unreadable: skipped
    new = text
    for pat, rep in pairs:
        new = pat.sub(lambda m: rep, new)
    if new != text:
        with open(f, "w", encoding="utf-8", newline="") as h:
            h.write(new)
PY
fi

# --- safety net: refuse to leave real secret values or private words in the working tree ------
if grep -rnIE --exclude-dir=.git --exclude=sync.sh \
     'tskey-[a-z]+-[A-Za-z0-9]|hc-ping\.com/[0-9a-f-]{8}|BEGIN [A-Z ]*PRIVATE KEY|"[a-z_]*(key|pass)"[[:space:]]*:[[:space:]]*"[^"]' . ; then
  echo "!! Possible secret values above. Fix before committing." >&2
  exit 2
fi
if find . -path ./.git -prune -o \( -name .env -o -name secrets.json -o -name ts-state -o -name '*.pem' -o -name '*.key' \) -print | grep -q .; then
  echo "!! A forbidden file is present in the tree." >&2
  exit 2
fi
if [ -f "$REDACT_FILE" ]; then
  words=$(grep -vE '^[[:space:]]*(#|$)' "$REDACT_FILE" | cut -d= -f1 | grep . || true)
  if [ -n "$words" ] && grep -rnIiwF --exclude-dir=.git --exclude=.sync-redact -f <(printf '%s\n' "$words") . ; then
    echo "!! A word listed in .sync-redact is still in the tree (see above). Fix before committing." >&2
    exit 2
  fi
fi

# --- show / commit the result --------------------------------------------------------------
if [ "$COMMIT" = 0 ]; then
  git add -N -- "${MANAGED[@]}" >/dev/null 2>&1 || true   # intent-to-add: new files show in the diff, nothing staged
  git status --short -- "${MANAGED[@]}"
  git --no-pager diff --stat -- "${MANAGED[@]}"
  echo
  echo "Review with 'git diff'. Nothing has been committed or pushed."
  exit 0
fi

git add -A -- "${MANAGED[@]}"
if git diff --cached --quiet; then
  echo "No changes since the last sync."
else
  git --no-pager diff --cached --stat
  if ! git commit -q -m "Sync from homelab $ARCHIVE_DAY" -m "Source: $(basename "$ARCHIVE"). Generated by sync.sh."; then
    git reset -q   # unstage, so the next run isn't blocked by the "already staged" check
    echo "!! git commit failed (see above); nothing committed." >&2
    exit 1
  fi
  echo "Committed: $(git log -1 --format='%h %s')"
fi
if [ "$PUSH" = 1 ]; then
  git push -q origin HEAD   # also retries an earlier commit whose push failed
  echo "Pushed."
fi
