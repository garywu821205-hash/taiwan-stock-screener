"""Free market-universe sources used by the scheduled static build."""

from __future__ import annotations

import json
import urllib.request
from typing import Any

from server import Stock


TWSE_COMPANIES = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
TPEX_COMPANIES = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"

# TWSE/TPEx use the same listed-company industry codes for these groups.
INDUSTRIES = {
    "01": "水泥工业", "02": "食品工业", "03": "塑胶工业", "04": "纺织纤维",
    "05": "电机机械", "06": "电器电缆", "08": "玻璃陶瓷", "09": "造纸工业",
    "10": "钢铁工业", "11": "橡胶工业", "12": "汽车工业", "14": "建材营造",
    "15": "航运业", "16": "观光餐旅", "17": "金融保险", "18": "贸易百货",
    "19": "综合", "20": "其他", "21": "化学工业", "22": "生技医疗",
    "23": "油电燃气", "24": "半导体", "25": "电脑及周边设备", "26": "光电",
    "27": "通信网络", "28": "电子零组件", "29": "电子通路", "30": "资讯服务",
    "31": "其他电子", "32": "文化创意", "33": "农业科技", "34": "电子商务",
    "35": "绿色能源及环保", "36": "数位云端", "37": "运动休闲", "38": "居家生活",
}


def fetch_json(url: str) -> Any:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 TaiwanStockScreener/1.0", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def first(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def normalize_company(item: dict[str, Any], market: str) -> Stock | None:
    code = first(item, "公司代號", "SecuritiesCompanyCode", "公司代码")
    name = first(item, "公司簡稱", "CompanyAbbreviation", "公司名稱", "CompanyName", "公司简称")
    industry_code = first(item, "產業別", "SecuritiesIndustryCode", "IndustryCode", "产业别").zfill(2)
    if not code.isdigit() or len(code) not in {4, 5, 6} or not name:
        return None
    return Stock(code, name, market, INDUSTRIES.get(industry_code, "其他"))


def fetch_universe() -> list[Stock]:
    stocks: dict[tuple[str, str], Stock] = {}
    for url, market in ((TWSE_COMPANIES, "上市"), (TPEX_COMPANIES, "上柜")):
        payload = fetch_json(url)
        if isinstance(payload, dict):
            payload = payload.get("data") or payload.get("result") or []
        for item in payload:
            if not isinstance(item, dict):
                continue
            stock = normalize_company(item, market)
            if stock:
                stocks[(stock.market, stock.code)] = stock
    return sorted(stocks.values(), key=lambda stock: (stock.market, stock.code))
