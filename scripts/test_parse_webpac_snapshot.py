"""Offline parser tests with SYNTHETIC HTML based on public column names."""
import unittest
from parse_webpac_snapshot import parse_webpac_html

HEADER = """<tr><th>條碼號</th><th>典藏館</th><th>目前所在館</th>
<th>索書號</th><th>館藏狀態</th><th>資料類型</th>
<th>附件</th><th>預約人數</th><th>備註</th><th>預約</th></tr>"""


def row(barcode, library, current, status, typ="兒童書", queue="0", note=""):
    cells = [barcode, library, current, "J 859.6 8041", status, typ, "", queue, note, "預約"]
    return "<tr>" + "".join("<td><span>" + c + "</span></td>" for c in cells) + "</tr>"


def page(*rows, isbn="9789861615929"):
    return "<html><body><h2>測試書籍</h2><p>ISBN：" + isbn + "</p>" + \
           "<table><tr><td>Other table</td></tr></table><table>" + HEADER + \
           "".join(rows) + "</table><script>const unused = '借出';</script></body></html>"


class ParserTest(unittest.TestCase):
    def test_exhibition_not_borrowable(self):
        d = parse_webpac_html(page(row("TPL0405647","新總館B1兒童書區",
            "新總館B1兒童書區","展覽用書(不外借)",note="布可星球")),
            "9789861615929")
        c = d["copies"][0]
        self.assertIs(c["borrowable"], False)
        self.assertEqual(c["status"], "展覽用書(不外借)")
        self.assertEqual(d["source"], "manual-html-snapshot")
        self.assertFalse(d["complete"])

    def test_borrowed_and_exhibition_mixed(self):
        d = parse_webpac_html(page(
            row("TPL0405647","新總館B1兒童書區","新總館B1兒童書區","展覽用書(不外借)"),
            row("SN1234567","善化兒童書區","善化兒童書區","借出 2026/11/29",queue="3")),
            "9789861615929")
        self.assertEqual(len(d["copies"]), 2)
        self.assertIs(d["copies"][1]["borrowable"], True)
        self.assertEqual(d["copies"][1]["reservationCount"], 3)

    def test_in_shelf_remains_unverified(self):
        d = parse_webpac_html(page(row("AP0001234","安平兒童區","安平兒童區","在架")),
            "9789861615929")
        self.assertIsNone(d["copies"][0]["borrowable"])

    def test_reference_area_restricted(self):
        d = parse_webpac_html(page(row("AP0001234","新總館4F參考資料區（限館內閱覽）",
            "新總館4F參考資料區（限館內閱覽）","在架",typ="中文參考書")),
            "9789861615929")
        self.assertIs(d["copies"][0]["borrowable"], False)

    def test_in_transit_not_in_shelf(self):
        d = parse_webpac_html(page(row("AP0001234","安平兒童區","公園總館浮動館藏區",
            "移送取書館中(跨館還書)")), "9789861615929")
        self.assertEqual(d["copies"][0]["status"], "移送取書館中(跨館還書)")
        self.assertIsNone(d["copies"][0]["borrowable"])

    def test_mismatched_isbn_rejected(self):
        with self.assertRaisesRegex(ValueError, "mismatch"):
            parse_webpac_html(page(row("AP0001234","安平","安平","在架")),
                "9789863203629")

    def test_missing_schema_rejected(self):
        with self.assertRaisesRegex(ValueError, "No recognizable"):
            parse_webpac_html("<html><table><tr><td>別的頁面</td></tr></table></html>",
                "9789861615929")

    def test_unknown_queue_null(self):
        d = parse_webpac_html(page(row("AP0001234","安平","安平","借出 2026/11/29",
            queue="—")), "9789861615929")
        self.assertIsNone(d["copies"][0]["reservationCount"])

    def test_empty_data_rejected(self):
        with self.assertRaisesRegex(ValueError, "no usable rows"):
            parse_webpac_html("<table>" + HEADER + "</table>", "9789861615929")

    def test_snapshot_time_preserved(self):
        d = parse_webpac_html(page(row("AP0001234","安平","安平","在架")),
            "9789861615929", "2026-11-05T08:00:00Z")
        self.assertEqual(d["checkedAt"], "2026-11-05T08:00:00Z")

if __name__ == "__main__":
    unittest.main()
