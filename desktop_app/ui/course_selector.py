"""Course selection panel with block A/B."""
from __future__ import annotations

from typing import Dict, List, Set, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from course_scheduler.models.course import Course


class CourseSelector(QWidget):
    selection_changed = Signal(list, list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._row_to_key: Dict[int, str] = {}
        self._availability: Dict[str, Set[str]] = {}
        self._updating = False

        self.title = QLabel("Cursos")
        self.credits_label = QLabel("Creditos totales: 0")
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Curso", "A", "B"])
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)

        layout = QVBoxLayout(self)
        layout.addWidget(self.title)
        layout.addWidget(self.credits_label)
        layout.addWidget(self.table)

    def set_courses(self, courses: List[Course]) -> None:
        self.table.clearContents()
        self._row_to_key.clear()
        self._availability.clear()

        course_by_key: Dict[str, Course] = {}
        for course in courses:
            key = course.course_key() or course.name
            course_by_key.setdefault(key, course)
            self._availability.setdefault(key, set())
            block_letter = course.block_letter()
            if block_letter:
                self._availability[key].add(block_letter)

        keys = sorted(course_by_key.keys(), key=lambda k: course_by_key[k].name)
        self.table.setRowCount(len(keys))

        for row, key in enumerate(keys):
            course = course_by_key[key]
            name_item = QTableWidgetItem(course.name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 0, name_item)
            self._row_to_key[row] = key

            self._set_block_item(row, 1, key, "A")
            self._set_block_item(row, 2, key, "B")

        self._update_credits(courses, [], [])

    def _set_block_item(self, row: int, col: int, key: str, block: str) -> None:
        item = QTableWidgetItem("")
        available = block in self._availability.get(key, set())
        if available:
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            item.setCheckState(Qt.Unchecked)
        else:
            item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
            item.setText("-")
        item.setData(Qt.UserRole, block)
        self.table.setItem(row, col, item)

    def _update_credits(self, courses: List[Course], selected_a: List[str], selected_b: List[str]) -> None:
        total = 0
        seen = set(selected_a + selected_b)
        for course in courses:
            key = course.course_key() or course.name
            if key in seen:
                total += course.credits
        self.credits_label.setText(f"Creditos totales: {total}")

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._updating:
            return
        row = item.row()
        col = item.column()
        if col not in (1, 2):
            return

        self._updating = True
        try:
            if item.checkState() == Qt.Checked:
                other_col = 2 if col == 1 else 1
                other_item = self.table.item(row, other_col)
                if other_item and other_item.flags() & Qt.ItemIsEnabled:
                    other_item.setCheckState(Qt.Unchecked)
        finally:
            self._updating = False

        selected_a, selected_b = self.selected_keys()
        self.selection_changed.emit(selected_a, selected_b)

    def selected_keys(self) -> Tuple[List[str], List[str]]:
        selected_a: List[str] = []
        selected_b: List[str] = []
        for row in range(self.table.rowCount()):
            key = self._row_to_key.get(row)
            if not key:
                continue
            item_a = self.table.item(row, 1)
            item_b = self.table.item(row, 2)
            if item_a and item_a.checkState() == Qt.Checked:
                selected_a.append(key)
            if item_b and item_b.checkState() == Qt.Checked:
                selected_b.append(key)
        return selected_a, selected_b

    def refresh_credits(self, courses: List[Course], selected_a: List[str], selected_b: List[str]) -> None:
        self._update_credits(courses, selected_a, selected_b)

    def set_selected_keys(self, selected_a: List[str], selected_b: List[str]) -> None:
        self._updating = True
        try:
            for row in range(self.table.rowCount()):
                key = self._row_to_key.get(row)
                if not key:
                    continue
                item_a = self.table.item(row, 1)
                item_b = self.table.item(row, 2)
                if item_a and item_a.flags() & Qt.ItemIsEnabled:
                    item_a.setCheckState(Qt.Checked if key in selected_a else Qt.Unchecked)
                if item_b and item_b.flags() & Qt.ItemIsEnabled:
                    item_b.setCheckState(Qt.Checked if key in selected_b else Qt.Unchecked)
        finally:
            self._updating = False
