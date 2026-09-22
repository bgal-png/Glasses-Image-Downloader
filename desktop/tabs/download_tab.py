# -*- coding: utf-8 -*-
"""🖼 Download — load frames, match images from the sources, save to a folder."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QFileDialog, QGroupBox, QHBoxLayout, QLabel,
    QMenu, QMessageBox, QPlainTextEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

import pipeline
from barcode_parser import parse_records
from fill_dialog import FillDialog
from tabs.base import BaseTab
from workers import Worker

COLUMNS = ["Barcode", "Name", "Status"]

_STATUS_TEXT = {
    "barcode": "✅ barcode",
    "luxottica": "✅ EssilorLuxottica",
    "alpina": "✅ Alpina",
    "safilo": "✅ Safilo",
    "url": "✅ manual (url)",
    "manual": "✅ manual",
    "pick": "🎨 pick an image",
    "todo": "· not fetched",
    "empty": "❌ no barcode & no name",
}

_SOURCES = [
    ("barcode", "🔎 Run barcode lookup"),
    ("luxottica", "🕶 Match EssilorLuxottica"),
    ("alpina", "🏔 Match Alpina"),
    ("safilo", "🅢 Match Safilo (login window)"),
]


class DownloadTab(BaseTab):
    TITLE = "🖼 Download"

    def __init__(self, session, settings, parent=None):
        super().__init__(session, settings, parent)
        self._worker = None
        self._saved_signature = self._signature()
        self._panel = self._build_panel()

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Paste frames (barcode, or `barcode, name` per line) "
                                "or use 📂 Open file:"))
        self.paste = QPlainTextEdit()
        self.paste.setPlaceholderText("4003692345981, Alpina DEFEY 2 black matt")
        self.paste.setMaximumHeight(90)
        layout.addWidget(self.paste)
        load_btn = QPushButton("Load pasted frames")
        load_btn.clicked.connect(self.load_pasted)
        layout.addWidget(load_btn)

        self.info = QLabel("No frames loaded.")
        layout.addWidget(self.info)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.doubleClicked.connect(self._edit_row)
        # Table cells aren't copyable by default — offer it explicitly.
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._table_menu)
        layout.addWidget(self.table, 1)
        layout.addWidget(QLabel("Double-click a row to pick a candidate or fill/replace its image. "
                                "Right-click to copy the barcode or name."))

    # ---------------------------------------------------------------- panel
    def _build_panel(self) -> QWidget:
        panel = QWidget()
        v = QVBoxLayout(panel)

        src_box = QGroupBox("Sources")
        sv = QVBoxLayout(src_box)
        self._source_buttons = []
        for key, label in _SOURCES:
            btn = QPushButton(label)
            btn.clicked.connect(lambda _=False, k=key: self.run_source(k))
            sv.addWidget(btn)
            self._source_buttons.append(btn)
        manual_btn = QPushButton("✍️ Manual link…")
        manual_btn.setToolTip(
            "Add images by hand: paste a link or choose a file. "
            "Works on the selected row(s); with nothing selected it walks every "
            "frame that still has no image.")
        manual_btn.clicked.connect(self.run_manual)
        sv.addWidget(manual_btn)
        self._source_buttons.append(manual_btn)
        v.addWidget(src_box)

        out_box = QGroupBox("Output")
        ov = QVBoxLayout(out_box)
        self.folder_label = QLabel("No folder chosen.")
        self.folder_label.setWordWrap(True)
        choose = QPushButton("📁 Choose output folder…")
        choose.clicked.connect(self.choose_folder)
        self.save_btn = QPushButton("💾 Save images")
        self.save_btn.clicked.connect(self.save_images)
        ov.addWidget(choose)
        ov.addWidget(self.folder_label)
        ov.addWidget(self.save_btn)
        v.addWidget(out_box)

        self.counts_label = QLabel("")
        self.counts_label.setWordWrap(True)
        v.addWidget(self.counts_label)
        v.addStretch(1)
        return panel

    def control_panel(self):
        return self._panel

    # ---------------------------------------------------------------- load
    def load_pasted(self) -> None:
        text = self.paste.toPlainText().strip()
        if not text:
            return
        self.session.load(parse_records(text=text))
        self._saved_signature = self._signature()
        self.refresh()
        self.changed.emit()
        self.status_message.emit(f"Loaded {len(self.session.records)} frame(s).")

    def load_file(self, path: str) -> None:
        with open(path, "rb") as handle:
            data = handle.read()
        self.session.load(parse_records(file_bytes=data, filename=os.path.basename(path)))
        self._saved_signature = self._signature()
        self.refresh()
        self.changed.emit()
        self.status_message.emit(f"Loaded {len(self.session.records)} frame(s) from {os.path.basename(path)}.")

    # ---------------------------------------------------------------- run
    def run_source(self, source: str) -> None:
        if not self.session.records:
            QMessageBox.information(self, "No frames", "Load some frames first.")
            return
        todo = [i for i in range(len(self.session.records)) if i not in self.session.images]
        if not todo:
            QMessageBox.information(self, "Nothing to do", "Every frame already has an image.")
            return
        self._set_running(True)
        self.status_message.emit(f"Matching via {source}…")
        worker = Worker(pipeline.RUNNERS[source], self.session.records, todo,
                        pass_progress=True)
        worker.progress.connect(lambda _f, text: self.status_message.emit(text))

        def done(outcomes):
            self._set_running(False)
            if outcomes.get("_needs_login"):
                self._handle_needs_login(source)
                return
            before = len(self.session.images)
            self.session.apply_source(source, outcomes)
            got = len(self.session.images) - before
            picks = sum(1 for o in outcomes.values()
                        if isinstance(o, dict) and "candidates" in o)
            self.refresh()
            self.changed.emit()
            self.status_message.emit(
                f"{source}: {got} image(s) downloaded"
                + (f", {picks} need a pick (double-click them)." if picks else "."))

        worker.done.connect(done)
        worker.failed.connect(
            lambda msg: (self._set_running(False),
                         QMessageBox.warning(self, f"{source} failed", msg)))
        worker.start()
        self._worker = worker

    def _handle_needs_login(self, source: str) -> None:
        if source == "luxottica":
            answer = QMessageBox.question(
                self, "EssilorLuxottica login",
                "Not logged in. Set a username/password in ⚙️ Settings for automatic "
                "login, or open a login window now?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if answer != QMessageBox.Yes:
                return
            import luxottica
            self._set_running(True)
            self.status_message.emit("Opening EssilorLuxottica login…")
            worker = Worker(luxottica.login)

            def done(ok):
                self._set_running(False)
                QMessageBox.information(
                    self, "Login" + (" done" if ok else " not detected"),
                    "Logged in — click Match again." if ok else "Login was not detected.")
            worker.done.connect(done)
            worker.failed.connect(lambda m: (self._set_running(False),
                                             QMessageBox.warning(self, "Login failed", m)))
            worker.start()
            self._worker = worker
        else:
            QMessageBox.information(self, "Safilo login",
                                    "Safilo login was not completed. Click Match via Safilo "
                                    "again and log in when the window opens.")

    def run_manual(self) -> None:
        """✍️ Manual — a source of its own: paste a link or choose a file.

        Acts on the selected row(s); with no selection it walks every frame that
        still has no image, so whatever the automatic sources missed can be
        filled in one pass (Skip moves on, Stop ends the walk).
        """
        if not self.session.records:
            QMessageBox.information(self, "No frames", "Load some frames first.")
            return
        rows = sorted({index.row() for index in self.table.selectedIndexes()})
        if not rows:
            rows = [i for i in range(len(self.session.records))
                    if i not in self.session.images
                    and (self.session.records[i].get("name")
                         or self.session.records[i].get("barcode"))]
        if not rows:
            QMessageBox.information(
                self, "Nothing to fill",
                "Every frame already has an image. Select a row to replace one.")
            return

        filled = 0
        for n, idx in enumerate(rows):
            dialog = FillDialog(self.session, idx, self, position=(n + 1, len(rows)))
            dialog.exec()
            if dialog.result:
                data, ext, _source = dialog.result
                self.session.store(idx, data, ext, "manual")
                filled += 1
            if dialog.stopped:
                break
        self.refresh()
        self.changed.emit()
        self.status_message.emit(f"Manual: {filled} image(s) added.")

    def _set_running(self, running: bool) -> None:
        self.busy.emit(running)
        for btn in self._source_buttons:
            btn.setEnabled(not running)

    # ---------------------------------------------------------------- table
    def refresh(self) -> None:
        recs = self.session.records
        self.table.setRowCount(0)
        for i, rec in enumerate(recs):
            self.table.insertRow(i)
            self.table.setItem(i, 0, QTableWidgetItem(rec.get("barcode", "")))
            self.table.setItem(i, 1, QTableWidgetItem(rec.get("name", "")))
            self.table.setItem(i, 2, QTableWidgetItem(_STATUS_TEXT.get(self.session.status(i), "")))
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)

        with_names = sum(1 for r in recs if r.get("name"))
        self.info.setText(
            f"{len(recs)} frame(s) — {with_names} with a name, {len(self.session.images)} with an image."
            if recs else "No frames loaded.")
        counts = self.session.counts()
        if counts:
            self.counts_label.setText("Images: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
        else:
            self.counts_label.setText("")
        self.save_btn.setEnabled(bool(self.session.images))

    # ---------------------------------------------------------------- copy
    def _table_menu(self, point) -> None:
        rows = sorted({index.row() for index in self.table.selectedIndexes()})
        menu = QMenu(self)
        if rows:
            menu.addAction("Copy barcode", lambda: self._copy_column(rows, 0))
            menu.addAction("Copy name", lambda: self._copy_column(rows, 1))
            menu.addAction("Copy row(s) as TSV", lambda: self._copy_rows(rows))
            menu.addSeparator()
        menu.addAction("Copy whole table as TSV",
                       lambda: self._copy_rows(range(self.table.rowCount())))
        menu.exec(self.table.viewport().mapToGlobal(point))

    def _cell(self, row: int, column: int) -> str:
        item = self.table.item(row, column)
        return item.text() if item is not None else ""

    def _copy_column(self, rows, column: int) -> None:
        values = [self._cell(row, column) for row in rows]
        QApplication.clipboard().setText("\n".join(values))
        self.status_message.emit(f"Copied {len(values)} {COLUMNS[column].lower()}(s).")

    def _copy_rows(self, rows) -> None:
        lines = ["\t".join(COLUMNS)]
        for row in rows:
            lines.append("\t".join(self._cell(row, c) for c in range(len(COLUMNS))))
        QApplication.clipboard().setText("\n".join(lines))
        self.status_message.emit("Copied — paste straight into Excel.")

    def _edit_row(self, index) -> None:
        idx = index.row()
        rec = self.session.records[idx]
        if not rec.get("name") and not rec.get("barcode"):
            return
        dialog = FillDialog(self.session, idx, self)
        dialog.exec()
        if dialog.result:
            data, ext, _source = dialog.result
            self.session.store(idx, data, ext, "manual")
            self.refresh()
            self.changed.emit()
            self.status_message.emit("Image set.")

    # ---------------------------------------------------------------- save
    def choose_folder(self) -> None:
        start = self.settings.last_dir("output") or os.path.expanduser("~")
        folder = QFileDialog.getExistingDirectory(self, "Choose output folder", start,
                                                  QFileDialog.Option(0))
        if folder:
            self.settings.set_last_dir("output", folder)
            self.folder_label.setText(folder)

    def save_images(self) -> None:
        if not self.session.images:
            QMessageBox.information(self, "Nothing to save", "No images gathered yet.")
            return
        folder = self.folder_label.text()
        if not folder or not os.path.isdir(folder):
            self.choose_folder()
            folder = self.folder_label.text()
            if not folder or not os.path.isdir(folder):
                return
        answer = QMessageBox.question(
            self, "Save images",
            f"Write {len(self.session.images)} image(s) to:\n{folder}?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if answer != QMessageBox.Yes:
            return
        written = pipeline.save_images(self.session.records, self.session.images, folder)
        self._saved_signature = self._signature()
        self.changed.emit()
        QMessageBox.information(self, "Saved", f"{len(written)} image(s) written to:\n{folder}")
        self.status_message.emit(f"Saved {len(written)} image(s).")

    # ---------------------------------------------------------------- dirty
    def _signature(self):
        return tuple(sorted(self.session.images.keys())) if self.session.images else ()

    def has_unsaved_changes(self) -> bool:
        return bool(self.session.images) and self._signature() != self._saved_signature
