#!/usr/bin/env python3

from pathlib import Path
import json


BASE_DIR = Path(__file__).resolve().parents[1]
CSS_DIR = BASE_DIR / "app" / "main" / "static" / "dpd_static_support" / "css"
JS_DIR = BASE_DIR / "app" / "main" / "static" / "dpd_static_support" / "js"


CSS_TARGETS = [
    "bootstrap.css",
    "bootstrap.min.css",
    "bootstrap-grid.css",
    "bootstrap-grid.min.css",
    "bootstrap-reboot.css",
    "bootstrap-reboot.min.css",
    "bootstrap-theme.css",
    "bootstrap-theme.min.css",
]

JS_TARGETS = [
    "bootstrap.js",
    "bootstrap.min.js",
    "bootstrap.bundle.js",
    "bootstrap.bundle.min.js",
    "popper.js",
    "popper.min.js",
    "alert.js",
    "alert.min.js",
    "button.js",
    "button.min.js",
    "carousel.js",
    "carousel.min.js",
    "collapse.js",
    "collapse.min.js",
    "dropdown.js",
    "dropdown.min.js",
    "index.js",
    "index.min.js",
    "modal.js",
    "modal.min.js",
    "popover.js",
    "popover.min.js",
    "scrollspy.js",
    "scrollspy.min.js",
    "tab.js",
    "tab.min.js",
    "toast.js",
    "toast.min.js",
    "tooltip.js",
    "tooltip.min.js",
    "util.js",
    "util.min.js",
]


def ensure_placeholder(directory: Path, asset_name: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    map_path = directory / f"{asset_name}.map"
    payload = {
        "version": 3,
        "file": asset_name,
        "sources": [],
        "names": [],
        "mappings": "",
    }
    map_path.write_text(json.dumps(payload, separators=(",", ":")) + "\n")


def main() -> None:
    for css_target in CSS_TARGETS:
        ensure_placeholder(CSS_DIR, css_target)

    for js_target in JS_TARGETS:
        ensure_placeholder(JS_DIR, js_target)


if __name__ == "__main__":
    main()
