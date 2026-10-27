# deepsy

`deepsy` — пиксельный маскот для рабочего стола. Он ходит по нижней границе рабочей области, реагирует на музыку и системные события, его можно перетаскивать, гладить и иногда отправлять бежать за курсором.

Поддерживаются:

- Linux + Wayland через GTK4 Layer Shell (в том числе niri и другие композиторы, которые поддерживают protocol layer-shell);
- Linux X11 и Linux Wayland через XWayland с Qt/PySide6;
- Windows 10/11 через Qt/PySide6.

Native Wayland не позволяет обычному Qt-окну свободно менять позицию. Поэтому Qt на Wayland требует XWayland (`DISPLAY`), а GTK backend использует layer-shell. Подробности и ограничения интеграций находятся в [`docs/platforms.md`](docs/platforms.md).

## Установка

### Fedora / Linux

```bash
sudo dnf install python3-gobject python3-cairo gtk4 gtk4-layer-shell playerctl dbus-tools
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.txt
```

`gtk4-layer-shell` может называться `gtk4-layer-shell-devel` в репозитории, если отсутствует runtime typelib.

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

`--doctor` выводит только возможности текущей машины. `--check` проверяет настройки и все кадры без открытия окна. Для smoke-теста окна используйте `--smoke-test 2`.

## Поведение

- Кадры ходьбы и бега привязаны к пройденному расстоянию, поэтому стопы не скользят. Голова, корпус и ноги собираются на общем каноническом силуэте; каждый кадр имеет видимые bounds и общий anchor ступней.
- Положение ограничивается alpha-bounds текущего кадра. При изменении разрешения, панели или монитора маскот пересчитывается и остаётся на полу рабочей области.
- Перетаскивание ограничено фактической областью маскота. Отпускание бросает его с ограниченной скоростью; края экрана отражают бросок, а приземление возвращает его на точную линию пола.
- Обычный клик выбирает неповторяющиеся реакции. Быстрые множественные клики вызывают отдельную реакцию. Движение туда-сюда над головой распознаётся как поглаживание и запускает мягкую анимацию `pet`, без уменьшения тела.
- Иногда движение курсора запускает короткую пробежку к нему. Частота и длительность задаются в конфиге.
- Музыка определяется по MPRIS/Windows GSMTC. Браузерное видео, YouTube и неизвестные медиасессии не считаются музыкой; `music.youtube.com` считается музыкой. Танец начинается при подтверждённом Playing и продолжается до остановки, смены трека с неизвестным типом или паузы.
- Уведомления проходят через privacy-фильтр. Маскот говорит только «Новое сообщение!», «Есть новое уведомление!» или «Важное уведомление!»; имена отправителей, заголовки, текст, названия устройств и OSD громкости не показываются.

## Настройка

Скопируйте [`config.example.json`](config.example.json) в каталог конфигурации:

- Linux: `~/.config/deepsy/config.json`;
- Windows: `%APPDATA%\deepsy\config.json`.

Основные параметры:

```json
{
  "backend": "auto",
  "monitor": 0,
  "scale": 1.0,
  "floor_gap": 0,
  "watchers": {"niri": true, "notifications": true, "system": true, "music": true, "time": true},
  "music": {"mode": "auto", "poll_interval": 1, "metadata_grace": 4},
  "interaction": {"follow_cursor": true, "follow_chance": 0.18, "petting": true}
}
```

Настройки проверяются до запуска. Числа ограничены безопасными диапазонами, регулярные выражения `app_reactions` компилируются заранее, а неизвестные значения не попадают в физику.

Переменные окружения `MASCOT_SCALE`, `MASCOT_GRAVITY`, `MASCOT_DROPIN`, `MASCOT_MONITOR`, `MASCOT_LAYER`, `MASCOT_MARGIN` и `MASCOT_FLOOR` поддерживаются для совместимости.

## Разработка

```bash
.venv/bin/python -m pytest -q
.venv/bin/python mascot.py --check
```

Для пересборки кадров нужны Pillow, NumPy и SciPy:

```bash
.venv/bin/python tools/frames.py
```

Генератор обновляет `frames/animations.json`, превью и [`previews/contact_sheet.png`](previews/contact_sheet.png). Не добавляйте в Git `.venv`, кэш Python, debug-выводы и локальные конфигурации.

## Лицензия

Перед публикацией выберите лицензию и добавьте файл `LICENSE`. Исходный арт находится в `tools/source.png`; укажите его автора в лицензии или README, если он не ваш.
