# -*- coding: utf-8 -*-
import sys
import unittest
from io import BytesIO
from pathlib import Path

from openpyxl import Workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from warehouse.batch_import import BatchParser


class EnhancedExcelParsingTests(unittest.TestCase):
    def test_eda_headers_are_structured_without_ai_request(self):
        rows = [
            ("Reference", "Value", "Footprint", "Qty", "Description", "Manufacturer"),
            ("C1", "100nF", "C_0603_1608Metric", "2", "100nF 50V X7R", "Murata"),
        ]

        result = BatchParser._parse_structured_rows(rows[0], rows[1:])

        self.assertIsNotNone(result)
        self.assertEqual(result[0]["name"], "100nF")
        self.assertEqual(result[0]["brand"], "Murata")
        self.assertEqual(result[0]["package"], "C_0603_1608Metric")
        self.assertEqual(result[0]["qty"], "2")
        self.assertIn("50V X7R", result[0]["spec"])

    def test_quantity_text_is_normalized_to_integer(self):
        rows = [
            ("型号", "数量", "封装"),
            ("STM32F103C8T6", "2 个", "LQFP48"),
            ("TPS5430", 3.0, "SOIC8"),
        ]

        result = BatchParser._parse_structured_rows(rows[0], rows[1:])

        self.assertEqual([item["qty"] for item in result], ["2", "3"])

    def test_excel_reader_chooses_bom_sheet_instead_of_active_summary_sheet(self):
        workbook = Workbook()
        summary = workbook.active
        summary.title = "说明"
        summary.append(["这是说明页"])
        bom = workbook.create_sheet("BOM")
        bom.append(["型号", "数量", "封装"])
        bom.append(["LM358", 4, "SOIC8"])
        stream = BytesIO()
        workbook.save(stream)

        rows = BatchParser._read_excel_rows(stream.getvalue(), "bom.xlsx")

        self.assertEqual(rows[0], ("型号", "数量", "封装"))
        self.assertEqual(rows[1], ("LM358", 4, "SOIC8"))

    def test_header_detection_skips_title_and_blank_rows(self):
        rows = [
            ("项目名称：主控板", None, None, None),
            (None, None, None, None),
            ("BOM 明细", None, None, None),
            ("位号", "值", "封装", "数量"),
            ("U1", "STM32F103C8T6", "LQFP48", 1),
        ]

        header_index = BatchParser._detect_header_row(rows)

        self.assertEqual(header_index, 3)


if __name__ == "__main__":
    unittest.main()
