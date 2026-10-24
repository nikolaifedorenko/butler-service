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
log="$(mktemp)"

docker run -d --rm --name "$name" -e POSTGRES_PASSWORD=check postgres:16-alpine >/dev/null
trap 'docker stop "$name" >/dev/null; rm -f "$log"' EXIT
until docker exec "$name" pg_isready -U postgres >/dev/null 2>&1; do sleep 1; done

# Копия — pg_dumpall --clean --if-exists (deploy/backup.sh). Восстановление идёт под ролью
# postgres, поэтому две ошибки неизбежны: её нельзя удалить и она уже есть. Любая другая
# ошибка — провал: раньше `|| true` глотал всё, и частичное восстановление давало «✓»
# (рецензия аудита 22.10.2026). Сбой расшифровки или распаковки — тоже провал (pipefail).
expected='current user cannot be dropped|role "postgres" already exists'
if ! age -d -i "$key" "$backup" | gunzip \
     | docker exec -i "$name" psql -q -U postgres -d postgres >/dev/null 2>"$log"; then
  echo "✗ копию $(basename "$backup") не удалось расшифровать, распаковать или загрузить:"
  tail -20 "$log"
  exit 1
fi
unexpected="$(grep -E 'ERROR|FATAL' "$log" | grep -vE "$expected" || true)"
if [ -n "$unexpected" ]; then
  echo "✗ восстановление прошло с ошибками ($(printf '%s\n' "$unexpected" | wc -l | tr -d ' ')):"
  printf '%s\n' "$unexpected" | head -20
  exit 1
fi

# таблицы обязаны быть, пользователи и ревизия схемы — непустыми
counts="$(docker exec "$name" psql -U postgres -d "$db" -v ON_ERROR_STOP=1 -tA -F '|' -c "
  select (select count(*) from users), (select count(*) from employees),
         (select count(*) from punches), (select version_num from alembic_version limit 1);")"
IFS='|' read -r users employees punches revision <<<"$counts"
echo "пользователей:  ${users:-?}"
echo "сотрудников:    ${employees:-?}"
echo "отметок:        ${punches:-?}"
echo "ревизия схемы:  ${revision:-?}"
if [ "${users:-0}" -eq 0 ] || [ -z "${revision:-}" ]; then
  echo "✗ в восстановленной базе нет пользователей или ревизии схемы"
  exit 1
fi
echo "✓ копия $(basename "$backup") восстанавливается"
