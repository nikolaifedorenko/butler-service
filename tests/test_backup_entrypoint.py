"""Проверки запуска backup-контейнера без базы и подключения по SSH."""
from __future__ import annotations

import os
import re
import stat
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

ENTRYPOINT = Path(__file__).resolve().parents[1] / "deploy" / "backup-entrypoint.sh"
BACKUP_UID = os.getuid() or 65534
KEY_CONTENT = "test private key\n"
KNOWN_HOSTS_CONTENT = "backup.example.test ssh-ed25519 test-public-key\n"


@pytest.fixture
def container_root():
    # Отдельный каталог доступен тестовому UID, даже если pytest запущен от root.
    with TemporaryDirectory() as directory:
        root = Path(directory)
        root.chmod(0o755)
        for path in (root / "home", root / "backups"):
            path.mkdir(mode=0o700)
            if os.getuid() == 0:
                os.chown(path, BACKUP_UID, -1)

        # Подменяем только точки монтирования и бесконечный цикл бэкапов.
        script = ENTRYPOINT.read_text(encoding="utf-8")
        script = re.sub(r"(?<!\.)/backups\b", "./backups", script)
        script = script.replace("/run/backup-ssh", "./default-ssh")
        script = script.replace("/usr/local/bin/backup.sh", "./backup.sh")
        (root / "entrypoint.sh").write_text(script, encoding="utf-8")
        (root / "entrypoint.sh").chmod(0o644)
        (root / "backup.sh").write_text("printf 'backup started as uid %s\\n' \"$(id -u)\"\n", encoding="utf-8")
        (root / "backup.sh").chmod(0o644)
        yield root


def run_entrypoint(root: Path, *, remote: str | None = None, ssh_source: Path | None = None):
    env = {"HOME": str(root / "home"), "PATH": os.defpath}
    if remote is not None:
        env["BACKUP_REMOTE"] = remote
    if ssh_source is not None:
        env["BACKUP_SSH_SOURCE"] = str(ssh_source)
    identity = {"user": BACKUP_UID, "group": 65534, "extra_groups": []} if os.getuid() == 0 else {}
    return subprocess.run(["/bin/sh", "./entrypoint.sh"], cwd=root, env=env,
                          capture_output=True, text=True, timeout=10, umask=0o022, **identity)


def write_ssh_source(source: Path):
    source.mkdir()
    source.chmod(0o755)
    key = source / "id_ed25519"
    key.write_text(KEY_CONTENT, encoding="utf-8")
    key.chmod(0o644)
    known_hosts = source / "known_hosts"
    known_hosts.write_text(KNOWN_HOSTS_CONTENT, encoding="utf-8")
    known_hosts.chmod(0o644)


@pytest.mark.parametrize("remote", [None, ""], ids=["unset", "empty"])
def test_local_backup_starts_without_ssh_material(container_root, remote):
    result = run_entrypoint(container_root, remote=remote)

    assert result.returncode == 0, result.stderr
    assert result.stdout == f"backup started as uid {BACKUP_UID}\n"
    assert result.stderr == ""
    assert not (container_root / "home" / ".ssh").exists()


@pytest.mark.parametrize("use_default_source", [False, True], ids=["override", "default"])
def test_remote_backup_copies_ssh_material_privately(container_root, use_default_source):
    source = container_root / ("default-ssh" if use_default_source else "mounted credentials")
    write_ssh_source(source)
    result = run_entrypoint(container_root, remote="backup.example.test:/archive",
                            ssh_source=None if use_default_source else source)

    assert result.returncode == 0, result.stderr
    assert result.stdout == f"backup started as uid {BACKUP_UID}\n"
    assert result.stderr == ""
    ssh_dir = container_root / "home" / ".ssh"
    assert stat.S_IMODE(ssh_dir.stat().st_mode) == 0o700
    key = ssh_dir / "id_ed25519"
    assert key.read_text(encoding="utf-8") == KEY_CONTENT
    assert key.stat().st_uid == BACKUP_UID
    assert stat.S_IMODE(key.stat().st_mode) == 0o600
    known_hosts = ssh_dir / "known_hosts"
    assert known_hosts.read_text(encoding="utf-8") == KNOWN_HOSTS_CONTENT
    assert stat.S_IMODE(known_hosts.stat().st_mode) == 0o600


@pytest.mark.parametrize(("name", "missing"), [("id_ed25519", False), ("known_hosts", True)],
                         ids=["unreadable-key", "missing-known-hosts"])
def test_remote_backup_rejects_unavailable_ssh_material(container_root, name, missing):
    source = container_root / "default-ssh"
    write_ssh_source(source)
    unavailable = source / name
    if missing:
        unavailable.unlink()
    else:
        unavailable.chmod(0o000)
    result = run_entrypoint(container_root, remote="backup.example.test:/archive")

    assert result.returncode == 1, result.stderr
    assert result.stdout == ""
    assert f"./default-ssh/{name}" in result.stderr
    assert "недоступен для чтения" in result.stderr
    assert f"uid {BACKUP_UID}" in result.stderr
    assert "BACKUP_SSH_SOURCE" in result.stderr
    assert KEY_CONTENT.strip() not in result.stderr
    assert KNOWN_HOSTS_CONTENT.strip() not in result.stderr
    assert not (container_root / "home" / ".ssh").exists()


@pytest.mark.parametrize("mode", [0o500, 0o600], ids=["not-writable", "not-searchable"])
def test_local_backup_rejects_inaccessible_backup_directory(container_root, mode):
    (container_root / "backups").chmod(mode)
    result = run_entrypoint(container_root, remote="")

    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stdout == ""
    assert "каталог ./backups недоступен для записи" in result.stderr
    assert f"uid {BACKUP_UID}" in result.stderr
    assert f"chown {BACKUP_UID}:" in result.stderr
