# Сервис бэкапов прод-профиля (docker-compose.prod.yml): pg_dumpall + шифрование age + rsync.
FROM postgres:18-alpine
RUN apk add --no-cache age rsync openssh-client
COPY deploy/backup.sh /usr/local/bin/backup.sh
ENTRYPOINT ["/bin/sh", "/usr/local/bin/backup.sh"]
