"""deploy/restore_check.sh не выдаёт «✓» при частичном восстановлении (рецензия аудита 22.10.2026).

Раньше `psql … || true` глотал любые ошибки загрузки копии, а проверка смотрела лишь
количества в трёх таблицах. Скрипт гоняется с заглушками docker и age в PATH: настоящий
PostgreSQL и ключ не нужны, проверяется логика разбора.

Что проверяется:
  * только ожидаемые ошибки pg_dumpall --clean (роль postgres) — «✓», код 0;
  * любая другая ошибка восстановления — провал;
  * битая копия (не gzip) — провал;
  * пустая таблица пользователей — провал.
"""
from __future__ import annotations

import gzip
import os
import pathlib
import subprocess
import textwrap

import pytest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "deploy" / "restore_check.sh"

EXPECTED = ('ERROR:  current user cannot be dropped\n'
            'ERROR:  role "postgres" already exists\n')

FAKE_DOCKER = textwrap.dedent("""\
    #!/usr/bin/env bash
    # заглушка docker: run/stop — ничего; exec … psql -i — «восстановление», -c — счётчики
    case "$1" in
      run|stop) exit 0 ;;
    esac
    for a in "$@"; do
      [ "$a" = pg_isready ] && exit 0
      [ "$a" = -c ] && { printf '%s\\n' "$FAKE_COUNTS"; exit 0; }
    done
    cat >/dev/null
    printf '%b' "$FAKE_STDERR" >&2
    exit 0
""")

FAKE_AGE = '#!/usr/bin/env bash\n# заглушка age: -d -i <ключ> <файл> — «расшифровка» = cat\ncat "$4"\n'


@pytest.fixture
def run(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("docker", FAKE_DOCKER), ("age", FAKE_AGE)):
        f = bin_dir / name
        f.write_text(body)
        f.chmod(0o755)
    good = tmp_path / "timetrack.sql.gz.age"
    good.write_bytes(gzip.compress(b"select 1;\n"))
    key = tmp_path / "key.txt"
    key.write_text("AGE-SECRET-KEY-TEST")

    def _run(stderr: str = EXPECTED, counts: str = "3|35|1200|0009", backup=good):
        env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
               "FAKE_STDERR": stderr, "FAKE_COUNTS": counts}
        return subprocess.run(["bash", str(SCRIPT), str(backup), str(key)], env=env,
                              capture_output=True, text=True, timeout=30)
    return _run, tmp_path


def test_only_expected_errors_pass(run):
    r = run[0]()
    assert r.returncode == 0, r.stdout + r.stderr
    assert "✓" in r.stdout and "ревизия схемы:  0009" in r.stdout


def test_unexpected_restore_error_fails(run):
    r = run[0](stderr=EXPECTED + 'ERROR:  relation "punches" does not exist\n')
    assert r.returncode != 0 and "✓" not in r.stdout, r.stdout
    assert 'relation "punches"' in r.stdout


def test_corrupt_backup_fails(run):
    _run, tmp_path = run
    bad = tmp_path / "broken.sql.gz.age"
    bad.write_bytes(b"not a gzip stream")
    r = _run(backup=bad)
    assert r.returncode != 0 and "✓" not in r.stdout, r.stdout


def test_empty_users_fails(run):
    r = run[0](counts="0|0|0|0009")
    assert r.returncode != 0 and "✓" not in r.stdout, r.stdout
