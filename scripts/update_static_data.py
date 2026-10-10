#!/usr/bin/env python3
"""Build the static full-market dataset used by GitHub Pages."""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import server  # noqa: E402
from data_sources import fetch_universe  # noqa: E402


OUTPUT = ROOT / "static" / "data"
FULL_RULES = dict(server.DEFAULT_RULES)
FULL_RULES.update({
    "maRiseBars": 1,
    "kd60Lookback": server.MAX_LOOKBACK,
    "kdDayLookback": server.MAX_LOOKBACK,
    "kdMonthLookback": server.MAX_LOOKBACK,
    "macdLookback": server.MAX_LOOKBACK,
    "dmiLookback": server.MAX_LOOKBACK,
    "rsiMax": 99,
})


def compact(record: dict[str, Any]) -> dict[str, Any]:
    """Keep facts needed by the browser; qualification is recalculated there."""
    return {key: record[key] for key in (
        "code", "name", "market", "category", "price", "change", "turnover", "date",
        "liquidityRisk", "signals",
    )}


def analyze_with_retry(stock: server.Stock, attempts: int = 3) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return compact(server.analyze(stock, FULL_RULES))
        except Exception as exc:  # individual failures are recorded in the output
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(1.5 * (attempt + 1))
    assert last_error is not None
    raise last_error


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="Only build the first N stocks for verification")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--minimum-success-rate", type=float, default=0.75)
    args = parser.parse_args()

    universe = fetch_universe()
    if args.limit:
        universe = universe[:args.limit]
    if not universe:
        raise RuntimeError("没有取得上市上柜公司清单")

    generated_at = datetime.now(server.TZ).isoformat(timespec="seconds")
    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 10))) as pool:
        futures = {pool.submit(analyze_with_retry, stock): stock for stock in universe}
        for completed, future in enumerate(as_completed(futures), 1):
            stock = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:
                errors.append({"code": stock.code, "name": stock.name, "message": str(exc)[:180]})
            if completed % 50 == 0 or completed == len(universe):
                print(f"进度 {completed}/{len(universe)}，成功 {len(results)}，异常 {len(errors)}", flush=True)

    success_rate = len(results) / len(universe)
    if success_rate < args.minimum_success_rate:
        raise RuntimeError(f"成功率仅 {success_rate:.1%}，为避免覆盖正常网页，本次停止发布")

    results.sort(key=lambda item: (item["market"], item["code"]))
    available = [
        {key: item[key] for key in ("code", "name", "market", "category")}
        for item in results
    ]
    write_json(OUTPUT / "universe.json", {
        "generatedAt": generated_at,
        "stocks": available,
    })
    write_json(OUTPUT / "signals.json", {
        "schemaVersion": 1,
        "generatedAt": generated_at,
        "source": "TWSE/TPEx 公司清单；Yahoo Finance 历史行情",
        "universeCount": len(universe),
        "availableCount": len(results),
        "errorCount": len(errors),
        "results": results,
        "errors": errors,
    })
    write_json(OUTPUT / "status.json", {
        "stocks": len(results),
        "universeCount": len(universe),
        "availableCount": len(results),
        "errorCount": len(errors),
        "source": "TWSE/TPEx 公司清单；Yahoo Finance 历史行情",
        "mode": "static",
        "generatedAt": generated_at,
        "defaultStocks": available,
        "categories": sorted({item["category"] for item in available}),
        "defaultRules": server.DEFAULT_RULES,
    })
    print(f"完成：{len(results)}/{len(universe)}，资料写入 {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

