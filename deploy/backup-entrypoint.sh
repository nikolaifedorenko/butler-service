#!/bin/sh
# Для удалённой копии ssh нужен закрытый ключ с правами 600 у пользователя backup.
set -eu

if [ ! -d /backups ] || [ ! -w /backups ] || [ ! -x /backups ]; then
  echo "каталог /backups недоступен для записи пользователю backup (uid $(id -u)):" >&2
  echo "chown $(id -u):$(id -g) ./backups на хосте или удалите каталог — docker создаст его заново" >&2
  exit 1
fi

if [ -n "${BACKUP_REMOTE:-}" ]; then
  ssh_source="${BACKUP_SSH_SOURCE:-/run/backup-ssh}"
  for name in id_ed25519 known_hosts; do
    source_file="$ssh_source/$name"
    if [ ! -f "$source_file" ] || [ ! -r "$source_file" ]; then
      printf 'BACKUP_REMOTE задан, но файл %s отсутствует или недоступен для чтения пользователю backup (uid %s).\n' \
        "$source_file" "$(id -u)" >&2
      echo 'Проверьте монтирование BACKUP_SSH_SOURCE и разрешите чтение файла этому UID.' >&2
      exit 1
    fi
  done

  # Ограничиваем права SSH-файлов, сохраняя прежний umask для backup.sh.
  (
    umask 077
    mkdir -p "$HOME/.ssh"
    chmod 700 "$HOME/.ssh"
    cp "$ssh_source/id_ed25519" "$ssh_source/known_hosts" "$HOME/.ssh/"
    chmod 600 "$HOME/.ssh/id_ed25519" "$HOME/.ssh/known_hosts"
  )
fi

exec /bin/sh /usr/local/bin/backup.sh
