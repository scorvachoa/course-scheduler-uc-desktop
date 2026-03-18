"""Scraping worker for background thread."""
from __future__ import annotations

import json
import os

from PySide6.QtCore import QObject, Signal

from course_scheduler.scraper_run import build_records


class ScrapeWorker(QObject):
    finished = Signal(object, object)
    failed = Signal(str)

    def __init__(self, data_path: str, term: str) -> None:
        super().__init__()
        self.data_path = data_path
        self.term = term

    def run(self) -> None:
        try:
            result = build_records(self.term)
            os.makedirs(os.path.dirname(self.data_path), exist_ok=True)
            with open(self.data_path, "w", encoding="utf-8") as f:
                json.dump(result["records"], f, ensure_ascii=False, indent=2)
            self.finished.emit(result["records"], result)
        except Exception as exc:
            self.failed.emit(str(exc))
