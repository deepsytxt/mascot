   
from __future__ import annotations

from collections import deque
import math
from queue import Empty, SimpleQueue
import random

EMOTIONS = ("calm", "joy", "anger", "sad", "fear", "surprise", "wink", "tired", "confused", "dance")
ACTIVITIES = ("walk", "sprint", "look", "stretch", "yawn", "sleep", "wake", "dance")
ONE_SHOTS = ("look", "stretch", "yawn", "land", "land_hard", "walk_end", "calm_blink")
POKES = (("wink", "Я тут!"), ("joy", "Рад тебя видеть!"), ("surprise", "О, привет!"),
         ("confused", "Что будем делать?"), ("wink", "На связи."), ("joy", "Дай пять!"),
         ("look", "Куда посмотрим?"), ("stretch", "Разомнёмся?"), ("wink", "Бип-бип!"),
         ("joy", "Хорошо, что ты рядом."), ("look", "Всё спокойно?"), ("wink", "Слушаю тебя."))


def clamp(value, low, high):
    return max(low, min(high, value)) if high >= low else (low + high) / 2


class EventProxy:
                                                                                  
    ALLOWED = {"react", "set_music", "touch", "say", "do_activity", "command"}

    def __init__(self, engine):
        self.engine = engine

    def __getattr__(self, name):
        if name not in self.ALLOWED:
            raise AttributeError(name)
        return lambda *args, **kwargs: self.engine.events.put((name, args, kwargs))


class Engine:
    def __init__(self, meta, cfg, rng=None):
        self.meta, self.cfg = meta, cfg
        self.rng = rng or random.Random()
        self.events = SimpleQueue()
        self.clips = meta["clips"]
                                                                               
                                                                         
        self.mascot_size = float(cfg.get("mascot_size", 1.0))
        self.scale = cfg["scale"] * self.mascot_size
        self.width = self.height = 0
        self.x = self.y = self.vx = self.vy = 0.0
        self.now = self.last_event = 0.0
        self.state = "ground"
        self.initialized = False
        self.music = False
        self.music_mode = cfg["music"]["mode"]
                                                                           
                                                                          
        self.clip, self.idx, self.frame_time = ("dance" if self.dancing else "calm"), 0, 0.0
        self.activity = None
        self.until = None
        self.sleeping = False
        self.walk = None
        self.walk_dist = 0.0
        self.next_idle = self.rng.uniform(*cfg["idle"]["gap"])
        self.last_idle = None
        self.next_follow = 5.0
        self.follow_until = 0.0
        self.cursor = None
        self.last_cursor_time = 0.0
        self.press = None
        self.dragging = False
        self.drag_offset = (0, 0)
        self.drag_history = deque(maxlen=12)
        self.ang = self.omega = 0.0
        self.rotating = False
        self.pose = "hang"
        self.pending = None
        self.bubble = ""
        self.bubble_until = 0.0
        self.quit_requested = False
        self.reactions = {}
        self.react_any = -100.0
        self.pokes = deque()
        self.poke_bag = []
        self.last_poke = None
        self.pet_points = deque()
        self.last_pet = -100.0
        self.chess = None

    @property
    def dancing(self):
        return self.music_mode == "on" or (self.music_mode == "auto" and self.music)

    @property
    def floor(self):
        return max(1, self.height - self.cfg["floor_gap"])

    def resize(self, width, height):
        width, height = max(1, float(width)), max(1, float(height))
        if (width, height) == (self.width, self.height):
            return
        self.width, self.height = width, height
                                                                     
        sizes = [self.meta["size"]] + [[f["w"], f["h"]] for frames in self.meta.get("rot", {}).get("sets", {}).values() for f in frames]
        target_scale = self.cfg["scale"] * self.mascot_size
        self.scale = min(target_scale, width / max(s[0] for s in sizes),
                         self.floor / max(s[1] for s in sizes))
        if not self.initialized:
            self.x = width - self.cfg["margin"] - self.meta["size"][0] * self.scale / 2
            self.y = self.floor
            self.initialized = True
            if self.cfg["drop_in"]:
                self.y = self.meta["size"][1] * self.scale
                self.state = "air"
                self.play("fall")
        elif self.state == "ground":
            self.y = self.floor
        self._constrain()
        if self.walk:
            self.walk["target"] = clamp(self.walk["target"], *self._x_limits())

    def _rot_frame(self):
        rot = self.meta.get("rot")
        if not rot or not self.rotating:
            return None
        frames = rot["sets"][self.pose]
        index = round(math.degrees(self.ang) / rot["step"]) + len(frames) // 2
        return frames[int(clamp(index, 0, len(frames) - 1))]

    def _visual(self):
        s = self.scale
        rotated = self._rot_frame()
        if rotated:
            length = self.meta["feet_dy"] * s
            px, py = self.x - length * math.sin(self.ang), self.y - length * math.cos(self.ang)
            return rotated["f"], px - rotated["ax"] * s, py - rotated["ay"] * s, rotated["w"] * s, rotated["h"] * s
        filename = self.clips[self.clip]["frames"][self.idx]
        return (filename, self.x - self.meta["feet"][0] * s, self.y - self.meta["feet"][1] * s,
                self.meta["size"][0] * s, self.meta["size"][1] * s)

    def _bbox(self, filename, body=False):
        key = "body_bounds" if body else "bounds"
        bounds = self.meta.get(key, {})
        if isinstance(bounds, dict) and filename in bounds:
            return bounds[filename]
        if body:
            return self._bbox(filename)
        rotated = self._rot_frame()
        return [0, 0, rotated["w"], rotated["h"]] if rotated else self.meta["hit"]

    def _x_limits(self):
        bounds = self.meta.get("bounds", {})
        boxes = [bounds[f] for c in self.clips.values() for f in c["frames"] if isinstance(bounds, dict) and f in bounds]
        left = min((b[0] for b in boxes), default=self.meta["hit"][0])
        right = max((b[2] for b in boxes), default=self.meta["hit"][2])
        feet = self.meta["feet"][0]
        return (feet - left) * self.scale, self.width - (right - feet) * self.scale

    def _constrain(self):
        if not self.initialized:
            return
        if self.state == "ground":
            self.y = self.floor
            self.x = clamp(self.x, *self._x_limits())
        filename, ox, oy, _, _ = self._visual()
        left, top, right, bottom = self._bbox(filename)
        s = self.scale
        dx = max(0, -ox - left * s) - max(0, ox + right * s - self.width)
        dy = max(0, -oy - top * s) - max(0, oy + bottom * s - self.floor)
        self.x += dx
        self.y += dy
        if dx and self.vx * dx < 0:
            self.vx *= -.25 if self.state == "air" else 0
        if dy and self.vy * dy < 0:
            self.vy = 0 if dy < 0 else abs(self.vy) * .2

    def frame(self):
        self._constrain()
        filename, x, y, width, height = self._visual()
        left, top, right, bottom = self._bbox(filename, body=True)
        hit = (x + left * self.scale, y + top * self.scale,
               (right - left) * self.scale, (bottom - top) * self.scale)
        return dict(file=filename, x=x, y=y, width=width, height=height, hit=hit,
                    bubble=self.bubble, bubble_x=hit[0] + hit[2] / 2, bubble_y=hit[1] - 8)

    def play(self, name):
        if name not in self.clips:
            name = "calm"
        self.clip, self.idx, self.frame_time = name, 0, 0.0

    def _rest(self):
        self.walk = None
        self.activity = None
        self.until = None
        self.play("tired" if self.sleeping else "dance" if self.dancing else "calm")
        self.next_idle = self.now + self.rng.uniform(*self.cfg["idle"]["gap"])

    def _animate(self, dt):
        if self.rotating or self.walk:
            return
        self.frame_time += dt * 1000
        for _ in range(40):
            clip = self.clips[self.clip]
            duration = max(15, clip["durs"][self.idx])
            if self.frame_time < duration:
                break
            self.frame_time -= duration
            self.idx += 1
            if self.idx >= len(clip["frames"]):
                self.idx = 0
                if not clip["loop"]:
                    if self.clip == "calm_blink":
                        self.play("calm")
                    elif self.clip == "surprise_in":
                        self.play("surprise")
                    elif self.state == "air":
                        self.play("fall")
                    else:
                        self._rest()
                    break
                if self.clip == "calm" and self.rng.random() < .35:
                    self.play("calm_blink")
                    break

    def tick(self, dt):
        dt = clamp(float(dt), 0, .1)
        self.now += dt
        for _ in range(256):
            try:
                method, args, kwargs = self.events.get_nowait()
            except Empty:
                break
            getattr(self, method)(*args, **kwargs)
        if self.cfg.get("run_seconds") and self.now >= self.cfg["run_seconds"]:
            self.quit_requested = True
        if not self.initialized:
            return
        if self.chess is not None:
            self.chess.tick(self.now)
        if self.bubble and self.now >= self.bubble_until:
            self.bubble = ""
        if self.state == "held":
            self._held(dt)
        elif self.state == "air":
            self._air(dt)
        elif self.walk:
            self._walk(dt)
        elif self.until is not None and self.now >= self.until:
            self._rest()
        elif self.is_free():
            sleep_after = self.cfg["idle"]["sleep_after"]
            if sleep_after and self.now - self.last_event >= sleep_after and not self.dancing:
                self.do_activity("sleep", user_activity=False)
            elif self.now >= self.next_idle and not self.dancing:
                weights = {name: weight for name, weight in self.cfg["idle"]["weights"].items() if weight > 0}
                if len(weights) > 1:
                    weights.pop(self.last_idle, None)
                if weights:
                    self.last_idle = self.rng.choices(list(weights), list(weights.values()))[0]
                    self.do_activity(self.last_idle, user_activity=False)
                self.next_idle = self.now + self.rng.uniform(*self.cfg["idle"]["gap"])
        self._animate(dt)
        self._constrain()

    def _air(self, dt):
        for _ in range(max(1, math.ceil(dt * 240))):
            h = dt / max(1, math.ceil(dt * 240))
            self.vy += self.cfg["gravity"] * h
            self.x += self.vx * h
            self.y += self.vy * h
            if self.rotating:
                self.omega += (-220 * self.ang - 22 * self.omega) * h
                self.ang += self.omega * h
                if abs(self.ang) < .04 and abs(self.omega) < .4:
                    self.rotating = False
                    self.play("fall")
            filename, _, oy, _, _ = self._visual()
            bottom = oy + self._bbox(filename)[3] * self.scale
            if self.vy >= 0 and (self.y >= self.floor or bottom >= self.floor):
                impact = self.vy
                self.state = "ground"
                self.rotating = False
                self.ang = self.omega = 0
                self.y = self.floor
                self.vx = self.vy = 0
                self.play("land_hard" if impact > 1500 else "land")
                self.until = None
                self.next_idle = self.now + self.rng.uniform(*self.cfg["idle"]["gap"])
                if self.pending:
                    args, self.pending = self.pending, None
                    self.set_emotion(*args[:3], user_activity=args[3])
                break
            self._constrain()

    def _held(self, dt):
        if not self.cursor:
            return
        target_x = self.cursor[0] + self.drag_offset[0]
        target_y = self.cursor[1] + self.drag_offset[1]
        old_x, old_y = self.x, self.y
        ease = 1 - math.exp(-22 * dt)
        self.x += (target_x - self.x) * ease
        self.y += (target_y - self.y) * ease
        desired = clamp(-(self.x - old_x) * .025 * self.cfg["swing"], -.7, .7)
        for _ in range(max(1, math.ceil(dt * 240))):
            h = dt / max(1, math.ceil(dt * 240))
            self.omega += (100 * (desired - self.ang) - 10 * self.omega) * h
            self.ang = clamp(self.ang + self.omega * h, -1.05, 1.05)
        self.pose = "flail" if abs(self.ang) > .45 else "hang"
        self.vx = (self.x - old_x) / max(dt, .001)
        self.vy = (self.y - old_y) / max(dt, .001)
        self._constrain()
        self.drag_history.append((self.now, self.x, self.y))

    def _walk(self, dt):
        walk = self.walk
        if walk.get("follow") and self.now >= self.follow_until:
            self.walk = None
            self.play("walk_end")
            return
        if walk.get("follow") and self.cursor:
            walk["target"] = clamp(self.cursor[0], *self._x_limits())
        remaining = walk["target"] - self.x
        direction = 1 if remaining > 0 else -1
        if walk.get("follow") and abs(remaining) < 24 * self.scale:
            self.walk = None
            self._rest()
            return
        name = ("sprint_" if walk["fast"] else "walk_") + ("r" if direction > 0 else "l")
        if self.clip != name:
            self.play(name)
        walk["age"] += dt
        ease_in = min(1, walk["age"] / .3)
        ease_out = min(1, abs(remaining) / max(1, walk["speed"] * .35))
        distance = min(abs(remaining), walk["speed"] * max(.15, min(ease_in, ease_out)) * dt)
        self.x += direction * distance
        self.walk_dist += distance
        clip = self.clips[self.clip]
        stride = max(1, clip.get("stride", 32) * self.scale)
        self.idx = int(self.walk_dist / stride * len(clip["frames"])) % len(clip["frames"])
        if abs(remaining) - distance < .5:
            self.walk = None
            self.activity = None
            self.play("walk_end")

    def is_free(self):
        return self.state == "ground" and not self.sleeping and not self.walk and self.until is None and self.clip in ("calm", "calm_blink", "dance")

    def touch(self, force=False):
        self.last_event = self.now
        if self.sleeping and (force or self.state == "ground"):
            self.sleeping = False
            self._rest()

    def say(self, text, secs=3):
                                                                            
                                                                
        text = text if isinstance(text, str) else "" if text is None else str(text)
        try:
            secs = float(secs)
        except (TypeError, ValueError):
            secs = 3.0
        self.bubble = text[:240]
        self.bubble_until = self.now + clamp(secs if math.isfinite(secs) else 3.0, .1, 60.0)

    def set_emotion(self, name, text=None, hold=None, *, user_activity=True):
        if not isinstance(name, str) or name not in EMOTIONS:
            return
        if text is not None and not isinstance(text, str):
            text = str(text)
        if isinstance(text, str):
            text = text[:240]
        try:
            hold = None if hold is None else float(hold)
        except (TypeError, ValueError):
            hold = None
        if hold is not None:
            hold = clamp(hold if math.isfinite(hold) else 3.5, .2, 60.0)
        if self.state != "ground":
            self.pending = (name, text, hold, user_activity)
            return
        if user_activity:
            self.touch(force=True)
        self.walk = None
        self.follow_until = 0
        self.activity = None
        self.until = self.now + (max(.2, float(hold)) if hold is not None else 3.5)
        if text:
            self.say(text, hold or 3.5)
        self.play(name + "_in" if name + "_in" in self.clips else name)

    def react(self, kind, emotion, text=None, hold=None, prio=1, cooldown=None):
        cooldown = self.cfg["reaction_cooldown"] if cooldown is None else cooldown
        if self.now - self.reactions.get(kind, -10000) < cooldown:
            return False
        if prio < 2 and (self.sleeping or self.state != "ground" or self.until is not None or self.now - self.react_any < 3):
            return False
        self.reactions[kind] = self.react_any = self.now
        self.set_emotion(emotion, text, hold, user_activity=False)
        return True

    def set_music(self, on):
        before = self.dancing
        was_sleeping = self.sleeping
        self.music = bool(on)
                                                                          
                                                  
        if self.dancing and self.sleeping and self.state == "ground":
            self.sleeping = False
        if (before != self.dancing or was_sleeping) and self.state == "ground" and not self.sleeping and not self.walk and self.until is None:
            self._rest()

    def do_activity(self, name, *, user_activity=True):
        if name == "wake":
            self.touch(force=True)
            return
        if self.state != "ground":
            return
        if user_activity:
            self.touch(force=True)
        self.walk = None
        self.until = None
        self.activity = name
        if name == "sleep":
            self.sleeping = True
            self._rest()
        elif name in ("walk", "sprint"):
            self.sleeping = False
            low, high = self._x_limits()
            target = self.rng.uniform(low, high) if high >= low else self.x
            if abs(target - self.x) < 80 * self.scale:
                target = low if self.x > (low + high) / 2 else high
            self.start_walk(target, fast=name == "sprint")
        elif name in ("look", "stretch", "yawn"):
            self.sleeping = False
            self.play(name)
        elif name == "dance":
            self.set_emotion("dance", hold=10, user_activity=user_activity)
        elif name == "wink":
            self.set_emotion("wink", hold=2, user_activity=user_activity)

    def start_walk(self, target, fast=False, follow=False):
        self.walk = dict(target=clamp(target, *self._x_limits()), fast=fast, follow=follow, age=0,
                         speed=self.cfg["sprint_speed" if fast else "walk_speed"] * self.scale)
        self.walk_dist = 0
        self.until = None
        self.play(("sprint_" if fast else "walk_") + ("r" if target > self.x else "l"))

    def pointer_press(self, x, y, button=1):
        if button != 1:
            return
        self.touch(force=True)
        self.press = (x, y)
        self.cursor = (x, y)
        self.dragging = False
        self.pet_points.clear()

    def pointer_move(self, x, y):
        self.cursor = (x, y)
        if self.press:
            if not self.dragging and math.hypot(x - self.press[0], y - self.press[1]) > 7:
                self.dragging = True
                self.drag_offset = (self.x - self.press[0], self.y - self.press[1])
                self.state = "held"
                self.rotating = bool(self.meta.get("rot"))
                self.walk = None
                self.until = None
                self.pending = None
                self.drag_history.clear()
                self.drag_history.append((self.now, self.x, self.y))
            return
        if not self.cfg["interaction"]["petting"] or self.state != "ground":
            return
        hx, hy, hw, hh = self.frame()["hit"]
        if not (hx <= x <= hx + hw and hy <= y <= hy + hh * .6):
            self.pet_points.clear()
            return
        self.last_event = self.now
        self.pet_points.append((self.now, x))
        while self.pet_points and self.now - self.pet_points[0][0] > 1.6:
            self.pet_points.popleft()
                                                                       
        points = [p[1] for p in self.pet_points]
        directions = []
        distance = 0
        if points:
            anchor = points[0]
            for point in points[1:]:
                delta = point - anchor
                if abs(delta) >= 6 * self.scale:
                    directions.append(1 if delta > 0 else -1)
                    distance += abs(delta)
                    anchor = point
        turns = sum(a != b for a, b in zip(directions, directions[1:]))
        if turns >= 3 and distance >= 45 * self.scale and self.now - self.last_pet >= 4:
            self.last_pet = self.now
            self.pet_points.clear()
            self.touch(force=True)
            self.walk = None
            self.follow_until = 0
                                                                            
                                                                             
                                                  
            self.activity = "pet"
            self.until = self.now + 4
            self.play("pet" if "pet" in self.clips else "joy")
            self.say(self.rng.choice(("Мур-бип…", "Ещё чуть-чуть?", "Как приятно!", "♥")), 4)

    def pointer_release(self, x, y, button=1):
        if button != 1 or self.press is None:
            return
        if self.dragging:
            recent = [p for p in self.drag_history if self.now - p[0] <= .12]
            self.vx = self.vy = 0
            if len(recent) >= 2:
                first, last = recent[0], recent[-1]
                elapsed = max(.016, last[0] - first[0])
                self.vx = clamp((last[1] - first[1]) / elapsed, -1800, 1800)
                self.vy = clamp((last[2] - first[2]) / elapsed, -1800, 1800)
            self.state = "air"
            self.play("fall")
            self._constrain()
        else:
            self.poke()
        self.dragging = False
        self.press = None
        self.last_event = self.now
        self.next_follow = self.now + self.cfg["interaction"]["follow_cooldown"]

    def poke(self):
        while self.pokes and self.now - self.pokes[0] > 3:
            self.pokes.popleft()
        self.pokes.append(self.now)
        if len(self.pokes) >= 6:
            self.pokes.clear()
            self.set_emotion("confused", "Щекотно! Давай помедленнее.", 3)
            return
        if not self.poke_bag:
            self.poke_bag = list(POKES)
            self.rng.shuffle(self.poke_bag)
            if self.poke_bag[-1] == self.last_poke:
                self.poke_bag[0], self.poke_bag[-1] = self.poke_bag[-1], self.poke_bag[0]
        name, text = self.poke_bag.pop()
        self.last_poke = (name, text)
        if name in ("look", "stretch"):
            self.do_activity(name)
            self.say(text, 3)
        else:
            self.set_emotion(name, text, 3)

    def pointer_sample(self, x, y):
        previous = self.cursor
        self.cursor = (x, y)
        moved = previous is not None and math.hypot(x - previous[0], y - previous[1]) > 2
        if not moved:
            return
        self.last_event = self.now
        if self.sleeping:
            self.touch(force=True)
        opts = self.cfg["interaction"]
        if (not opts["follow_cursor"] or self.dancing or self.press or not self.is_free()
                or self.now < self.next_follow or not 0 <= x <= self.width or not 0 <= y <= self.height
                or abs(x - self.x) < 70 * self.scale):
            return
        self.next_follow = self.now + opts["follow_cooldown"]
        if self.rng.random() < opts["follow_chance"]:
            self.follow_until = self.now + opts["follow_duration"]
            self.start_walk(x, fast=True, follow=True)

    def chess_command(self, action):
        if not self.initialized:
            return
        if self.chess is None:
            from chess_ui import ChessPanel
            self.chess = ChessPanel(self)
        if action == "open":
            self.chess.open()
        elif action == "close":
            self.chess.close()
        elif action == "toggle":
            self.chess.toggle()
        else:
            self.chess.open()
            self.chess.new_game(self.chess.player)

    def command(self, message):
        if not isinstance(message, dict):
            return
        if message.get("quit"):
            self.quit_requested = True
            if self.chess is not None:
                self.chess.cancel()
        elif message.get("chess") in ("open", "close", "toggle", "new"):
            self.chess_command(message["chess"])
        elif message.get("music_mode") in ("auto", "on", "off"):
            self.music_mode = message["music_mode"]
            if self.state == "ground" and not self.sleeping:
                self._rest()
        elif message.get("activity") in ACTIVITIES:
            self.do_activity(message["activity"])
        elif isinstance(message.get("emotion"), str) and message["emotion"] in EMOTIONS:
            self.set_emotion(message["emotion"], message.get("text"), message.get("hold"))
