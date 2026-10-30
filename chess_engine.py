from __future__ import annotations

import random
import time

P, N, B, R, Q, K = 1, 2, 3, 4, 5, 6
WHITE, BLACK = 1, -1
INF = 10 ** 7
MATE = 100000

LEVEL_NAMES = {1: "Новичок", 2: "Любитель", 3: "Клубный", 4: "Мастер"}
                                                             
LEVELS = {1: (1, 0.4, 150), 2: (2, 1.0, 60), 3: (4, 2.5, 0), 4: (8, 6.0, 0)}

START = [R, N, B, Q, K, B, N, R] + [P] * 8 + [0] * 32 + [-P] * 8 + [-p for p in (R, N, B, Q, K, B, N, R)]

KNIGHT_D = ((1, 2), (2, 1), (2, -1), (1, -2), (-1, -2), (-2, -1), (-2, 1), (-1, 2))
KING_D = ((1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1))
ROOK_D = ((1, 0), (-1, 0), (0, 1), (0, -1))
BISHOP_D = ((1, 1), (1, -1), (-1, 1), (-1, -1))


def _targets(deltas):
    table = []
    for sq in range(64):
        f, r = sq & 7, sq >> 3
        table.append([(r + dr) * 8 + f + df for df, dr in deltas if 0 <= f + df < 8 and 0 <= r + dr < 8])
    return table


def _rays(deltas):
    table = []
    for sq in range(64):
        f, r = sq & 7, sq >> 3
        rays = []
        for df, dr in deltas:
            ray, nf, nr = [], f + df, r + dr
            while 0 <= nf < 8 and 0 <= nr < 8:
                ray.append(nr * 8 + nf)
                nf, nr = nf + df, nr + dr
            rays.append(ray)
        table.append(rays)
    return table


KNIGHT_T, KING_T = _targets(KNIGHT_D), _targets(KING_D)
ROOK_R, BISHOP_R = _rays(ROOK_D), _rays(BISHOP_D)
QUEEN_R = [ROOK_R[s] + BISHOP_R[s] for s in range(64)]

                                                                                           
CASTLE_MASK = [15] * 64
for _sq, _mask in ((0, ~2), (7, ~1), (4, ~3), (56, ~8), (63, ~4), (60, ~12)):
    CASTLE_MASK[_sq] = _mask & 15

VALUE = {P: 100, N: 320, B: 330, R: 500, Q: 900, K: 0}


def sq_name(sq):
    return "abcdefgh"[sq & 7] + str((sq >> 3) + 1)


def move_str(m):
    return sq_name(m & 63) + sq_name((m >> 6) & 63) + ("  nbrq"[m >> 12] if m >> 12 else "")


def parse_move(text):
                                           
    try:
        text = text.strip().lower()
        fr = "abcdefgh".index(text[0]) + 8 * (int(text[1]) - 1)
        to = "abcdefgh".index(text[2]) + 8 * (int(text[3]) - 1)
        promo = "  nbrq".index(text[4]) if len(text) > 4 else 0
        if not (0 <= fr < 64 and 0 <= to < 64) or len(text) > 5 or (len(text) == 5 and promo < 2):
            return None
        return fr | to << 6 | promo << 12
    except (ValueError, IndexError):
        return None


class Board:
    def __init__(self):
        self.b = list(START)
        self.side = WHITE
        self.castling = 15
        self.ep = -1
        self.half = 0
        self.kpos = [4, 60]                   

    def copy(self):
        other = Board.__new__(Board)
        other.b = self.b[:]
        other.side, other.castling, other.ep, other.half = self.side, self.castling, self.ep, self.half
        other.kpos = self.kpos[:]
        return other

    def key(self):
        return (tuple(self.b), self.side, self.castling, self.ep)

                                                   
    def attacked(self, sq, by):
        b = self.b
        f, r = sq & 7, sq >> 3
        pr = r - 1 if by == 1 else r + 1
        if 0 <= pr < 8:
            pawn = by * P
            if f > 0 and b[pr * 8 + f - 1] == pawn:
                return True
            if f < 7 and b[pr * 8 + f + 1] == pawn:
                return True
        knight, king = by * N, by * K
        for t in KNIGHT_T[sq]:
            if b[t] == knight:
                return True
        for t in KING_T[sq]:
            if b[t] == king:
                return True
        rook, queen, bishop = by * R, by * Q, by * B
        for ray in ROOK_R[sq]:
            for t in ray:
                p = b[t]
                if p:
                    if p == rook or p == queen:
                        return True
                    break
        for ray in BISHOP_R[sq]:
            for t in ray:
                p = b[t]
                if p:
                    if p == bishop or p == queen:
                        return True
                    break
        return False

    def in_check(self, side=None):
        side = self.side if side is None else side
        return self.attacked(self.kpos[0 if side == 1 else 1], -side)

    def pseudo(self, caps=False):
        b, s, out = self.b, self.side, []
        add = out.append
        for sq in range(64):
            p = b[sq]
            if p * s <= 0:
                continue
            t = p if p > 0 else -p
            if t == P:
                f, r = sq & 7, sq >> 3
                to = sq + 8 * s
                promoting = (to >> 3) in (0, 7)
                if b[to] == 0:
                    if promoting:
                        for pr in ((5,) if caps else (5, 4, 3, 2)):
                            add(sq | to << 6 | pr << 12)
                    elif not caps:
                        add(sq | to << 6)
                        if r == (1 if s == 1 else 6) and b[to + 8 * s] == 0:
                            add(sq | (to + 8 * s) << 6)
                for df in (-1, 1):
                    if 0 <= f + df < 8:
                        t2 = to + df
                        if b[t2] * s < 0:
                            if promoting:
                                for pr in ((5,) if caps else (5, 4, 3, 2)):
                                    add(sq | t2 << 6 | pr << 12)
                            else:
                                add(sq | t2 << 6)
                        elif t2 == self.ep:
                            add(sq | t2 << 6)
            elif t == N or t == K:
                for to in (KNIGHT_T if t == N else KING_T)[sq]:
                    q = b[to]
                    if q * s <= 0 and (q or not caps):
                        add(sq | to << 6)
                if t == K and not caps:
                    self._castles(add)
            else:
                for ray in (BISHOP_R if t == B else ROOK_R if t == R else QUEEN_R)[sq]:
                    for to in ray:
                        q = b[to]
                        if q == 0:
                            if not caps:
                                add(sq | to << 6)
                            continue
                        if q * s < 0:
                            add(sq | to << 6)
                        break
        return out

    def _castles(self, add):
        b, s = self.b, self.side
        base = 0 if s == 1 else 56
        if b[base + 4] != s * K:
            return
        short, long_ = (1, 2) if s == 1 else (4, 8)
        if not self.castling & (short | long_) or self.attacked(base + 4, -s):
            return
        if (self.castling & short and b[base + 7] == s * R and not b[base + 5] and not b[base + 6]
                and not self.attacked(base + 5, -s) and not self.attacked(base + 6, -s)):
            add((base + 4) | (base + 6) << 6)
        if (self.castling & long_ and b[base] == s * R and not b[base + 1] and not b[base + 2] and not b[base + 3]
                and not self.attacked(base + 3, -s) and not self.attacked(base + 2, -s)):
            add((base + 4) | (base + 2) << 6)

                                       
    def make(self, m):
        b, s = self.b, self.side
        fr, to, promo = m & 63, (m >> 6) & 63, m >> 12
        p = b[fr]
        t = p if p > 0 else -p
        cap, capsq = b[to], to
        if t == P and to == self.ep and not cap and (fr & 7) != (to & 7):
            capsq = to - 8 * s
            cap = b[capsq]
            b[capsq] = 0
        undo = (m, p, cap, capsq, self.castling, self.ep, self.half, self.kpos[0], self.kpos[1])
        b[fr] = 0
        b[to] = s * promo if promo else p
        if t == K:
            self.kpos[0 if s == 1 else 1] = to
            if to - fr == 2:
                b[fr + 1], b[fr + 3] = b[fr + 3], 0
            elif fr - to == 2:
                b[fr - 1], b[fr - 4] = b[fr - 4], 0
        self.castling &= CASTLE_MASK[fr] & CASTLE_MASK[to]
        self.ep = (fr + to) // 2 if t == P and abs(to - fr) == 16 else -1
        self.half = 0 if t == P or cap else self.half + 1
        self.side = -s
        return undo

    def unmake(self, u):
        m, p, cap, capsq, self.castling, self.ep, self.half, kw, kb = u
        self.kpos[0], self.kpos[1] = kw, kb
        self.side = s = -self.side
        b = self.b
        fr, to = m & 63, (m >> 6) & 63
        b[fr] = p
        b[to] = 0
        b[capsq] = cap
        if (p if p > 0 else -p) == K:
            if to - fr == 2:
                b[fr + 3], b[fr + 1] = b[fr + 1], 0
            elif fr - to == 2:
                b[fr - 4], b[fr - 1] = b[fr - 1], 0

    def make_legal(self, m):
                                                                                                    
        s = self.side
        u = self.make(m)
        if self.attacked(self.kpos[0 if s == 1 else 1], -s):
            self.unmake(u)
            return None
        return u

    def legal_moves(self):
        out = []
        for m in self.pseudo():
            u = self.make_legal(m)
            if u is not None:
                out.append(m)
                self.unmake(u)
        return out

    def insufficient(self):
        minors = 0
        for p in self.b:
            t = p if p > 0 else -p
            if t in (P, R, Q):
                return False
            if t in (N, B):
                minors += 1
        return minors <= 1

    def result(self, history=()):
                                                               
        if not self.legal_moves():
            return ("mate", -self.side) if self.in_check() else ("draw", "пат")
        if self.insufficient():
            return ("draw", "не хватает материала")
        if self.half >= 100:
            return ("draw", "правило 50 ходов")
        if history and list(history).count(self.key()) >= 3:
            return ("draw", "троекратное повторение")
        return None


def perft(board, depth):
    if depth == 0:
        return 1
    total = 0
    for m in board.pseudo():
        u = board.make_legal(m)
        if u is not None:
            total += perft(board, depth - 1)
            board.unmake(u)
    return total


                              
def evaluate(board):
                                                       
    score = mat = 0
    kings = []
    bishops = [0, 0]
    for sq, p in enumerate(board.b):
        if not p:
            continue
        t = p if p > 0 else -p
        f, r = sq & 7, sq >> 3
        rr = r if p > 0 else 7 - r
        cd = abs(2 * f - 7) + abs(2 * r - 7)                           
        if t == P:
            v = 100 + rr * 6 + (rr * 2 if 3 <= f <= 4 else 0)
        elif t == N:
            v = 320 + (10 - cd) * 4
            mat += 320
        elif t == B:
            v = 330 + (10 - cd) * 2
            mat += 330
            bishops[0 if p > 0 else 1] += 1
        elif t == R:
            v = 500 + (15 if rr == 6 else 0)
            mat += 500
        elif t == Q:
            v = 900 + (10 - cd)
            mat += 900
        else:
            kings.append((p, f, rr, cd))
            continue
        score += v if p > 0 else -v
    endgame = mat < 2600
    for p, f, rr, cd in kings:
        v = 4 * (14 - cd) if endgame else -rr * 10 + (25 if rr == 0 and f in (1, 2, 6) else 0)
        score += v if p > 0 else -v
    score += 25 * ((bishops[0] > 1) - (bishops[1] > 1))
    return score if board.side == 1 else -score


class _Timeout(Exception):
    pass


class Searcher:
    def __init__(self, board, stop, deadline):
        self.b, self.stop, self.deadline = board, stop, deadline
        self.nodes = 0

    def tick(self):
        self.nodes += 1
        if not self.nodes & 255:
            time.sleep(0.0005)                                              
            if self.stop.is_set() or time.monotonic() > self.deadline:
                raise _Timeout

    def order(self, moves):
        b = self.b.b

        def key(m):
            to = (m >> 6) & 63
            victim = b[to]
            score = 0
            if victim:
                score = 10 * VALUE[abs(victim)] - VALUE[abs(b[m & 63])] + 1000
            elif abs(b[m & 63]) == P and to == self.b.ep:
                score = 1000 + 100
            if m >> 12:
                score += 800 + 10 * (m >> 12)
            return -score
        return sorted(moves, key=key)

    def qs(self, alpha, beta):
        self.tick()
        stand = evaluate(self.b)
        if stand >= beta:
            return stand
        alpha = max(alpha, stand)
        board = self.b
        for m in self.order(board.pseudo(caps=True)):
            u = board.make_legal(m)
            if u is None:
                continue
            score = -self.qs(-beta, -alpha)
            board.unmake(u)
            if score >= beta:
                return score
            alpha = max(alpha, score)
        return alpha

    def negamax(self, depth, alpha, beta, ply):
        self.tick()
        board = self.b
        if board.half >= 100 or board.insufficient():
            return 0
        checked = board.in_check()
        if checked and ply < 24:
            depth += 1
        if depth <= 0:
            return self.qs(alpha, beta)
        best, legal = -INF, 0
        for m in self.order(board.pseudo()):
            u = board.make_legal(m)
            if u is None:
                continue
            legal += 1
            score = -self.negamax(depth - 1, -beta, -alpha, ply + 1)
            board.unmake(u)
            if score > best:
                best = score
                if best > alpha:
                    alpha = best
                    if alpha >= beta:
                        break
        if not legal:
            return -MATE + ply if checked else 0
        return best


def best_move(board, level=2, history=(), stop=None, rng=None):
                                                                               
    import threading
    stop = stop or threading.Event()
    rng = rng or random.Random()
    depth_max, seconds, noise = LEVELS.get(level, LEVELS[2])
    board = board.copy()
    moves = board.legal_moves()
    if not moves:
        return None
    if len(moves) == 1:
        return moves[0]
    search = Searcher(board, stop, time.monotonic() + seconds)
    order = search.order(moves)
    scores = {}
    try:
        for depth in range(1, depth_max + 1):
            current = {}
            alpha = -INF
            for m in order:
                u = board.make(m)
                score = -search.negamax(depth - 1, -INF, INF if noise else -alpha, 1)
                if history and board.key() in history:
                    score -= 40                                   
                board.unmake(u)
                current[m] = score
                if score > alpha:
                    alpha = score
            scores = current
            order = sorted(order, key=lambda m: -current[m])
            if abs(max(current.values())) > MATE - 100:
                break
    except _Timeout:
        pass
    if not scores:
        return order[0]
    return max(scores, key=lambda m: scores[m] + (rng.uniform(-noise, noise) if noise else 0))
