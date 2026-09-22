# -*- coding: utf-8 -*-
"""Pick / fill an image for one frame.

Shows the source's candidate thumbnails (when a match was ambiguous) plus a
manual paste-URL and choose-file fallback. Sets `result` to
(bytes, ext, source) on accept.
"""
from __future__ import annotations

import os

from fetcher import download_url_bytes
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication, QDialogButtonBox, QDialog, QFileDialog, QGridLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

_IMG_EXTS = (".jpg", ".jpeg", ".png", ".webp")


class FillDialog(QDialog):
    def __init__(self, session, idx, parent=None, position=None):
        super().__init__(parent)
        self.session = session
        self.idx = idx
        self.result = None    # (bytes, ext, source)
        self.stopped = False  # set by Stop when walking a list of frames

        rec = session.records[idx]
        where = f"[{position[0]}/{position[1]}] " if position else ""
        self.setWindowTitle(
            f"{where}Image for: {rec.get('name') or rec.get('barcode') or 'frame'}")
        self.resize(680, 560)

        layout = QVBoxLayout(self)
        header = QLabel(f"<b>{rec.get('name') or '(no name)'}</b><br>"
                        f"<code>{rec.get('barcode') or 'no barcode'}</code>")
        header.setTextFormat(Qt.RichText)
        # Qt labels aren't selectable by default — make the name/barcode
        # selectable so they can be copied straight into a search.
        header.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        header.setCursor(Qt.IBeamCursor)
        layout.addWidget(header)

        copy_row = QHBoxLayout()
        for label, value in (("📋 Copy name", rec.get("name") or ""),
                             ("📋 Copy barcode", rec.get("barcode") or "")):
            button = QPushButton(label)
            button.setEnabled(bool(value))
            button.clicked.connect(
                lambda _=False, v=value, b=button, t=label: self._copy(v, b, t))
            copy_row.addWidget(button)
        copy_row.addStretch(1)
        layout.addLayout(copy_row)

        # current image preview, if any
        current = session.images.get(idx)
        if current:
            box = QGroupBox("Current image")
            row = QHBoxLayout(box)
            pic = QLabel()
            pm = QPixmap()
            pm.loadFromData(current["bytes"])
            pic.setPixmap(pm.scaled(140, 140, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            row.addWidget(pic)
            row.addWidget(QLabel(f"source: {current['source']}"))
            row.addStretch(1)
            layout.addWidget(box)

        # candidate thumbnails
        candidates = session.variants.get(idx) or []
        if candidates:
            box = QGroupBox(f"Candidates ({len(candidates)}) — click one to use it")
            outer = QVBoxLayout(box)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            grid_host = QWidget()
            grid = QGridLayout(grid_host)
            for n, cand in enumerate(candidates[:12]):
                grid.addWidget(self._candidate_button(cand), n // 4, n % 4)
            scroll.setWidget(grid_host)
            outer.addWidget(scroll)
            layout.addWidget(box, 1)

        # manual fallback
        manual = QGroupBox("Or provide it manually")
        mform = QVBoxLayout(manual)
        url_row = QHBoxLayout()
        self.url = QLineEdit()
        self.url.setPlaceholderText("paste a direct image URL")
        url_btn = QPushButton("Use URL")
        url_btn.clicked.connect(self._use_url)
        url_row.addWidget(self.url, 1)
        url_row.addWidget(url_btn)
        mform.addLayout(url_row)
        file_btn = QPushButton("Choose image file…")
        file_btn.clicked.connect(self._use_file)
        mform.addWidget(file_btn)
        layout.addWidget(manual)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        if position:
            # Walking a list: Close = skip this frame, Stop = end the walk.
            buttons.button(QDialogButtonBox.Close).setText("Skip")
            stop = buttons.addButton("Stop", QDialogButtonBox.RejectRole)
            stop.clicked.connect(self._stop)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _stop(self) -> None:
        self.stopped = True

    def _copy(self, value: str, button, label: str) -> None:
        """Copy to the clipboard, confirming on the button itself for a moment."""
        QApplication.clipboard().setText(value)
        button.setText("✓ Copied")
        QTimer.singleShot(1200, lambda: button.setText(label))

    def _candidate_button(self, cand) -> QWidget:
        btn = QPushButton()
        btn.setFixedSize(150, 150)
        dl = download_url_bytes(cand["image_url"])
        if dl:
            pm = QPixmap()
            pm.loadFromData(dl[0])
            btn.setIcon(pm)  # type: ignore[arg-type]
            from PySide6.QtCore import QSize
            from PySide6.QtGui import QIcon
            btn.setIcon(QIcon(pm))
            btn.setIconSize(QSize(132, 120))
        btn.setText((cand.get("label") or "")[:22])
        btn.clicked.connect(lambda: self._pick_candidate(cand))
        return btn

    def _pick_candidate(self, cand) -> None:
        dl = download_url_bytes(cand["image_url"])
        if not dl:
            QMessageBox.warning(self, "Download failed",
                                "That candidate image could not be downloaded. Try another.")
            return
        self.result = (dl[0], dl[1], "manual")
        self.accept()

    def _use_url(self) -> None:
        url = self.url.text().strip()
        if not url:
            return
        dl = download_url_bytes(url)
        if not dl:
            QMessageBox.warning(self, "Couldn't fetch that URL",
                                "The URL did not return an image. Try 'Choose image file…' instead.")
            return
        self.result = (dl[0], dl[1], "url")
        self.accept()

    def _use_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose image", os.path.expanduser("~"),
            "Images (*.jpg *.jpeg *.png *.webp)",
        )
        if not path:
            return
        ext = os.path.splitext(path)[1].lower() or ".jpg"
        if ext not in _IMG_EXTS:
            QMessageBox.warning(self, "Unsupported", f"{ext} is not a supported image type.")
            return
        with open(path, "rb") as handle:
            data = handle.read()
        self.result = (data, ext, "manual")
        self.accept()
