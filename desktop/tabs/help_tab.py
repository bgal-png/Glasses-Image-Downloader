# -*- coding: utf-8 -*-
"""❔ Help — how the app works. No control panel (the dock hides on this tab)."""
from __future__ import annotations

from PySide6.QtWidgets import QTextBrowser, QVBoxLayout

from tabs.base import BaseTab
from version import __version__

_HTML = f"""
<h2>Glasses Image Downloader {__version__}</h2>
<p>Match product images for a list of glasses by <b>barcode</b> and <b>name</b>,
then save them to a folder.</p>
<ol>
<li><b>Load frames</b> — paste lines (<code>barcode</code> or
    <code>barcode, name</code>) on the Download tab, or use <b>📂 Open file</b>
    (.xlsx / .csv / .txt). Spreadsheets auto-detect the <i>Barcode</i> and
    <i>Glasses name</i> columns.</li>
<li><b>Match a source</b> from the Control panel:
  <ul>
    <li><b>Run barcode lookup</b> — barcodelookup.com by barcode.</li>
    <li><b>EssilorLuxottica</b> — Ray-Ban, Oakley, Persol, Prada, Miu Miu…
        (auto-logs in if you saved credentials in ⚙️ Settings).</li>
    <li><b>Alpina</b> — public, no login.</li>
    <li><b>Safilo</b> — Hugo Boss, Marc Jacobs, Carrera… opens a login window.</li>
  </ul>
  You can run several sources; each only fills frames that don't have an image yet.</li>
<li><b>Pick / fill</b> — double-click any row to choose among candidate images or
    paste a URL / choose a file. Rows marked “🎨 pick an image” need a choice.</li>
<li><b>Save</b> — choose an output folder and <b>💾 Save images</b>; each file is
    named by its barcode (or product name).</li>
</ol>
<p>Credentials (EssilorLuxottica login, update token) live only on this PC —
in ⚙️ Settings / Windows Credential Manager, never in the app file.</p>
"""


class HelpTab(BaseTab):
    TITLE = "❔ Help"

    def __init__(self, session, settings, parent=None):
        super().__init__(session, settings, parent)
        layout = QVBoxLayout(self)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setHtml(_HTML)
        layout.addWidget(browser)
