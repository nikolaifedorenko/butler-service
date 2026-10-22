#!/bin/sh
# Ежесуточный бэкап базы (решение владельца В-12, аудит 21.10.2026):
#   pg_dumpall → gzip → age (открытый ключ: на сервере копию не расшифровать) → ./backups
#   → копия на второй сервер (rsync по SSH; уходят только зашифрованные файлы).
# Закрытый ключ хранится ВНЕ сервера; проверка восстановления — deploy/restore_check.sh.
set -eu
set -o pipefail

: "${BACKUP_AGE_RECIPIENT:?задайте BACKUP_AGE_RECIPIENT — открытый ключ age (age1…), см. deploy/README.md §4}"
BACKUP_INTERVAL="${BACKUP_INTERVAL:-86400}"
BACKUP_KEEP="${BACKUP_KEEP:-14}"
SSH_DIR=/run/backup-ssh

mkdir -p /backups
while true; do
  f="/backups/timetrack-$(date +%F-%H%M%S).sql.gz.age"
  if pg_dumpall --clean --if-exists | gzip | age -r "$BACKUP_AGE_RECIPIENT" > "$f.part"; then
    mv "$f.part" "$f"
    echo "backup ok: $f"
  else
    rm -f "$f.part"
    echo "backup FAILED" >&2
  fi
  ls -1t /backups/timetrack-*.age 2>/dev/null | tail -n +"$((BACKUP_KEEP + 1))" | xargs -r rm --

  if [ -n "${BACKUP_REMOTE:-}" ]; then
    # --delete: на втором сервере остаются те же BACKUP_KEEP последних копий
    if rsync -a --delete --include='timetrack-*.age' --exclude='*' \
        -e "ssh -i $SSH_DIR/id_ed25519 -o UserKnownHostsFile=$SSH_DIR/known_hosts -o StrictHostKeyChecking=yes -o BatchMode=yes" \
        /backups/ "$BACKUP_REMOTE"; then
      echo "copy ok: $BACKUP_REMOTE"
    else
      echo "copy FAILED: $BACKUP_REMOTE" >&2
    fi
  else
    echo "BACKUP_REMOTE не задан — копия только на этом сервере" >&2
  fi
  sleep "$BACKUP_INTERVAL"
done
