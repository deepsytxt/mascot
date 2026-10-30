                      
                                                        
from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import math
import os
from pathlib import Path
import subprocess
import sys
import time

from config import load_config
from core import ACTIVITIES, EMOTIONS, Engine, EventProxy
from ipc import AlreadyRunning, Server, send

HERE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def load_assets():
    directory = HERE / "frames"
    meta = json.loads((directory / "animations.json").read_text(encoding="utf-8"))
    for name, clip in meta["clips"].items():
        if not clip["frames"] or len(clip["frames"]) != len(clip["durs"]) or any(d <= 0 for d in clip["durs"]):
            raise ValueError(f"Некорректный клип: {name}")
    files = [f for clip in meta["clips"].values() for f in clip["frames"]]
    files += [f["f"] for frames in meta.get("rot", {}).get("sets", {}).values() for f in frames]
    for filename in files:
        if Path(filename).name != filename or not (directory / filename).is_file():
            raise ValueError(f"Не найден кадр: {filename}")
    return directory, meta


def doctor(cfg):
    import watchers
    result = {
        "python": sys.version.split()[0], "platform": sys.platform,
        "session": os.environ.get("XDG_SESSION_TYPE", "windows" if os.name == "nt" else "unknown"),
        "backend": cfg["backend"],
        "dependencies": {name: importlib.util.find_spec(name) is not None for name in ("PySide6", "gi", "cairo", "psutil")},
        "watchers": watchers.capability_report(cfg),
    }
    try:
        _, meta = load_assets()
        result["assets"] = {"ok": True, "clips": len(meta["clips"])}
    except (OSError, ValueError, KeyError) as error:
        result["assets"] = {"ok": False, "error": str(error)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["assets"]["ok"] else 1


def client(words):
    command = words[0]
    if command == "run":
        if len(words) < 2:
            raise ValueError("Использование: python mascot.py run <команда> [аргументы]")
        started = time.monotonic()
        code = subprocess.call(words[1:])
        elapsed = time.monotonic() - started
        send({"emotion": "joy" if code == 0 else "sad", "text": f"Готово · {elapsed:.0f} с" if code == 0 else f"Код завершения: {code}"})
        return code
    if command == "say":
        words = words[1:]
        command = words[0] if words else "calm"
    if command in EMOTIONS:
        payload = {"emotion": command, "text": " ".join(words[1:]) or None}
    elif command in ACTIVITIES:
        payload = {"activity": command}
    elif command == "chess":
        action = words[1] if len(words) > 1 else "open"
        if action not in ("open", "close", "toggle", "new"):
            raise ValueError("Использование: python mascot.py chess [open|close|toggle|new]")
        payload = {"chess": action}
    elif command == "quit":
        payload = {"quit": True}
    elif command == "music" and len(words) == 2 and words[1] in ("auto", "on", "off"):
        payload = {"music_mode": words[1]}
    else:
        raise ValueError("Неизвестная команда. Список: python mascot.py --help")
    if not send(payload):
        print("deepsy не запущен. Сначала выполните: python mascot.py", file=sys.stderr)
        return 1
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, epilog="Команды: " + ", ".join(EMOTIONS + ACTIVITIES) + ", say <эмоция> <текст>, music auto|on|off, chess [open|close|toggle|new], run <команда>, quit")
    parser.add_argument("--config", help="Путь к config.json")
    parser.add_argument("--backend", choices=("auto", "gtk", "qt"))
    parser.add_argument("--doctor", action="store_true", help="Диагностика доступных интеграций")
    parser.add_argument("--check", action="store_true", help="Проверить настройки и кадры без запуска окна")
    parser.add_argument("--smoke-test", type=float, metavar="SECONDS", help="Запустить окно на заданное число секунд без наблюдателей")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    options = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="deepsy: %(message)s")
    try:
        if options.command and options.command != ["daemon"]:
            return client(options.command)
        cfg = load_config(options.config)
        if options.backend:
            cfg["backend"] = options.backend
        if options.doctor:
            return doctor(cfg)
        directory, meta = load_assets()
        if options.check:
            print(f"Настройки и {len(meta['clips'])} анимаций проверены.")
            return 0
        if options.smoke_test is not None:
            if not math.isfinite(options.smoke_test):
                raise ValueError("--smoke-test должен быть конечным числом")
            cfg["run_seconds"] = max(.1, options.smoke_test)
            cfg["watchers"] = {key: False for key in cfg["watchers"]}
        import backends
        import watchers
        engine = Engine(meta, cfg)
        proxy = EventProxy(engine)
        with Server(proxy.command):
            observers = watchers.start_all(proxy, cfg)
            try:
                return backends.run(engine, directory, requested=cfg["backend"]) or 0
            finally:
                for observer in observers:
                    observer.stop()
    except AlreadyRunning:
        print("deepsy уже запущен. Команда остановки: python mascot.py quit")
        return 0
    except (OSError, ValueError, ImportError, RuntimeError) as error:
        print(f"deepsy: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
