"""Production entry point: ``python -m rdi.server``.

Binds to 127.0.0.1 by default. Binding to another interface is refused unless
APP_ALLOW_REMOTE=true AND an APP_ACCESS_TOKEN is configured.

Graceful stop: ``stop.bat`` creates ``runtime/stop.request``; the server notices
it within ~2 seconds and shuts down cleanly (finishing in-flight requests).
"""
from __future__ import annotations

import ipaddress
import os
import sys
import threading

import uvicorn

from .config import settings


def _is_loopback(host: str) -> bool:
    if host in ("localhost",):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def main() -> int:
    if not _is_loopback(settings.host):
        if not settings.allow_remote or not settings.access_token:
            print(f"Refusing to bind to {settings.host}: set APP_ALLOW_REMOTE=true and a strong APP_ACCESS_TOKEN "
                  f"in .env to expose the application on the network.", file=sys.stderr)
            return 2
        if len(settings.access_token) < 16:
            print("APP_ACCESS_TOKEN must be at least 16 characters.", file=sys.stderr)
            return 2
    settings.ensure_dirs()
    pid_file = settings.runtime_dir / "backend.pid"
    stop_file = settings.runtime_dir / "stop.request"
    if stop_file.exists():
        stop_file.unlink()
    pid_file.write_text(f"{os.getpid()}\n{settings.port}\n", encoding="utf-8")
    try:
        from .main import create_app
        server = uvicorn.Server(uvicorn.Config(create_app(), host=settings.host, port=settings.port,
                                               log_level="warning", access_log=False, timeout_graceful_shutdown=10))
        done = threading.Event()

        def watch_stop() -> None:
            while not done.wait(2):
                if stop_file.exists():
                    print("Stop requested - shutting down gracefully.", flush=True)
                    server.should_exit = True
                    return

        threading.Thread(target=watch_stop, daemon=True, name="rdi-stop-watch").start()
        print(f"Road Disruption Intelligence running at http://{settings.host}:{settings.port}/ (Ctrl+C to stop)", flush=True)
        server.run()
        done.set()
    finally:
        for f in (pid_file, stop_file):
            try:
                if f == stop_file or f.read_text(encoding="utf-8").split()[0] == str(os.getpid()):
                    f.unlink(missing_ok=True)
            except (OSError, IndexError):
                pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
