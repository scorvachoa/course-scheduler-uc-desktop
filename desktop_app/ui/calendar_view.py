"""Weekly calendar view."""
from __future__ import annotations

import math
from typing import Dict, Iterable, List

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from course_scheduler.models.course import Course


DAY_LABELS = ["L", "M", "X", "J", "V", "S", "D"]
DAY_MAP = {
    "Lunes": 0,
    "Martes": 1,
    "Miercoles": 2,
    "Miércoles": 2,
    "Jueves": 3,
    "Viernes": 4,
    "Sabado": 5,
    "Sábado": 5,
    "Domingo": 6,
}

SLOT_MINUTES = 30
START_HOUR = 7
END_HOUR = 23


def _slot_labels() -> List[str]:
    labels: List[str] = []
    for minutes in range(START_HOUR * 60, (END_HOUR * 60) + 1, SLOT_MINUTES):
        labels.append(f"{minutes // 60:02d}:{minutes % 60:02d}")
    return labels


def _to_minutes(value: str) -> int:
    parts = value.split(":")
    if len(parts) != 2:
        return START_HOUR * 60
    return int(parts[0]) * 60 + int(parts[1])


def _minutes_to_row(minutes: int) -> int:
    base = START_HOUR * 60
    return max(0, (minutes - base) // SLOT_MINUTES)


class CalendarView(QWidget):
    def __init__(self, title: str = "Calendario", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.title = QLabel(title)
        self.table = QTableWidget()
        self.table.setColumnCount(len(DAY_LABELS))
        self.table.setHorizontalHeaderLabels(DAY_LABELS)
        labels = _slot_labels()
        self.table.setRowCount(len(labels))
        self.table.setVerticalHeaderLabels(labels)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.NoSelection)

        layout = QVBoxLayout(self)
        layout.addWidget(self.title)
        layout.addWidget(self.table)

    def set_title(self, title: str) -> None:
        self.title.setText(title)

    def clear(self) -> None:
        self.table.clearContents()
        self.table.clearSpans()

    def set_schedule(self, courses: Iterable[Course], colors: Dict[str, QColor]) -> None:
        self.clear()
        for course in courses:
            color = colors.get(course.course_key() or course.name, QColor("#CCCCCC"))
            for sched in course.schedules:
                day_index = DAY_MAP.get(sched.day)
                if day_index is None:
                    continue
                start_min = _to_minutes(sched.start)
                end_min = _to_minutes(sched.end)
                if end_min <= start_min:
                    continue

                start_row = _minutes_to_row(start_min)
                span = max(1, int(math.ceil((end_min - start_min) / SLOT_MINUTES)))
                if start_row >= self.table.rowCount():
                    continue
                span = min(span, self.table.rowCount() - start_row)

                item = self.table.item(start_row, day_index)
                text = f"{course.name}\n{sched.start}-{sched.end}"
                if item is None:
                    item = QTableWidgetItem(text)
                    self.table.setItem(start_row, day_index, item)
                else:
                    existing = item.text().strip()
                    if existing:
                        item.setText(existing + "\n" + text)
                    else:
                        item.setText(text)

                item.setBackground(color)
                item.setTextAlignment(Qt.AlignCenter)
                item.setToolTip(f"{sched.day} {sched.start}-{sched.end} ({sched.modality})")
                self.table.setSpan(start_row, day_index, span, 1)

    def export_png(self, path: str) -> None:
        pixmap = self.grab()
        pixmap.save(path, "PNG")

    def export_pdf(self, path: str) -> None:
        from PySide6.QtGui import QPainter
        from PySide6.QtPrintSupport import QPrinter

        printer = QPrinter(QPrinter.HighResolution)
        printer.setOutputFormat(QPrinter.PdfFormat)
        printer.setOutputFileName(path)

        painter = QPainter(printer)
        pixmap = self.grab()
        rect = painter.viewport()
        size = pixmap.size()
        size.scale(rect.size(), Qt.KeepAspectRatio)
        painter.setViewport(rect.x(), rect.y(), size.width(), size.height())
        painter.setWindow(pixmap.rect())
        painter.drawPixmap(0, 0, pixmap)
        painter.end()
