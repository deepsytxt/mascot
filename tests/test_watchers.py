                                                                            
import asyncio
from dataclasses import replace
from enum import IntEnum
import sys
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from media import MediaSession, MusicState, PlayerctlProvider, WindowsMediaProvider, classify_music
from watchers import Clock, LineWatcher, Music, NotificationPolicy, Notifications, PollingWatcher, System, capability_report


class App:
    def __init__(self):
        self.events = []
        self.music = []

    def react(self, *args, **kwargs):
        self.events.append((args, kwargs))

    def set_music(self, value):
        self.music.append(value)

    def say(self, *args):
        self.events.append((args, {}))


class MediaTests(unittest.TestCase):
    def test_browser_video_artist_is_not_evidence_of_music(self):
        self.assertIs(classify_music(MediaSession("firefox.instance1", "Playing", "A video", "Channel", url="https://www.youtube.com/watch?v=x")), False)
        self.assertIsNone(classify_music(MediaSession("chrome.exe", "Playing", "A video", "Channel", media_type="music")))

    def test_music_service_and_native_players(self):
        for session in (
            MediaSession("firefox.instance1", "Playing", url="https://music.youtube.com/watch?v=x"),
            MediaSession("SpotifyAB.SpotifyMusic_123!Spotify", "Playing"),
            MediaSession("mpv", "Playing", url="file:///tmp/song.flac"),
            MediaSession("unknown.exe", "Playing", media_type="music"),
        ):
            with self.subTest(session=session):
                self.assertIs(classify_music(session), True)

    def test_video_extensions_and_spoofed_music_domains(self):
        self.assertIs(classify_music(MediaSession("vlc", "Playing", url="file:///tmp/film.mkv")), False)
        self.assertIs(classify_music(MediaSession("firefox", "Playing", url="https://music.youtube.com.attacker.test/video")), False)
        self.assertIs(classify_music(MediaSession("spotify", "Playing", media_type="video")), False)

    def test_explicit_allow_deny_and_case(self):
        browser = MediaSession("Firefox.instance1", "Playing", url="https://www.youtube.com/watch?v=x")
        self.assertIs(classify_music(browser, {"allow_players": ["firefox.*"]}), True)
        self.assertIs(classify_music(browser, {"allow_players": ["firefox.*"], "deny_players": ["FIREFOX.*"]}), False)

    def test_dance_remains_on_through_tracks_and_paused_other_player(self):
        state = MusicState()
        song = MediaSession("spotify", "Playing", "first", track_id="1")
        paused = MediaSession("firefox.instance1", "Paused")
        self.assertTrue(state.update([song, paused], 0))
        self.assertTrue(state.update([replace(song, title="second", track_id="2"), paused], 60))
        self.assertTrue(state.update([song], 3600))
        self.assertFalse(state.update([replace(song, status="Paused"), paused], 3601))

    def test_metadata_grace_expires_and_explicit_pause_is_immediate(self):
        state = MusicState({"metadata_grace": 4})
        song = MediaSession("firefox", "Playing", "song", url="https://music.youtube.com/watch?v=x", track_id="x")
        self.assertTrue(state.update([song], 0))
        self.assertTrue(state.update([replace(song, url="")], 2))
        self.assertTrue(state.update(None, 3))
        self.assertFalse(state.update([], 5))
        self.assertTrue(state.update([song], 6))
        self.assertFalse(state.update([replace(song, status="Paused", url="")], 6.1))

    def test_new_unknown_track_or_video_drops_music_without_grace(self):
        state = MusicState()
        song = MediaSession("firefox", "Playing", "song", url="https://music.youtube.com/watch?v=x", track_id="x")
        state.update([song], 0)
        self.assertFalse(state.update([replace(song, title="video", url="", track_id="y")], 1))
        state.update([song], 2)
        self.assertFalse(state.update([replace(song, url="https://youtube.com/watch?v=x")], 2.1))

    def test_all_windows_sessions_with_same_application_are_preserved(self):
        state = MusicState()
        first = MediaSession("spotify.exe", "Playing", session_id="spotify#0")
        second = MediaSession("spotify.exe", "Paused", session_id="spotify#1")
        self.assertTrue(state.update([first, second], 0))

    def test_playerctl_roundtrip_with_multiline_and_tabs_in_title(self):
        provider = PlayerctlProvider
        first = ["spotify.instance1", "Playing", "some\ttrack\non two lines", "artist", "album", "file:///song.flac", "id1"]
        second = ["firefox.instance2", "Paused", "video", "", "", "https://youtube.com/watch?v=x", "id2"]
        raw = "\n".join(provider.separator.join(fields) + provider.record_separator for fields in (first, second))
        sessions = provider.parse(raw)
        self.assertEqual(len(sessions), 2)
        self.assertEqual(sessions[0].title, first[2])
        self.assertEqual(sessions[1].status, "Paused")

    def test_status_snapshot_survives_missing_metadata(self):
        provider = PlayerctlProvider()
        status = provider.separator.join(["firefox.instance1", "Paused"]) + provider.record_separator
        with patch.object(provider, "_run", side_effect=[None, status]) as run:
            sessions = provider.snapshot()
        self.assertEqual(sessions, [MediaSession("firefox.instance1", "Paused")])
        self.assertEqual([call.args[0] for call in run.call_args_list], ["metadata", "status"])

    def test_music_not_restarted_on_each_poll_and_stop_clears_state(self):
        app = App()
        provider = SimpleNamespace(snapshot=lambda: [MediaSession("spotify", "Playing")],
                                   cancel=lambda: None, close=lambda: None, available=True)
        watcher = Music(app, {}, provider=provider)
        for _ in range(5):
            watcher.poll()
        self.assertEqual(app.music, [True])
        watcher.stop()
        watcher.poll()
        self.assertEqual(app.music, [True, False])

    def test_windows_real_async_protocol_and_pause_without_properties(self):
        class Status(IntEnum):
            PLAYING = 4
            PAUSED = 5

        class Session:
            source_app_user_model_id = "spotify.exe"

            def __init__(self, status, fail=False):
                self.status, self.fail = status, fail

            def get_playback_info(self):
                return SimpleNamespace(playback_status=self.status)

            async def try_get_media_properties_async(self):
                await asyncio.sleep(0)
                if self.fail:
                    raise OSError("metadata unavailable")
                return SimpleNamespace(title="song", artist="artist", album_title="album", playback_type=1)

        manager = SimpleNamespace(get_sessions=lambda: [Session(Status.PLAYING), Session(Status.PAUSED, fail=True)])
        with patch("media.windows_namespace", return_value="winrt"):
            provider = WindowsMediaProvider()
        provider.manager = manager
        try:
            sessions = provider.snapshot()
            self.assertEqual([item.status for item in sessions], ["playing", "paused"])
            self.assertEqual(sessions[0].media_type, "music")
            self.assertEqual(sessions[0].player, "spotify.exe")
            self.assertNotEqual(sessions[0].session_id, sessions[1].session_id)
        finally:
            provider.close()


NOTIFY = '''method call time=123 sender=:1.2 -> destination=org.freedesktop.Notifications serial=2 path=/org/freedesktop/Notifications; interface=org.freedesktop.Notifications; member=Notify
   string "Telegram Desktop"
   uint32 0
   string "telegram"
   string "Private Sender"
   string "Secret message and device name"
   array [
      string "default"
      string "Open private conversation"
   ]
   array [
      dict entry(
         string "urgency"
         variant             byte 1
      )
      dict entry(
         string "x-dunst-stack-tag"
         variant             string "chat-123"
      )
   ]
   int32 -1'''


class NotificationTests(unittest.TestCase):
    def test_nested_action_labels_do_not_change_generic_message(self):
        app = App()
        watcher = Notifications(app, {})
        for line in NOTIFY.splitlines():
            watcher.on_line(line)
        self.assertEqual(len(app.events), 1)
        self.assertEqual(app.events[0][0][2], "Новое сообщение!")
        self.assertNotIn("Private", repr(app.events))
        self.assertNotIn("Secret", repr(app.events))

    def test_critical_notification_stays_generic(self):
        app = App()
        watcher = Notifications(app, {})
        fixture = NOTIFY.replace('string "Telegram Desktop"', 'string "Calendar"').replace("byte 1", "byte 2")
        for line in fixture.splitlines():
            watcher.on_line(line)
        self.assertEqual(app.events[0][0][2], "Важное уведомление!")

    def test_partial_messages_are_not_emitted_at_next_header(self):
        app = App()
        watcher = Notifications(app, {})
        for line in NOTIFY.splitlines()[:-1]:
            watcher.on_line(line)
        watcher.on_line("signal time=123 member=SomethingElse")
        self.assertEqual(app.events, [])

    def test_osd_device_spam_and_bursts_are_filtered(self):
        policy = NotificationPolicy({"cooldown": 12})
        for app, hints in (
            ("blueman", {}),
            ("Shell", {"category": "device.added"}),
            ("Shell", {"x-canonical-private-synchronous": "volume"}),
            ("dunstify", {"x-dunst-stack-tag": "audio-volume"}),
        ):
            self.assertIsNone(policy.reaction(app, hints, 0))
        self.assertEqual(policy.reaction("Telegram", {"x-dunst-stack-tag": "chat-1"}, 1)[1], "Новое сообщение!")
        self.assertIsNone(policy.reaction("Telegram", {}, 2))
        self.assertIsNotNone(policy.reaction("Telegram", {}, 13))

    def test_custom_ignore_uses_application_and_desktop_entry(self):
        policy = NotificationPolicy({"ignore_apps": ["org.example.*"]})
        self.assertIsNone(policy.reaction("Private app", {"desktop-entry": "org.example.chat"}, 1))


class LifecycleTests(unittest.TestCase):
    def test_stop_before_start_prevents_greeting(self):
        app = App()
        watcher = Clock(app, {})
        watcher.stop()
        self.assertFalse(watcher.start())
        self.assertEqual(app.events, [])

    def test_poll_thread_stops_and_does_not_restart(self):
        event = threading.Event()

        class Probe(PollingWatcher):
            def poll(self):
                event.set()

        watcher = Probe(60)
        self.assertTrue(watcher.start())
        self.assertTrue(event.wait(2))
        watcher.stop()
        self.assertFalse(watcher.thread.is_alive())
        self.assertFalse(watcher.start())

    def test_line_process_and_restart_timer_are_stopped(self):
        event = threading.Event()
        lines = []

        def received(line):
            lines.append(line)
            event.set()

        watcher = LineWatcher([sys.executable, "-u", "-c", "import time; print('ready'); time.sleep(30)"], received, restart=0.1)
        self.assertTrue(watcher.start())
        self.assertTrue(event.wait(2))
        watcher.stop()
        self.assertFalse(watcher.thread.is_alive())
        self.assertIsNotNone(watcher.proc.poll())
        self.assertEqual(lines, ["ready"])
        self.assertFalse(watcher.start())

    def test_system_uses_optional_psutil_and_no_proc_files(self):
        app = App()
        watcher = System(app, {})
        watcher.psutil = SimpleNamespace(sensors_battery=lambda: SimpleNamespace(percent=8, power_plugged=False))
        watcher.check_battery()
        watcher.check_battery()
        self.assertEqual(len(app.events), 1)
        self.assertEqual(app.events[0][0][0], "bat")

    def test_windows_notifications_are_reported_unavailable(self):
        with patch("watchers.sys.platform", "win32"), patch("watchers.windows_namespace", return_value=None):
            report = capability_report()
        self.assertFalse(report["notifications"]["available"])
        self.assertIn("not implemented", report["notifications"]["detail"])
        self.assertFalse(report["music"]["available"])


if __name__ == "__main__":
    unittest.main()
