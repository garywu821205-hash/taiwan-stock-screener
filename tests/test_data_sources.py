import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data_sources import normalize_company


class DataSourceTests(unittest.TestCase):
    def test_twse_company_fields(self):
        stock = normalize_company({"公司代號": "2330", "公司簡稱": "台積電", "產業別": "24"}, "上市")
        self.assertEqual((stock.name, stock.category), ("台積電", "半导体"))

    def test_tpex_company_fields(self):
        stock = normalize_company({
            "SecuritiesCompanyCode": "6194",
            "CompanyAbbreviation": "育富",
            "CompanyName": "育富電子股份有限公司",
            "SecuritiesIndustryCode": "28",
        }, "上柜")
        self.assertEqual((stock.name, stock.category), ("育富", "电子零组件"))


if __name__ == "__main__":
    unittest.main()
