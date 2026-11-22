#!/bin/sh
# Запуск бэкапов не от root: ssh отказывается работать с закрытым ключом, смонтированным
# из каталога владельца репозитория (чужой пользователь), — копируем ключ в домашний
# каталог контейнерного пользователя и выставляем ему права 600.
set -eu

mkdir -p "$HOME/.ssh"
cp /run/backup-ssh/id_ed25519 "$HOME/.ssh/id_ed25519"
chmod 600 "$HOME/.ssh/id_ed25519"
cp /run/backup-ssh/known_hosts "$HOME/.ssh/known_hosts"

if [ ! -w /backups ]; then
  echo "каталог /backups недоступен для записи пользователю backup (uid $(id -u)):" >&2
  echo "chown $(id -u):$(id -g) ./backups на хосте или удалите каталог — docker создаст его заново" >&2
  exit 1
fi

exec /bin/sh /usr/local/bin/backup.sh
