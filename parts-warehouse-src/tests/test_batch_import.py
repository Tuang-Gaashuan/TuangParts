# -*- coding: utf-8 -*-
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from warehouse.batch_import import BatchParser


class HeaderRowDetectionTests(unittest.TestCase):
    def test_detect_header_row_skips_leading_summary_rows(self):
        rows = [
            ("", "￥184.47", "", ""),
            ("立创商城物料明细对账单", "", "", ""),
            ("订单编号", "品牌", "商品型号", "订购数量"),
            ("SO001", "TI", "TPS5430", 10),
        ]

        self.assertEqual(BatchParser._detect_header_row(rows), 2)

    def test_detect_header_row_keeps_first_row_when_it_is_a_real_header(self):
        rows = [
            ("型号", "品牌", "封装", "数量"),
            ("STM32F103C8T6", "ST", "LQFP48", 5),
        ]

        self.assertEqual(BatchParser._detect_header_row(rows), 0)


if __name__ == "__main__":
    unittest.main()
