@echo off
REM Launch the Barcode Image Downloader and open it in the browser.
cd /d "%~dp0"
python -m streamlit run app.py
