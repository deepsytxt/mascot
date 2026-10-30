# Платформы и ограничения

## Linux Wayland

GTK backend использует [gtk4-layer-shell](https://wmww.github.io/gtk4-layer-shell/gtk4-layer-shell-GTK4-Layer-Shell.html). Окно закрепляется на выбранном output, не резервирует место (`exclusive_zone=0`) и получает input region только по текущему hit-bounds маскота. Панели и рабочая область предоставляются композитором.

Layer-shell — протокол для layer-shell compositor. GNOME Wayland обычно его не поддерживает; в таком случае используйте XWayland или X11. Библиотека layer-shell предварительно загружается до GTK, иначе Wayland shim может не зарегистрироваться.

Глобальное положение курсора Wayland не раскрывает. Поэтому следование за курсором работает при движении над поверхностью маскота; это ограничение протокола.

## Linux X11 и Windows

Qt backend использует прозрачное окно без фокуса и маску фактического hit-bounds. Для каждого кадра считывается `availableGeometry`, включая отрицательные координаты и изменение панели/монитора. На native Wayland Qt произвольное перемещение запрещено, поэтому backend требует XWayland (`DISPLAY`) и выбирает `xcb`.

На X11 некоторые оконные менеджеры не сообщают панели одинаково для всех мониторов. `workarea_insets` позволяет вручную добавить отступ, если `availableGeometry` неточна.

## Музыка и уведомления

Linux: музыка через MPRIS/playerctl, уведомления через session D-Bus. Windows: музыка через optional Windows Global System Media Transport Controls (PyWinRT). Универсального безопасного Windows toast-listener без отдельного разрешения нет, поэтому `--doctor` честно показывает эту возможность как недоступную. Содержимое уведомлений нигде не передаётся в реплику.
