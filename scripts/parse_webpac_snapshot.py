#!/usr/bin/env python3
"""Offline parser for a SAVED public WebPAC detail page. Never sends HTTP requests.

Usage: python scripts/parse_webpac_snapshot.py saved_detail.html --isbn 9789861615929
Output: JSON to stdout, designed for scripts/holdings_rules.mjs.
All results are manual observations, NOT live/authorized API results.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

WHITESPACE = re.compile(r"\s+")
ISBN_ON_PAGE = re.compile(r"ISBN\s*[：:]\s*([0-9Xx\-]{10,20})(?![0-9Xx])", re.I)
NON_CIRCULATING = re.compile(
    r"不外借|限館內閱覽|僅限館內|館內閱覽|參考資料區|參考書區|參考工具書|中文參考書"
)
BORROWED = re.compile(r"^借出(?:\s|$|[（(])")
EXHIBITION_BORROWABLE = re.compile(r"^展覽用書\s*[（(]\s*可外借\s*[）)]")
HEADER_LABELS = {
    "barcode": ("條碼號", "登錄號"),
    "homeLibrary": ("典藏館", "館藏地"),
    "currentLibrary": ("目前所在館",),
    "shelfMark": ("索書號",),
    "status": ("館藏狀態", "借閱狀態"),
    "dataType": ("資料類型",),
    "reservationCount": ("預約人數",),
    "notes": ("備註",),
}


def normalize(cell: str) -> str:
    return WHITESPACE.sub("", cell).strip()


class HTMLTables(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self.table_depth = 0
        self.table = None
        self.row = None
        self.cell = None
        self.skip_text_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip_text_depth += 1
        if tag == "table":
            self.table_depth += 1
            if self.table_depth == 1:
                self.table = []
        elif self.table_depth == 1 and tag == "tr":
            self.row = []
        elif self.table_depth == 1 and tag in ("td", "th") and self.row is not None:
            self.cell = []
        elif tag == "br" and self.cell is not None:
            self.cell.append(" ")

    def handle_data(self, data):
        if self.skip_text_depth == 0 and self.table_depth == 1 and self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip_text_depth = max(0, self.skip_text_depth - 1)
        elif self.table_depth == 1 and tag in ("td", "th") and self.cell is not None:
            self.row.append(WHITESPACE.sub(" ", "".join(self.cell)).strip())
            self.cell = None
        elif self.table_depth == 1 and tag == "tr" and self.row is not None:
            if self.row:
                self.table.append(self.row)
            self.row = None
        elif tag == "table" and self.table_depth > 0:
            if self.table_depth == 1 and self.table is not None:
                self.tables.append(self.table)
                self.table = None
            self.table_depth -= 1


def get_header_indices(row):
    cells = [normalize(c) for c in row]
    idx = {}
    for key, labels in HEADER_LABELS.items():
        for name in labels:
            try:
                idx[key] = cells.index(normalize(name))
                break
            except ValueError:
                pass
    if not {"barcode", "homeLibrary", "currentLibrary", "status", "reservationCount"}.issubset(idx):
        return None
    return idx


def parse_webpac_html(html: str, isbn: str, captured_at: str = "") -> dict:
    # The page ISBN is checked where possible, so unrelated books aren't merged.
    page_match = ISBN_ON_PAGE.search(re.sub(r"<[^>]+>", " ", html))
    page_isbn = re.sub(r"[^0-9Xx]", "", page_match.group(1)).upper() if page_match else None
    clean_isbn = re.sub(r"[^0-9Xx]", "", isbn).upper()
    if not re.fullmatch(r"(?:\d{13}|\d{9}[\dX])", clean_isbn):
        raise ValueError("Invalid ISBN")
    if page_isbn and page_isbn != clean_isbn:
        raise ValueError(f"Page ISBN mismatch: expected {clean_isbn}, got {page_isbn}")
    tables = HTMLTables()
    tables.feed(html)
    copies = []
    found_table = False
    for table in tables.tables:
        indexes = None
        for row in table:
            header = get_header_indices(row)
            if header is not None:
                indexes, found_table = header, True
                continue
            if indexes is None or len(row) <= max(indexes.values()):
                continue
            obj = {key: row[pos].strip() for key, pos in indexes.items()}
            barcode = obj.get("barcode", "")
            status = obj.get("status", "")
            if not barcode or normalize(barcode) in ("條碼號", "登錄號") or not status:
                continue
            if not re.fullmatch(r"[A-Za-z0-9\-]{4,32}", barcode):
                continue
            count_str = normalize(obj.get("reservationCount", ""))
            count = int(count_str) if count_str.isdigit() else None
            restriction = NON_CIRCULATING.search(" ".join([
                status, obj.get("homeLibrary", ""), obj.get("currentLibrary", ""),
                obj.get("dataType", ""), obj.get("notes", "")
            ]))
            # Borrowed is evidence of circulation; on-shelf without explicit
            # eligibility remains UNKNOWN rather than being declared borrowable.
            eligibility = False if restriction else True if (BORROWED.search(status) or EXHIBITION_BORROWABLE.search(status)) else None
            copies.append({
                "barcode": barcode,
                "homeLibrary": obj.get("homeLibrary", ""),
                "currentLibrary": obj.get("currentLibrary", ""),
                "shelfLocation": obj.get("homeLibrary", ""),
                "shelfMark": obj.get("shelfMark", ""),
                "status": status,
                "circulationPolicy": "不外借" if restriction else "",
                "dataType": obj.get("dataType", ""),
                "borrowable": eligibility,
                "reservationCount": count,
            })
    if not found_table:
        raise ValueError("No recognizable holdings table. Page may be search results, or layout changed.")
    if not copies:
        raise ValueError("Holdings table found but no usable rows; inspect page before importing.")
    # Some detailed WebPAC views have multiple pages of copies. Never claim
    # total citywide availability from a single HTML snapshot.
    return {
        "isbn": clean_isbn,
        "checkedAt": captured_at,
        "source": "manual-html-snapshot",
        "complete": False,
        "notes": "離線頁面觀察；可能只有部分館藏頁數，不能代表全市完整或即時館藏。",
        "pageIsbnVerified": bool(page_isbn),
        "copies": copies,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("html_file", type=Path)
    ap.add_argument("--isbn", required=True)
    ap.add_argument("--captured-at", default="", help="UTC ISO8601 time when snapshot was saved; otherwise blank")
    ap.add_argument("--output", type=Path, help="Write result JSON to specified file instead of stdout")
    args = ap.parse_args()
    try:
        if args.captured_at:
            from datetime import datetime
            stamp = args.captured_at.replace("Z", "+00:00")
            if datetime.fromisoformat(stamp).tzinfo is None:
                raise ValueError("--captured-at must include timezone (e.g. Z)")
        html = args.html_file.read_text(encoding="utf-8-sig")
        result = parse_webpac_html(html, args.isbn, args.captured_at)
        raw = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.write_text(raw, encoding="utf-8")
            print(f"Saved {len(result['copies'])} holdings to {args.output}", file=sys.stderr)
        else:
            print(raw, end="")
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
