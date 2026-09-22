# -*- coding: utf-8 -*-
"""Self-update from GitHub Releases.

Compares version.__version__ with the newest `desktop-v*` release tag. If the
user accepts, downloads the .exe asset next to the running one and swaps it via
a detached PowerShell command that waits for this process to exit, replaces the
file and relaunches it — a running .exe can't overwrite itself on Windows.

This repo is private, so both the release lookup and the asset download require
a GitHub token (Settings > update token); without one, callers get a "not
configured" outcome rather than an HTTP failure.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request

from app_paths import is_frozen
from version import RELEASE_REPO, RELEASE_TAG_PREFIX, __version__

_TIMEOUT = 30


def _version_tuple(text: str) -> tuple:
    parts = []
    for chunk in str(text).strip().lstrip("vV").split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def _request(url: str, token: str, accept: str) -> urllib.request.Request:
    request = urllib.request.Request(url)
    request.add_header("User-Agent", "GlassesImageDownloader-Desktop")
    request.add_header("Accept", accept)
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    return request


def latest_release(token: str = "") -> dict | None:
    """Newest desktop release as {'version','tag','url','name'} or None."""
    url = f"https://api.github.com/repos/{RELEASE_REPO}/releases"
    with urllib.request.urlopen(
        _request(url, token, "application/vnd.github+json"), timeout=_TIMEOUT
    ) as response:
        releases = json.loads(response.read().decode("utf-8"))

    best = None
    for release in releases:
        tag = str(release.get("tag_name", ""))
        if not tag.startswith(RELEASE_TAG_PREFIX) or release.get("draft"):
            continue
        version = tag[len(RELEASE_TAG_PREFIX):]
        asset = next(
            (a for a in release.get("assets", [])
             if str(a.get("name", "")).lower().endswith(".exe")),
            None,
        )
        if not asset:
            continue
        candidate = {
            "version": version,
            "tag": tag,
            "url": asset["url"],  # API asset URL works for private repos
            "name": asset["name"],
        }
        if best is None or _version_tuple(version) > _version_tuple(best["version"]):
            best = candidate
    return best


def update_available(token: str = "") -> dict | None:
    """The newer release, or None if we're current / can't tell."""
    try:
        release = latest_release(token)
    except Exception:
        return None
    if release and _version_tuple(release["version"]) > _version_tuple(__version__):
        return release
    return None


SWAP_LOG_NAME = "glassesimagedownloader_update.log"


def swap_log_path() -> str:
    import tempfile
    return os.path.join(tempfile.gettempdir(), SWAP_LOG_NAME)


def _ps_quote(path: str) -> str:
    """Single-quote a path for PowerShell (doubling any embedded quote)."""
    return "'" + str(path).replace("'", "''") + "'"


def build_swap_script(pid: int, src: str, dst: str, log: str) -> str:
    """The PowerShell one-liner that replaces the running .exe and relaunches it.

    PowerShell rather than a .bat: `timeout` fails without a console inside a
    detached process, which silently breaks the wait+relaunch. `Wait-Process`
    needs no console. The move is retried because Windows can hold the old file
    briefly after the process object is gone; everything is logged.
    """
    q_src, q_dst, q_log = _ps_quote(src), _ps_quote(dst), _ps_quote(log)
    q_bak = _ps_quote(str(dst) + ".bak")
    return (
        "$ErrorActionPreference='Continue'; "
        f"function L($m){{ \"$(Get-Date -Format o) $m\" | Out-File -FilePath {q_log} -Append -Encoding utf8 }}; "
        f"L 'waiting for pid {pid}'; "
        f"Wait-Process -Id {pid} -Timeout 180 -ErrorAction SilentlyContinue; "
        f"try{{ Move-Item -LiteralPath {q_dst} -Destination {q_bak} -Force -ErrorAction Stop; L 'backed up old exe to .bak' }}"
        f"catch{{ L \"backup failed: $_\" }}; "
        "$moved=$false; "
        "for($i=0;$i -lt 40 -and -not $moved;$i++){ "
        f"  try{{ Move-Item -LiteralPath {q_src} -Destination {q_dst} -Force -ErrorAction Stop; $moved=$true }}"
        "  catch{ Start-Sleep -Milliseconds 500 } }; "
        "if($moved){ L 'replaced the exe' } else { L 'MOVE FAILED - the old version is still in place' }; "
        f"try{{ Start-Process -FilePath {q_dst}; L 'relaunched' }}catch{{ L \"relaunch failed: $_\" }}"
    )


def download_and_swap(release: dict, token: str = "", progress=None) -> str:
    """Download the new .exe and hand over to the swap script. Returns the path
    of the downloaded file. The swap only happens when running frozen."""
    target_dir = os.path.dirname(
        sys.executable if is_frozen() else os.path.abspath(__file__)
    )
    new_path = os.path.join(target_dir, f"_update_{release['name']}")

    request = _request(release["url"], token, "application/octet-stream")
    with urllib.request.urlopen(request, timeout=300) as response:
        total = int(response.headers.get("Content-Length") or 0)
        read = 0
        with open(new_path, "wb") as handle:
            while True:
                chunk = response.read(256 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
                read += len(chunk)
                if progress and total:
                    progress(read / total, f"Downloading update… {read // 1048576} MB")

    if total and read < total:
        os.remove(new_path)
        raise IOError(f"Download incomplete ({read} of {total} bytes) — update aborted.")

    with open(new_path, "rb") as handle:
        magic = handle.read(2)
    if magic != b"MZ" or os.path.getsize(new_path) < 1_000_000:
        os.remove(new_path)
        raise IOError(
            "The downloaded file is not a valid Windows executable — update aborted."
        )

    if not is_frozen():
        return new_path  # nothing to swap when running from source

    script = build_swap_script(os.getpid(), new_path, sys.executable, swap_log_path())
    subprocess.Popen(
        ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", script],
        creationflags=0x08000000,  # CREATE_NO_WINDOW
    )
    return new_path
