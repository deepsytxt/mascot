   
from __future__ import annotations

import os
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
os.chdir(HERE)
sys.path.insert(0, str(HERE))

from config import config_dir              
from ipc import send              

LOG_LIMIT = 512 * 1024


def redirect_output():
                                                                                 
    log = config_dir() / "mascot.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    if log.exists() and log.stat().st_size > LOG_LIMIT:
        log.replace(log.with_suffix(".log.old"))
    stream = log.open("a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = stream
    print(f"--- {time.strftime('%Y-%m-%d %H:%M:%S')} запуск ---")


def main(argv=None, *, redirect=True):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv and send({"ping": True}):
        send({"emotion": "joy", "text": "Я здесь!"})
        return 0
    if redirect:
        redirect_output()
    import mascot
    return mascot.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
