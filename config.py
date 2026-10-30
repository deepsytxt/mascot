                                                               
from __future__ import annotations

import copy
import json
import math
import os
from pathlib import Path
import re
import sys

DEFAULT_CONFIG = {
    "backend": "auto", "scale": 1.0, "mascot_size": 0.6, "monitor": 0, "layer": "top", "fps": 60,
    "floor_gap": 0, "margin": 16, "gravity": 2600, "swing": 0.75,
    "drop_in": False, "walk_speed": 52, "sprint_speed": 140,
    "workarea_insets": {"left": 0, "top": 0, "right": 0, "bottom": 0},
    "watchers": {"niri": True, "notifications": True, "system": True, "music": True, "time": True},
    "idle": {"gap": [8, 18], "sleep_after": 900,
             "weights": {"walk": 3, "look": 3, "stretch": 2, "yawn": 1.5, "wink": 1, "sprint": 0.6}},
    "interaction": {"follow_cursor": True, "follow_chance": 0.18,
                    "follow_cooldown": 35, "follow_duration": 4, "petting": True},
    "music": {"mode": "auto", "poll_interval": 1.0, "metadata_grace": 4.0,
              "allow_players": [], "deny_players": []},
    "notifications": {"cooldown": 12, "ignore_apps": []},
    "system": {"poll_interval": 10}, "reaction_cooldown": 8,
    "chess": {"scale": 3, "level": 2},
}


def config_dir() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("APPDATA", str(Path.home() / "AppData/Roaming"))) / "deepsy"
    return Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "deepsy"


def merge(base, custom):
    for key, value in custom.items():
        if isinstance(base.get(key), dict) and isinstance(value, dict):
            merge(base[key], value)
        else:
            base[key] = copy.deepcopy(value)
    return base


def number(value, default, minimum, maximum):
    try:
        value = float(value)
        return max(minimum, min(maximum, value)) if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


def load_config(path=None):
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    location = Path(path) if path else config_dir() / "config.json"
    if not path and not location.exists() and os.name != "nt":
        legacy = location.parent.parent / "mascot/config.json"
        if legacy.exists():
            location = legacy
    try:
        user = json.loads(location.read_text(encoding="utf-8"))
        if not isinstance(user, dict):
            raise ValueError("ожидается JSON-объект")
        merge(cfg, user)
    except FileNotFoundError:
        if path:
            raise ValueError(f"Файл настроек не найден: {location}") from None
    except (OSError, ValueError) as error:
        raise ValueError(f"Не удалось прочитать {location}: {error}") from error
    for key, default in DEFAULT_CONFIG.items():
        if isinstance(default, dict) and not isinstance(cfg.get(key), dict):
            raise ValueError(f"Настройка {key} должна быть объектом")
    env = {"MASCOT_SCALE": "scale", "MASCOT_FLOOR": "floor_gap", "MASCOT_MARGIN": "margin",
           "MASCOT_GRAVITY": "gravity", "MASCOT_SWING": "swing", "MASCOT_MONITOR": "monitor",
           "MASCOT_LAYER": "layer"}
    for name, key in env.items():
        if name in os.environ:
            cfg[key] = os.environ[name]
    if "MASCOT_DROPIN" in os.environ:
        cfg["drop_in"] = os.environ["MASCOT_DROPIN"] == "1"
    for key, limits in {"scale": (.25, 4), "mascot_size": (.1, 1), "floor_gap": (0, 200), "margin": (0, 1000),
                        "gravity": (100, 10000), "swing": (0, 2), "fps": (15, 144),
                        "walk_speed": (1, 600), "sprint_speed": (1, 1200),
                        "reaction_cooldown": (0, 3600)}.items():
        cfg[key] = number(cfg[key], DEFAULT_CONFIG[key], *limits)
    cfg["fps"] = int(cfg["fps"])
    if isinstance(cfg["monitor"], str) and cfg["monitor"].isdigit():
        cfg["monitor"] = int(cfg["monitor"])
    if cfg["backend"] not in ("auto", "gtk", "qt"):
        raise ValueError("backend: auto, gtk или qt")
    if cfg["music"].get("mode") not in ("auto", "on", "off"):
        raise ValueError("music.mode: auto, on или off")
    gap = cfg["idle"].get("gap")
    if not isinstance(gap, list) or len(gap) != 2:
        raise ValueError("idle.gap: [минимум, максимум] в секундах")
    cfg["idle"]["gap"] = sorted(number(v, 12, 1, 3600) for v in gap)
    cfg["idle"]["sleep_after"] = number(cfg["idle"].get("sleep_after"), 900, 0, 86400)
    weights = cfg["idle"].get("weights")
    if not isinstance(weights, dict):
        raise ValueError("idle.weights должен быть объектом")
    cfg["idle"]["weights"] = {k: number(v, 0, 0, 100) for k, v in weights.items()
                              if k in ("walk", "sprint", "look", "stretch", "yawn", "wink")}
    for key, default, low, high in (("poll_interval", 1, .1, 86400), ("metadata_grace", 4, 0, 86400)):
        cfg["music"][key] = number(cfg["music"].get(key), default, low, high)
    for key in ("allow_players", "deny_players"):
        values = cfg["music"].get(key, [])
        if not isinstance(values, list) or not all(isinstance(value, str) and value.strip() for value in values):
            raise ValueError(f"music.{key} должен быть списком строк")
        cfg["music"][key] = values[:64]
    cfg["notifications"]["cooldown"] = number(cfg["notifications"].get("cooldown"), 12, 0, 86400)
    ignored = cfg["notifications"].get("ignore_apps", [])
    if not isinstance(ignored, list) or not all(isinstance(value, str) and value.strip() for value in ignored):
        raise ValueError("notifications.ignore_apps должен быть списком строк")
    cfg["notifications"]["ignore_apps"] = ignored[:64]
    cfg["chess"]["scale"] = int(number(cfg["chess"].get("scale"), 3, 1, 6))
    cfg["chess"]["level"] = int(number(cfg["chess"].get("level"), 2, 1, 4))
    cfg["system"]["poll_interval"] = number(cfg["system"].get("poll_interval"), 10, .1, 86400)
    rules = cfg.get("app_reactions", [])
    if not isinstance(rules, list):
        raise ValueError("app_reactions должен быть списком объектов")
    checked_rules = []
    for rule in rules[:128]:
        if not isinstance(rule, dict) or not isinstance(rule.get("match"), str):
            raise ValueError("app_reactions.match должен быть строкой")
        try:
            re.compile(rule["match"], re.I)
            if rule.get("title") is not None:
                re.compile(str(rule["title"]), re.I)
        except re.error as error:
            raise ValueError(f"Некорректный regex в app_reactions: {error}") from error
        if rule.get("emotion") not in (None, "calm", "joy", "anger", "sad", "fear", "surprise", "wink", "tired", "confused", "dance"):
            raise ValueError("app_reactions.emotion содержит неизвестную эмоцию")
        checked_rules.append(rule)
    cfg["app_reactions"] = checked_rules
    for key in ("left", "right", "top", "bottom"):
        cfg["workarea_insets"][key] = number(cfg["workarea_insets"].get(key), 0, 0, 4000)
    for key, default, low, high in (("follow_chance", .18, 0, 1), ("follow_cooldown", 35, 5, 600),
                                  ("follow_duration", 4, 1, 10)):
        cfg["interaction"][key] = number(cfg["interaction"].get(key), default, low, high)
    return cfg
