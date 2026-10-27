"""Media snapshots and conservative music detection, independent of either GUI.

MPRIS/GSMTC report metadata, not the audio signal: unknown browser content is
ignored. A user can explicitly allow a player when its metadata is insufficient.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from fnmatch import fnmatchcase
import importlib
import importlib.util
from pathlib import PurePosixPath
import shutil
import subprocess
import threading
from urllib.parse import urlparse


@dataclass(frozen=True)
class MediaSession:
    player: str
    status: str
    title: str = ""
    artist: str = ""
    album: str = ""
    url: str = ""
    media_type: str = ""
    track_id: str = ""
    session_id: str = ""


def matches(value, patterns):
    return any(fnmatchcase(value.casefold(), pattern.casefold()) for pattern in patterns)


MUSIC_PLAYERS = (
    "spotify*", "*spotify*", "rhythmbox*", "lollypop*", "strawberry*", "clementine*",
    "audacious*", "deadbeef*", "quodlibet*", "cmus*", "mpd*", "mopidy*", "elisa*",
    "org.kde.elisa*", "*yandexmusic*", "*yandex-music*", "*applemusic*", "*tidal*",
    "*deezer*", "*foobar2000*", "*musicbee*", "*aimp*",
)
BROWSERS = (
    "*firefox*", "*chromium*", "*chrome*", "*msedge*", "*microsoftedge*", "*brave*",
    "*vivaldi*", "*opera*", "*librewolf*", "*floorp*", "*zen*browser*", "zen*",
)
MUSIC_HOSTS = (
    "music.youtube.com", "open.spotify.com", "music.yandex.ru", "music.yandex.com",
    "music.apple.com", "listen.tidal.com", "deezer.com", "soundcloud.com", "bandcamp.com",
)
AUDIO_EXTENSIONS = {".mp3", ".flac", ".ogg", ".opus", ".m4a", ".aac", ".wav", ".aiff", ".wma"}
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm", ".avi", ".mov", ".wmv", ".m4v", ".ts"}


def classify_music(session, config=None):
    """Return True for music, False for known nonmusic, None for missing evidence.

    Explicit deny wins over allow; a native Music type is useful, but browsers
    often label ordinary videos as Music too, so their URL must identify a music
    service (or the user must explicitly allow that browser).
    """
    cfg = config or {}
    if matches(session.player, cfg.get("deny_players", [])):
        return False
    if matches(session.player, cfg.get("allow_players", [])):
        return True
    media_type = session.media_type.casefold()
    if media_type in ("video", "image"):
        return False
    try:
        url = urlparse(session.url)
        host = (url.hostname or "").casefold()
    except ValueError:
        return False
    extension = PurePosixPath(url.path).suffix.casefold()
    if extension in VIDEO_EXTENSIONS:
        return False
    if host and any(host == known or host.endswith("." + known) for known in MUSIC_HOSTS):
        return True
    if host in ("youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"):
        return False
    if matches(session.player, BROWSERS):
                                                                              
        return False if session.url else None
    if extension in AUDIO_EXTENSIONS or media_type in ("music", "audio"):
        return True
    if matches(session.player, MUSIC_PLAYERS):
        return True
                                                                          
    return None


class MusicState:
    """Aggregate every player; only unavailable evidence gets a short grace period."""

    def __init__(self, config=None):
        self.config = config or {}
        self.grace = max(0.0, float(self.config.get("metadata_grace", 4.0)))
        self.confirmed = {}
        self.active = False

    def update(self, sessions, now):
                                                                              
                                                                            
        for session in sessions or []:
            key = session.session_id or session.player
            previous = self.confirmed.get(key)
            if session.status.casefold() in ("paused", "stopped", "closed"):
                self.confirmed.pop(key, None)
                continue
            classification = classify_music(session, self.config)
            if classification is False:
                self.confirmed.pop(key, None)
            elif session.status.casefold() == "playing" and classification is True:
                self.confirmed[key] = (now, session)
            elif previous:
                old = previous[1]
                                                                                      
                changed = ((old.track_id and session.track_id and old.track_id != session.track_id)
                           or (old.title and session.title and old.title != session.title))
                if changed:
                    self.confirmed.pop(key, None)
        self.confirmed = {key: value for key, value in self.confirmed.items()
                          if now - value[0] <= self.grace}
        self.active = bool(self.confirmed)
        return self.active


class PlayerctlProvider:
    """One bounded process per poll; all players are queried in the same snapshot."""

    separator = "\x1f"
    record_separator = "\x1e"
    fields = ("playerInstance", "status", "title", "artist", "album", "xesam:url", "mpris:trackid")

    def __init__(self):
        self._lock = threading.Lock()
        self._proc = None
        self._stopped = False

    @property
    def available(self):
        return bool(shutil.which("playerctl"))

    @classmethod
    def parse(cls, output):
        sessions = []
        for record in output.split(cls.record_separator):
            values = record.strip("\r\n").split(cls.separator)
            if len(values) != len(cls.fields) or not values[0]:
                continue
            player, status, title, artist, album, url, track = values
            sessions.append(MediaSession(player, status, title, artist, album, url, track_id=track))
        return sessions

    def _run(self, command, fmt):
        with self._lock:
            if self._stopped:
                return None
            proc = subprocess.Popen(
                ["playerctl", "--all-players", command, "--format", fmt],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                encoding="utf-8", errors="replace",
            )
            self._proc = proc
        try:
            output, _ = proc.communicate(timeout=2)
            return output if proc.returncode == 0 else None
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            return None
        finally:
            with self._lock:
                if self._proc is proc:
                    self._proc = None

    def snapshot(self):
        fmt = self.separator.join("{{" + key + "}}" for key in self.fields) + self.record_separator
        metadata = self._run("metadata", fmt)
                                                                                 
                                                                              
        status_format = "{{playerInstance}}" + self.separator + "{{status}}" + self.record_separator
        statuses = self._run("status", status_format)
        if statuses is None:
            return None
        details = {session.player: session for session in self.parse(metadata or "")}
        sessions = []
        for record in statuses.split(self.record_separator):
            values = record.strip("\r\n").split(self.separator)
            if len(values) != 2 or not values[0]:
                continue
            player, status = values
            old = details.get(player)
            if old is None:
                sessions.append(MediaSession(player, status))
            else:
                sessions.append(MediaSession(player, status, old.title, old.artist,
                                             old.album, old.url, old.media_type, old.track_id))
        return sessions

    def cancel(self):
        with self._lock:
            self._stopped = True
            if self._proc and self._proc.poll() is None:
                self._proc.kill()

    def close(self):
        self.cancel()


def windows_namespace():
    """Prefer maintained modular PyWinRT; tolerate legacy winsdk installations."""
    for namespace in ("winrt", "winsdk"):
        try:
            if importlib.util.find_spec(namespace + ".windows.media.control") is not None:
                return namespace
        except (ImportError, ValueError, AttributeError):
            continue
    return None


class WindowsMediaProvider:
    """Read GSMTC sessions in a worker-owned asyncio loop (Windows 10 1809+)."""

    def __init__(self):
        self.namespace = windows_namespace()
        self.loop = None
        self.manager = None
        self._task = None
        self._stopped = False

    @property
    def available(self):
        return bool(self.namespace)

    @staticmethod
    def _enum_name(value, fallback):
        if value is None:
            return ""
                                                                                   
        value = getattr(value, "value", value)
        name = getattr(value, "name", "")
        if name:
            return name.casefold()
        try:
            return fallback.get(int(value), "")
        except (TypeError, ValueError):
            return ""

    async def _snapshot(self):
        if self.manager is None:
            module = importlib.import_module(self.namespace + ".windows.media.control")
            self.manager = await module.GlobalSystemMediaTransportControlsSessionManager.request_async()

        async def read(session, index):
            player = session.source_app_user_model_id
                                                                                
            key = f"{player}#{index}"
            try:
                info = session.get_playback_info()
                status = self._enum_name(info.playback_status, {
                    0: "closed", 1: "stopped", 2: "changing", 3: "stopped", 4: "playing", 5: "paused",
                })
                properties = await session.try_get_media_properties_async()
                return MediaSession(
                    player, status, properties.title or "", properties.artist or "",
                    properties.album_title or "", media_type=self._enum_name(
                        properties.playback_type, {0: "unknown", 1: "music", 2: "video", 3: "image"}),
                    session_id=key,
                )
            except Exception:
                                                                                        
                return MediaSession(player, locals().get("status", "unknown"), session_id=key)

        return await asyncio.gather(*(read(session, index)
                                      for index, session in enumerate(self.manager.get_sessions())))

    def snapshot(self):
        if self._stopped:
            return None
        if self.loop is None:
            self.loop = asyncio.new_event_loop()
        self._task = self.loop.create_task(self._snapshot())
        try:
            return self.loop.run_until_complete(asyncio.wait_for(self._task, timeout=4))
        except (asyncio.CancelledError, Exception):
            self.manager = None
            return None
        finally:
            self._task = None

    def cancel(self):
        self._stopped = True
        loop, task = self.loop, self._task
        if loop and not loop.is_closed() and task:
            try:
                loop.call_soon_threadsafe(task.cancel)
            except RuntimeError:
                pass

    def close(self):
                                                                              
        self.manager = None
        if self.loop:
            self.loop.close()
            self.loop = None
