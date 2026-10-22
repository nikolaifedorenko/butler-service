#!/usr/bin/env bash
# Проверка восстановления бэкапа (раз в месяц, решение владельца В-12):
# расшифровать → поднять временный PostgreSQL → восстановить → показать, что данные на месте.
# Запускать там, где лежит ЗАКРЫТЫЙ ключ age (не на боевом сервере). Нужны docker и age.
#   deploy/restore_check.sh <копия .sql.gz.age> <закрытый ключ age>
set -euo pipefail

backup="${1:?укажите файл копии timetrack-….sql.gz.age}"
key="${2:?укажите файл закрытого ключа age}"
db="${RESTORE_DB:-timetrack}"
name="butler-restore-check-$$"

docker run -d --rm --name "$name" -e POSTGRES_PASSWORD=check postgres:16-alpine >/dev/null
trap 'docker stop "$name" >/dev/null' EXIT
until docker exec "$name" pg_isready -U postgres >/dev/null 2>&1; do sleep 1; done

# роли и базы из pg_dumpall пересоздаются; отдельные предупреждения (роль postgres уже есть) не страшны
age -d -i "$key" "$backup" | gunzip | docker exec -i "$name" psql -q -U postgres -d postgres >/dev/null 2>&1 || true

docker exec "$name" psql -U postgres -d "$db" -tA -c "
  select 'пользователей:  ' || count(*) from users;
  select 'сотрудников:    ' || count(*) from employees;
  select 'отметок:        ' || count(*) from punches;
  select 'ревизия схемы:  ' || version_num from alembic_version;"
echo "✓ копия $(basename "$backup") восстанавливается"
