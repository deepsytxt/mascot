"""Single instance and authenticated local commands on Linux and Windows."""
from __future__ import annotations

import hmac
import json
import os
from pathlib import Path
import secrets
import socket
import threading

from config import config_dir

MAX_MESSAGE = 8192


def runtime_dir():
    directory = config_dir() / "runtime"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    return directory


def _receive(connection):
    data = bytearray()
    while len(data) <= MAX_MESSAGE:
        chunk = connection.recv(min(1024, MAX_MESSAGE + 1 - len(data)))
        if not chunk:
            break
        data.extend(chunk)
        if b"\n" in data:
            break
    if len(data) > MAX_MESSAGE or b"\n" not in data:
        raise ValueError("invalid message size")
    return json.loads(data.split(b"\n", 1)[0])


def send(message, directory=None):
    try:
        endpoint = json.loads(((Path(directory) if directory else runtime_dir()) / "endpoint.json").read_text(encoding="utf-8"))
        payload = json.dumps({"token": endpoint["token"], "message": message}, ensure_ascii=False).encode("utf-8") + b"\n"
        if len(payload) > MAX_MESSAGE:
            return False
        with socket.create_connection(("127.0.0.1", int(endpoint["port"])), timeout=1) as connection:
            connection.sendall(payload)
            return _receive(connection).get("ok") is True
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False


class AlreadyRunning(RuntimeError):
    pass


class Server:
    def __init__(self, callback, directory=None):
        self.callback = callback
        self.directory = Path(directory) if directory else runtime_dir()
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.endpoint = self.directory / "endpoint.json"
        self.lock = None
        self.socket = None
        self.thread = None
        self.stopped = threading.Event()
        self.token = secrets.token_hex(32)

    def start(self):
        self.lock = (self.directory / "instance.lock").open("a+b")
        try:
            if os.name == "nt":
                import msvcrt
                self.lock.seek(0)
                if not self.lock.read(1):
                    self.lock.write(b"0")
                    self.lock.flush()
                self.lock.seek(0)
                msvcrt.locking(self.lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.lock.close()
            self.lock = None
            raise AlreadyRunning("deepsy уже запущен") from None
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.bind(("127.0.0.1", 0))
            self.socket.listen(4)
            self.socket.settimeout(.25)
            data = json.dumps({"port": self.socket.getsockname()[1], "token": self.token})
            temporary = self.endpoint.with_suffix(".tmp")
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(data)
            os.replace(temporary, self.endpoint)
            self.thread = threading.Thread(target=self._run, name="deepsy-ipc", daemon=True)
            self.thread.start()
            return self
        except Exception:
            self.stop()
            raise

    def _run(self):
        while not self.stopped.is_set():
            try:
                connection, _ = self.socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with connection:
                connection.settimeout(.5)
                try:
                    payload = _receive(connection)
                    token = payload.get("token", "")
                    message = payload.get("message")
                    valid = isinstance(token, str) and hmac.compare_digest(token, self.token) and isinstance(message, dict)
                    if valid and not message.get("ping"):
                        self.callback(message)
                    connection.sendall(json.dumps({"ok": valid}).encode() + b"\n")
                except (OSError, ValueError, AttributeError, TypeError):
                    pass

    def stop(self):
        self.stopped.set()
        if self.socket:
            self.socket.close()
        if self.thread:
            self.thread.join(timeout=1)
        if self.lock:
            try:
                self.endpoint.unlink(missing_ok=True)
            finally:
                self.lock.close()
                self.lock = None

    def __enter__(self):
        return self.start()

    def __exit__(self, *_):
        self.stop()
