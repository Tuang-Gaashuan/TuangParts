# -*- coding: utf-8 -*-
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from warehouse.batch_import import BatchParser


class StructuredExcelParsingTests(unittest.TestCase):
    def test_lcsc_detail_headers_are_parsed_without_ai_request(self):
        rows = [
            ("订单编号", "品牌", "商品类型", "商品名称", "商品型号", "封装格式", "订购数量"),
            ("SO001", "APV(爱普微)", "功率电感", "10uH ±20%", "ANR3015T100M", "SMD,3x3mm", 20),
        ]

        result = BatchParser._parse_structured_rows(rows[0], rows[1:])

        self.assertIsNotNone(result)
        self.assertEqual(result[0]["name"], "10uH")
        self.assertEqual(result[0]["brand"], "APV(爱普微)")
        self.assertEqual(result[0]["package"], "SMD,3x3mm")
        self.assertEqual(result[0]["qty"], "20")
        self.assertEqual(result[0]["cat_key"], "inductor")
        self.assertEqual(result[0]["subcat"], "功率电感")
        self.assertIn("ANR3015T100M", result[0]["spec"])

    def test_unknown_headers_return_none_to_fall_back_to_ai(self):
        self.assertIsNone(BatchParser._parse_structured_rows(["甲", "乙"], [("1", "2")]))


if __name__ == "__main__":
    unittest.main()
