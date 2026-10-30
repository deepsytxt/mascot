#!/usr/bin/env python3
   
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
VENV = ROOT / ".venv"
APP_NAME = "deepsy"
APP_COMMENT = "Пиксельный маскот на рабочем столе"
WINDOWS = os.name == "nt"
OPTIONAL_WINDOWS = ("winrt-Windows.Media.Control", "winrt-Windows.Media")
DEV_ONLY = ("pytest",)


class InstallError(RuntimeError):
    pass


def say(text=""):
    print(text, flush=True)


def step(number, total, text):
    say(f"\n[{number}/{total}] {text}")


                                 

def venv_python(gui=False) -> Path:
    if WINDOWS:
        name = "pythonw.exe" if gui else "python.exe"
        path = VENV / "Scripts" / name
        return path if path.exists() else VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def run(command, **kwargs):
    return subprocess.run([str(part) for part in command], cwd=ROOT, **kwargs)


def venv_usable() -> bool:
    python = venv_python()
    if not python.exists():
        return False
    try:
        return run([python, "-c", "pass"], capture_output=True, timeout=30).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def venv_sees_system_packages() -> bool:
    try:
        text = (VENV / "pyvenv.cfg").read_text(encoding="utf-8")
    except OSError:
        return False
    return re.search(r"include-system-site-packages\s*=\s*true", text, re.I) is not None


def ensure_venv():
                                                                             
                                                         
    system_packages = not WINDOWS
    if venv_usable() and (WINDOWS or venv_sees_system_packages()):
        say("Окружение .venv уже есть.")
        return
    if VENV.exists():
        say("Пересоздаю .venv…")
        shutil.rmtree(VENV)
    command = [sys.executable, "-m", "venv"] + (["--system-site-packages"] if system_packages else []) + [VENV]
    result = run(command, capture_output=True, text=True)
    if result.returncode != 0 or not venv_usable():
        hint = "\nНа Debian/Ubuntu: sudo apt install python3-venv" if not WINDOWS else ""
        raise InstallError(f"Не удалось создать .venv.\n{result.stderr.strip()}{hint}")


def runtime_requirements():
    lines = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    specs = []
    for line in lines:
        spec = line.split("#", 1)[0].strip()
        name = re.split(r"[<>=!~\[; ]", spec, 1)[0].lower()
        if spec and name not in DEV_ONLY:
            specs.append(spec)
    return specs


def install_dependencies():
    pip = [venv_python(), "-m", "pip", "install", "--disable-pip-version-check"]
    say("Ставлю зависимости (первый раз может занять пару минут)…")
    if run(pip + ["--upgrade", "pip"], capture_output=True).returncode != 0:
        say("  pip обновить не удалось — продолжаю с текущим.")
    if run(pip + runtime_requirements()).returncode != 0:
        raise InstallError("Не удалось установить зависимости. Проверьте интернет и повторите запуск.")
    if WINDOWS:
        for package in OPTIONAL_WINDOWS:
            if run(pip + [package], capture_output=True).returncode != 0:
                say(f"  необязательный {package} не поставился — танцы под музыку работать не будут.")


def build_icons():
    result = run([venv_python(), ROOT / "tools" / "make_icon.py"], capture_output=True, text=True)
    if result.returncode != 0:
        raise InstallError(f"Не удалось создать иконку.\n{result.stderr.strip()}")


def verify():
    result = run([venv_python(), ROOT / "mascot.py", "--check"], capture_output=True, text=True)
    if result.returncode != 0:
        raise InstallError(f"Проверка проекта не прошла.\n{(result.stdout + result.stderr).strip()}")
    say(result.stdout.strip())
    doctor = run([venv_python(), ROOT / "mascot.py", "--doctor"], capture_output=True, text=True)
    try:
        deps = json.loads(doctor.stdout)["dependencies"]
    except (ValueError, KeyError):
        return
    if not WINDOWS and not (deps.get("PySide6") or (deps.get("gi") and deps.get("cairo"))):
        say("Внимание: нет ни PySide6, ни GTK-биндингов — окно не откроется.")
    if not WINDOWS and not deps.get("gi") and os.environ.get("WAYLAND_DISPLAY"):
        say("Подсказка: для layer-shell (niri и др.) нужны системные пакеты, например на Fedora:\n"
            "  sudo dnf install python3-gobject python3-cairo gtk4-layer-shell\n"
            "Без них маскот попробует работать через XWayland.")


                               

def powershell(script, **env):
    prefix = "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;$ErrorActionPreference='Stop';"
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", prefix + script],
        env=dict(os.environ, **env), capture_output=True, check=False)
    if result.returncode != 0:
        raise InstallError(result.stderr.decode("utf-8", "replace").strip() or "PowerShell завершился с ошибкой")
    return result.stdout.decode("utf-8", "replace").strip()


def windows_folder(kind: str) -> Path:
    return Path(powershell(f"[Environment]::GetFolderPath('{kind}')"))


def windows_shortcut_paths(autostart=False, desktop=True):
    paths = []
    if desktop:
        paths.append(windows_folder("Desktop") / f"{APP_NAME}.lnk")
    paths.append(windows_folder("Programs") / f"{APP_NAME}.lnk")
    if autostart:
        paths.append(windows_folder("Startup") / f"{APP_NAME}.lnk")
    return paths


def make_windows_shortcut(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    powershell(
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:LNK_PATH);"
        "$s.TargetPath=$env:LNK_TARGET;$s.Arguments=$env:LNK_ARGS;$s.WorkingDirectory=$env:LNK_DIR;"
        "$s.IconLocation=$env:LNK_ICON;$s.Description=$env:LNK_DESC;$s.WindowStyle=7;$s.Save()",
        LNK_PATH=str(path), LNK_TARGET=str(venv_python(gui=True)), LNK_ARGS=f'"{ROOT / "launch.py"}"',
        LNK_DIR=str(ROOT), LNK_ICON=f"{ROOT / 'assets' / 'mascot.ico'},0", LNK_DESC=APP_COMMENT)


                             

def _quote_exec(argument: str) -> str:
    argument = argument.replace("%", "%%")
    if argument and not any(char in ' \t\n"\'\\><~|&;$*?#()`' for char in argument):
        return argument
    return '"' + re.sub(r'(["`$\\])', r"\\\1", argument) + '"'


def desktop_exec(arguments) -> str:
                                                                                       
    return " ".join(_quote_exec(str(a)) for a in arguments).replace("\\", "\\\\")


def desktop_entry(autostart=False) -> str:
    lines = [
        "[Desktop Entry]", "Type=Application", "Version=1.0",
        f"Name={APP_NAME}", f"Comment={APP_COMMENT}",
        f"Exec={desktop_exec([venv_python(), ROOT / 'launch.py'])}",
        f"Path={str(ROOT).replace(chr(92), chr(92) * 2)}",
        f"Icon={ROOT / 'assets' / 'mascot.png'}",
        "Terminal=false", "Categories=Utility;", "StartupNotify=false",
    ]
    if autostart:
        lines.append("X-GNOME-Autostart-enabled=true")
    return "\n".join(lines) + "\n"


def _xdg(variable, fallback):
    return Path(os.environ.get(variable) or Path.home() / fallback)


def linux_desktop_dir():
    try:
        out = subprocess.run(["xdg-user-dir", "DESKTOP"], capture_output=True, text=True, timeout=5).stdout.strip()
        if out:
            return Path(out)
    except (OSError, subprocess.TimeoutExpired):
        pass
    return Path.home() / "Desktop"


def linux_shortcut_paths(autostart=False, desktop=True):
    name = f"{APP_NAME}.desktop"
    paths = [_xdg("XDG_DATA_HOME", ".local/share") / "applications" / name]
    if desktop and linux_desktop_dir().is_dir():
        paths.append(linux_desktop_dir() / name)
    if autostart:
        paths.append(_xdg("XDG_CONFIG_HOME", ".config") / "autostart" / name)
    return paths


def make_linux_shortcut(path: Path, autostart=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(desktop_entry(autostart), encoding="utf-8")
    path.chmod(0o755)
    if path.parent == linux_desktop_dir() and shutil.which("gio"):
        subprocess.run(["gio", "set", str(path), "metadata::trusted", "true"], capture_output=True, check=False)


def refresh_linux_menu():
    if shutil.which("update-desktop-database"):
        directory = _xdg("XDG_DATA_HOME", ".local/share") / "applications"
        subprocess.run(["update-desktop-database", str(directory)], capture_output=True, check=False)


                             

def create_shortcuts(autostart, desktop):
    created = []
    if WINDOWS:
        for path in windows_shortcut_paths(autostart, desktop):
            make_windows_shortcut(path)
            created.append(path)
    else:
        for path in linux_shortcut_paths(autostart, desktop):
            make_linux_shortcut(path, autostart=path.parent.name == "autostart")
            created.append(path)
        refresh_linux_menu()
    return created


def launch_now():
    if WINDOWS:
        flags = 0x00000008 | 0x00000200 | 0x08000000                                                    
        subprocess.Popen([str(venv_python(gui=True)), str(ROOT / "launch.py")], cwd=ROOT, creationflags=flags,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
    else:
        subprocess.Popen([str(venv_python()), str(ROOT / "launch.py")], cwd=ROOT, start_new_session=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)


def install(options):
    if sys.version_info < (3, 9):
        raise InstallError("Нужен Python 3.9 или новее.")
    if not (ROOT / "mascot.py").is_file():
        raise InstallError(f"Не похоже на папку проекта: {ROOT}")
    total = 5
    step(1, total, "Python-окружение")
    ensure_venv()
    step(2, total, "Зависимости")
    if options.no_deps:
        say("Пропущено (--no-deps).")
    else:
        install_dependencies()
    step(3, total, "Иконка")
    build_icons()
    step(4, total, "Проверка")
    verify()
    step(5, total, "Ярлыки")
    created = create_shortcuts(options.autostart, not options.no_desktop)
    for path in created:
        say(f"  {path}")
    if not options.no_launch:
        say("\nЗапускаю маскота…")
        launch_now()
    say(f"\nГотово. Ярлык «{APP_NAME}» с головой маскота — на рабочем столе и в меню приложений."
        f"\nЕсли переместите папку проекта, запустите установщик ещё раз.")


def uninstall():
    sys.path.insert(0, str(ROOT))
    try:
        from ipc import send
        if send({"quit": True}):
            say("Маскот остановлен.")
    except ImportError:
        pass
    paths = windows_shortcut_paths(True, True) if WINDOWS else linux_shortcut_paths(True, True)
    for path in paths:
        if path.exists():
            path.unlink()
            say(f"Удалено: {path}")
    if not WINDOWS:
        refresh_linux_menu()
    if VENV.exists():
        shutil.rmtree(VENV, ignore_errors=True)
        say(f"Удалено: {VENV}")
    say("\nГотово. Настройки (config.json) и сама папка проекта не тронуты.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--autostart", action="store_true", help="запускать маскота при входе в систему")
    parser.add_argument("--no-desktop", action="store_true", help="не создавать ярлык на рабочем столе")
    parser.add_argument("--no-launch", action="store_true", help="не запускать маскота после установки")
    parser.add_argument("--no-deps", action="store_true", help="не ставить зависимости через pip")
    parser.add_argument("--uninstall", action="store_true", help="удалить ярлыки, автозапуск и .venv")
    options = parser.parse_args(argv)
    try:
        uninstall() if options.uninstall else install(options)
    except InstallError as error:
        print(f"\nОшибка: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
