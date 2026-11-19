#!/usr/bin/env bash
set -uo pipefail
cd /opt/pitwall
REQ=trigger/request
[ -s "$REQ" ] || exit 0
ACTION=$(cat "$REQ"); : > "$REQ"
{
  echo "=== $(date '+%F %T') $ACTION"
  case "$ACTION" in
    restart) docker compose restart pitwall ;;
    update)  git -C src pull --ff-only && docker compose up -d --build pitwall ;;
  esac
  echo "exit $?"
} >> trigger/last.log 2>&1
