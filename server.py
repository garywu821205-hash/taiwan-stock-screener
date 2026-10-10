#!/usr/bin/env python3
"""Local-only Taiwan stock multi-timeframe screener demo.

Uses Yahoo Finance's public chart endpoint for demonstration data. No API key is
required, but the endpoint is unofficial and should be replaced by Fugle/TWSE
before production use.
"""

from __future__ import annotations

import json
import math
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from statistics import fmean
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
TZ = ZoneInfo("Asia/Taipei")
CACHE_SECONDS = 15 * 60
MAX_LOOKBACK = 10
_cache: dict[str, tuple[float, Any]] = {}
_cache_lock = threading.Lock()


@dataclass(frozen=True)
class Stock:
    code: str
    name: str
    market: str
    category: str

    @property
    def yahoo_symbol(self) -> str:
        return f"{self.code}.TW" if self.market == "上市" else f"{self.code}.TWO"


STOCKS = [
    Stock("1101", "台泥", "上市", "原物料"), Stock("1216", "统一", "上市", "民生消费"),
    Stock("1301", "台塑", "上市", "原物料"), Stock("2002", "中钢", "上市", "原物料"),
    Stock("2303", "联电", "上市", "半导体"), Stock("2308", "台达电", "上市", "电子零组件"),
    Stock("2317", "鸿海", "上市", "电脑及周边"), Stock("2330", "台积电", "上市", "半导体"),
    Stock("2345", "智邦", "上市", "通信网络"), Stock("2382", "广达", "上市", "电脑及周边"),
    Stock("2383", "台光电", "上市", "电子零组件"), Stock("2454", "联发科", "上市", "半导体"),
    Stock("2881", "富邦金", "上市", "金融"), Stock("2882", "国泰金", "上市", "金融"),
    Stock("2891", "中信金", "上市", "金融"), Stock("3017", "奇鋐", "上市", "电子零组件"),
    Stock("3231", "纬创", "上市", "电脑及周边"), Stock("3711", "日月光投控", "上市", "半导体"),
    Stock("4904", "远传", "上市", "通信网络"), Stock("6505", "台塑化", "上市", "原物料"),
    Stock("8069", "元太", "上柜", "电子零组件"), Stock("6488", "环球晶", "上柜", "半导体"),
    Stock("5347", "世界", "上柜", "半导体"), Stock("5274", "信骅", "上柜", "半导体"),
    Stock("3529", "力旺", "上柜", "半导体"), Stock("3293", "钰创", "上柜", "半导体"),
    Stock("3105", "稳懋", "上柜", "半导体"), Stock("8299", "群联", "上柜", "半导体"),
    Stock("4966", "谱瑞-KY", "上柜", "半导体"), Stock("6188", "广明", "上柜", "电脑及周边"),
]


def load_generated_stocks() -> list[Stock]:
    """Use the generated full-market universe when it is available."""
    path = STATIC / "data" / "universe.json"
    if not path.exists():
        return STOCKS
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        items = payload.get("stocks", payload)
        loaded = [
            Stock(str(item["code"]), str(item["name"]), str(item["market"]), str(item["category"]))
            for item in items
            if str(item.get("market")) in {"上市", "上柜"}
        ]
        return loaded or STOCKS
    except (OSError, ValueError, KeyError, TypeError):
        return STOCKS

DEFAULT_RULES = {
    "maOrder": True, "maRising": True, "maRiseBars": 3,
    "kd60": True, "kd60Lookback": 3,
    "kdDay": True, "kdDayLookback": 3,
    "kdMonth": True, "kdMonthLookback": 3,
    "macd": True, "macdLookback": 3,
    "rsi": True, "rsiMax": 50,
    "dmi": True, "dmiLookback": 3,
}


def finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(value)


def ema(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) < period:
        return out
    seed = fmean(values[:period])
    out[period - 1] = seed
    alpha = 2 / (period + 1)
    prev = seed
    for i in range(period, len(values)):
        prev = values[i] * alpha + prev * (1 - alpha)
        out[i] = prev
    return out


def sma(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    total = 0.0
    for i, value in enumerate(values):
        total += value
        if i >= period:
            total -= values[i - period]
        if i >= period - 1:
            out[i] = total / period
    return out


def kd(highs: list[float], lows: list[float], closes: list[float], period: int = 9):
    k_values: list[float | None] = [None] * len(closes)
    d_values: list[float | None] = [None] * len(closes)
    k = d = 50.0
    for i in range(period - 1, len(closes)):
        high = max(highs[i - period + 1:i + 1])
        low = min(lows[i - period + 1:i + 1])
        rsv = 50.0 if high == low else (closes[i] - low) / (high - low) * 100
        k = (2 * k + rsv) / 3
        d = (2 * d + k) / 3
        k_values[i], d_values[i] = k, d
    return k_values, d_values


def rsi_wilder(closes: list[float], period: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(closes)
    if len(closes) <= period:
        return out
    gains = [max(closes[i] - closes[i - 1], 0) for i in range(1, len(closes))]
    losses = [max(closes[i - 1] - closes[i], 0) for i in range(1, len(closes))]
    avg_gain, avg_loss = fmean(gains[:period]), fmean(losses[:period])
    out[period] = 100 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)
    for i in range(period + 1, len(closes)):
        avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period
        out[i] = 100 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)
    return out


def macd(closes: list[float]):
    fast, slow = ema(closes, 12), ema(closes, 26)
    line: list[float | None] = [None] * len(closes)
    valid: list[float] = []
    indexes: list[int] = []
    for i, (a, b) in enumerate(zip(fast, slow)):
        if a is not None and b is not None:
            line[i] = a - b
            valid.append(line[i])
            indexes.append(i)
    signal_short = ema(valid, 9)
    signal: list[float | None] = [None] * len(closes)
    for j, idx in enumerate(indexes):
        signal[idx] = signal_short[j]
    hist = [None if line[i] is None or signal[i] is None else line[i] - signal[i] for i in range(len(closes))]
    return line, signal, hist


def dmi(highs: list[float], lows: list[float], closes: list[float], period: int = 14):
    n = len(closes)
    plus_di: list[float | None] = [None] * n
    minus_di: list[float | None] = [None] * n
    adx: list[float | None] = [None] * n
    if n <= period:
        return plus_di, minus_di, adx
    trs, plus_dm, minus_dm = [], [], []
    for i in range(1, n):
        up, down = highs[i] - highs[i - 1], lows[i - 1] - lows[i]
        trs.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
        plus_dm.append(up if up > down and up > 0 else 0)
        minus_dm.append(down if down > up and down > 0 else 0)
    atr, psm, msm = sum(trs[:period]), sum(plus_dm[:period]), sum(minus_dm[:period])
    dxs: list[tuple[int, float]] = []
    for i in range(period, n):
        if i > period:
            atr = atr - atr / period + trs[i - 1]
            psm = psm - psm / period + plus_dm[i - 1]
            msm = msm - msm / period + minus_dm[i - 1]
        p = 100 * psm / atr if atr else 0
        m = 100 * msm / atr if atr else 0
        plus_di[i], minus_di[i] = p, m
        dxs.append((i, 100 * abs(p - m) / (p + m) if p + m else 0))
    if len(dxs) >= period:
        current = fmean(v for _, v in dxs[:period])
        adx[dxs[period - 1][0]] = current
        for idx, value in dxs[period:]:
            current = (current * (period - 1) + value) / period
            adx[idx] = current
    return plus_di, minus_di, adx


def latest_two(values: list[float | None]) -> tuple[float, float]:
    valid = [v for v in values if v is not None and finite(v)]
    if len(valid) < 2:
        raise ValueError("有效资料不足")
    return float(valid[-2]), float(valid[-1])


def crossed_recent(a: list[float | None], b: list[float | None], lookback: int) -> bool:
    return cross_age(a, b, lookback) is not None


def cross_age(a: list[float | None], b: list[float | None], lookback: int) -> int | None:
    pairs = [(x, y) for x, y in zip(a, b) if x is not None and y is not None]
    for i in range(max(1, len(pairs) - lookback), len(pairs)):
        if pairs[i][0] > pairs[i][1] and pairs[i - 1][0] <= pairs[i - 1][1]:
            return len(pairs) - 1 - i
    return None


def signal(a: list[float | None], b: list[float | None], mode: str) -> bool:
    pa, ca = latest_two(a)
    pb, cb = latest_two(b)
    if mode == "recent3":
        return crossed_recent(a, b, 3) and ca > cb
    if mode == "bullish":
        return ca > cb and ca > pa
    return ca > cb and pa <= pb


def yahoo_chart(symbol: str, interval: str, range_value: str) -> list[dict[str, Any]]:
    key = f"{symbol}:{interval}:{range_value}"
    with _cache_lock:
        cached = _cache.get(key)
    if cached and time.time() - cached[0] < CACHE_SECONDS:
        return cached[1]
    url = "https://query1.finance.yahoo.com/v8/finance/chart/" + urllib.parse.quote(symbol)
    url += "?" + urllib.parse.urlencode({"interval": interval, "range": range_value, "events": "div,splits"})
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 TaiwanStockDemo/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            payload = json.load(response)
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"行情连接失败：{exc}") from exc
    result = payload.get("chart", {}).get("result")
    if not result:
        description = payload.get("chart", {}).get("error", {}).get("description", "查无资料")
        raise RuntimeError(description)
    item = result[0]
    timestamps = item.get("timestamp") or []
    quote = (item.get("indicators", {}).get("quote") or [{}])[0]
    rows = []
    for i, stamp in enumerate(timestamps):
        values = {k: (quote.get(k) or [None] * len(timestamps))[i] for k in ("open", "high", "low", "close", "volume")}
        if all(finite(values[k]) for k in ("open", "high", "low", "close")):
            rows.append({"ts": stamp, **values})
    with _cache_lock:
        _cache[key] = (time.time(), rows)
    return rows


def completed_rows(rows: list[dict[str, Any]], interval: str) -> list[dict[str, Any]]:
    now = datetime.now(TZ)
    if interval == "1d" and now.weekday() < 5 and now.hour * 60 + now.minute < 13 * 60 + 30:
        return [r for r in rows if datetime.fromtimestamp(r["ts"], TZ).date() < now.date()]
    if interval == "60m" and now.weekday() < 5:
        now_ts = now.timestamp()
        return [r for r in rows if r["ts"] + 3600 <= now_ts or datetime.fromtimestamp(r["ts"], TZ).date() < now.date()]
    return rows


def monthly_from_daily(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    current_month = datetime.now(TZ).strftime("%Y-%m")
    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = datetime.fromtimestamp(row["ts"], TZ).strftime("%Y-%m")
        if key != current_month:
            buckets.setdefault(key, []).append(row)
    monthly = []
    for key in sorted(buckets):
        items = buckets[key]
        monthly.append({
            "ts": items[-1]["ts"], "open": items[0]["open"], "high": max(x["high"] for x in items),
            "low": min(x["low"] for x in items), "close": items[-1]["close"],
            "volume": sum((x.get("volume") or 0) for x in items),
        })
    return monthly


def series(rows: list[dict[str, Any]]) -> tuple[list[float], list[float], list[float]]:
    return ([float(r["high"]) for r in rows], [float(r["low"]) for r in rows], [float(r["close"]) for r in rows])


def analyze(stock: Stock, options: dict[str, Any]) -> dict[str, Any]:
    daily = completed_rows(yahoo_chart(stock.yahoo_symbol, "1d", "2y"), "1d")
    hourly = completed_rows(yahoo_chart(stock.yahoo_symbol, "60m", "3mo"), "60m")
    monthly = monthly_from_daily(daily)
    if len(daily) < 80 or len(hourly) < 20 or len(monthly) < 12:
        raise RuntimeError("历史资料不足")
    dh, dl, dc = series(daily)
    hh, hl, hc = series(hourly)
    mh, ml, mc = series(monthly)
    mas = {p: sma(dc, p) for p in (5, 10, 20, 60)}
    ma_now = {p: latest_two(mas[p])[1] for p in mas}
    def rising_streak(values: list[float | None]) -> int:
        valid = [v for v in values if v is not None]
        streak = 0
        for i in range(len(valid) - 1, 0, -1):
            if valid[i] <= valid[i - 1]:
                break
            streak += 1
        return min(streak, MAX_LOOKBACK)
    ma_streaks = {p: rising_streak(mas[p]) for p in mas}
    ma_order_pass = ma_now[5] > ma_now[10] > ma_now[20] > ma_now[60]
    ma_rising_pass = all(ma_streaks[p] >= options["maRiseBars"] for p in mas)
    ma_enabled = options["maOrder"] or options["maRising"]
    ma_pass = ((not options["maOrder"] or ma_order_pass) and
               (not options["maRising"] or ma_rising_pass))
    kd_values = {}
    kd_passes = []
    kd_ages = []
    kd_specs = (
        ("60分", (hh, hl, hc), options["kd60"], options["kd60Lookback"]),
        ("日", (dh, dl, dc), options["kdDay"], options["kdDayLookback"]),
        ("月", (mh, ml, mc), options["kdMonth"], options["kdMonthLookback"]),
    )
    for label, values, enabled, lookback in kd_specs:
        kvals, dvals = kd(*values)
        _, know = latest_two(kvals)
        _, dnow = latest_two(dvals)
        age = cross_age(kvals, dvals, MAX_LOOKBACK)
        passed = age is not None and age < lookback and know > dnow
        kd_values[label] = {"enabled": enabled, "lookback": lookback, "k": round(know, 1), "d": round(dnow, 1), "pass": passed, "age": age}
        if enabled:
            kd_passes.append(passed)
            kd_ages.append(age)
    kd_enabled = any((options["kd60"], options["kdDay"], options["kdMonth"]))
    kd_pass = all(kd_passes) if kd_enabled else True
    _, _, hist = macd(dc)
    hp, hn = latest_two(hist)
    zero = [0.0 if v is not None else None for v in hist]
    macd_age = cross_age(hist, zero, MAX_LOOKBACK)
    macd_pass = macd_age is not None and macd_age < options["macdLookback"] and hn > 0
    rsi = rsi_wilder(dc)
    rp, rn = latest_two(rsi)
    rsi_pass = rn < options["rsiMax"] and rn > rp
    pdi, mdi, adx = dmi(dh, dl, dc)
    dmi_age = cross_age(pdi, mdi, MAX_LOOKBACK)
    dmi_pass = dmi_age is not None and dmi_age < options["dmiLookback"] and latest_two(pdi)[1] > latest_two(mdi)[1]
    _, an = latest_two(adx)
    groups = [
        ("ma", ma_enabled, ma_pass, 30.0), ("kd", kd_enabled, kd_pass, 30.0),
        ("macd", options["macd"], macd_pass, 40 / 3),
        ("rsi", options["rsi"], rsi_pass, 40 / 3),
        ("dmi", options["dmi"], dmi_pass, 40 / 3),
    ]
    enabled_groups = [g for g in groups if g[1]]
    matched = sum(1 for g in enabled_groups if g[2])
    qualified = bool(enabled_groups) and matched == len(enabled_groups)
    other_groups = [g for g in groups[1:] if g[1]]
    other_required = math.ceil(len(other_groups) / 2)
    ma_gate = ma_pass if ma_enabled else True
    near = not qualified and ma_gate and other_required > 0 and sum(1 for g in other_groups if g[2]) >= other_required
    score = round(sum(g[3] for g in enabled_groups if g[2]), 1)
    max_score = round(sum(g[3] for g in enabled_groups), 1)
    optional_ages = [*kd_ages]
    if options["macd"]:
        optional_ages.append(macd_age)
    if options["dmi"]:
        optional_ages.append(dmi_age)
    ages = [age for age in optional_ages if age is not None]
    trigger_age = max(ages) if ages else 99
    latest = daily[-1]
    prev_close = dc[-2]
    change = (dc[-1] / prev_close - 1) * 100
    turnover = (latest.get("volume") or 0) * dc[-1]
    return {
        "code": stock.code, "name": stock.name, "market": stock.market, "category": stock.category,
        "price": round(dc[-1], 2), "change": round(change, 2), "turnover": round(turnover),
        "date": datetime.fromtimestamp(latest["ts"], TZ).strftime("%Y-%m-%d"),
        "qualified": qualified, "near": near, "matched": matched, "enabledCount": len(enabled_groups),
        "score": score, "maxScore": max_score,
        "triggerAge": trigger_age, "liquidityRisk": turnover < 50_000_000,
        "signals": {
            "ma": {"enabled": ma_enabled, "pass": ma_pass, "orderEnabled": options["maOrder"], "orderPass": ma_order_pass,
                   "risingEnabled": options["maRising"], "risingPass": ma_rising_pass, "riseBars": options["maRiseBars"],
                   "riseStreaks": {str(k): v for k, v in ma_streaks.items()},
                   "values": {str(k): round(v, 2) for k, v in ma_now.items()}},
            "kd": {"enabled": kd_enabled, "pass": kd_pass, "values": kd_values},
            "macd": {"enabled": options["macd"], "lookback": options["macdLookback"], "pass": macd_pass, "hist": round(hn, 3), "previous": round(hp, 3), "age": macd_age},
            "rsi": {"enabled": options["rsi"], "max": options["rsiMax"], "pass": rsi_pass, "value": round(rn, 1), "up": rn > rp},
            "dmi": {"enabled": options["dmi"], "lookback": options["dmiLookback"], "pass": dmi_pass, "plus": round(latest_two(pdi)[1], 1), "minus": round(latest_two(mdi)[1], 1), "adx": round(an, 1), "age": dmi_age},
        },
    }


def parse_options(query: dict[str, list[str]]) -> dict[str, Any]:
    return dict(DEFAULT_RULES)


def normalize_rules(data: dict[str, Any]) -> dict[str, Any]:
    rules = dict(DEFAULT_RULES)
    for key in ("maOrder", "maRising", "kd60", "kdDay", "kdMonth", "macd", "rsi", "dmi"):
        if key in data:
            rules[key] = bool(data[key])
    for key in ("maRiseBars", "kd60Lookback", "kdDayLookback", "kdMonthLookback", "macdLookback", "dmiLookback"):
        if key in data:
            rules[key] = max(1, min(10, int(data[key])))
    if "rsiMax" in data:
        rules["rsiMax"] = max(1, min(99, int(data["rsiMax"])))
    if not any((rules["maOrder"], rules["maRising"], rules["kd60"], rules["kdDay"],
                rules["kdMonth"], rules["macd"], rules["rsi"], rules["dmi"])):
        raise ValueError("请至少启用一项筛选条件")
    return rules


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC), **kwargs)

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[{self.log_date_time_string()}] {fmt % args}")

    def send_json(self, payload: Any, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def run_scan(self, selected: list[Stock], options: dict[str, Any]) -> None:
        results, errors = [], []
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = {pool.submit(analyze, stock, options): stock for stock in selected}
            for future in as_completed(futures):
                stock = futures[future]
                try:
                    results.append(future.result())
                except Exception as exc:
                    errors.append({"code": stock.code, "name": stock.name, "message": str(exc)})
        qualified = sorted((x for x in results if x["qualified"]), key=lambda x: (x["triggerAge"], -x["turnover"]))
        near = sorted((x for x in results if x["near"]), key=lambda x: (-x["score"], x["triggerAge"], -x["turnover"]))[:5]
        self.send_json({
            "generatedAt": datetime.now(TZ).isoformat(timespec="seconds"),
            "scanned": len(selected), "qualifiedCount": len(qualified), "nearCount": len(near),
            "results": qualified + near, "errors": errors, "options": options,
            "disclaimer": "仅供研究与演示，不构成投资建议。Yahoo Finance 为非正式演示数据源。",
        })

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/status":
            stocks = load_generated_stocks()
            self.send_json({
                "stocks": len(stocks), "source": "交易所公司清单 + Yahoo Finance 历史行情", "cacheMinutes": CACHE_SECONDS // 60,
                "mode": "local", "defaultStocks": [s.__dict__ for s in stocks], "categories": sorted({s.category for s in stocks}),
                "defaultRules": DEFAULT_RULES,
            })
            return
        if parsed.path == "/api/scan":
            options = parse_options(urllib.parse.parse_qs(parsed.query))
            self.run_scan(load_generated_stocks(), options)
            return
        super().do_GET()

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/api/scan":
            self.send_json({"message": "找不到接口"}, 404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 65_536:
                raise ValueError("请求内容大小不正确")
            body = json.loads(self.rfile.read(length))
            options = normalize_rules(body.get("rules") or {})
            categories = set(body.get("categories") or [])
            selected = []
            for item in body.get("stocks") or []:
                code = str(item.get("code", "")).strip()
                name = str(item.get("name", code)).strip()[:30]
                market = str(item.get("market", "上市"))
                category = str(item.get("category", "其他")).strip()[:20] or "其他"
                if not code.isdigit() or len(code) not in {4, 5, 6} or market not in {"上市", "上柜"}:
                    continue
                if categories and category not in categories:
                    continue
                selected.append(Stock(code, name, market, category))
            if not selected:
                raise ValueError("当前产业族群中没有可扫描的股票")
            self.run_scan(selected[:100], options)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self.send_json({"message": str(exc)}, 400)


def main() -> None:
    port = int(os.environ.get("PORT", "8765"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"台股多周期筛选 Demo：http://127.0.0.1:{port}")
    print("按 Ctrl+C 停止。数据仅供研究与演示。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")


if __name__ == "__main__":
    main()
