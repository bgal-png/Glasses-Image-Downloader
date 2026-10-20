# -*- coding: utf-8 -*-
"""Glasses Image Downloader — desktop entry point.

Run from source:   "C:\\gv\\Scripts\\python.exe" desktop\\main.py
Selftest:          "C:\\gv\\Scripts\\python.exe" desktop\\main.py --selftest
Build:             "C:\\gv\\Scripts\\pyinstaller.exe" desktop\\GlassesImageDownloader.spec
"""
from __future__ import annotations

import os
import sys

# --- import bootstrap: desktop modules (flat) + the shared core modules (root) ---
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_HERE, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)
# ---------------------------------------------------------------------------

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QAction, QIcon  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication, QDockWidget, QFileDialog, QMainWindow, QMessageBox,
    QProgressBar, QTabWidget, QVBoxLayout, QWidget,
)

import theme  # noqa: E402
import updater  # noqa: E402
from app_paths import resource_path  # noqa: E402
from settings import Settings  # noqa: E402
from settings_dialog import SettingsDialog  # noqa: E402
from state import Session  # noqa: E402
from tabs import ALL_TABS  # noqa: E402
from version import APP_NAME, ORG_NAME, __version__  # noqa: E402
from workers import Worker  # noqa: E402


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = Settings()
        self.session = Session()
        self._update_worker = None

        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.resize(1150, 760)

        self.tabs = QTabWidget()
        self.tab_widgets = []
        for cls in ALL_TABS:
            tab = cls(self.session, self.settings, self)
            tab.status_message.connect(self.show_status)
            tab.busy.connect(self.set_busy)
            tab.changed.connect(self._on_changed)
            self.tabs.addTab(tab, cls.TITLE)
            self.tab_widgets.append(tab)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.setCentralWidget(self.tabs)
        self.download_tab = self.tab_widgets[0]

        self.dock = QDockWidget("Control panel", self)
        self.dock.setObjectName("control_panel")
        self.dock.setAllowedAreas(Qt.RightDockWidgetArea | Qt.LeftDockWidgetArea)
        self.dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        self._empty_dock = QWidget()
        QVBoxLayout(self._empty_dock)
        self.dock.setWidget(self._empty_dock)
        self.addDockWidget(Qt.RightDockWidgetArea, self.dock)
        self.resizeDocks([self.dock], [300], Qt.Horizontal)

        self._build_toolbar()

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        self.progress.setMaximumWidth(180)
        self.statusBar().addPermanentWidget(self.progress)

        self._on_tab_changed(self.tabs.currentIndex())
        self.download_tab.refresh()

    # ------------------------------------------------------------- toolbar
    def _build_toolbar(self) -> None:
        bar = self.addToolBar("Main")
        bar.setObjectName("main_toolbar")

        self.act_open = QAction("📂 Open file", self)
        self.act_open.triggered.connect(self.open_file)
        bar.addAction(self.act_open)

        bar.addSeparator()

        self.act_settings = QAction("⚙️ Settings", self)
        self.act_settings.triggered.connect(self.open_settings)
        bar.addAction(self.act_settings)

        self.act_update = QAction("⬆️ Check updates", self)
        self.act_update.triggered.connect(self.check_updates)
        bar.addAction(self.act_update)

        self.act_dark = QAction("🌙 Dark mode", self)
        self.act_dark.setCheckable(True)
        self.act_dark.setChecked(self.settings.dark_mode)
        self.act_dark.toggled.connect(self.toggle_dark)
        bar.addAction(self.act_dark)

    def _on_tab_changed(self, index: int) -> None:
        tab = self.tabs.widget(index)
        panel = tab.control_panel() if tab else None
        if panel is None:
            self.dock.setWidget(self._empty_dock)
            self.dock.hide()
        else:
            self.dock.setWidget(panel)
            self.dock.show()

    def _on_changed(self) -> None:
        for tab in self.tab_widgets:
            tab.refresh()
        self._update_title()

    # -------------------------------------------------------------- status
    def show_status(self, message: str) -> None:
        self.statusBar().showMessage(message, 8000)

    def set_busy(self, busy: bool) -> None:
        self.progress.setVisible(bool(busy))
        self.act_open.setEnabled(not busy)
        self.act_update.setEnabled(not busy)

    def _update_title(self) -> None:
        mark = " •" if self.download_tab.has_unsaved_changes() else ""
        self.setWindowTitle(f"{APP_NAME} {__version__}{mark}")

    # --------------------------------------------------------------- open
    def open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open frames file",
            self.settings.last_dir("input") or os.path.expanduser("~"),
            "Frames (*.xlsx *.xls *.csv *.txt)",
        )
        if not path:
            return
        self.settings.set_last_dir("input", os.path.dirname(path))
        try:
            self.download_tab.load_file(path)
        except Exception as error:
            QMessageBox.warning(self, "Could not load file",
                                f"{error.__class__.__name__}: {error}")

    # ------------------------------------------------------------ settings
    def open_settings(self) -> None:
        SettingsDialog(self.settings, self).exec()

    def toggle_dark(self, enabled: bool) -> None:
        self.settings.dark_mode = bool(enabled)
        theme.apply_theme(QApplication.instance(), bool(enabled))

    # ------------------------------------------------------------- updates
    def check_updates(self) -> None:
        if not self.settings.update_token:
            QMessageBox.information(
                self, "Updates not configured",
                "This repo is private, so the update check needs a GitHub token "
                "with read access to its Releases.\nAdd one in ⚙️ Settings.")
            return
        self.set_busy(True)
        worker = Worker(updater.update_available, self.settings.update_token)

        def done(release):
            self.set_busy(False)
            if not release:
                QMessageBox.information(self, "Up to date",
                                       f"You are on the latest version ({__version__}).")
                return
            answer = QMessageBox.question(
                self, "Update available",
                f"Version {release['version']} is available (you have {__version__}).\n"
                "Download and install it now?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer == QMessageBox.Yes:
                self._download_update(release)

        worker.done.connect(done)
        worker.failed.connect(lambda m: (self.set_busy(False),
                                         QMessageBox.warning(self, "Update check failed", m)))
        worker.start()
        self._update_worker = worker

    def _download_update(self, release: dict) -> None:
        self.set_busy(True)
        worker = Worker(updater.download_and_swap, release, self.settings.update_token,
                        pass_progress=True)
        worker.progress.connect(lambda _f, text: self.show_status(text))

        def done(_path):
            self.set_busy(False)
            QMessageBox.information(self, "Restarting",
                                   "The update was downloaded. The app will now close and reopen.")
            QApplication.instance().quit()

        worker.done.connect(done)
        worker.failed.connect(lambda m: (self.set_busy(False),
                                         QMessageBox.warning(self, "Update failed", m)))
        worker.start()
        self._update_worker = worker

    # --------------------------------------------------------------- close
    def closeEvent(self, event) -> None:
        busy_workers = [self._update_worker, getattr(self.download_tab, "_worker", None)]
        for worker in busy_workers:
            if worker is not None and worker.isRunning():
                QMessageBox.information(self, "Still working",
                                       "A task is still running. Wait for it to finish before closing.")
                event.ignore()
                return
        if self.download_tab.has_unsaved_changes():
            answer = QMessageBox.question(
                self, "Images not saved",
                f"{len(self.session.images)} image(s) have not been saved to a folder yet. "
                "Close anyway?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes:
                event.ignore()
                return
        event.accept()


def _selftest(win) -> int:
    """--selftest: build the whole UI headlessly, print a report, exit."""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    problems = []
    print(f"{APP_NAME} {__version__}")
    print(f"tabs: {win.tabs.count()}")
    for index in range(win.tabs.count()):
        tab = win.tabs.widget(index)
        win.tabs.setCurrentIndex(index)
        QApplication.processEvents()
        panel = tab.control_panel()
        print(f"  [{index}] {win.tabs.tabText(index)!r:16} dock={'yes' if panel is not None else 'no'}")
        dock_visible = not win.dock.isHidden()
        if panel is not None and not dock_visible:
            problems.append(f"{tab.__class__.__name__}: dock hidden on a tab with a control panel")
        elif panel is None and dock_visible:
            problems.append(f"{tab.__class__.__name__}: dock shown on a tab with no control panel")
        for name in ("refresh", "control_panel", "has_unsaved_changes"):
            if not callable(getattr(tab, name, None)):
                problems.append(f"{tab.__class__.__name__} missing {name}")

    print(f"update token configured: {bool(win.settings.update_token)}")
    if problems:
        print("PROBLEMS:")
        for problem in problems:
            print("  -", problem)
        return 1
    print("SELFTEST OK — UI built.")
    return 0


def _sourcetest() -> int:
    """--sourcetest: prove every login-free browser source really works from a
    FROZEN build (bundled Playwright driver + the system Edge).

    Covers barcode (fetcher) and Alpina — the two that need no login. Both must
    launch Edge; a source missing `channel="msedge"` fails here rather than in
    the user's hands. EssilorLuxottica and Safilo need a login so they can't run
    unattended, but they use the same msedge channel.
    """
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    import pipeline

    problems = []

    def report(label, outcome):
        if outcome and "image" in outcome:
            print(f"  OK    {label}: image ({len(outcome['image'])} bytes)")
        elif outcome and "candidates" in outcome:
            print(f"  OK    {label}: {len(outcome['candidates'])} candidate(s)")
        else:
            print(f"  FAIL  {label}: no result")
            problems.append(label)

    print("sourcetest — Playwright + system Edge from this build")
    try:
        out = pipeline.run_barcode([{"barcode": "197737257521", "name": ""}], [0], delay=0.0)
        report("barcode", out.get(0))
    except Exception as error:
        print(f"  FAIL  barcode: {error.__class__.__name__}: {error}")
        problems.append("barcode")

    try:
        out = pipeline.run_alpina([{"barcode": "", "name": "Alpina DEFEY 2 black matt"}], [0])
        report("alpina", out.get(0))
    except Exception as error:
        print(f"  FAIL  alpina: {error.__class__.__name__}: {error}")
        problems.append("alpina")

    # Edel needs no browser, but it does need Pillow to turn the CDN's WebP
    # into JPEG — and a missing Pillow would only show up in a frozen build.
    try:
        out = pipeline.run_edel([{"barcode": "", "name": "Ray-Ban RB3793 001/31"}], [0])
        report("edel", out.get(0))
        data = (out.get(0) or {}).get("image", b"")
        if data and data[:2] != b"\xff\xd8":
            print("  FAIL  edel: not JPEG — Pillow missing from the build?")
            problems.append("edel (webp not converted)")
    except Exception as error:
        print(f"  FAIL  edel: {error.__class__.__name__}: {error}")
        problems.append("edel")

    if problems:
        print("SOURCETEST FAILED — " + ", ".join(problems))
        return 1
    print("SOURCETEST OK — all login-free sources work from this build.")
    return 0


def main() -> int:
    if "--sourcetest" in sys.argv:
        return _sourcetest()
    selftest = "--selftest" in sys.argv
    if selftest:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)
    app.setApplicationVersion(__version__)

    icon_path = resource_path("app_icon.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    settings = Settings()
    theme.apply_theme(app, settings.dark_mode)

    win = MainWindow()
    if selftest:
        QApplication.processEvents()
        code = _selftest(win)
        # Never leave a QThread alive at interpreter exit — Qt hangs on it.
        for attr in ("_update_worker",):
            worker = getattr(win, attr, None)
            if worker is not None and worker.isRunning():
                worker.wait(5000)
        dl_worker = getattr(win.download_tab, "_worker", None)
        if dl_worker is not None and dl_worker.isRunning():
            dl_worker.wait(5000)
        return code

    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
