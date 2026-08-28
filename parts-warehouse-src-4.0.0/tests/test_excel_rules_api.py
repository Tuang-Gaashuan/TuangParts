# -*- coding: utf-8 -*-
import sys
import unittest
from io import BytesIO
from pathlib import Path

from openpyxl import Workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import app


class ExcelRulesApiTests(unittest.TestCase):
    def test_rules_excel_upload_uses_structured_excel_parser(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["Reference", "Value", "Footprint", "Qty", "Description"])
        sheet.append(["C1", "100nF", "C0603", "2 个", "100nF 50V X7R"])
        stream = BytesIO()
        workbook.save(stream)

        with app.test_client() as client:
            response = client.post(
                "/api/import_parse_rules",
                data={
                    "file": (
                        BytesIO(stream.getvalue()),
                        "bom.xlsx",
                    )
                },
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["items"][0]["qty"], "2")
        self.assertEqual(payload["items"][0]["name"], "100nF")
        self.assertIn("50V X7R", payload["items"][0]["spec"])


if __name__ == "__main__":
    unittest.main()
