#!/usr/bin/env sh
set -eu

# Phase 002 backup sidecar stub; full restic + pg_dump schedule lands in Milestone M12 (Phase 013).
echo "djet-backup sidecar standby (repository: ${BACKUP_REPOSITORY:-/backups/restic-repo})"
trap 'exit 0' TERM INT
while true; do
  sleep 300 &
  wait $!
done
