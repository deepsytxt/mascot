# deepsy
Поддерживаются:
Linux + Wayland через GTK4 Layer Shell (в том числе niri и другие композиторы, которые поддерживают protocol layer-shell);
Linux X11 и Linux Wayland через XWayland с Qt/PySide6;
Windows 10/11 через Qt/PySide6.

Native Wayland не позволяет обычному Qt-окну свободно менять позицию. Поэтому Qt на Wayland требует XWayland (`DISPLAY`), а GTK backend использует layer-shell. Подробности и ограничения интеграций находятся в [`docs/platforms.md`](docs/platforms.md).

### Windows

```powershell
py -3 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

Windows GSMTC поддерживается при наличии `winrt-Windows.Media.Control` и `winrt-Windows.Media`; без них deepsy продолжает работать, но не включает автоматический танец по музыке.

## Запуск

```bash
.venv/bin/python mascot.py
.venv/bin/python mascot.py --doctor
.venv/bin/python mascot.py --check
.venv/bin/python mascot.py joy "Привет!"
.venv/bin/python mascot.py music auto       # автоматическое определение
.venv/bin/python mascot.py music on         # танцевать всегда
.venv/bin/python mascot.py music off        # не танцевать автоматически
.venv/bin/python mascot.py run cargo build
.venv/bin/python mascot.py quit
```

Для Windows замените `.venv/bin/python` на `.venv\Scripts\python.exe`.
