                                                                              
import threading
import time

import chess_engine as ce
import chess_ui
from chess_engine import Board, best_move, move_str, parse_move, perft
from chess_ui import ChessPanel
from test_core import advance, make_engine


def setup(rows, side=1, castling=0, ep=-1):
    board = Board()
    board.b = [0] * 64
    codes = {"P": 1, "N": 2, "B": 3, "R": 4, "Q": 5, "K": 6}
    for index, row in enumerate(rows.split("/")):
        rank, file = 7 - index, 0
        for ch in row:
            if ch.isdigit():
                file += int(ch)
                continue
            piece = codes[ch.upper()] * (1 if ch.isupper() else -1)
            board.b[rank * 8 + file] = piece
            if abs(piece) == 6:
                board.kpos[0 if piece > 0 else 1] = rank * 8 + file
            file += 1
    board.side, board.castling, board.ep = side, castling, ep
    return board


def legal_strings(board):
    return {move_str(m) for m in board.legal_moves()}


def test_perft_reference_positions():
    assert perft(Board(), 3) == 8902
    kiwipete = setup("r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R", 1, 15)
    assert perft(kiwipete, 2) == 2039
    rook_ending = setup("8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8", 1, 0)
    assert perft(rook_ending, 3) == 2812


def test_special_moves():
    board = setup("r3k2r/8/8/8/8/8/8/R3K2R", 1, 15)
    assert {"e1g1", "e1c1"} <= legal_strings(board)
    board = setup("r3k2r/8/8/8/8/8/8/R3K2R", 1, 15)
    board.b[61] = -ce.R                            
    assert "e1g1" not in legal_strings(board)
    ep = setup("4k3/8/8/3pP3/8/8/8/4K3", 1, 0, ep=43)
    assert "e5d6" in legal_strings(ep)
    ep.make(parse_move("e5d6"))
    assert ep.b[35] == 0                     
    promo = setup("4k3/P7/8/8/8/8/8/4K3", 1, 0)
    assert {"a7a8q", "a7a8r", "a7a8b", "a7a8n"} <= legal_strings(promo)


def test_make_unmake_restores_position():
    board = setup("r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R", 1, 15)
    before = (board.key(), list(board.kpos), board.half)
    for m in board.legal_moves():
        undo = board.make(m)
        board.unmake(undo)
        assert (board.key(), list(board.kpos), board.half) == before


def test_game_results():
    mate = setup("7k/6Q1/6K1/8/8/8/8/8", -1, 0)
    assert mate.result() == ("mate", 1)
    stalemate = setup("7k/5Q2/8/6K1/8/8/8/8", -1, 0)
    assert stalemate.legal_moves() == [] and stalemate.result()[0] == "draw"
    assert setup("4k3/8/8/8/8/8/8/4KB2", 1, 0).result()[0] == "draw"


def test_ai_finds_mate_and_wins_material():
    mate_in_one = setup("6k1/5ppp/8/8/8/8/8/R5K1", 1, 0)
    assert move_str(best_move(mate_in_one, 3)) == "a1a8"
    free_queen = setup("4k3/8/8/3q4/8/8/8/3RK3", 1, 0)
    assert move_str(best_move(free_queen, 2)) == "d1d5"


def test_ai_stops_quickly_on_request():
    stop = threading.Event()
    result = []
    thread = threading.Thread(target=lambda: result.append(best_move(Board(), 4, (), stop)))
    start = time.monotonic()
    thread.start()
    stop.set()
    thread.join(3)
    assert not thread.is_alive() and time.monotonic() - start < 3


                                          
def make_panel(tmp_path, level=1):
    engine = make_engine()
    panel = ChessPanel(engine, path=tmp_path / "chess.json")
    panel.level = level
    engine.chess = panel
    panel.open()
    return engine, panel


def click_square(engine, panel, name):
    sq = parse_move(name + name)  & 63
    x, y = panel._square_xy(sq)
    px, py = panel.x + (x + 8) * panel.u, panel.y + (y + 8) * panel.u
    assert panel.press(px, py)
    assert panel.release(px, py)


def wait_for_ai(engine, panel, seconds=8):
    deadline = time.monotonic() + seconds
    while panel.thinking and time.monotonic() < deadline:
        advance(engine, .05)
        time.sleep(.02)
    assert not panel.thinking


def test_panel_opens_beside_the_mascot_inside_the_screen(tmp_path):
    engine, panel = make_panel(tmp_path)
    width, height = panel.size
    assert panel.visible and panel.contains(panel.x + 1, panel.y + 1)
    assert 0 <= panel.x and panel.x + width <= engine.width
    assert 0 <= panel.y and panel.y + height <= engine.height
    for item in panel.scene():
        assert 0 <= item[1] and item[1] + item[3] <= width
        assert 0 <= item[2] and item[2] + item[4] <= height


def test_player_move_then_ai_reply_and_undo(tmp_path):
    engine, panel = make_panel(tmp_path)
    click_square(engine, panel, "e2")
    assert {"e3", "e4"} == {ce.sq_name(t) for t in panel.targets}
    click_square(engine, panel, "e4")
    assert panel.moves[0] == parse_move("e2e4") and panel.thinking
    wait_for_ai(engine, panel)
    assert len(panel.moves) == 2 and panel.board.side == ce.WHITE
    panel.undo()
    assert panel.moves == [] and panel.board.key() == Board().key()


def test_illegal_clicks_are_ignored(tmp_path):
    engine, panel = make_panel(tmp_path)
    click_square(engine, panel, "e7")                
    click_square(engine, panel, "e5")
    click_square(engine, panel, "a1")                   
    click_square(engine, panel, "a5")
    assert panel.moves == []


def test_playing_black_lets_the_ai_open(tmp_path):
    engine, panel = make_panel(tmp_path)
    panel.new_game(ce.BLACK)
    assert panel.thinking
    wait_for_ai(engine, panel)
    assert len(panel.moves) == 1 and panel.board.side == ce.BLACK
                                                 
    assert panel._square_xy(56)[0] > panel._square_xy(63)[0]


def test_promotion_chooser(tmp_path):
    engine, panel = make_panel(tmp_path)
    panel.cancel()
    panel.board = setup("4k3/P7/8/8/8/8/8/4K3", 1, 0)
    panel.moves, panel.keys = [], [panel.board.key()]
    panel._refresh()
    click_square(engine, panel, "a7")
    click_square(engine, panel, "a8")
    assert panel.promo and len(panel.promo) == 4 and not panel.moves
    px, py, _, _ = chess_ui.PROMO_RECT
    x, y = panel.x + (px + 4 + 8) * panel.u, panel.y + (py + 4 + 8) * panel.u
    panel.press(x, y)
    panel.release(x, y)                                
    assert panel.board.b[56] == ce.Q


def test_checkmate_ends_game_and_blocks_input(tmp_path):
    engine, panel = make_panel(tmp_path)
    panel.cancel()
    assert panel.replay([parse_move(m) for m in ("f2f3", "e7e5", "g2g4", "d8h4")])
    panel.over = panel.board.result(panel.keys)
    panel._refresh()
    assert panel.over == ("mate", ce.BLACK)
    assert "Я победил" in panel.status()
    click_square(engine, panel, "e2")
    assert panel.targets == {}


def test_game_is_saved_and_resumed(tmp_path):
    engine, panel = make_panel(tmp_path)
    click_square(engine, panel, "d2")
    click_square(engine, panel, "d4")
    wait_for_ai(engine, panel)
    saved = list(panel.moves)
    panel.close()
    other = ChessPanel(make_engine(), path=tmp_path / "chess.json")
    assert other.load() and other.moves == saved and other.board.key() == panel.board.key()


def test_corrupt_save_falls_back_to_new_game(tmp_path):
    (tmp_path / "chess.json").write_text('{"player": 1, "moves": [1, 2, 3]}')
    engine, panel = make_panel(tmp_path)
    assert panel.moves == [] and panel.board.key() == Board().key()


def test_panel_dragging_stays_on_screen(tmp_path):
    engine, panel = make_panel(tmp_path)
    x, y = panel.x + 20, panel.y + 5
    panel.press(x, y)
    panel.move(x - 5000, y - 5000)
    panel.release(x - 5000, y - 5000)
    assert (panel.x, panel.y) == (0, 0) and panel.moves == []


def test_command_opens_and_closes_panel(tmp_path, monkeypatch):
    monkeypatch.setattr(chess_ui, "config_dir", lambda: tmp_path)
    engine = make_engine()
    engine.command({"chess": "open"})
    assert engine.chess.visible
    engine.command({"chess": "toggle"})
    assert not engine.chess.visible
    engine.command({"quit": True})
