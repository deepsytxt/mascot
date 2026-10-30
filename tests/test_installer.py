                                                                                
import importlib.util
from pathlib import Path
import sys

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_runtime_requirements_skip_dev_tools():
    installer = load("deepsy_install", "tools/install.py")
    specs = installer.runtime_requirements()
    assert any(spec.startswith("PySide6") for spec in specs)
    assert not any(spec.lower().startswith("pytest") for spec in specs)


def test_desktop_exec_quotes_spaces_and_percent():
    installer = load("deepsy_install", "tools/install.py")
    assert installer.desktop_exec(["/a b/python", "/a b/100%/launch.py"]) == '"/a b/python" "/a b/100%%/launch.py"'
    assert installer.desktop_exec(["/usr/bin/python", "launch.py"]) == "/usr/bin/python launch.py"


def test_desktop_entry_points_to_launcher_and_icon():
    installer = load("deepsy_install", "tools/install.py")
    entry = installer.desktop_entry(autostart=True)
    assert "launch.py" in entry and "mascot.png" in entry
    assert "Terminal=false" in entry and "X-GNOME-Autostart-enabled=true" in entry


def test_icon_is_square_head_with_all_ico_sizes(tmp_path):
    make_icon = load("deepsy_make_icon", "tools/make_icon.py")
    png, ico = make_icon.build(tmp_path)
    with Image.open(png) as image:
        assert image.size == (256, 256) and image.mode == "RGBA"
        assert image.getchannel("A").getbbox() is not None
    with Image.open(ico) as image:
        assert {(16, 16), (32, 32), (48, 48), (256, 256)} <= set(image.info["sizes"])


def test_second_launch_only_greets_running_mascot(tmp_path, monkeypatch):
    for variable in ("XDG_CONFIG_HOME", "APPDATA"):
        monkeypatch.setenv(variable, str(tmp_path))
    sys.path.insert(0, str(ROOT))
    from ipc import Server
    launch = load("deepsy_launch", "launch.py")
    received = []
    with Server(received.append):
        assert launch.main([], redirect=False) == 0
    assert received == [{"emotion": "joy", "text": "Я здесь!"}]
