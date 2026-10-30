   
from __future__ import annotations

import json
import random
import threading

from chess_engine import (B, K, LEVEL_NAMES, N, P, Q, R, WHITE, BLACK, Board, best_move)
from config import config_dir

                                                    
BG, EDGE, HEAD = "#173d2a", "#6b9b52", "#2f5d3e"
LIGHT, DARK, FRAME = "#d9e4c5", "#6b9b52", "#12291d"
TEXT, MUTED = "#f7f4e8", "#b9c8a8"
SEL, LAST, CHECK, CAPTURE, DOT = "#d8bd55", "#aebf79", "#b46b57", "#a47a52", "#2f5d3e"

                                                                      
W_ART, H_ART = 140, 178
BX, BY, SQ = 6, 16, 16
HEADER, STATUS_Y, BUTTON_Y, BUTTON_H = 14, 146, 160, 12
BUTTONS = (("new", 6), ("undo", 39), ("level", 72), ("color", 105))
BUTTON_W = 29
CLOSE_RECT = (126, 2, 12, 10)
PROMO_RECT = (34, BY + 52, 72, 24)

SPRITES = {
    P: ("............", "............", "....####....", "...######...", "...######...", "....####....",
        ".....##.....", "....####....", "....####....", "...######...", "..########..", "..########.."),
    N: ("............", "....##......", "...####.....", "..#######...", ".########...", ".#.######...",
        ".....#####..", "....######..", "...#######..", "..########..", "..########..", "..########.."),
    B: (".....##.....", "....####....", "...######...", "...######...", "....####....", ".....##.....",
        "....####....", "...######...", "....####....", "...######...", "..########..", "..########.."),
    R: ("............", "..##.##.##..", "..########..", "..########..", "...######...", "...######...",
        "...######...", "...######...", "...######...", "..########..", "..########..", "............"),
    Q: (".#...##...#.", ".##.####.##.", "..########..", "..########..", "...######...", "...######...",
        "....####....", "...######...", "...######...", "..########..", "..########..", "..########.."),
    K: (".....##.....", "...######...", ".....##.....", "....####....", "...######...", "..########..",
        "...######...", "...######...", "...######...", "..########..", "..########..", "..########.."),
}
PIECE_COLORS = {WHITE: ("#fdfdfe", "#cfe3b5", "#15512f"), BLACK: ("#15512f", "#639f3d", "#0a2916")}


def _build_runs(kind, side):
    fill_c, accent_c, outline_c = PIECE_COLORS[side]
    rows = SPRITES[kind]
    fill = {(x + 1, y + 1) for y, row in enumerate(rows) for x, c in enumerate(row) if c == "#"}
    cells = {}
    for x, y in fill:
        edge = (x + 1, y) not in fill if side == WHITE else (x - 1, y) not in fill
        cells[(x, y)] = accent_c if edge else fill_c
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if (nx, ny) not in fill and 0 <= nx < 14 and 0 <= ny < 14:
                cells[(nx, ny)] = outline_c
    runs = []
    for y in range(14):
        x = 0
        while x < 14:
            color = cells.get((x, y))
            if color is None:
                x += 1
                continue
            end = x
            while end + 1 < 14 and cells.get((end + 1, y)) == color:
                end += 1
            runs.append((x + 1, y + 1, end - x + 1, 1, color))
            x = end + 1
    return runs


PIECE_RUNS = {(kind, side): _build_runs(kind, side) for kind in SPRITES for side in (WHITE, BLACK)}

GREETINGS = ("Сыграем? Твои — белые.", "Партию? Ходи первым!")
CAPTURE_BY_ME = ("Взято.", "Фигура снята.", "Хороший размен.")
CAPTURE_BY_YOU = ("Фигура снята.", "Хороший размен.", "Размен принят.")


class ChessPanel:
    def __init__(self, engine, path="default"):
        self.engine = engine
        cc = engine.cfg.get("chess", {})
        self.max_scale = int(cc.get("scale", 3))
        self.u = self.max_scale
        self.level = int(cc.get("level", 2))
        self.player = WHITE
        self.path = (config_dir() / "chess.json") if path == "default" else path
        self.visible = False
        self.x = self.y = 0.0
        self.board = None
        self.moves, self.keys = [], []
        self.last = None
        self.sel = None
        self.targets, self.promo = {}, None
        self.legal = []
        self.over = None
        self.thinking = False
        self.token = 0
        self.stop = threading.Event()
        self._result = None
        self._ready_at = 0.0
        self._phase = -1
        self._down = None
        self._dragging = False
        self._scene = None
        self._last_react = -100.0

                                   
    @property
    def size(self):
        return W_ART * self.u, H_ART * self.u

    def contains(self, x, y):
        w, h = self.size
        return self.visible and self.x <= x < self.x + w and self.y <= y < self.y + h

    def _fit(self):
        e = self.engine
        u = max(1, min(self.max_scale, int(e.width // W_ART), int(e.height // H_ART)))
        if u != self.u:
            self.u, self._scene = u, None
        self._clamp()

    def _clamp(self):
        w, h = self.size
        self.x = max(0.0, min(self.x, self.engine.width - w))
        self.y = max(0.0, min(self.y, self.engine.height - h))

    def _place(self):
        e = self.engine
        w, h = self.size
        hx, _, hw, _ = e.frame()["hit"]
        x = hx - w - 16
        if x < 0:
            x = hx + hw + 16
        if x + w > e.width:
            x = (e.width - w) / 2
        self.x, self.y = x, e.floor - h - 6
        self._clamp()

                                             
    def open(self):
        if self.visible:
            return
        self.visible = True
        self._fit()
        self._place()
        self._scene = None
        if self.board is None and not self.load():
            self.new_game(WHITE)
        elif not self.over and not self.thinking and self.board.side != self.player:
            self.start_ai()

    def close(self):
        self.cancel()
        self.visible = False
        self.save()

    def toggle(self):
        self.close() if self.visible else self.open()

                                      
    def save(self):
        if not self.path or self.board is None:
            return
        try:
            tmp = self.path.with_suffix(".tmp")
            tmp.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps({"player": self.player, "level": self.level, "moves": self.moves}), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            pass

    def load(self):
        if not self.path:
            return False
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            player = data["player"]
            moves = [int(m) for m in data["moves"]]
            if player not in (WHITE, BLACK) or not 0 <= len(moves) < 1000:
                return False
            level = int(data.get("level", self.level))
        except (OSError, ValueError, KeyError, TypeError):
            return False
        if not self.replay(moves) or not moves:
            return False
        self.player, self.level = player, min(max(level, 1), len(LEVEL_NAMES))
        self.over = self.board.result(self.keys)
        self._refresh()
        if not self.over and self.board.side != self.player:
            self.start_ai()
        self.say("Продолжим партию?", "wink")
        return True

    def replay(self, moves):
        board, keys = Board(), []
        keys.append(board.key())
        for m in moves:
            if m not in board.legal_moves():
                return False
            board.make(m)
            keys.append(board.key())
        self.board, self.moves, self.keys = board, list(moves), keys
        self.last = ((moves[-1] & 63, (moves[-1] >> 6) & 63) if moves else None)
        self.sel, self.targets, self.promo = None, {}, None
        return True

                                  
    def new_game(self, player=None):
        self.cancel()
        if player is not None:
            self.player = player
        self.replay([])
        self.over = None
        self._refresh()
        self.save()
        if self.board.side != self.player:
            self.say("Я хожу первым!", "wink")
            self.start_ai()
        else:
            self.say(GREETINGS[0] if self.player == WHITE else GREETINGS[1], "joy")

    def _refresh(self):
        self.legal = self.board.legal_moves()
        self._scene = None

    def play(self, m, by_player):
        board = self.board
        fr, to = m & 63, (m >> 6) & 63
        moved = abs(board.b[fr])
        captured = bool(board.b[to]) or (moved == P and to == board.ep and (fr & 7) != (to & 7))
        board.make(m)
        self.moves.append(m)
        self.keys.append(board.key())
        self.last = (fr, to)
        self.sel, self.targets, self.promo = None, {}, None
        self.over = board.result(self.keys)
        self._refresh()
        self.save()
        self._react(by_player, captured)
        if not self.over and board.side != self.player:
            self.start_ai()

    def undo(self):
        if not self.moves:
            return
        self.cancel()
        keep = self.moves[:-1]
                                                                            
        if keep and (WHITE if len(keep) % 2 == 0 else BLACK) != self.player:
            keep = keep[:-1]
        self.replay(keep)
        self.over = None
        self._refresh()
        self.save()
        self.say("Ладно, возьми ход назад.", "surprise")
        if self.board.side != self.player:
            self.start_ai()

                                                 
    def start_ai(self):
        self.cancel()
        self.token += 1
        token, stop = self.token, threading.Event()
        self.stop, self.thinking = stop, True
        self._ready_at = self.engine.now + 0.6
        board, history, level = self.board.copy(), list(self.keys), self.level

        def work():
            try:
                move = best_move(board, level, history, stop, random.Random())
            except Exception:                                                 
                move = None
            if not stop.is_set():
                self._result = (token, move)

        threading.Thread(target=work, name="deepsy-chess", daemon=True).start()
        if self.level >= 3:
            self.engine.say("Думаю…", 2)
        self._scene = None

    def cancel(self):
        self.token += 1
        self.stop.set()
        self.thinking = False
        self._result = None

    def tick(self, now):
        if not self.visible:
            return
        if self.thinking:
            phase = int(now * 2.5) % 3
            if phase != self._phase:
                self._phase, self._scene = phase, None
            result = self._result
            if result and result[0] == self.token and now >= self._ready_at:
                self._result = None
                self.thinking = False
                if result[1] in self.legal:
                    self.play(result[1], False)
                else:
                    self.over = self.board.result(self.keys)
                    self._scene = None
        self._clamp()

                                             
    def say(self, text, emotion="calm", hold=3.5):
        try:
            self.engine.set_emotion(emotion, text, hold)
        except Exception:
            pass

    def _react(self, by_player, captured):
        e, rng = self.engine, self.engine.rng
        if self.over:
            kind, who = self.over[0], self.over[1]
            if kind == "mate":
                if who == self.player:
                    self.say("Мат… Ты победил!", "sad", 6)
                else:
                    self.say("Мат! Хорошая партия.", "joy", 6)
            else:
                self.say(f"Ничья: {who}.", "confused", 5)
            return
        check = self.board.in_check()
        recent = e.now - self._last_react < 4
        if check:
            self.say("Шах!" if not by_player else "Ой, шах!", "wink" if not by_player else "fear", 3)
        elif captured and not recent:
            if by_player:
                self.say(rng.choice(CAPTURE_BY_YOU), "sad", 2.5)
            else:
                self.say(rng.choice(CAPTURE_BY_ME), "joy", 2.5)
        else:
            return
        self._last_react = e.now

                                
    def press(self, x, y):
        if not self.contains(x, y):
            return False
        self.engine.touch()
        self._down = (x - self.x, y - self.y)
        self._dragging = False
        return True

    def move(self, x, y):
        if self._down is None:
            return False
        lx, ly = self._down
        u = self.u
        in_header = ly < HEADER * u and not self._in(lx / u, ly / u, CLOSE_RECT)
        if in_header:
            if not self._dragging and abs(x - self.x - lx) + abs(y - self.y - ly) > 6:
                self._dragging = True
            if self._dragging:
                self.x, self.y = x - lx, y - ly
                self._clamp()
        return True

    def release(self, x, y):
        if self._down is None:
            return False
        dragged, self._down, self._dragging = self._dragging, None, False
        if not dragged:
            self._click((x - self.x) / self.u, (y - self.y) / self.u)
        return True

    @staticmethod
    def _in(ax, ay, rect):
        return rect[0] <= ax < rect[0] + rect[2] and rect[1] <= ay < rect[1] + rect[3]

    def _click(self, ax, ay):
        self.engine.touch()
        if self._in(ax, ay, CLOSE_RECT):
            self.close()
            return
        if self.promo:
            self._promo_click(ax, ay)
            return
        for name, bx in BUTTONS:
            if self._in(ax, ay, (bx, BUTTON_Y, BUTTON_W, BUTTON_H)):
                self._button(name)
                return
        if BX <= ax < BX + 8 * SQ and BY <= ay < BY + 8 * SQ:
            col, row = int((ax - BX) // SQ), int((ay - BY) // SQ)
            if self.player == WHITE:
                sq = (7 - row) * 8 + col
            else:
                sq = row * 8 + (7 - col)
            self._square(sq)

    def _button(self, name):
        if name == "new":
            self.new_game(self.player)
        elif name == "undo":
            self.undo()
        elif name == "level":
            self.level = self.level % len(LEVEL_NAMES) + 1
            self.save()
            self._scene = None
            self.say(f"Уровень: {LEVEL_NAMES[self.level]}.", "wink", 2.5)
        elif name == "color":
            self.new_game(-self.player)

    def _square(self, sq):
        if self.board is None or self.over or self.board.side != self.player:
            return
        if self.thinking:
            self.engine.say("Подожди, я думаю…", 1.5)
            return
        if sq in self.targets:
            moves = self.targets[sq]
            if len(moves) > 1:
                self.promo = sorted(moves, key=lambda m: -(m >> 12))
                self._scene = None
            else:
                self.play(moves[0], True)
            return
        piece = self.board.b[sq]
        if piece * self.player > 0:
            self.sel = sq
            self.targets = {}
            for m in self.legal:
                if m & 63 == sq:
                    self.targets.setdefault((m >> 6) & 63, []).append(m)
        else:
            self.sel, self.targets = None, {}
        self._scene = None

    def _promo_click(self, ax, ay):
        px, py, pw, ph = PROMO_RECT
        index = int((ax - px - 4) // SQ)
        if self._in(ax, ay, PROMO_RECT) and 0 <= index < len(self.promo) and py + 4 <= ay < py + 4 + SQ:
            self.play(self.promo[index], True)
        else:
            self.promo = None
            self._scene = None

                                     
    def status(self):
        if self.over:
            kind, who = self.over
            if kind == "mate":
                return "Мат! Ты победил!" if who == self.player else "Мат. Я победил!"
            return f"Ничья: {who}"
        if self.thinking:
            return "Думаю" + "." * (1 + max(self._phase, 0))
        if self.board.side == self.player:
            return "Твой ход — шах!" if self.board.in_check() else "Твой ход"
        return "Ход соперника"

    def scene(self):
        if self._scene is None:
            self._scene = self._build()
        return self._scene

    def _square_xy(self, sq):
        f, r = sq & 7, sq >> 3
        if self.player == WHITE:
            return BX + f * SQ, BY + (7 - r) * SQ
        return BX + (7 - f) * SQ, BY + r * SQ

    def _build(self):
        u = self.u
        out = []
        rect = lambda x, y, w, h, c: out.append(("r", x * u, y * u, w * u, h * u, c))
        px = max(9, 4 * u)
        text = lambda x, y, w, h, s, c, align="c": out.append(("t", x * u, y * u, w * u, h * u, s, c, px, align))
        rect(0, 0, W_ART, H_ART, EDGE)
        rect(1, 1, W_ART - 2, H_ART - 2, BG)
        rect(1, 1, W_ART - 2, HEADER - 1, HEAD)
        text(5, 1, 118, HEADER - 1, "Шахматы", TEXT, "l")
        rect(*CLOSE_RECT, EDGE)
        text(*CLOSE_RECT, "×", FRAME)
        rect(BX - 1, BY - 1, 8 * SQ + 2, 8 * SQ + 2, FRAME)
        board = self.board
        check_sq = board.kpos[0 if board.side == WHITE else 1] if board.in_check() else -1
        for sq in range(64):
            x, y = self._square_xy(sq)
            color = LIGHT if ((sq & 7) + (sq >> 3)) % 2 else DARK
            if self.last and sq in self.last:
                color = LAST
            if sq == check_sq:
                color = CHECK
            if sq == self.sel:
                color = SEL
            if sq in self.targets and board.b[sq]:
                color = CAPTURE
            rect(x, y, SQ, SQ, color)
            piece = board.b[sq]
            if piece:
                for rx, ry, rw, rh, c in PIECE_RUNS[(abs(piece), WHITE if piece > 0 else BLACK)]:
                    rect(x + rx, y + ry, rw, rh, c)
            elif sq in self.targets:
                rect(x + 6, y + 6, 4, 4, DOT)
        text(6, STATUS_Y, 128, 12, self.status(), TEXT if not self.over else SEL)
        labels = {"new": "Новая", "undo": "Назад", "level": f"Ур. {self.level}",
                  "color": "Белыми" if self.player == WHITE else "Чёрными"}
        for name, bx in BUTTONS:
            off = name == "undo" and not self.moves
            rect(bx, BUTTON_Y, BUTTON_W, BUTTON_H, EDGE)
            rect(bx + 1, BUTTON_Y + 1, BUTTON_W - 2, BUTTON_H - 2, HEAD)
            text(bx, BUTTON_Y, BUTTON_W, BUTTON_H, labels[name], MUTED if off else TEXT)
        if self.promo:
            x, y, w, h = PROMO_RECT
            rect(x - 1, y - 1, w + 2, h + 2, FRAME)
            rect(x, y, w, h, HEAD)
            for i, m in enumerate(self.promo):
                cx = x + 4 + i * SQ
                rect(cx, y + 4, SQ, SQ, LIGHT if i % 2 else DARK)
                for rx, ry, rw, rh, c in PIECE_RUNS[(m >> 12, self.player)]:
                    rect(cx + rx, y + 4 + ry, rw, rh, c)
        return out
