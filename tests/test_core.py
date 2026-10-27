import copy
import json
from pathlib import Path
import random

import pytest

from config import DEFAULT_CONFIG, load_config
from core import Engine, EventProxy

META = json.loads((Path(__file__).resolve().parents[1] / 'frames/animations.json').read_text())


def make_engine(**overrides):
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    cfg['idle']['gap'] = [10000, 10000]
    cfg['idle']['sleep_after'] = 0
    cfg.update(overrides)
    engine = Engine(META, cfg, random.Random(42))
    engine.resize(1280, 720)
    return engine


def advance(engine, seconds):
    for _ in range(round(seconds * 60)):
        engine.tick(1 / 60)


def assert_visible(engine):
    frame = engine.frame()
    box = engine._bbox(frame['file'])
    assert frame['x'] + box[0] * engine.scale >= -1e-6
    assert frame['y'] + box[1] * engine.scale >= -1e-6
    assert frame['x'] + box[2] * engine.scale <= engine.width + 1e-6
    assert frame['y'] + box[3] * engine.scale <= engine.floor + 1e-6


def test_music_continues_across_loops_and_resumes_after_interaction():
    engine = make_engine()
    engine.set_music(True)
    advance(engine, 35)
    assert engine.clip == 'dance'
    engine.set_emotion('wink', 'Привет', hold=2)
    assert engine.clip == 'wink'
    advance(engine, 3)
    assert engine.clip == 'dance'
    engine.set_music(False)
    advance(engine, .1)
    assert engine.clip == 'calm'


def test_music_mode_on_starts_dancing_and_wakes_sleeping_mascot():
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    cfg['music']['mode'] = 'on'
    engine = Engine(META, cfg, random.Random(42))
    engine.resize(1280, 720)
    assert engine.clip == 'dance'
    engine.do_activity('sleep')
    assert engine.sleeping and engine.clip == 'tired'
    engine.set_music(True)
    assert not engine.sleeping and engine.clip == 'dance'


def test_explicit_music_override_and_sleep():
    engine = make_engine()
    engine.command({'music_mode': 'on'})
    engine.set_music(False)
    assert engine.clip == 'dance'
    engine.do_activity('sleep')
    advance(engine, 20)
    assert engine.clip == 'tired'
    engine.do_activity('wake')
    assert engine.clip == 'dance'
    engine.command({'music_mode': 'off'})
    assert engine.clip == 'calm'


@pytest.mark.parametrize('size', [(1280, 720), (320, 240), (80, 60)])
def test_every_animation_stays_visible_at_edges(size):
    engine = make_engine()
    engine.resize(*size)
    for name, clip in META['clips'].items():
        engine.play(name)
        for index in range(len(clip['frames'])):
            engine.idx = index
            for edge in (-9999, 9999):
                engine.x = edge
                assert_visible(engine)


def test_drag_throw_resize_and_fall_never_escape():
    engine = make_engine()
    frame = engine.frame()
    x, y, w, h = frame['hit']
    engine.pointer_press(x + w / 2, y + h / 3)
    for px, py in [(-500, -500), (2000, 1500), (600, 100), (0, 719), (1279, 20)]:
        engine.pointer_move(px, py)
        for _ in range(20):
            engine.tick(1 / 60)
            assert_visible(engine)
    engine.pointer_release(1279, 20)
    engine.resize(350, 220)
    for _ in range(360):
        engine.tick(1 / 60)
        assert_visible(engine)
    assert engine.state == 'ground'
    assert engine.y == engine.floor
    engine.resize(1600, 900)
    assert engine.y == 900
    assert_visible(engine)


def test_random_throw_velocity_is_bounded_after_each_tick():
    engine = make_engine()
    rng = random.Random(2)
    for _ in range(20):
        engine.state = 'air'
        engine.rotating = True
        engine.x = rng.uniform(-500, 1500)
        engine.y = rng.uniform(-500, 1200)
        engine.ang = rng.uniform(-1, 1)
        engine.vx, engine.vy = rng.uniform(-4000, 4000), rng.uniform(-4000, 4000)
        for _ in range(30):
            engine.tick(.05)
            assert_visible(engine)


def test_click_does_not_begin_drag_or_scale_sprite():
    engine = make_engine()
    old_scale = engine.scale
    engine.pointer_press(engine.x, engine.y - 80)
    engine.pointer_move(engine.x + 2, engine.y - 81)
    engine.pointer_release(engine.x + 2, engine.y - 81)
    assert engine.state == 'ground'
    assert not engine.rotating
    assert engine.scale == old_scale
    assert engine.bubble


def test_pokes_do_not_repeat_before_bag_is_exhausted():
    engine = make_engine()
    phrases = []
    for _ in range(12):
        engine.poke()
        phrases.append(engine.bubble)
        advance(engine, 4)
    assert len(set(phrases)) == 12


def test_petting_requires_repeated_strokes_and_does_not_drag():
    engine = make_engine()
    x, y, w, h = engine.frame()['hit']
    for dx in [20, 50, 20, 50, 20]:
        engine.pointer_move(x + dx, y + 20)
        engine.tick(.1)
    assert engine.last_pet >= 0
    assert engine.bubble
    assert engine.state == 'ground'
    assert not engine.dragging


def test_single_hover_pass_does_not_trigger_petting():
    engine = make_engine()
    x, y, w, h = engine.frame()['hit']
    for dx in range(0, int(w), 5):
        engine.pointer_move(x + dx, y + 20)
        engine.tick(.02)
    assert engine.last_pet < 0


def test_following_is_temporary_and_has_cooldown():
    engine = make_engine()
    engine.cfg['interaction']['follow_chance'] = 1
    advance(engine, 6)
    engine.pointer_sample(400, 200)
    engine.pointer_sample(100, 200)
    assert engine.walk and engine.walk['follow']
    advance(engine, 6)
    assert not engine.walk
    engine.pointer_sample(1100, 200)
    assert not engine.walk
    assert_visible(engine)


def test_worker_events_are_applied_on_tick():
    engine = make_engine()
    proxy = EventProxy(engine)
    proxy.set_music(True)
    assert not engine.music
    engine.tick(.01)
    assert engine.music and engine.clip == 'dance'


def test_bad_config_and_nested_defaults(tmp_path):
    path = tmp_path / 'config.json'
    path.write_text('{"scale":"nan", "idle":{"weights":{"walk":7}}, "interaction":{"follow_chance":2}}')
    cfg = load_config(path)
    assert cfg['scale'] == 1
    assert cfg['idle']['weights']['look'] == 3
    assert cfg['interaction']['follow_chance'] == 1
    path.write_text('{"idle":false}')
    with pytest.raises(ValueError, match='idle'):
        load_config(path)


def test_config_rejects_invalid_regex_and_nonfinite_smoke_values(tmp_path):
    path = tmp_path / 'config.json'
    path.write_text('{"app_reactions":[{"match":"["}]}')
    with pytest.raises(ValueError, match='regex'):
        load_config(path)


def test_blink_does_not_postpone_walk():
    engine = make_engine()
    engine.cfg['idle']['weights'] = {'walk': 1}
    engine.next_idle = 7
    engine.rng.random = lambda: 0
    advance(engine, 6)
    assert engine.next_idle == 7
    advance(engine, 2)
    assert engine.walk is not None
    assert engine.clip.startswith('walk_')


def test_autonomous_winks_do_not_prevent_sleep():
    engine = make_engine()
    engine.cfg['idle'].update(gap=[1, 1], sleep_after=15, weights={'wink': 1})
    engine.next_idle = 1
    advance(engine, 20)
    assert engine.sleeping
    assert engine.clip == 'tired'
    assert engine.last_event == 0
    engine.pointer_press(engine.x, engine.y - 60)
    assert not engine.sleeping
    engine.pointer_release(engine.x, engine.y - 60)


def test_system_events_do_not_reset_user_idle_timer():
    engine = make_engine()
    engine.cfg['idle']['sleep_after'] = 10
    for _ in range(5):
        advance(engine, 2)
        engine.react('system', 'wink', hold=.2, cooldown=0)
    advance(engine, 2)
    assert engine.sleeping
    assert engine.last_event == 0


def test_idle_actions_change_without_consecutive_repeats():
    engine = make_engine()
    engine.cfg['idle'].update(gap=[1, 1], weights={'look': 1, 'stretch': 1, 'yawn': 1})
    engine.next_idle = 1
    actions = []
    for _ in range(90 * 60):
        previous = engine.last_idle
        engine.tick(1 / 60)
        if engine.last_idle != previous:
            actions.append(engine.last_idle)
    assert len(actions) >= 10
    assert len(set(actions)) == 3


def test_petting_a_walking_mascot_stops_its_walk():
    engine = make_engine()
    engine.start_walk(100)
    x, y, _, _ = engine.frame()['hit']
    for dx in (20, 50, 20, 50, 20):
        engine.pointer_move(x + dx, y + 20)
    assert engine.walk is None
    assert engine.clip == 'pet'
