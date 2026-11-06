"""Offline parser tests with SYNTHETIC HTML based on public column names."""
import unittest
import json
from pathlib import Path
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
    def test_saved_actual_webpac_html_fragment(self):
        # Extracted from a user-supplied, PUBLIC library detail-page HTML,
        # with scripts and click handlers removed but real table DOM retained.
        p = Path(__file__).parent / "fixtures" / "webpac_saved_real_detail.html"
        html = p.read_text(encoding="utf-8")
        record = parse_webpac_html(html, "9789861615929")
        self.assertEqual(record["source"], "manual-html-snapshot")
        self.assertEqual(record["reportedHoldingsCount"], 71)
        self.assertEqual(record["currentPageNumber"], 1)
        self.assertEqual(record["totalPagesReported"], 8)
        self.assertEqual(record["parsedPageCopyCount"], 10)
        self.assertTrue(record["paginationLikely"])
        self.assertFalse(record["complete"])
        self.assertEqual(len(record["copies"]), 10)
        by_id = {c["barcode"]: c for c in record["copies"]}
        self.assertEqual(by_id["KZ0162536"]["status"], "借出 2026/11/19")
        self.assertEqual(by_id["KZ0162536"]["reservationCount"], 1)
        self.assertEqual(by_id["TPL0487499"]["status"], "在架")
        self.assertIsNone(by_id["TPL0487499"]["borrowable"])
        self.assertEqual(by_id["TPL0487499"]["dataType"], "視障資料")
        self.assertEqual(by_id["TPL0405647"]["status"], "展覽用書(不外借)")
        self.assertIs(by_id["TPL0405647"]["borrowable"], False)
        self.assertIsNone(by_id["NC0095700"]["borrowable"])
        self.assertIn("閉館整修", by_id["NC0095700"]["currentLibrary"])


    def test_public_catalog_observations_reconstructed_as_table(self):
        fixture_path = Path(__file__).parent / "fixtures" / "catalog_public_observation.json"
        sample = json.loads(fixture_path.read_text(encoding="utf-8"))
        observed_rows = [
            row(item["barcode"], item["homeLibrary"], item["currentLibrary"],
                item["status"], typ=item["dataType"], queue=str(item["reservationCount"]))
            for item in sample["rows"]
        ]
        # DOM is reconstructed from publicly rendered rows; NOT a captured HTML original.
        html = page(*observed_rows, isbn=sample["isbn"])
        html = html.replace("<table>" + HEADER,
            "<h3>館藏(" + str(sample["reportedHoldingsCount"]) + ")</h3><table>" + HEADER)
        parsed = parse_webpac_html(html, sample["isbn"])
        self.assertEqual(parsed["reportedHoldingsCount"], 27)
        self.assertEqual(parsed["parsedPageCopyCount"], 5)
        self.assertTrue(parsed["paginationLikely"])
        self.assertFalse(parsed["complete"])
        self.assertIs(parsed["copies"][1]["borrowable"], True) # 展覽用書(可外借)
        self.assertIs(parsed["copies"][2]["borrowable"], False) # 展覽用書(不外借)
        self.assertIsNone(parsed["copies"][4]["borrowable"])    # 閉館但在架 → 不推定可借


    def test_exhibition_not_borrowable(self):
        d = parse_webpac_html(page(row("TPL0405647","新總館B1兒童書區",
            "新總館B1兒童書區","展覽用書(不外借)",note="布可星球")),
            "9789861615929")
        c = d["copies"][0]
        self.assertIs(c["borrowable"], False)
        self.assertEqual(c["status"], "展覽用書(不外借)")
        self.assertEqual(d["source"], "manual-html-snapshot")
        self.assertFalse(d["complete"])

    def test_exhibition_can_be_borrowable(self):
        d = parse_webpac_html(page(row("PH0098062","白河年度新書區",
            "白河年度新書區","展覽用書(可外借)",typ="中文書")), "9789861615929")
        self.assertIs(d["copies"][0]["borrowable"], True)
        self.assertEqual(d["copies"][0]["status"], "展覽用書(可外借)")

    def test_exhibition_borrowable_in_closed_branch(self):
        d = parse_webpac_html(page(row("TC0084111","左鎮年度新書區(閉館整修)",
            "左鎮年度新書區(閉館整修)","展覽用書(可外借)")), "9789861615929")
        self.assertIs(d["copies"][0]["borrowable"], True)
        self.assertIn("閉館整修", d["copies"][0]["currentLibrary"])

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
