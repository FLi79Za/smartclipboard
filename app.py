import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from core.settings import SettingsStore
from core.db import ClipDB
from ui.main_window import MainWindow

APP_ROOT = Path(__file__).resolve().parent
DATA_DIR = APP_ROOT / "data"


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    settings = SettingsStore(DATA_DIR / "settings.json")
    db = ClipDB(DATA_DIR / "smart_clipboard.db")

    app = QApplication(sys.argv)
    win = MainWindow(app_root=APP_ROOT, data_dir=DATA_DIR, settings=settings, db=db)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
