#!/usr/bin/env bash
# Runs on the host when the ops page writes a request (pitwall-ops.path watches trigger/request)
set -uo pipefail
cd /opt/pitwall
REQ=trigger/request
[ -s "$REQ" ] || exit 0
read -r ACTION ARG < "$REQ"; : > "$REQ"
mkdir -p trigger/runs

list_branches() {
  git -C src for-each-ref --format='%(refname:lstrip=3)' refs/remotes/origin | grep -vx HEAD > trigger/branches.txt
  echo "$(git -C src rev-parse --abbrev-ref HEAD) @ $(git -C src log -1 --format='%h %s')" > trigger/current.txt
}

run_action() {
  case "$ACTION" in
    restart) docker compose restart pitwall ;;
    update)  git -C src fetch --prune origin && git -C src pull --ff-only && docker compose up -d --build pitwall ;;
    refresh) git -C src fetch --prune origin && echo "branches refreshed" ;;
    switch)
      # only names that exist on GitHub, and only safe characters
      if [[ "${ARG:-}" =~ ^[A-Za-z0-9._/-]+$ ]] && git -C src fetch --prune origin \
         && git -C src show-ref --verify --quiet "refs/remotes/origin/$ARG"; then
        git -C src checkout -B "$ARG" "origin/$ARG" && docker compose up -d --build pitwall
      else
        echo "refused: '${ARG:-}' is not a branch on origin"; false
      fi ;;
    *) echo "unknown action"; false ;;
  esac
}

START=$(date +%s); RUN="$(date '+%Y%m%d-%H%M%S').log"
run_action > "trigger/runs/$RUN" 2>&1; RC=$?
list_branches
# one tab-separated line per run: start, action, arg, exit code, seconds, what's running now, full log file
printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$START" "$ACTION" "${ARG:-}" "$RC" "$(( $(date +%s) - START ))" \
  "$(cat trigger/current.txt)" "$RUN" >> trigger/history.tsv
# keep the last 200 entries and 50 full logs
tail -n 200 trigger/history.tsv > trigger/history.tmp && mv trigger/history.tmp trigger/history.tsv
ls -1t trigger/runs | tail -n +51 | sed 's#^#trigger/runs/#' | xargs -r rm -f
