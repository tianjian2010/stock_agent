import unittest

from skills.mx_data import MXDataSkill, MXSearchSkill, MXSelectStockSkill


class MXFormattingTests(unittest.TestCase):
    def test_market_data_formatting(self) -> None:
        skill = MXDataSkill()
        output = skill.format_result(
            {
                "data": {
                    "data": {
                        "diff": [
                            {"code": "300750", "name": "宁德时代", "price": "201.50", "change": "1.25"}
                        ]
                    }
                }
            }
        )
        self.assertIn("300750", output)
        self.assertIn("宁德时代", output)

    def test_news_formatting(self) -> None:
        skill = MXSearchSkill()
        output = skill.format_result(
            {
                "data": {
                    "newsList": [
                        {
                            "title": "量子科技出现新进展",
                            "source": "证券时报",
                            "publishTime": "2026-05-03 09:30:00",
                            "trunk": "这里是一段摘要",
                        }
                    ]
                }
            }
        )
        self.assertIn("量子科技出现新进展", output)
        self.assertIn("证券时报", output)

    def test_select_stock_formatting(self) -> None:
        skill = MXSelectStockSkill()
        output = skill.format_result(
            {
                "data": {
                    "data": {
                        "result": {
                            "total": 1,
                            "dataList": [
                                {
                                    "SECURITY_CODE": "688256",
                                    "SECURITY_SHORT_NAME": "寒武纪",
                                    "MARKET_SHORT_NAME": "SH",
                                    "NEWEST_PRICE": "123.45",
                                    "CHG": "5.20",
                                }
                            ],
                        }
                    }
                }
            }
        )
        self.assertIn("688256", output)
        self.assertIn("寒武纪", output)


if __name__ == "__main__":
    unittest.main()
