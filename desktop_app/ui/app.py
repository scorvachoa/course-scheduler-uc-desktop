# -*- coding: utf-8 -*-
"""Main application window."""
from __future__ import annotations

import json
import os
from typing import Dict, List, Tuple, Optional

from PySide6.QtCore import QObject, QThread, Signal, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QAbstractItemView,
    QCheckBox,
    QHeaderView,
    QVBoxLayout,
    QWidget,
    QDialog,
)

from course_scheduler.models.course import Course
from desktop_app.ui.calendar_view import CalendarView
from desktop_app.ui.course_selector import CourseSelector
from desktop_app.ui.exporter import PALETTE, export_schedule_json, export_schedule_pdf
from desktop_app.ui.scrape_worker import ScrapeWorker
from course_scheduler.utils.data_utils import flatten_courses
from course_scheduler.utils.time_utils import format_minutes, to_minutes
from course_scheduler.planner.auto_scheduler import generate_auto_schedule


DAY_ORDER = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
DAY_ALIAS = {
    "Lunes": "L",
    "Martes": "M",
    "Miércoles": "X",
    "Miercoles": "X",
    "Jueves": "J",
    "Viernes": "V",
    "Sábado": "S",
    "Sabado": "S",
    "Domingo": "D",
}


def load_courses(path: str) -> List[Course]:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        return []
    data = flatten_courses(data)
    return [Course.from_dict(item) for item in data if isinstance(item, dict)]


def build_colors(courses: List[Course]) -> Dict[str, QColor]:
    colors_map: Dict[str, QColor] = {}
    keys: List[str] = []
    for course in courses:
        key = course.course_key() or course.name
        if key not in colors_map:
            keys.append(key)
    for idx, key in enumerate(keys):
        colors_map[key] = QColor(PALETTE[idx % len(PALETTE)])
    return colors_map

def build_block_colors(courses: List[Course]) -> Dict[str, QColor]:
    colors_map: Dict[str, QColor] = {}
    keys: List[str] = []
    for course in courses:
        key = course.course_key() or course.name
        if key not in colors_map:
            keys.append(key)

    total = max(1, len(keys))
    for idx, key in enumerate(keys):
        if idx < len(PALETTE):
            colors_map[key] = QColor(PALETTE[idx])
        else:
            hue = int((idx * 360) / total)
            colors_map[key] = QColor.fromHsv(hue, 140, 220)
    return colors_map


def summarize_course_schedule(course: Course) -> str:
    by_day: Dict[str, List[Tuple[int, int]]] = {}
    for sched in course.schedules:
        if not sched.day or not sched.start or not sched.end:
            continue
        by_day.setdefault(sched.day, []).append(
            (to_minutes(sched.start), to_minutes(sched.end))
        )

    if not by_day:
        return f"{course.name} (NRC {course.nrc}): sin horarios"

    parts: List[str] = []
    for day in DAY_ORDER:
        if day not in by_day:
            continue
        ranges = by_day[day]
        start = min(r[0] for r in ranges)
        end = max(r[1] for r in ranges)
        label = DAY_ALIAS.get(day, day[:1])
        parts.append(f"{label} {format_minutes(start)}-{format_minutes(end)}")

    return f"{course.name} (NRC {course.nrc}): " + " | ".join(parts)


class MainWindow(QMainWindow):
    def __init__(self, courses: List[Course], data_path: str) -> None:
        super().__init__()
        self.setWindowTitle("Course Scheduler UC")
        self.data_path = data_path
        self.courses = courses
        self.colors = build_colors(courses)
        self._theme_mode = "dark"

        self.selected_nrc_a: Dict[str, str] = {}
        self.selected_nrc_b: Dict[str, str] = {}
        self._nrc_updating = False

        self.selector = CourseSelector()
        self.selector.set_courses(courses)
        self.selector.selection_changed.connect(self._on_selection_changed)

        self.calendar_a = CalendarView("CALENDARIO BLOQUE A")
        self.calendar_b = CalendarView("CALENDARIO BLOQUE B")

        self.nrc_table_a = self._build_nrc_table()
        self.nrc_table_a.itemChanged.connect(lambda item: self._on_nrc_changed(item, "A"))

        self.nrc_table_b = self._build_nrc_table()
        self.nrc_table_b.itemChanged.connect(lambda item: self._on_nrc_changed(item, "B"))

        self.results_list_a = QListWidget()
        self.results_list_b = QListWidget()

        self.scrape_btn = QPushButton("ACTUALIZAR CURSOS (SCRAPING)")
        self.scrape_btn.clicked.connect(self._start_scrape)
        self.export_pdf_btn = QPushButton("DESCARGAR HORARIO PDF")
        self.export_pdf_btn.clicked.connect(self._export_pdf)
        self.auto_schedule_btn = QPushButton("GENERAR HORARIO AUTOMÁTICO")
        self.auto_schedule_btn.clicked.connect(self._open_auto_schedule)
        self.load_json_btn = QPushButton("CARGAR HORARIO JSON")
        self.load_json_btn.clicked.connect(self._load_schedule_json)
        self.clear_schedule_btn = QPushButton("BORRAR HORARIO")
        self.clear_schedule_btn.clicked.connect(self._clear_schedule)

        self.status_label = QLabel("")

        left_box = self._wrap_group("LISTA DE CURSOS", self.selector)

        btn_box = QWidget()
        btn_layout = QHBoxLayout(btn_box)
        btn_layout.addWidget(self.export_pdf_btn)
        btn_layout.addWidget(self.auto_schedule_btn)
        btn_layout.addWidget(self.scrape_btn)
        btn_layout.addWidget(self.load_json_btn)
        btn_layout.addWidget(self.clear_schedule_btn)
        btn_layout.addWidget(self.status_label)
        btn_layout.addStretch()

        nrc_box_a = self._wrap_group("NRC BLOQUE A", self.nrc_table_a)
        nrc_box_b = self._wrap_group("NRC BLOQUE B", self.nrc_table_b)

        cal_box_a = self._wrap_group("CALENDARIO BLOQUE A", self.calendar_a)
        cal_box_b = self._wrap_group("CALENDARIO BLOQUE B", self.calendar_b)

        sum_box_a = self._wrap_group("RESUMEN CURSOS BLOQUE A", self.results_list_a)
        sum_box_b = self._wrap_group("RESUMEN CURSOS BLOQUE B", self.results_list_b)

        central = QWidget()
        grid = QGridLayout(central)
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(20)
        grid.setContentsMargins(20, 20, 20, 20)

        grid.addWidget(left_box, 0, 0, 3, 1)
        grid.addWidget(nrc_box_a, 0, 1, 1, 1)
        grid.addWidget(nrc_box_b, 0, 2, 1, 1)
        grid.addWidget(cal_box_a, 1, 1, 1, 1)
        grid.addWidget(cal_box_b, 1, 2, 1, 1)
        grid.addWidget(sum_box_a, 2, 1, 1, 1)
        grid.addWidget(sum_box_b, 2, 2, 1, 1)
        grid.addWidget(btn_box, 3, 0, 1, 3)

        grid.setRowStretch(1, 6)
        grid.setRowStretch(2, 1)
        grid.setColumnStretch(1, 2)
        grid.setColumnStretch(2, 2)

        self.setCentralWidget(central)

        self._apply_theme(self._theme_mode)
        self._on_selection_changed([], [])

    def _wrap_group(self, title: str, widget: QWidget) -> QGroupBox:
        box = QGroupBox(title)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(12, 18, 12, 12)
        layout.addWidget(widget)
        return box

    def _apply_theme(self, mode: str) -> None:
        if mode == "dark":
            bg = "#1e1e1e"
            panel = "#2a2a2a"
            border = "#3a3a3a"
            text = "#e8e8e8"
            button = "#333333"
            field = "#2f2f2f"
            header = "#3a3a3a"
        else:
            bg = "#f7f7f7"
            panel = "#fafafa"
            border = "#cfcfcf"
            text = "#1f1f1f"
            button = "#e5e5e5"
            field = "#ffffff"
            header = "#ededed"

        self.setStyleSheet(
            f"QMainWindow {{ background: {bg}; color: {text}; }}"
            f"QGroupBox {{ background: {panel}; border: 1px solid {border}; border-radius: 6px; margin-top: 18px; }}"
            f"QGroupBox::title {{ subcontrol-origin: margin; left: 10px; top: 4px; font-weight: 700; letter-spacing: 0.5px; color: {text}; }}"
            f"QPushButton {{ background: {button}; border: 1px solid {border}; padding: 10px; font-weight: 600; color: {text}; }}"
            f"QTableWidget, QListWidget {{ background: {panel}; border: 1px solid {border}; color: {text}; gridline-color: {border}; }}"
            f"QHeaderView::section {{ background: {header}; color: {text}; border: 1px solid {border}; padding: 4px; }}"
            f"QLineEdit {{ background: {field}; border: 1px solid {border}; color: {text}; padding: 8px; }}"
        )

    def _build_nrc_table(self) -> QTableWidget:
        table = QTableWidget()
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(["Curso", "NRC"])
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        return table

    def _selected_course_sections(self, selected_keys: List[str], block: str) -> List[Course]:
        selected: List[Course] = []
        for course in self.courses:
            key = course.course_key() or course.name
            if key in selected_keys and course.block_letter() == block:
                selected.append(course)
        return selected

    def _occupied_blocks(self, block: str) -> List[Tuple[str, str, str, int, int]]:
        occupied: List[Tuple[str, str, str, int, int]] = []
        selected = self.selected_nrc_a if block == "A" else self.selected_nrc_b
        for course in self._sections_from_nrc(selected, block):
            key = course.course_key() or course.name
            for sched in course.schedules:
                if not sched.day or not sched.start or not sched.end:
                    continue
                start = to_minutes(sched.start)
                end = to_minutes(sched.end)
                if start >= end:
                    continue
                occupied.append((key, course.name, sched.day, start, end))
        return occupied

    def _conflict_with_occupied(
        self,
        course: Course,
        occupied: List[Tuple[str, str, str, int, int]],
        ignore_key: str,
    ) -> Optional[str]:
        for sched in course.schedules:
            if not sched.day or not sched.start or not sched.end:
                continue
            start = to_minutes(sched.start)
            end = to_minutes(sched.end)
            if start >= end:
                continue
            for key, name, day, o_start, o_end in occupied:
                if key == ignore_key:
                    continue
                if sched.day != day:
                    continue
                if start < o_end and end > o_start:
                    return f"Conflicto con {name}: {day} {format_minutes(o_start)}-{format_minutes(o_end)}"
        return None

    def _on_selection_changed(self, selected_a: List[str], selected_b: List[str]) -> None:
        self.selector.refresh_credits(self.courses, selected_a, selected_b)
        self._populate_nrc_table(self.nrc_table_a, selected_a, "A")
        self._populate_nrc_table(self.nrc_table_b, selected_b, "B")
        self._refresh_block("A")
        self._refresh_block("B")

    def _populate_nrc_table(self, table: QTableWidget, selected_keys: List[str], block: str) -> None:
        self._nrc_updating = True
        try:
            table.clearContents()
            rows: List[Tuple[str, Course]] = []
            for course in self._selected_course_sections(selected_keys, block):
                key = course.course_key() or course.name
                rows.append((key, course))

            rows.sort(key=lambda r: (r[0], r[1].nrc))
            table.setRowCount(len(rows))
            occupied = self._occupied_blocks(block)

            for row, (key, course) in enumerate(rows):
                name_item = QTableWidgetItem(course.name)
                name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
                table.setItem(row, 0, name_item)

                nrc_item = QTableWidgetItem(course.nrc)
                nrc_item.setFlags(nrc_item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                nrc_item.setCheckState(Qt.Unchecked)
                nrc_item.setData(Qt.UserRole, key)
                table.setItem(row, 1, nrc_item)

                selected_nrc = self.selected_nrc_a.get(key) if block == "A" else self.selected_nrc_b.get(key)
                if selected_nrc and selected_nrc == course.nrc:
                    nrc_item.setCheckState(Qt.Checked)
                else:
                    conflict = self._conflict_with_occupied(course, occupied, key)
                    if conflict:
                        nrc_item.setFlags(nrc_item.flags() & ~Qt.ItemIsEnabled)
                        nrc_item.setToolTip(conflict)
        finally:
            self._nrc_updating = False

    def _on_nrc_changed(self, item: QTableWidgetItem, block: str) -> None:
        if self._nrc_updating:
            return
        if item.column() != 1:
            return

        table = self.nrc_table_a if block == "A" else self.nrc_table_b
        key = item.data(Qt.UserRole)
        if not key:
            return

        self._nrc_updating = True
        try:
            if item.checkState() == Qt.Checked:
                for row in range(table.rowCount()):
                    if row == item.row():
                        continue
                    other = table.item(row, 1)
                    if other and other.data(Qt.UserRole) == key:
                        other.setCheckState(Qt.Unchecked)
                if block == "A":
                    self.selected_nrc_a[str(key)] = item.text()
                else:
                    self.selected_nrc_b[str(key)] = item.text()
            else:
                if block == "A":
                    self.selected_nrc_a.pop(str(key), None)
                else:
                    self.selected_nrc_b.pop(str(key), None)
        finally:
            self._nrc_updating = False

        self._refresh_block(block)

    def _refresh_block(self, block: str) -> None:
        if block == "A":
            selected = self._sections_from_nrc(self.selected_nrc_a, "A")
            block_colors = build_block_colors(selected)
            self.calendar_a.set_schedule(selected, block_colors)
            self._populate_schedule_list(self.results_list_a, selected, "A")
            selected_keys = self.selector.selected_keys()[0]
            self._populate_nrc_table(self.nrc_table_a, selected_keys, "A")
        else:
            selected = self._sections_from_nrc(self.selected_nrc_b, "B")
            block_colors = build_block_colors(selected)
            self.calendar_b.set_schedule(selected, block_colors)
            self._populate_schedule_list(self.results_list_b, selected, "B")
            selected_keys = self.selector.selected_keys()[1]
            self._populate_nrc_table(self.nrc_table_b, selected_keys, "B")

    def _sections_from_nrc(self, selected: Dict[str, str], block: str) -> List[Course]:
        sections: List[Course] = []
        for course in self.courses:
            key = course.course_key() or course.name
            if key in selected and course.nrc == selected[key] and course.block_letter() == block:
                sections.append(course)
        return sections

    def _populate_schedule_list(self, list_widget: QListWidget, sections: List[Course], block: str) -> None:
        list_widget.clear()
        if not sections:
            list_widget.addItem(f"Selecciona NRC {block}")
            return
        for course in sections:
            list_widget.addItem(QListWidgetItem(summarize_course_schedule(course)))

    def _load_schedule_json(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Cargar horario JSON", "", "JSON (*.json)")
        if not path:
            return
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.selected_nrc_a.clear()
        self.selected_nrc_b.clear()
        selected_a = []
        selected_b = []
        for item in data.get("bloque_a", []):
            key = item.get("course_key")
            nrc = item.get("nrc")
            if key and nrc:
                self.selected_nrc_a[str(key)] = str(nrc)
                selected_a.append(str(key))
        for item in data.get("bloque_b", []):
            key = item.get("course_key")
            nrc = item.get("nrc")
            if key and nrc:
                self.selected_nrc_b[str(key)] = str(nrc)
                selected_b.append(str(key))
        self.selector.set_selected_keys(selected_a, selected_b)
        self._populate_nrc_table(self.nrc_table_a, selected_a, "A")
        self._populate_nrc_table(self.nrc_table_b, selected_b, "B")
        self._refresh_block("A")
        self._refresh_block("B")
        self.status_label.setText("Horario cargado")

    def _clear_schedule(self) -> None:
        confirm = QMessageBox.question(
            self,
            "Borrar horario",
            "?Deseas borrar el horario seleccionado?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        self.selected_nrc_a.clear()
        self.selected_nrc_b.clear()
        self.selector.set_selected_keys([], [])
        self._populate_nrc_table(self.nrc_table_a, [], "A")
        self._populate_nrc_table(self.nrc_table_b, [], "B")
        self._refresh_block("A")
        self._refresh_block("B")
        self.status_label.setText("Horario borrado")

    def _start_scrape(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Cookie requerida")
        dialog.resize(1000, 300)
        instructions_text = (
            "Pega el header Cookie completo.\n\n"
            "Como obtenerlo:\n"
            "1. Inicia sesion en el portal.\n"
            "2. Abre DevTools (F12) y ve a Network.\n"
            "3. Recarga y abre una request a /api/academic/.\n"
            "4. Copia el header Cookie completo y pegalo aqui."
        )
        instructions = QLabel("".join(instructions_text))
        instructions.setWordWrap(True)
        input_box = QLineEdit()
        input_box.setPlaceholderText("Pega el header Cookie completo")
        ok_btn = QPushButton("Aceptar")
        cancel_btn = QPushButton("Cancelar")
        result = {"accepted": False}

        def accept():
            value = input_box.text().strip()
            if not value:
                return
            result["accepted"] = True
            result["value"] = value
            dialog.accept()

        ok_btn.clicked.connect(accept)
        cancel_btn.clicked.connect(dialog.reject)
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(ok_btn)
        buttons.addWidget(cancel_btn)
        layout = QVBoxLayout(dialog)
        layout.addWidget(instructions)
        layout.addWidget(input_box)
        layout.addLayout(buttons)
        dialog.exec()
        if not result.get("accepted"):
            return
        os.environ["API_COOKIE"] = result["value"]

        term = os.environ.get("TERM_CODE", "202610")
        self.scrape_btn.setEnabled(False)
        self.status_label.setText("Scraping en progreso...")

        self._thread = QThread()
        self._worker = ScrapeWorker(self.data_path, term)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_scrape_finished)
        self._worker.failed.connect(self._on_scrape_failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.failed.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)

        self._thread.start()

    def _export_pdf(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Exportar PDF", "horario.pdf", "PDF (*.pdf)")
        if not path:
            return
        bloque_a = self._sections_from_nrc(self.selected_nrc_a, "A")
        bloque_b = self._sections_from_nrc(self.selected_nrc_b, "B")
        export_schedule_pdf(path, bloque_a, bloque_b)
        json_path = os.path.splitext(path)[0] + ".json"
        export_schedule_json(json_path, bloque_a, bloque_b)
        self.status_label.setText("Exportado PDF y JSON")

    def _on_scrape_finished(self, records: object, result: object) -> None:
        self.scrape_btn.setEnabled(True)
        self.status_label.setText("Scraping completado")
        self.courses = load_courses(self.data_path)
        self.colors = build_colors(self.courses)
        self.selector.set_courses(self.courses)
        self.selected_nrc_a.clear()
        self.selected_nrc_b.clear()
        self._populate_nrc_table(self.nrc_table_a, [], "A")
        self._populate_nrc_table(self.nrc_table_b, [], "B")
        self._refresh_block("A")
        self._refresh_block("B")

    def _on_scrape_failed(self, message: str) -> None:
        self.scrape_btn.setEnabled(True)
        self.status_label.setText("Scraping fallo")
        QMessageBox.critical(self, "Error de scraping", message)



    def _open_auto_schedule(self) -> None:
        dialog = AutoScheduleDialog(self, self.courses, self._apply_auto_schedule_result)
        dialog.exec()

    def _apply_auto_schedule_result(self, result: dict) -> None:
        if not result:
            return
        bloque_a = result.get("bloque_a", {}).get("courses", [])
        bloque_b = result.get("bloque_b", {}).get("courses", [])
        self.selected_nrc_a.clear()
        self.selected_nrc_b.clear()
        selected_keys_a = []
        selected_keys_b = []

        for course in bloque_a:
            key = course.course_key() or course.name
            self.selected_nrc_a[key] = course.nrc
            selected_keys_a.append(key)

        for course in bloque_b:
            key = course.course_key() or course.name
            self.selected_nrc_b[key] = course.nrc
            selected_keys_b.append(key)

        self.selector.set_selected_keys(selected_keys_a, selected_keys_b)
        self._populate_nrc_table(self.nrc_table_a, selected_keys_a, "A")
        self._populate_nrc_table(self.nrc_table_b, selected_keys_b, "B")
        self._refresh_block("A")
        self._refresh_block("B")
        self.status_label.setText("Horario automático aplicado")

class AutoScheduleDialog(QDialog):
    def __init__(self, parent: QWidget, courses: List[Course], apply_cb) -> None:
        super().__init__(parent)
        self.courses = courses
        self.apply_cb = apply_cb
        self.result = None
        self.setWindowTitle("Generador automático")
        self.resize(900, 600)

        days_box = QGroupBox("Días permitidos")
        days_layout = QHBoxLayout(days_box)
        self.day_checks: Dict[str, QCheckBox] = {}
        for day in ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]:
            chk = QCheckBox(day)
            chk.setChecked(True)
            self.day_checks[day] = chk
            days_layout.addWidget(chk)

        courses_box = QGroupBox("Cursos a considerar")
        courses_layout = QVBoxLayout(courses_box)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Buscar curso...")
        self.search_input.textChanged.connect(self._filter_courses)

        self.courses_table = QTableWidget()
        self.courses_table.setColumnCount(4)
        self.courses_table.setHorizontalHeaderLabels(["Seleccionar", "Curso", "Créditos", "Bloques"])
        self.courses_table.verticalHeader().setVisible(False)
        self.courses_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.courses_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.courses_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.courses_table.setColumnWidth(0, 90)
        self.courses_table.setColumnWidth(2, 70)
        self.courses_table.setColumnWidth(3, 70)

        courses_layout.addWidget(self.search_input)
        courses_layout.addWidget(self.courses_table)

        params_box = QGroupBox("Parámetros")
        params_layout = QVBoxLayout(params_box)
        self.target_label = QLabel("Objetivo: 12 créditos por bloque A y 12 por bloque B")
        self.allow_less_chk = QCheckBox("Permitir menor a 12 si no hay exacto")
        self.allow_less_chk.setChecked(True)
        params_layout.addWidget(self.target_label)
        params_layout.addWidget(self.allow_less_chk)

        result_box = QGroupBox("Resultado")
        result_layout = QVBoxLayout(result_box)
        self.status_label = QLabel("Pendiente")
        self.block_a_label = QLabel("Bloque A: 0 créditos")
        self.block_b_label = QLabel("Bloque B: 0 créditos")
        self.block_a_list = QListWidget()
        self.block_b_list = QListWidget()
        result_layout.addWidget(self.status_label)
        result_layout.addWidget(self.block_a_label)
        result_layout.addWidget(self.block_a_list)
        result_layout.addWidget(self.block_b_label)
        result_layout.addWidget(self.block_b_list)

        self.generate_btn = QPushButton("GENERAR")
        self.generate_btn.clicked.connect(self._generate)
        self.apply_btn = QPushButton("APLICAR A HORARIO")
        self.apply_btn.setEnabled(False)
        self.apply_btn.clicked.connect(self._apply)
        self.cancel_btn = QPushButton("CANCELAR")
        self.cancel_btn.clicked.connect(self.reject)

        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(self.generate_btn)
        actions.addWidget(self.apply_btn)
        actions.addWidget(self.cancel_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(days_box)
        layout.addWidget(courses_box)
        layout.addWidget(params_box)
        layout.addWidget(result_box)
        layout.addLayout(actions)

        self._load_courses()

    def _load_courses(self) -> None:
        grouped: Dict[str, Course] = {}
        availability: Dict[str, set] = {}
        for course in self.courses:
            key = course.course_key() or course.name
            grouped.setdefault(key, course)
            availability.setdefault(key, set())
            block = course.block_letter()
            if block:
                availability[key].add(block)

        keys = sorted(grouped.keys(), key=lambda k: grouped[k].name)
        self.courses_table.setRowCount(len(keys))
        self.row_key_map: Dict[int, str] = {}

        for row, key in enumerate(keys):
            course = grouped[key]
            self.row_key_map[row] = key
            sel_item = QTableWidgetItem()
            sel_item.setFlags(sel_item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            sel_item.setCheckState(Qt.Unchecked)
            self.courses_table.setItem(row, 0, sel_item)

            name_item = QTableWidgetItem(f"{course.name} ({key})")
            self.courses_table.setItem(row, 1, name_item)

            credits_item = QTableWidgetItem(str(course.credits))
            credits_item.setTextAlignment(Qt.AlignCenter)
            self.courses_table.setItem(row, 2, credits_item)

            blocks = "".join(sorted(list(availability.get(key, set())))) or "-"
            block_item = QTableWidgetItem(blocks)
            block_item.setTextAlignment(Qt.AlignCenter)
            self.courses_table.setItem(row, 3, block_item)

    def _filter_courses(self, text: str) -> None:
        query = (text or "").strip().lower()
        for row in range(self.courses_table.rowCount()):
            key = self.row_key_map.get(row, "")
            name_item = self.courses_table.item(row, 1)
            name = name_item.text().lower() if name_item else ""
            visible = (query in name) or (query in key.lower()) if query else True
            self.courses_table.setRowHidden(row, not visible)

    def _selected_course_keys(self) -> List[str]:
        keys: List[str] = []
        for row in range(self.courses_table.rowCount()):
            item = self.courses_table.item(row, 0)
            if item and item.checkState() == Qt.Checked:
                key = self.row_key_map.get(row)
                if key:
                    keys.append(key)
        return keys

    def _selected_days(self) -> List[str]:
        return [day for day, chk in self.day_checks.items() if chk.isChecked()]

    def _generate(self) -> None:
        selected_keys = self._selected_course_keys()
        if not selected_keys:
            self.status_label.setText("Selecciona al menos un curso")
            self.apply_btn.setEnabled(False)
            return
        days = self._selected_days()
        self.status_label.setText("Generando...")
        result = generate_auto_schedule(
            self.courses,
            selected_course_keys=selected_keys,
            allowed_days=days,
            target_credits=12,
            allow_less=self.allow_less_chk.isChecked(),
        )
        self.result = result
        bloque_a = result.get("bloque_a", {}).get("courses", [])
        bloque_b = result.get("bloque_b", {}).get("courses", [])
        credits_a = result.get("bloque_a", {}).get("credits", 0)
        credits_b = result.get("bloque_b", {}).get("credits", 0)

        self.block_a_list.clear()
        self.block_b_list.clear()
        for course in bloque_a:
            self.block_a_list.addItem(f"{course.name} (NRC {course.nrc})")
        for course in bloque_b:
            self.block_b_list.addItem(f"{course.name} (NRC {course.nrc})")

        self.block_a_label.setText(f"Bloque A: {credits_a} créditos")
        self.block_b_label.setText(f"Bloque B: {credits_b} créditos")
        if not bloque_a and not bloque_b:
            self.status_label.setText("No se encontró horario")
            self.apply_btn.setEnabled(False)
        else:
            self.status_label.setText("Horario encontrado")
            self.apply_btn.setEnabled(True)

    def _apply(self) -> None:
        if not self.result:
            return
        self.apply_cb(self.result)
        self.accept()
def run_app(data_path: str) -> None:
    courses = load_courses(data_path)
    app = QApplication([])
    window = MainWindow(courses, data_path)
    window.resize(1600, 1000)
    window.show()
    app.exec()



