import importlib.util
import math
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("demo_server", ROOT / "server.py")
server = importlib.util.module_from_spec(spec)
assert spec.loader
sys.modules[spec.name] = server
spec.loader.exec_module(server)


class IndicatorTests(unittest.TestCase):
    def test_sma(self):
        self.assertEqual(server.sma([1, 2, 3, 4], 3), [None, None, 2.0, 3.0])

    def test_ema_finishes_at_latest_value(self):
        values = server.ema([1, 2, 3, 4, 5], 3)
        self.assertIsNone(values[1])
        self.assertTrue(math.isclose(values[-1], 4.0))

    def test_kd_stays_bounded(self):
        closes = [float(i) for i in range(1, 25)]
        k, d = server.kd([x + 1 for x in closes], [x - 1 for x in closes], closes)
        self.assertTrue(0 <= server.latest_two(k)[1] <= 100)
        self.assertTrue(0 <= server.latest_two(d)[1] <= 100)

    def test_monthly_excludes_current_month(self):
        now = server.datetime.now(server.TZ)
        rows = [{"ts": now.timestamp(), "open": 1, "high": 2, "low": 1, "close": 2, "volume": 10}]
        self.assertEqual(server.monthly_from_daily(rows), [])

    def test_cross_age_finds_recent_cross(self):
        a = [1.0, 2.0, 4.0, 5.0]
        b = [3.0, 3.0, 3.0, 3.0]
        self.assertEqual(server.cross_age(a, b, 3), 1)

    def test_cross_age_respects_lookback(self):
        a = [1.0, 4.0, 5.0, 6.0]
        b = [3.0, 3.0, 3.0, 3.0]
        self.assertIsNone(server.cross_age(a, b, 2))
        self.assertEqual(server.cross_age(a, b, 3), 2)

    def test_near_match_requires_ma_and_two_more_groups(self):
        groups = [True, True, True, False, False]
        self.assertTrue(groups[0] and sum(groups[1:]) >= 2)
        groups = [False, True, True, True, True]
        self.assertFalse(groups[0] and sum(groups[1:]) >= 2)

    def test_rule_ranges_are_clamped(self):
        rules = server.normalize_rules({"kdDayLookback": 99, "macd": False})
        self.assertEqual(rules["kdDayLookback"], 10)
        self.assertFalse(rules["macd"])

    def test_at_least_one_rule_is_required(self):
        switches = {key: False for key in ("maOrder", "maRising", "kd60", "kdDay", "kdMonth", "macd", "rsi", "dmi")}
        with self.assertRaises(ValueError):
            server.normalize_rules(switches)


if __name__ == "__main__":
    unittest.main()
