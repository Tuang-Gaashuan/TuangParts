# -*- coding: utf-8 -*-
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from warehouse.batch_import import (
    BatchParser, _fast_ocr_passive_item, _fast_ocr_semiconductor_item,
    _ocr_candidate_categories,
)


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


class OcrGroupParsingTests(unittest.TestCase):
    def _parser_with_reply(self, reply):
        parser = BatchParser("key", "http://127.0.0.1", "model")
        parser._chat = lambda _messages: reply
        return parser

    def test_ocr_groups_are_sent_and_kept_per_image(self):
        parser = self._parser_with_reply(
            '[{"source_image":"图1","name":"10uF","brand":"Murata",'
            '"package":"0805","qty":"100","spec":"25V X7R",'
            '"cat":"电容","subcat":"贴片电容"},'
            '{"source_image":"图2","name":"STM32F103C8T6","brand":"ST",'
            '"package":"LQFP48","qty":"5","spec":"",'
            '"cat":"集成电路","subcat":"微控制器"}]'
        )
        items = parser.parse_ocr_groups(
            "【图1】\n订单 20260824\n10uF 25V X7R 0805 QTY 100\n【图2】\nSTM32F103C8T6 LQFP48 5pcs"
        )

        self.assertEqual(len(items), 2)
        self.assertEqual([item["source_image"] for item in items], ["图1", "图2"])
        self.assertEqual(items[0]["name"], "10uF")
        self.assertTrue(items[0]["raw"].startswith("【图1】"))

    def test_ocr_spec_removes_labeled_trace_numbers_but_keeps_part_number(self):
        parser = self._parser_with_reply(
            '[{"source_image":"图1","name":"10uF","brand":"Murata",'
            '"package":"0805","qty":"100",'
            '"spec":"GRM21BR61E106KA73 25V X5R; 订单号: SO-20260824; 批次: L2408; 条码: A1B2C3",'
            '"cat":"电容","subcat":"贴片电容"}]'
        )
        item = parser.parse_ocr_groups("【图1】\n10uF 25V X5R 0805")[0]

        self.assertIn("GRM21BR61E106KA73", item["spec"])
        self.assertIn("25V X5R", item["spec"])
        self.assertNotIn("SO-20260824", item["spec"])
        self.assertNotIn("L2408", item["spec"])
        self.assertNotIn("A1B2C3", item["spec"])


    def test_standard_passive_label_uses_rules_without_ai(self):
        parser = BatchParser("key", "http://127.0.0.1", "model")
        parser._chat = lambda _messages: self.fail("标准被动件标签不应调用 AI")
        item = parser.parse_ocr_groups(
            "【图1】\nQTY:100个\n贴片电阻\n10kΩ ±1% 62.5mW\n0402\nFRC0402F1002TS\nFOJAN(富捷)"
        )[0]

        self.assertEqual(item["name"], "10kΩ")
        self.assertEqual(item["qty"], "100")
        self.assertEqual(item["package"], "0402")
        self.assertIn("FRC0402F1002TS", item["spec"])
        self.assertEqual(item["source_image"], "图1")

    def test_passive_rule_keeps_package_prefixed_part_number(self):
        item = _fast_ocr_passive_item(
            "图1", "QTY:100个 贴片电阻 75kΩ±1% 62.5mW厚膜电阻 0402 0402WGF7502TCE UNI-ROYAL(厚声)"
        )

        self.assertIsNotNone(item)
        self.assertEqual(item["qty"], "100")
        self.assertIn("0402WGF7502TCE", item["spec"])

    def test_passive_rule_accepts_ocr_dropped_q_in_qty_label(self):
        item = _fast_ocr_passive_item(
            "图1", "TY:100个 贴片电容(MLCC) 1uF ±10% 25V 0402 CL05A105KA5NQNC SAMSUNG(三星)"
        )

        self.assertIsNotNone(item)
        self.assertEqual(item["qty"], "100")
        self.assertEqual(item["name"], "1uF")


    def test_passive_rule_accepts_complete_no_model_label(self):
        item = _fast_ocr_passive_item(
            "图1", "型号:0402贴片电容 10uF±10% 10V 封装:0402 数量:100 品牌:中性电容"
        )

        self.assertIsNotNone(item)
        self.assertEqual(item["name"], "10uF")
        self.assertEqual(item["spec"], "±10% 10V")

    def test_passive_rule_uses_eia_code_to_resolve_ocr_capacitance_conflict(self):
        item = _fast_ocr_passive_item(
            "图1", "QTY:100个 贴片电容(MLCC) 10nF ±10% 50V 0402 5nF FCC0402B103K500AT"
        )

        self.assertIsNotNone(item)
        self.assertEqual(item["name"], "10nF")
        self.assertIn("FCC0402B103K500AT", item["spec"])


    def test_passive_rule_ignores_package_model_false_capacitance(self):
        item = _fast_ocr_passive_item(
            "图1", "QTY:100个 贴片电容(MLCC) 2.2nF ±10% 50V 0603 FCC0603B222K500CT"
        )

        self.assertIsNotNone(item)
        self.assertEqual(item["name"], "2.2nF")
        self.assertIn("FCC0603B222K500CT", item["spec"])


    def test_semiconductor_rule_parses_verified_tvs_label(self):
        item = _fast_ocr_semiconductor_item(
            "图1", "QTY:20个 双向TVS24V SOD-123FL SMF24CA TECHPUBLIC(台舟)"
        )

        self.assertIsNotNone(item)
        self.assertEqual(item["name"], "SMF24CA")
        self.assertEqual(item["cat_key"], "diode")
        self.assertEqual(item["subcat"], "静电和浪涌保护(TVS / ESD)")
        self.assertEqual(item["qty"], "20")

    def test_semiconductor_rule_parses_pesd_and_smaj_labels(self):
        pesd = _fast_ocr_semiconductor_item(
            "图1", "型号:PESD5V0F1BL 封装:SOD-882 数量:50 品牌:UMW"
        )
        smaj = _fast_ocr_semiconductor_item(
            "图2", "QTY:20个 单向TVS5V DO-214AC(SMA) SMAJ5.0A TECHPUBLIC"
        )

        self.assertEqual(pesd["name"], "PESD5V0F1BL")
        self.assertEqual(pesd["package"], "SOD-882")
        self.assertEqual(smaj["name"], "SMAJ5.0A")
        self.assertEqual(smaj["package"], "DO-214AC(SMA)")


    def test_semiconductor_rule_requires_explicit_ldo_description(self):
        self.assertIsNone(_fast_ocr_semiconductor_item(
            "图1", "数量:30 SOT-23-5 LN1134A332MR-G"
        ))
        item = _fast_ocr_semiconductor_item(
            "图1", "数量:30 SOT-23-5 LN1134A332MR-G 低压差线性稳压器"
        )
        self.assertEqual(item["cat_key"], "power_mgmt")

    def test_multi_item_order_label_stays_outside_fast_rules(self):
        text = "数量 10 LN1134A332MR-G SOT23-5 低压差线性稳压器 15 RY8411 SOT23-6 DC-DC SMF24CA SOD-123FL"
        self.assertIsNone(_fast_ocr_passive_item("图1", text))
        self.assertIsNone(_fast_ocr_semiconductor_item("图1", text))


    def test_complex_label_falls_back_to_ai_and_keeps_order(self):
        parser = self._parser_with_reply(
            '[{"source_image":"图2","name":"SMF6.0CA","brand":"",'
            '"package":"SOD-123FL","qty":"10","spec":"双向TVS 6V",'
            '"cat":"二极管","subcat":"静电和浪涌保护(TVS/ESD)"}]'
        )
        items = parser.parse_ocr_groups(
            "【图1】\nQTY:100个\n贴片电阻\n10kΩ ±1%\n0402\nFRC0402F1002TS\n"
            "【图2】\nSMF6.0CA SOD-123FL 双向TVS 6V"
        )

        self.assertEqual([item["source_image"] for item in items], ["图1", "图2"])
        self.assertEqual(items[0]["name"], "10kΩ")
        self.assertEqual(items[1]["name"], "SMF6.0CA")


    def test_ocr_groups_rejects_a_missing_image(self):
        parser = self._parser_with_reply(
            '[{"source_image":"图1","name":"10uF","brand":"",'
            '"package":"0805","qty":"100","spec":"25V",'
            '"cat":"电容","subcat":"贴片电容"}]'
        )

        with self.assertRaisesRegex(ValueError, "图2"):
            parser.parse_ocr_groups("【图1】\n10uF 25V\n【图2】\n1kΩ 1%")


class OcrCategoryCandidateTests(unittest.TestCase):
    def test_candidates_prioritize_detected_types_and_stay_limited(self):
        candidates = _ocr_candidate_categories(
            "10uF 25V X7R capacitor STM32F103C8T6 LQFP48 USB-C connector", limit=10
        )

        self.assertIn("capacitor", candidates)
        self.assertIn("mcu", candidates)
        self.assertIn("connector", candidates)
        self.assertLessEqual(len(candidates), 10)
        self.assertNotIn("instrument", candidates)
    def test_explicit_mlcc_label_uses_capacitor_only_candidate_tree(self):
        candidates = _ocr_candidate_categories(
            "贴片电容(MLCC) 10nF 0402 FCC0402B103K500AT", limit=10
        )

        self.assertEqual(candidates, ["capacitor"])


if __name__ == "__main__":
    unittest.main()
