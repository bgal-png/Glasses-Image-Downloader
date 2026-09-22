# -*- coding: utf-8 -*-
"""In-memory session model (Qt-free): the frames and the images gathered for them."""
from __future__ import annotations


class Session:
    def __init__(self) -> None:
        self.records = []      # [{"barcode": str, "name": str}]
        self.images = {}       # idx -> {"bytes": bytes, "ext": str, "source": str}
        self.variants = {}     # idx -> [{"label": str, "image_url": str}]

    def load(self, records) -> None:
        self.records = list(records)
        self.images = {}
        self.variants = {}

    def store(self, idx: int, image: bytes, ext: str, source: str) -> None:
        self.images[idx] = {"bytes": image, "ext": ext or ".jpg", "source": source}
        self.variants.pop(idx, None)

    def apply_source(self, source: str, outcomes: dict) -> None:
        """Fold a run_* result into the session."""
        for idx, outcome in outcomes.items():
            if not isinstance(idx, int):
                continue  # e.g. the "_needs_login" marker
            if "image" in outcome:
                self.store(idx, outcome["image"], outcome["ext"], source)
            elif "candidates" in outcome and idx not in self.images:
                self.variants[idx] = outcome["candidates"]

    def names_todo(self) -> list:
        return [i for i in range(len(self.records))
                if self.records[i].get("name") and i not in self.images]

    def status(self, idx: int) -> str:
        if idx in self.images:
            return self.images[idx]["source"]     # "barcode"/"luxottica"/"alpina"/"safilo"/"manual"/"url"
        if idx in self.variants:
            return "pick"
        rec = self.records[idx]
        if not rec.get("name") and not rec.get("barcode"):
            return "empty"
        return "todo"

    def counts(self) -> dict:
        c = {}
        for data in self.images.values():
            c[data["source"]] = c.get(data["source"], 0) + 1
        return c
