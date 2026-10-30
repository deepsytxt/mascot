#!/bin/sh
cd "$(dirname "$0")" || exit 1
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 &&
       "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>/dev/null; then
        exec "$candidate" tools/install.py "$@"
    fi
done
echo "Не найден Python 3.9 или новее. Установите его (например: sudo dnf install python3)." >&2
exit 1
