# -*- coding: utf-8 -*-
"""Single source of truth for the desktop app version.

Bump this, tag the repo `desktop-v<x.y.z>` and attach the built .exe to the
GitHub Release — installed copies compare against the latest tag and offer to
self-update. The repo is private, so the check needs a token in Settings.
"""

APP_NAME = "Glasses Image Downloader"
ORG_NAME = "Alensa"
__version__ = "1.0.3"

RELEASE_REPO = "bgal-png/Glasses-Image-Downloader"
RELEASE_TAG_PREFIX = "desktop-v"
