"""Убить процессы uvicorn-сервера приложения (не трогая сам скрипт)."""
import os
import signal

me = os.getpid()
killed = []
for pid in os.listdir("/proc"):
    if not pid.isdigit() or int(pid) == me:
        continue
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            argv = [a.decode("utf-8", "replace") for a in f.read().split(b"\0") if a]
    except OSError:
        continue
    if any("app.main:app" in a for a in argv) and argv and "python" in os.path.basename(argv[0]):
        try:
            os.kill(int(pid), signal.SIGKILL)
            killed.append((pid, " ".join(argv)[:100]))
        except OSError:
            pass
print("killed:", killed or "none")
