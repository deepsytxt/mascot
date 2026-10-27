"""Desktop observers shared by GTK and Qt.

Workers only call the thread-safe app proxy. Missing optional desktop services
silently disable their observer. Notification content is never displayed or logged.
"""
from __future__ import annotations

import json
import logging
import math
import os
import random
import re
import shutil
import subprocess
import sys
import threading
import time

from media import MusicState, PlayerctlProvider, WindowsMediaProvider, matches, windows_namespace

log = logging.getLogger(__name__)

DEFAULT_APP_REACTIONS = [
    {"match": r"^(foot|footclient|alacritty|kitty|wezterm|org\.wezfurlong\.wezterm|com\.mitchellh\.ghostty|ghostty|org\.gnome\.ptyxis|org\.gnome\.console|konsole|xterm)$",
     "emotion": "joy", "text": "Терминал! Мой дом."},
    {"match": r"steam_app_|^steam$|lutris|heroic|minecraft|prismlauncher|gamescope",
     "emotion": "joy", "text": "Играем?!"},
    {"match": r"obs|kooha|simplescreenrecorder|wf-recorder",
     "emotion": "surprise", "text": "Запись?"},
    {"match": r"keepassxc|bitwarden|1password",
     "emotion": "fear", "text": "Я ничего не видел."},
    {"match": r"^(mpv|io\.mpv\.mpv|vlc|celluloid)$",
     "emotion": "surprise", "text": "Кино?"},
    {"match": r"telegram|discord|vesktop|element|signal|thunderbird",
     "emotion": "wink", "text": "Чатимся?"},
    {"match": r"firefox|chromium|chrome|brave|zen|librewolf|vivaldi",
     "emotion": "wink", "text": "Серфим?"},
    {"match": r"^(code|code-oss|codium|zed|neovide|emacs)$|jetbrains|idea|pycharm|clion",
     "emotion": "wink", "text": "Пишем код?"},
    {"match": r"pavucontrol|nm-connection|blueman|gnome-control-center|systemsettings",
     "emotion": "confused", "text": "Настройки…"},
]


class PollingWatcher:
    """A stoppable daemon worker; Event.wait makes both timers and shutdown interruptible."""

    def __init__(self, interval, initial_delay=0):
        try:
            interval = float(interval)
        except (TypeError, ValueError):
            interval = 10.0
        try:
            initial_delay = float(initial_delay)
        except (TypeError, ValueError):
            initial_delay = 0.0
        self.interval = min(86400.0, max(0.1, interval)) if math.isfinite(interval) else 10.0
        self.initial_delay = min(86400.0, max(0, initial_delay)) if math.isfinite(initial_delay) else 0.0
        self._stop = threading.Event()
        self.thread = None
        self.last_error = None

    def start(self):
        if self._stop.is_set():
            return False
        if self.thread and self.thread.is_alive():
            return True
        self.thread = threading.Thread(target=self._run, name="deepsy-" + type(self).__name__, daemon=True)
        self.thread.start()
        return True

    def _run(self):
        try:
            if self._stop.wait(self.initial_delay):
                return
            while not self._stop.is_set():
                try:
                    self.poll()
                    self.last_error = None
                except Exception as error:
                                                                                     
                    self.last_error = type(error).__name__
                if self._stop.wait(self.interval):
                    break
        finally:
            self.cleanup()

    def poll(self):
        raise NotImplementedError

    def cleanup(self):
        pass

    def stop(self):
        self._stop.set()
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(timeout=5)


class LineWatcher:
    """Read an optional desktop command off the GUI thread, with bounded shutdown."""

    def __init__(self, argv, on_line, restart=30):
        self.argv, self.on_line, self.restart = argv, on_line, restart
        self.proc = None
        self.thread = None
        self._stop = threading.Event()
        self._lock = threading.Lock()

    def _spawn(self):
        with self._lock:
            if self._stop.is_set():
                return False
            try:
                self.proc = subprocess.Popen(
                    self.argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    text=True, encoding="utf-8", errors="replace", bufsize=1,
                )
                return True
            except OSError:
                return False

    def start(self):
        if self._stop.is_set():
            return False
        if self.thread and self.thread.is_alive():
            return True
        if not self._spawn():
            return False
        self.thread = threading.Thread(target=self._read, name="deepsy-" + self.argv[0], daemon=True)
        self.thread.start()
        return True

    def _read(self):
        while not self._stop.is_set():
            proc = self.proc
            try:
                for line in proc.stdout:
                    if self._stop.is_set():
                        break
                    try:
                        self.on_line(line.rstrip("\r\n"))
                    except (ValueError, KeyError, TypeError):
                                                                                  
                        continue
            finally:
                if proc.poll() is None:
                    proc.terminate()
                try:
                    proc.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=1)
                proc.stdout.close()
            if not self.restart or self._stop.wait(self.restart):
                break
            if not self._spawn():
                break

    def stop(self):
        self._stop.set()
        with self._lock:
            if self.proc and self.proc.poll() is None:
                self.proc.terminate()
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(timeout=2)
            if self.thread.is_alive():
                with self._lock:
                    if self.proc and self.proc.poll() is None:
                        self.proc.kill()
                self.thread.join(timeout=2)


class Niri:
    def __init__(self, app, cfg):
        self.app = app
        rules = cfg.get("app_reactions") or DEFAULT_APP_REACTIONS
        self.rules = [(re.compile(r["match"], re.I), r) for r in rules]
        self.known = {}
        self.ready = False
        self.w = LineWatcher(["niri", "msg", "--json", "event-stream"], self.on_line, restart=20)

    def start(self):
        return sys.platform.startswith("linux") and bool(os.environ.get("NIRI_SOCKET")) and self.w.start()

    def stop(self):
        self.w.stop()

    def match(self, win):
        """Правило: "match" — regex по app_id; необязательный "title" — ещё и regex по заголовку."""
        app_id, title = win.get("app_id") or "", win.get("title") or ""
        for rx, rule in self.rules:
            if rx.search(app_id) and (not rule.get("title") or re.search(rule["title"], title, re.I)):
                return rule
        return None

    @staticmethod
    def nice_name(win):
        parts = (win.get("app_id") or "").split(".")
        name = parts[-1] if parts[-1].lower() not in ("desktop", "app", "client", "gtk", "qt", "") else (parts[-2] if len(parts) > 1 else "")
        return name or (win.get("title") or "окно")[:24]

    def on_line(self, line):
        ev = json.loads(line)
        if not isinstance(ev, dict) or len(ev) != 1:
            return
        (kind, v), = ev.items()
        app = self.app
        if kind == "WindowsChanged":                                                       
            self.known = {w["id"]: w for w in v["windows"]}
            self.ready = True
        elif kind == "WindowOpenedOrChanged":
            w = v["window"]
            new = w["id"] not in self.known
            self.known[w["id"]] = w
            if new:                                                                                    
                app.touch()
                if self.ready:
                    self.opened(w)
        elif kind == "WindowClosed":
            w = self.known.pop(v["id"], None)
            app.touch()
            if w and self.ready and not self.known:
                app.react("empty", "sad", "Пусто…", 3, cooldown=120)
        elif kind == "WindowUrgencyChanged":
            w = self.known.get(v["id"])
            if v["urgent"] and w:
                app.react("urgent", "surprise", "Нужно твоё внимание!", 3, prio=2, cooldown=10)
        elif kind in ("WindowFocusChanged", "WorkspaceActivated"):
            app.touch()
        elif kind == "OverviewOpenedOrClosed":
            app.touch()
            if v["is_open"]:
                app.react("overview", "surprise", None, 1.5, cooldown=25)
        elif kind == "ScreenshotCaptured":
            app.react("shot", "wink", "Снимок!", 2, cooldown=3)
        elif kind == "CastStartedOrChanged":
            app.react("cast", "surprise", "Идёт запись экрана!", 3, prio=2, cooldown=90)

    def opened(self, w):
        if len(self.known) >= 14:
            self.app.react("many", "confused", "Окон многовато…", 3, cooldown=300)
            return
        rule = self.match(w)
        if rule:
            self.app.react("open", rule["emotion"], rule.get("text"), rule.get("hold", 2.5), cooldown=6)
        elif random.random() < 0.25:
            self.app.react("open", "surprise", None, 1.5, cooldown=6)


class NotificationPolicy:
    """Only fixed phrases leave this boundary, irrespective of title/body/device names."""

    SYSTEM_APPS = (
        "*blueman*", "*bluetooth*", "*bluez*", "*wireplumber*", "*pulseaudio*",
        "*pavucontrol*", "*networkmanager*", "*nm-applet*", "*powerdevil*",
        "*power-manager*", "*brightness*", "*volume*", "*osd*", "*mako-osd*",
    )
    CHAT_APPS = ("*telegram*", "*discord*", "*vesktop*", "*signal*", "*element*",
                 "*whatsapp*", "*slack*", "*teams*", "*viber*", "*thunderbird*", "*outlook*")
    OSD_HINTS = {"x-canonical-private-synchronous", "x-canonical-private-icon-only"}
    SYSTEM_CATEGORIES = ("device.*", "network.*", "system.*", "hardware.*")

    def __init__(self, config=None):
        self.config = config or {}
        self.cooldown = max(0.0, float(self.config.get("cooldown", 12)))
        self.last = float("-inf")

    def reaction(self, app_name, hints, now):
        desktop = str(hints.get("desktop-entry", ""))
        sources = (app_name, desktop)
        ignored = self.SYSTEM_APPS + tuple(self.config.get("ignore_apps", []))
        if any(matches(source, ignored) for source in sources):
            return None
        if any(key in hints for key in self.OSD_HINTS):
            return None
        category = str(hints.get("category", "")).casefold()
        if matches(category, self.SYSTEM_CATEGORIES):
            return None
                                                                               
                                                                            
        stack = str(hints.get("x-dunst-stack-tag", "")).casefold()
        if matches(stack, ("*volume*", "*brightness*", "*bluetooth*", "*backlight*", "*audio*")):
            return None
        if now - self.last < self.cooldown:
            return None
        self.last = now
        if category.startswith("im") or category.startswith("email") or any(matches(source, self.CHAT_APPS) for source in sources):
            return "surprise", "Новое сообщение!"
        if hints.get("urgency") == 2:
            return "surprise", "Важное уведомление!"
        return "wink", "Есть новое уведомление!"


class Notifications:
    HEADER = re.compile(r"^(method call|method return|signal|error)\b")
    TOP_STR = re.compile(r'^   string "((?:\\.|[^"\\])*)"$')
    HINT = re.compile(r'dict entry\(\s+string "([^"\\]+)"\s+variant\s+(?:string "((?:\\.|[^"\\])*)"|byte (\d+)|boolean (true|false))', re.S)

    def __init__(self, app, cfg):
        self.app = app
        self.policy = NotificationPolicy(cfg.get("notifications", {}))
        self.buf = None
        self.w = LineWatcher(
            ["dbus-monitor", "--session",
             "type='method_call',interface='org.freedesktop.Notifications',member='Notify'"],
            self.on_line, restart=30,
        )

    def start(self):
        return sys.platform.startswith("linux") and bool(os.environ.get("DBUS_SESSION_BUS_ADDRESS")) and self.w.start()

    def stop(self):
        self.w.stop()
        self.buf = None

    def on_line(self, line):
        if self.HEADER.match(line):
                                                                                
                                                                            
            self.buf = [] if "member=Notify" in line else None
            return
        if self.buf is None:
            return
        self.buf.append(line)
        if len(self.buf) > 2048:
            self.buf = None
            return
        if re.fullmatch(r"   int32 -?\d+", line):
            self.flush()

    def flush(self):
        buf, self.buf = self.buf, None
        if not buf:
            return
                                                                             
                                                                                 
        strings = [match.group(1) for line in buf if (match := self.TOP_STR.fullmatch(line))]
        if len(strings) != 4:
            return
        hints = {}
        for match in self.HINT.finditer("\n".join(buf)):
            key, text, byte, boolean = match.groups()
            hints[key] = int(byte) if byte is not None else (boolean == "true" if boolean else text)
        reaction = self.policy.reaction(strings[0], hints, time.monotonic())
        if reaction:
            emotion, text = reaction
            self.app.react("notify", emotion, text, 3.5, prio=2, cooldown=self.policy.cooldown)


class System(PollingWatcher):
    def __init__(self, app, cfg):
        super().__init__(cfg.get("system", {}).get("poll_interval", 10), initial_delay=2)
        self.app = app
        self.cpu_high = 0
        self.was_high = False
        self.net_state = self.net_pending = None
        self.bat_status = None
        self.warned = set()
        self.psutil = None

    def start(self):
        try:
            import psutil
        except ImportError:
            return False
        self.psutil = psutil
        return super().start()

    def poll(self):
        for check in (self.check_cpu, self.check_mem, self.check_battery, self.check_net, self.check_temp):
            if self._stop.is_set():
                break
            try:
                check()
            except (OSError, AttributeError, NotImplementedError):
                pass

    def check_cpu(self):
        usage = self.psutil.cpu_percent(interval=None)
        self.cpu_high = self.cpu_high + 1 if usage > 92 else 0
        if self.cpu_high >= 3:
            self.was_high = True
            self.app.react("cpu", "fear", "Процессор перегружен!", 4, cooldown=300)
        elif self.was_high and usage < 40:
            self.was_high = False
            self.app.react("cpu_ok", "wink", "Фух…", 2, cooldown=60)

    def check_mem(self):
        mem = self.psutil.virtual_memory()
        if mem.total and mem.available / mem.total < 0.07:
            self.app.react("mem", "fear", "Память кончается!", 4, cooldown=600)

    def check_battery(self):
        battery = self.psutil.sensors_battery()
        if battery is None:
            return
        cap = round(battery.percent)
        plugged = battery.power_plugged
        if not plugged:
            threshold = 10 if cap <= 10 else 20 if cap <= 20 else None
            if threshold and threshold not in self.warned:
                self.warned.add(threshold)
                if threshold == 10:
                    self.warned.add(20)
                self.app.react("bat", "fear" if threshold == 10 else "sad",
                               f"Батарея {cap}%!", 4, prio=2, cooldown=0)
        else:
            if self.bat_status is False:
                self.app.react("plug", "joy", "Зарядка!", 2.5, cooldown=30)
            self.warned.clear()
        self.bat_status = plugged

    def check_net(self):
        stats = self.psutil.net_if_stats()
        up = any(stat.isup for name, stat in stats.items()
                 if not name.casefold().startswith(("lo", "loopback", "docker", "veth", "virbr", "br-", "tun", "tap", "vnet")))
        if self.net_state is None:
            self.net_state = up
            return
        if up == self.net_state:
            self.net_pending = None
        elif self.net_pending == up:
            self.net_state, self.net_pending = up, None
            self.app.react("net", "joy" if up else "sad", "Сеть вернулась" if up else "Сеть пропала", 3, cooldown=30)
        else:
            self.net_pending = up

    def check_temp(self):
        if not hasattr(self.psutil, "sensors_temperatures"):
            return
        groups = self.psutil.sensors_temperatures()
        temperatures = [sensor.current for group in groups.values() for sensor in group if sensor.current is not None]
        if temperatures and max(temperatures) > 92:
            self.app.react("temp", "fear", "Жарко!", 4, cooldown=600)


class Music(PollingWatcher):
    def __init__(self, app, cfg, provider=None):
        music_cfg = cfg.get("music", {})
        super().__init__(music_cfg.get("poll_interval", 1))
        self.app = app
        self.state = MusicState(music_cfg)
        self.provider = provider or (WindowsMediaProvider() if sys.platform == "win32" else PlayerctlProvider())
        self.active = False

    def start(self):
        return self.provider.available and super().start()

    def poll(self):
        try:
            sessions = self.provider.snapshot()
        except (OSError, RuntimeError):
            sessions = None
        if self._stop.is_set():
            return
        active = self.state.update(sessions, time.monotonic())
        if active != self.active:
            self.active = active
            self.app.set_music(active)
            if active:
                self.app.say("♪ Музыка!", 2.5)

    def stop(self):
        self._stop.set()
        self.provider.cancel()
        super().stop()
        if self.active:
            self.active = False
            self.app.set_music(False)

    def cleanup(self):
        self.provider.close()


class Clock(PollingWatcher):
    def __init__(self, app, cfg):
        super().__init__(60, initial_delay=4)
        self.app, self.last_late, self.greeted = app, 0.0, False

    def poll(self):
        if not self.greeted:
            self.greeted = True
            self.greet()
        else:
            self.tick()

    def greet(self):
        hour = time.localtime().tm_hour
        if hour < 5:
            self.app.react("greet", "confused", "Ты не спишь?", 3, cooldown=0)
        elif hour < 11:
            self.app.react("greet", "joy", "Доброе утро!", 3, cooldown=0)
        elif hour < 18:
            self.app.react("greet", "wink", "Привет!", 2.5, cooldown=0)
        else:
            self.app.react("greet", "wink", "Добрый вечер!", 2.5, cooldown=0)

    def tick(self):
        now = time.monotonic()
        if time.localtime().tm_hour < 5 and now - self.last_late > 45 * 60:
            self.last_late = now
                                                                             
                                                                         
            self.app.react("late", "tired", "Пора спать…", 4, cooldown=45 * 60)


WATCHERS = {"niri": Niri, "notifications": Notifications, "system": System, "music": Music, "time": Clock}


def capability_report(cfg=None):
    """Report prerequisites, without claiming a session bus has granted monitoring."""
    import importlib.util

    enabled = (cfg or {}).get("watchers", {})
    linux = sys.platform.startswith("linux")
    report = {
        "niri": (linux and bool(os.environ.get("NIRI_SOCKET")) and bool(shutil.which("niri")), "niri event stream; requires a niri session"),
        "notifications": (linux and bool(os.environ.get("DBUS_SESSION_BUS_ADDRESS")) and bool(shutil.which("dbus-monitor")),
                          "Linux D-Bus monitor; session policy may restrict access" if linux else "Windows notification listening is not implemented"),
        "music": (bool(windows_namespace()) if sys.platform == "win32" else linux and bool(shutil.which("playerctl")),
                  "Windows GSMTC; requires optional PyWinRT media bindings" if sys.platform == "win32" else "Linux MPRIS via playerctl"),
        "system": (importlib.util.find_spec("psutil") is not None, "psutil; sensors depend on OS/hardware"),
        "time": (True, "local clock"),
    }
    return {name: {"available": bool(available), "enabled": enabled.get(name, True), "detail": detail}
            for name, (available, detail) in report.items()}


def start_all(app, cfg):
    on = cfg.get("watchers", {})
    started = []
    for name, cls in WATCHERS.items():
        if on.get(name, True):
            watcher = None
            try:
                watcher = cls(app, cfg)
                if watcher.start():
                    started.append(watcher)
                    continue
            except (OSError, ImportError, ValueError, TypeError):
                if watcher:
                    watcher.stop()
            log.info("Observer %s is unavailable; see --diagnose for prerequisites", name)
    return started
