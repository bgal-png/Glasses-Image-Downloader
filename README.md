# Barcode Image Downloader

Local Streamlit app that downloads the main product image for a list of
barcodes from barcodelookup.com.

## One-time setup

```
pip install -r requirements.txt
python -m playwright install chromium
```

## Run

Double-click `run.bat`, or from a terminal:

```
python -m streamlit run app.py
```

The app opens in your browser. Paste barcodes (one per line) or upload an
`.xlsx` / `.csv` / `.txt`. For spreadsheets it auto-detects the column named
**Barcode** (falling back to the first column). Click **Download images**, then
**Download all as ZIP**. Images are named by barcode (e.g. `197737257521.jpg`).

## Make a desktop shortcut

1. Right-click `run.bat` → **Show more options** → **Send to** → **Desktop
   (create shortcut)**.
2. On the Desktop, rename the shortcut to "Barcode Image Downloader".
3. (Optional) Right-click the shortcut → **Properties** → **Change Icon** to
   pick a nicer icon.

Now double-clicking the shortcut launches the app.

## Notes

- Runs locally on purpose: a real browser on your own IP passes the site's
  Cloudflare protection. Cloud hosting (e.g. Streamlit Cloud) gets blocked.
- Only the main/biggest image is downloaded (not gallery thumbnails).
- Barcodes that don't exist or have no image are marked ❌ and skipped; the run
  continues.
- A short polite delay between barcodes (adjustable in the app) avoids tripping
  rate limits.
