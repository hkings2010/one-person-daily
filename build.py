#!/usr/bin/env python3
"""Inject archive.json into template.html and emit a self-contained index.html."""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent
ARCHIVE = ROOT / "archive.json"
TEMPLATE = ROOT / "template.html"
OUTPUT = ROOT / "index.html"

MIN_ITEMS = 1
MAX_ITEMS = 500


def fail(msg: str) -> None:
    print(f"build failed: {msg}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    try:
        data = json.loads(ARCHIVE.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        fail(f"archive.json is not valid JSON: {exc}")

    items = data.get("items")
    if not isinstance(items, list) or not (MIN_ITEMS <= len(items) <= MAX_ITEMS):
        fail("items must be a list with a sane number of entries")

    ids = set()
    dates = set()
    for item in items:
        for key in ("id", "date", "title", "url", "source", "summary"):
            if not str(item.get(key, "")).strip():
                fail(f"item missing {key}: {item.get('id')!r}")
        if item["id"] in ids:
            fail(f"duplicate item id: {item['id']}")
        ids.add(item["id"])
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", item["date"]):
            fail(f"bad date on {item['id']}: {item['date']!r}")
        dates.add(item["date"])
        if not str(item["url"]).startswith(("http://", "https://")):
            fail(f"bad url on {item['id']}")

    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    # Keep the inline script safe inside <script>.
    payload = payload.replace("</", "<\\/")

    latest = max(dates) if dates else ""
    title_date = latest.replace("-", ".") if latest else "今日"

    template = TEMPLATE.read_text(encoding="utf-8")
    if "__DATA_JSON__" not in template or "__TITLE_DATE__" not in template:
        fail("template is missing placeholders")

    html = template.replace("__DATA_JSON__", payload).replace("__TITLE_DATE__", title_date)

    # Guard: no external resources may slip into the single-file page.
    for pattern in ("https://fonts.", "cdn.", "unpkg.com", "jsdelivr.net"):
        if pattern in html:
            fail(f"external resource reference found: {pattern}")

    OUTPUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUTPUT} ({OUTPUT.stat().st_size} bytes, {len(items)} items, {len(dates)} days)")


if __name__ == "__main__":
    main()