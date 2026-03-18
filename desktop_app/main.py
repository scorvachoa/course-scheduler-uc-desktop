"""Entry point for the UI."""
from __future__ import annotations

import os

from desktop_app.ui.app import run_app


DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "cursos.json")


def main() -> None:
    run_app(DATA_PATH)


if __name__ == "__main__":
    main()
