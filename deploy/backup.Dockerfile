# Сервис бэкапов прод-профиля (docker-compose.prod.yml): pg_dumpall + шифрование age + rsync.
# Работает не от root (остаток аудита 25.10.2026, C2): в контейнер смонтирован закрытый
# ключ SSH второго сервера и через окружение приходит ключ age — root там не нужен.
FROM postgres:18-alpine
RUN apk add --no-cache age rsync openssh-client \
    && addgroup -S backup && adduser -S -G backup -h /home/backup backup
COPY --chmod=0755 deploy/backup.sh /usr/local/bin/backup.sh
COPY --chmod=0644 deploy/backup-entrypoint.sh /usr/local/bin/backup-entrypoint.sh
USER backup
ENTRYPOINT ["/bin/sh", "/usr/local/bin/backup-entrypoint.sh"]
