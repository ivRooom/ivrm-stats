#!/usr/bin/env python3
from __future__ import annotations

import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML_FILES = [
    ROOT / "index.html",
    ROOT / "history" / "index.html",
]
REQUIRED_FILES = [
    *HTML_FILES,
    ROOT / "assets" / "styles.css",
    ROOT / "assets" / "app.js",
    ROOT / "assets" / "history.css",
    ROOT / "assets" / "history.js",
    ROOT / "assets" / "navigation.css",
    ROOT / "assets" / "status-presentation.js",
]


class DocumentInspector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.duplicate_ids: set[str] = set()
        self.has_lang = False
        self.has_title = False
        self.has_viewport = False
        self.has_main = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "html" and values.get("lang"):
            self.has_lang = True
        if tag == "meta" and values.get("name") == "viewport":
            self.has_viewport = True
        if tag == "main":
            self.has_main = True
        element_id = values.get("id")
        if element_id:
            if element_id in self.ids:
                self.duplicate_ids.add(element_id)
            self.ids.add(element_id)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)


errors: list[str] = []

for path in REQUIRED_FILES:
    if not path.is_file():
        errors.append(f"missing required file: {path.relative_to(ROOT)}")

if not errors:
    for path in HTML_FILES:
        relative = path.relative_to(ROOT)
        html = path.read_text(encoding="utf-8")
        inspector = DocumentInspector()
        inspector.feed(html)
        inspector.has_title = "<title>" in html and "</title>" in html

        if not inspector.has_lang:
            errors.append(f"{relative} must declare html[lang]")
        if not inspector.has_title:
            errors.append(f"{relative} must include a title")
        if not inspector.has_viewport:
            errors.append(f"{relative} must include a viewport meta tag")
        if not inspector.has_main:
            errors.append(f"{relative} must include a main element")
        if inspector.duplicate_ids:
            errors.append(
                f"{relative} duplicate ids: {', '.join(sorted(inspector.duplicate_ids))}"
            )

if errors:
    print("Validation failed:")
    for error in errors:
        print(f"- {error}")
    sys.exit(1)

print("Public status pages validation passed.")
