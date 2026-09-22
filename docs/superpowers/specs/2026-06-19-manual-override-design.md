# Manual Override for Any Frame — Design

**Date:** 2026-06-19
**Author:** bgal@alensa.eu

## Purpose

Let the user manually replace the image of **any** frame, not just the ones the
barcode lookup missed. If an auto-found image is wrong/ugly, the user pulls that
frame into the manual-fill area, sees a preview of the current image, and
overrides it via the existing paste-URL / upload flow. The manual image wins.

## Context

This is a UI-only change to `app.py` (v2). The engine (`fetcher.py`) and parser
(`barcode_parser.py`) are unchanged. Current v2 state in app.py:
- `st.session_state.records` — list of `{"barcode","name"}`.
- `st.session_state.results` — aligned list of `{"status": "found"|"needs_image"|"no_source"}`.
- `st.session_state.images` — `idx -> {"bytes","ext","source"}` (`source` is
  "barcode" / "url" / "upload").
- The manual-fill section currently lists only `needs` = indices whose status is
  `needs_image` and which are not yet in `images`.

## Change

### 1. "Redo these frames" selector (new)
In the results area (after the table, before the fill section), add a
`st.multiselect` listing frames the user might want to override. To keep it
useful and not overwhelming:
- Options = every frame that currently HAS an image (source "barcode", "url", or
  "upload") — i.e. candidates worth replacing. (Misses without an image are
  already in the fill section, so they need not appear here.)
- Each option label: `"{barcode or '(no barcode)'} — {name or '(no name)'}"`.
- The selected indices are stored in `st.session_state.redo` (a set/list) so the
  selection survives reruns.

### 2. Fill section covers misses + redo selections
The list rendered in the "fill" section becomes the union, in record order, of:
- auto misses: status `needs_image` AND not in `images`, plus
- user-selected redo frames: indices in `st.session_state.redo`.
(De-duplicated; preserve record order.)

Each entry shows:
- `**{name}**` + `` `{barcode or 'no barcode'}` ``.
- **If the frame currently has an image:** a small preview via
  `st.image(images[idx]["bytes"], width=160)` with a caption noting the source
  (e.g. "current: barcode"). Misses with no image show nothing here.
- The `search_links(name)` links (only when the frame has a name; a redo frame
  with no name simply shows no links).
- Paste-URL `st.text_input` (key `url_{idx}`) and file `st.file_uploader`
  (key `file_{idx}`), exactly as today.

Providing a new image calls `_store_image(idx, ...)` which overwrites the entry
in `images` — overriding whatever was there (barcode/url/upload). Then
`st.rerun()`.

### 3. Status label reflects overrides
The results table label logic already shows
`"✅ filled ({source})"` when `idx in images and status != "found"`. Extend so a
**found** frame that has been overridden (source no longer "barcode") also shows
`"✅ replaced ({source})"`. Concretely: if `idx in images` and
`images[idx]["source"] != "barcode"`, label = `"✅ {source} image"`; else if
status == "found", `"✅ found by barcode"`; else the existing miss labels.

### 4. Deselect = revert
If a user selects a frame to redo but does NOT provide a new image, its existing
image is untouched. Removing it from the multiselect simply drops it from the
fill section. (We never delete from `images` on deselect.) A frame the user
selected and then uploaded a replacement for stays replaced even if later
deselected — the new image is already stored.

### 5. ZIP
Unchanged. It iterates `st.session_state.images` and names each by
`barcode or sanitized name`. Because overrides overwrite in place, the ZIP
naturally contains the latest image per frame.

## Error handling

Unchanged from v2: `download_url_bytes` failure shows the "try uploading
instead" warning; nothing crashes; deselecting is always safe.

## Testing

`app.py` is glue; verified by:
- Boot test (py_compile + headless health 200).
- Controller real-app walkthrough: run a barcode hit, select that found frame in
  the redo multiselect, confirm its current-image preview appears, paste a
  different image URL, confirm the table flips to a replaced/url label and the
  ZIP contains the new bytes (different size) under the same barcode filename.

No parser/engine tests change (no engine/parser change).

## Out of scope

- Retrying the barcode lookup for individual frames (user chose manual-replace
  only).
- A full thumbnail gallery of all found images (only per-entry previews in the
  redo/fill section).
- Editing barcodes/names after parsing.

## Notes

- NOT a git repo; skip git steps.
- Change is confined to `app.py`; keep it readable (the fill-list construction
  and label logic are the only added complexity).
