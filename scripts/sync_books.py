#!/usr/bin/env python3
"""Download the education bureau's published book-list ZIP once, convert ODS to JSON.

Only fetches the published file. No crawling, credentials, OPAC requests or availability guesses.
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

SOURCE = os.environ.get("BUKE_SOURCE_URL", "https://read.tn.edu.tw/upload/Guide/%E5%B8%83%E5%8F%AF%E6%98%9F%E7%90%83%E5%9C%96%E6%9B%B8%E5%88%97%E8%A1%A8%2820250815%E7%89%88%29.zip")
OUTPUT = Path(os.environ.get("BUKE_OUTPUT", "data/books.json"))
MIN_BOOKS = int(os.environ.get("BUKE_MIN_BOOKS", "100"))
HEADERS = {"User-Agent": "BukeFindBookListSync/1.0 (+https://github.com/kio5232000/buke-find)", "Accept": "application/zip,application/octet-stream,*/*"}
NS = {
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
    "xlink": "http://www.w3.org/1999/xlink",
}
T = "{%s}" % NS["table"]
X = "{%s}" % NS["xlink"]
ISBN_RE = re.compile(r"(?<![\dX])(?:97[89]\d{10}|\d{9}[\dX])(?!\d)", re.I)


def get_bytes(url):
    if urlparse(url).hostname != 'read.tn.edu.tw' or not url.startswith('https://'):
        raise ValueError('Only the education bureau official HTTPS download is accepted')
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=35) as resp:
        size = int(resp.headers.get("content-length") or 0)
        if size > 20_000_000:
            raise ValueError('Official ZIP unexpectedly large')
        blob = resp.read(20_000_001)
    if len(blob) > 20_000_000:
        raise ValueError('Download limit exceeded')
    return blob


def cell_data(cell):
    # ODS can hide a URL under text:a, or under an of:=HYPERLINK() formula.
    value = ' '.join(''.join(p.itertext()).strip() for p in cell.findall('.//text:p', NS)).strip()
    if not value:
        value = cell.get('{%s}string-value' % NS['office'], '')
    hrefs = [a.get(X+'href', '') for a in cell.findall('.//text:a', NS)]
    formula = cell.get(T+'formula', '')
    if 'HYPERLINK' in formula.upper():
        hrefs.extend(re.findall(r'https?://[^\";]+', formula, flags=re.I))
    return value, hrefs


def ods_sheets(blob):
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        data = z.read('content.xml')
    root = ET.fromstring(data)
    for sheet in root.findall('.//table:table', NS):
        name = sheet.get(T+'name', '')
        rows = []
        for row in sheet.findall('table:table-row', NS):
            columns = []
            for c in row:
                if c.tag not in (T+'table-cell', T+'covered-table-cell'):
                    continue
                content = cell_data(c) if c.tag == T+'table-cell' else ('', [])
                repeats = min(int(c.get(T+'number-columns-repeated', 1)), 70)
                columns.extend([content] * repeats)
                if len(columns) >= 70:
                    break
            if any(v for v, _ in columns):
                rows.append(columns)
            # Never expand repeated empty rows in giant spreadsheets.
            if len(rows) >= 20000:
                break
        yield name, rows


def clean(v):
    return re.sub(r'\s+', ' ', str(v or '')).strip()


def find_header(rows):
    best = (-1, None)
    for i, row in enumerate(rows[:35]):
        words = [clean(cell[0]).lower().replace(' ', '') for cell in row]
        has_title = any(any(k in x for k in ('書名','布可名稱','圖書名稱','圖書名','書籍名稱')) for x in words)
        has_isbn = any('isbn' in x or '國際書號' in x for x in words)
        score = (3 if has_title else 0) + (3 if has_isbn else 0) + sum(any(k in x for k in ('作者','適合','年級','領域','出版','布可星球連結')) for x in words)
        if score > best[0]:
            best = (score, i)
    return best[1] if best[0] >= 5 else None


def match_index(headers, *tokens):
    for j, h in enumerate(headers):
        h = clean(h).lower().replace(' ', '')
        if any(t.lower() in h for t in tokens):
            return j
    return None


def grade_for(*values):
    s = ' '.join(map(clean, values)).replace(' ', '')
    if any(x in s for x in ('國小低', '低年級', '1-2年級', '一二年級')):
        return 'low'
    if any(x in s for x in ('國小中', '中年級', '3-4年級', '三四年級')):
        return 'mid'
    if any(x in s for x in ('國小高', '高年級', '5-6年級', '五六年級')):
        return 'high'
    return 'all'


def parse_booklist(blob):
    if not zipfile.is_zipfile(io.BytesIO(blob)):
        raise ValueError('Expected ZIP download')
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        candidates = [n for n in z.namelist() if n.lower().endswith('.ods') and not n.startswith('__MACOSX/')]
        if not candidates:
            raise ValueError('No ODS found in official ZIP')
        filename = candidates[0]
        if z.getinfo(filename).file_size > 35_000_000:
            raise ValueError('ODS too large')
        ods = z.read(filename)
    found = {}
    sheet_names = []
    for sheet, rows in ods_sheets(ods):
        header = find_header(rows)
        if header is None:
            continue
        sheet_names.append(sheet)
        hdr = [v for v, _ in rows[header]]
        title_i = match_index(hdr, '書名','布可名稱','圖書名稱','圖書名','書籍名稱')
        isbn_i = match_index(hdr, 'isbn', '國際書號')
        author_i = match_index(hdr, '作者','著者')
        grade_i = match_index(hdr, '適合','年級','對象','階段')
        subject_i = match_index(hdr, '領域', '類別','分類')
        book_i = match_index(hdr, '布可星球連結','布可連結')
        library_i = match_index(hdr, '圖書館連結','市立圖書館連結','圖書館網址')
        if title_i is None:
            continue
        for row in rows[header+1:]:
            def at(i):
                return row[i] if i is not None and i < len(row) else ('', [])
            title = clean(at(title_i)[0])
            if not (2 <= len(title) <= 180) or title.lower() in ('書名','圖書名稱','布可名稱'):
                continue
            src_isbn = clean(at(isbn_i)[0])
            urls = [u for cell in row for u in cell[1]]
            booklinks = [u for u in urls if u.startswith('https://read.tn.edu.tw/Book/BookEntrance')]
            if book_i is not None:
                booklinks.extend([u for u in at(book_i)[1] if u.startswith('https://read.tn.edu.tw/Book/BookEntrance')])
            isbn_candidate = ISBN_RE.search(src_isbn)
            if not isbn_candidate:
                isbn_candidate = ISBN_RE.search(' '.join(booklinks))
            if not isbn_candidate:
                continue
            isbn = isbn_candidate.group(0).upper()
            author = clean(at(author_i)[0])[:150]
            category = clean(at(subject_i)[0])[:90] or '推薦書'
            grade = grade_for(at(grade_i)[0], sheet)
            library_links = [u for u in urls if ('lib.tnml.tn.edu.tw/webpac' in u or 'www.tnpl.tn.edu.tw' in u) and u.startswith('https://')]
            if library_i is not None:
                library_links += [u for u in at(library_i)[1] if u.startswith('https://')]
            direct = next((u for u in library_links if urlparse(u).hostname in ('lib.tnml.tn.edu.tw','www.tnpl.tn.edu.tw')), None)
            found[isbn] = {
                'title': title, 'author': author, 'isbn': isbn, 'grade': grade,
                'category': category,
                'url': booklinks[0] if booklinks else 'https://read.tn.edu.tw/Book/BookEntrance?BISBN='+isbn,
                'libraryUrl': direct or f'https://lib.tnml.tn.edu.tw/webpac/search.cfm?m=ss&k0={isbn}&t0=k&c0=and'
            }
    return list(found.values()), filename, sheet_names


def main():
    books, filename, sheets = parse_booklist(get_bytes(SOURCE))
    if len(books) < MIN_BOOKS:
        raise ValueError(f'Only {len(books)} parsed books (need >= {MIN_BOOKS}); refusing to replace previously published data')
    payload = {
        'source': '臺南市政府教育局｜布可星球官方公開書單',
        'source_url': SOURCE,
        'source_file': filename,
        'updated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'count': len(books),
        'notes': '本資料僅包含公開書目資訊，不代表市圖館藏即時可借狀態。',
        'books': sorted(books, key=lambda b: (b['grade'], b['title']))
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUTPUT.with_suffix('.tmp')
    tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    tmp.replace(OUTPUT)
    print(f'Synced {len(books)} official books across {len(sheets)} sheets from {filename}')

if __name__ == '__main__':
    main()