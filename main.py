"""One-file launcher for the BSL v68 Python server."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
SOURCE_DIR = PROJECT_DIR / "src"


def ensure_dependencies() -> None:
    try:
        import nacl  # noqa: F401
    except ImportError:
        print("PyNaCl не найден. Устанавливаю зависимость...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-r", str(PROJECT_DIR / "requirements.txt")]
        )


def main() -> None:
    ensure_dependencies()
    sys.path.insert(0, str(SOURCE_DIR))

    from bsl68.__main__ import main as run_server

    run_server()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Ошибка запуска: {error}")
        if sys.stdin.isatty():
            try:
                input("Нажмите Enter для выхода...")
            except EOFError:
                pass
        raise
