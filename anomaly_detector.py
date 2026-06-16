#!/usr/bin/env python3

import argparse
import json
import logging
import sqlite3
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any, Dict, List, Optional, Tuple


logger = logging.getLogger(__name__)


DEFAULT_CONFIG: Dict[str, Any] = {
    "s1": {
        "history_window": 30,
        "history_end_offset": 3,
        "volatility_14d_max": 0.035,
        "volatility_7d_max": 0.03,
        "volume_ma_period": 5,
        "volume_ma_t7_offset": 7,
        "spike_ratio_threshold": 2.0,
        "spike_count_min": 4,
        "acc_end_volume_peak_ratio": 0.6,
        "washout_day_min": 3,
        "washout_day_max": 5,
        "pullback_min": 0.08,
        "pullback_max": 0.12,
        "contraction_ratio": 0.7,
    },
    "s2": {
        "window": 30,
        "sideways_range_min": 0.10,
        "sideways_range_max": 0.40,
        "bottom_min_sep": 5,
        "bottom_band_tolerance": 0.03,
        "bottom_count_min": 2,
        "bottom_spread_max": 0.10,
        "support_ratio_min": 0.98,
        "support_ratio_max": 1.05,
        "shrink_ratio_min": 0.10,
        "shrink_ratio_max": 0.14,
        "rebound_low_guard": 0.98,
        "recent_pump_ratio_14_max": 1.22,
        "recent_max_abs_return_14_max": 0.10,
    },
    "s3": {
        "volume_multiple": 3.0,
        "non_zero_window": 20,
        "non_zero_min_ratio": 0.80,
    },
}


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = deepcopy(base)
    for k, v in override.items():
        if k in merged and isinstance(merged[k], dict) and isinstance(v, dict):
            merged[k] = _deep_merge(merged[k], v)
        else:
            merged[k] = v
    return merged


def load_config(config_path: str) -> Dict[str, Any]:
    cfg = deepcopy(DEFAULT_CONFIG)
    p = Path(config_path)
    if not p.exists():
        logger.warning("配置文件不存在，使用默认参数: %s", p)
        return cfg
    with open(p, "r", encoding="utf-8") as f:
        user_cfg = json.load(f)
    if not isinstance(user_cfg, dict):
        logger.warning("配置文件格式无效，使用默认参数")
        return cfg
    return _deep_merge(cfg, user_cfg)


EXPLANATIONS = {
    "item_id": "饰品ID",
    "item_name": "饰品名称",
    "date": "信号日期",
    "snapshot_date": "快照日期(daily_snapshots.date)",
    "snapshot_fetch_time": "快照抓取时间(daily_snapshots.fetch_time)",
    "strategy": "触发策略名称",
    "core_1_volume_up_vol_flat": "历史阶段量涨价平：MA5(历史末)>MA5(历史T-7) 且14d/7d波动率满足配置阈值",
    "core_2_spike_count": "历史阶段放量异动次数满足配置阈值",
    "core_3_washout_window": "今天处于吸筹完成后的洗盘窗口（按配置判断）",
    "core_4_pullback_pct": "从吸筹结束价回调幅度落在配置区间",
    "core_5_volume_contraction": "近期缩量：MA5(当前) 相对MA5(T-7)满足配置阈值",
    "core_1_sideways_range": "近30日横盘振幅位于配置区间",
    "core_2_multi_bottom_valid": "双底及以上且底部价差满足配置约束",
    "core_3_retest_support_zone": "当前回踩到前底支撑区间（按配置判断）",
    "core_4_shrink_retest": "缩量回踩：SMA3/SMA10_prev位于配置区间",
    "core_5_rebound_candle": "支撑区出现止跌阳线确认",
    "guard_1_recent_pump_cap": "近14根K线未出现过强拉升（按配置判断）",
    "guard_2_recent_turbulence_cap": "近14根K线不存在过大单日波动（按配置判断）",
    "core_1_volume_3x": "今日成交量>=昨日成交量4倍",
    "core_5_non_stagnant": "近20根非零成交比例>=80%",
    "spike_count": "历史阶段2倍放量次数",
    "bars_since_acc_end": "距离吸筹结束已过去K线根数",
    "decline_pct": "从吸筹结束价到当前回调比例",
    "hist_volatility_14d": "历史阶段近14日收益率波动率",
    "hist_volatility_7d": "历史阶段近7日收益率波动率",
    "hist_ma5_now": "历史阶段末端MA5成交量",
    "hist_ma5_t7": "历史阶段T-7时点MA5成交量",
    "hist_ma5_ratio_now_t7": "历史阶段MA5(末端)/MA5(T-7)",
    "ma5_now": "当前MA5成交量",
    "ma5_t7": "当前视角T-7时点MA5成交量",
    "ma5_ratio_now_t7": "当前MA5/T-7 MA5",
    "sideways_range": "近30根横盘振幅比例",
    "bottom_count": "有效底数量",
    "bottom_med": "有效底价格中位数",
    "bottom_spread": "有效底最大价差比例",
    "close_to_bottom_ratio": "当前价/底部中位价",
    "sma3_sma10prev_ratio": "当前SMA3(volume)/前序SMA10(volume)",
    "recent_pump_ratio_14": "近14根K线高低点振幅比(HHV14/LLV14)",
    "recent_max_abs_return_14": "近14根K线单日最大绝对涨跌幅",
    "today_volume": "今日成交量",
    "yesterday_volume": "昨日成交量",
    "volume_ratio": "今日成交量/昨日成交量",
    "non_zero_ratio_20": "近20根非零成交比例",
    "turnover_number": "近期成交数",
    "rank_num": "热度排名",
    "yyyp_lease_annual": "YYYP租赁年化",
    "buff_sell_price": "BUFF售价",
    "yyyp_sell_price": "YYYP售价",
    "steam_sell_price": "Steam售价",
    "yyyp_buy_num": "YYYP求购数",
    "yyyp_sell_num": "YYYP在售数",
    "steam_buff_sell_conversion": "Steam/BUFF挂刀比例",
    "statistic": "存世量",
    "sell_price_rate_1": "BUFF 1日涨跌幅",
    "yyyp_sell_price_rate_1": "YYYP 1日涨跌幅",
    "yyyp_sell_price_rate_15": "YYYP 15日涨跌幅",
}


@dataclass
class StrategyResult:
    strategy_name: str
    triggered: bool
    core_checks: Dict[str, bool]
    core_metrics: Dict[str, float]
    reason: str


class AnomalyDetector:
    def __init__(self, db_path: str = "./csgo_monitor.db", config: Optional[Dict[str, Any]] = None):
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.config = deepcopy(config) if config else deepcopy(DEFAULT_CONFIG)

    def close(self) -> None:
        if self.conn:
            self.conn.close()

    def get_item_ids(self, item_id: Optional[int] = None) -> List[int]:
        cursor = self.conn.cursor()
        if item_id is not None:
            cursor.execute("SELECT DISTINCT item_id FROM kline_data WHERE item_id = ?", (item_id,))
        else:
            cursor.execute("SELECT DISTINCT item_id FROM kline_data ORDER BY item_id")
        return [int(row[0]) for row in cursor.fetchall()]

    def get_item_name(self, item_id: int) -> str:
        cursor = self.conn.cursor()
        cursor.execute("SELECT name FROM items WHERE id = ?", (item_id,))
        row = cursor.fetchone()
        return row[0] if row else f"item_{item_id}"

    def get_klines(self, item_id: int, limit: int = 180) -> List[sqlite3.Row]:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT timestamp, open, high, low, close, volume
            FROM (
                SELECT timestamp, open, high, low, close, volume
                FROM kline_data
                WHERE item_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            )
            ORDER BY timestamp ASC
            """,
            (item_id, limit),
        )
        return cursor.fetchall()

    def get_latest_snapshot(self, item_id: int) -> Dict[str, Any]:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT *
            FROM daily_snapshots
            WHERE item_id = ?
            ORDER BY date DESC, fetch_time DESC
            LIMIT 1
            """,
            (item_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else {}

    def get_snapshot_on_or_before(self, item_id: int, date_str: str) -> Dict[str, Any]:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT *
            FROM daily_snapshots
            WHERE item_id = ? AND date <= ?
            ORDER BY date DESC, fetch_time DESC
            LIMIT 1
            """,
            (item_id, date_str),
        )
        row = cursor.fetchone()
        return dict(row) if row else {}

    @staticmethod
    def sma(values: List[float], period: int) -> Optional[float]:
        if len(values) < period:
            return None
        return sum(values[-period:]) / period

    @staticmethod
    def safe_ratio(a: float, b: float) -> float:
        if b == 0:
            return 0.0
        return a / b

    @staticmethod
    def volatility(values: List[float]) -> float:
        if len(values) <= 1:
            return 0.0
        mean_v = sum(values) / len(values)
        var = sum((x - mean_v) ** 2 for x in values) / len(values)
        return var ** 0.5

    def _cfg(self, path: str, default: Any) -> Any:
        node: Any = self.config
        for key in path.split("."):
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node

    def _strategy_1(self, rows: List[sqlite3.Row]) -> StrategyResult:
        name = "S1_MAIN_FORCE_ENTRY"
        hist_window = int(self._cfg("s1.history_window", 30))
        hist_end_offset = int(self._cfg("s1.history_end_offset", 3))
        ma_period = int(self._cfg("s1.volume_ma_period", 5))
        t7_offset = int(self._cfg("s1.volume_ma_t7_offset", 7))

        min_required = max(hist_window + hist_end_offset + 2, ma_period + t7_offset + ma_period + 2)
        if len(rows) < min_required:
            return StrategyResult(name, False, {"enough_data": False}, {}, f"K线不足{min_required}根")

        closes = [float(r["close"]) for r in rows]
        volumes = [float(r["volume"] or 0) for r in rows]
        close_now = closes[-1]

        historical_closes = closes[-(hist_window + hist_end_offset):-hist_end_offset]
        historical_volumes = volumes[-(hist_window + hist_end_offset):-hist_end_offset]

        hist_returns = []
        for i in range(1, len(historical_closes)):
            prev_c = historical_closes[i - 1]
            hist_returns.append(self.safe_ratio(historical_closes[i] - prev_c, prev_c) if prev_c != 0 else 0.0)

        hist_vol14 = self.volatility(hist_returns[-14:])
        hist_vol7 = self.volatility(hist_returns[-7:])

        hist_ma5_now_window = volumes[-(hist_end_offset + ma_period):-hist_end_offset]
        hist_ma5_t7_end = hist_end_offset + t7_offset
        hist_ma5_t7_start = hist_ma5_t7_end + ma_period
        hist_ma5_t7_window = volumes[-hist_ma5_t7_start:-hist_ma5_t7_end]
        hist_ma5_now = sum(hist_ma5_now_window) / float(ma_period) if len(hist_ma5_now_window) == ma_period else 0.0
        hist_ma5_t7 = sum(hist_ma5_t7_window) / float(ma_period) if len(hist_ma5_t7_window) == ma_period else 0.0
        hist_ma5_ratio_now_t7 = self.safe_ratio(hist_ma5_now, hist_ma5_t7 if hist_ma5_t7 > 0 else 1.0)

        core_1 = (
            hist_ma5_now > hist_ma5_t7
            and hist_vol14 <= float(self._cfg("s1.volatility_14d_max", 0.035))
            and hist_vol7 <= float(self._cfg("s1.volatility_7d_max", 0.03))
        )

        spike_count = 0
        spike_indices = []
        for i in range(1, len(historical_volumes)):
            prev_v = max(historical_volumes[i - 1], 1.0)
            if (historical_volumes[i] / prev_v) >= float(self._cfg("s1.spike_ratio_threshold", 2.0)):
                spike_count += 1
                spike_indices.append(i)
        core_2 = spike_count >= int(self._cfg("s1.spike_count_min", 4))

        bars_since = -1
        decline_pct = -1.0
        core_3 = False
        core_4 = False
        if spike_indices:
            last_spike_idx = spike_indices[-1]
            peak_volume = max(historical_volumes)
            accumulation_end_idx = None
            for j in range(last_spike_idx + 1, len(historical_volumes)):
                if historical_volumes[j] <= peak_volume * float(self._cfg("s1.acc_end_volume_peak_ratio", 0.6)):
                    accumulation_end_idx = j
                    break

            if accumulation_end_idx is not None:
                today_idx = len(volumes) - 1
                acc_end_global_idx = (len(volumes) - (hist_window + hist_end_offset)) + accumulation_end_idx
                bars_since = today_idx - acc_end_global_idx
                core_3 = int(self._cfg("s1.washout_day_min", 3)) <= bars_since <= int(self._cfg("s1.washout_day_max", 5))
                acc_end_price = closes[acc_end_global_idx]
                decline_pct = self.safe_ratio(acc_end_price - close_now, acc_end_price)
                core_4 = float(self._cfg("s1.pullback_min", 0.08)) <= decline_pct <= float(self._cfg("s1.pullback_max", 0.12))

        ma5_now = sum(volumes[-ma_period:]) / float(ma_period)
        ma5_t7_window = volumes[-(t7_offset + ma_period):-t7_offset]
        ma5_t7 = sum(ma5_t7_window) / float(ma_period) if len(ma5_t7_window) == ma_period else 0.0
        ma5_ratio_now_t7 = self.safe_ratio(ma5_now, ma5_t7 if ma5_t7 > 0 else 1.0)
        core_5 = ma5_now < ma5_t7 * float(self._cfg("s1.contraction_ratio", 0.7))

        core_checks = {
            "core_1_volume_up_vol_flat": core_1,
            "core_2_spike_count": core_2,
            "core_3_washout_window": core_3,
            "core_4_pullback_pct": core_4,
            "core_5_volume_contraction": core_5,
        }
        triggered = all(core_checks.values())
        metrics = {
            "hist_volatility_14d": round(hist_vol14, 6),
            "hist_volatility_7d": round(hist_vol7, 6),
            "hist_ma5_now": round(hist_ma5_now, 6),
            "hist_ma5_t7": round(hist_ma5_t7, 6),
            "hist_ma5_ratio_now_t7": round(hist_ma5_ratio_now_t7, 6),
            "spike_count": float(spike_count),
            "bars_since_acc_end": float(bars_since),
            "decline_pct": round(decline_pct, 6),
            "ma5_now": round(ma5_now, 6),
            "ma5_t7": round(ma5_t7, 6),
            "ma5_ratio_now_t7": round(ma5_ratio_now_t7, 6),
        }
        reason = "S1核心规则全满足" if triggered else "S1核心规则未全满足"
        return StrategyResult(name, triggered, core_checks, metrics, reason)

    def _dedupe_bottom_candidates(self, lows: List[float], min_sep: int = 5) -> List[Tuple[int, float]]:
        candidates: List[Tuple[int, float]] = []
        for i in range(2, len(lows) - 2):
            if lows[i] < lows[i - 1] and lows[i] < lows[i - 2] and lows[i] < lows[i + 1] and lows[i] < lows[i + 2]:
                if not candidates:
                    candidates.append((i, lows[i]))
                else:
                    prev_i, prev_low = candidates[-1]
                    if i - prev_i >= min_sep:
                        candidates.append((i, lows[i]))
                    elif lows[i] < prev_low:
                        candidates[-1] = (i, lows[i])
        return candidates

    def _strategy_2(self, rows: List[sqlite3.Row]) -> StrategyResult:
        name = "S2_MULTI_BOTTOM_RETRACE"
        window = int(self._cfg("s2.window", 30))
        if len(rows) < window:
            return StrategyResult(name, False, {"enough_data": False}, {}, f"K线不足{window}根")

        rows_w = rows[-window:]
        closes = [float(r["close"]) for r in rows_w]
        lows = [float(r["low"]) for r in rows_w]
        opens = [float(r["open"]) for r in rows_w]
        volumes = [float(r["volume"] or 0) for r in rows_w]
        close_now = closes[-1]
        open_now = opens[-1]
        low_now = lows[-1]

        sideways_range = self.safe_ratio(max(closes) - min(closes), sum(closes) / len(closes))
        core_1 = float(self._cfg("s2.sideways_range_min", 0.10)) <= sideways_range <= float(self._cfg("s2.sideways_range_max", 0.40))

        candidates = self._dedupe_bottom_candidates(lows, min_sep=int(self._cfg("s2.bottom_min_sep", 5)))
        if candidates:
            med = median([x[1] for x in candidates])
            tolerance = float(self._cfg("s2.bottom_band_tolerance", 0.03))
            valid_bottoms = [(i, p) for (i, p) in candidates if abs(p - med) / med <= tolerance]
            bottom_med = median([x[1] for x in valid_bottoms]) if valid_bottoms else 0.0
            bottom_prices = [x[1] for x in valid_bottoms]
            bottom_spread = self.safe_ratio(max(bottom_prices) - min(bottom_prices), bottom_med) if bottom_prices and bottom_med > 0 else 0.0
        else:
            valid_bottoms = []
            bottom_med = 0.0
            bottom_spread = 0.0

        bottom_count = len(valid_bottoms)
        core_2 = bottom_count >= int(self._cfg("s2.bottom_count_min", 2)) and bottom_spread <= float(self._cfg("s2.bottom_spread_max", 0.10))

        close_to_bottom_ratio = self.safe_ratio(close_now, bottom_med) if bottom_med > 0 else 0.0
        core_3 = bottom_med > 0 and float(self._cfg("s2.support_ratio_min", 0.98)) <= close_to_bottom_ratio <= float(self._cfg("s2.support_ratio_max", 1.05))

        sma3_now = sum(volumes[-3:]) / 3.0
        prev_10 = volumes[-13:-3]
        sma10_prev = (sum(prev_10) / 10.0) if len(prev_10) == 10 else None
        shrink_ratio = self.safe_ratio(sma3_now, sma10_prev or 1.0)
        core_4 = sma10_prev is not None and float(self._cfg("s2.shrink_ratio_min", 0.10)) <= shrink_ratio <= float(self._cfg("s2.shrink_ratio_max", 0.14))

        core_5 = bottom_med > 0 and close_now > open_now and low_now >= bottom_med * float(self._cfg("s2.rebound_low_guard", 0.98))

        recent_rows = rows_w[-14:]
        recent_highs = [float(r["high"]) for r in recent_rows]
        recent_lows = [float(r["low"]) for r in recent_rows]
        recent_closes = [float(r["close"]) for r in recent_rows]
        recent_pump_ratio_14 = self.safe_ratio(max(recent_highs), min(recent_lows)) if recent_lows and min(recent_lows) > 0 else 0.0
        recent_abs_returns = []
        for i in range(1, len(recent_closes)):
            prev_c = recent_closes[i - 1]
            recent_abs_returns.append(abs(self.safe_ratio(recent_closes[i] - prev_c, prev_c)) if prev_c != 0 else 0.0)
        recent_max_abs_return_14 = max(recent_abs_returns) if recent_abs_returns else 0.0
        guard_1 = recent_pump_ratio_14 <= float(self._cfg("s2.recent_pump_ratio_14_max", 1.22))
        guard_2 = recent_max_abs_return_14 <= float(self._cfg("s2.recent_max_abs_return_14_max", 0.10))

        core_checks = {
            "core_1_sideways_range": core_1,
            "core_2_multi_bottom_valid": core_2,
            "core_3_retest_support_zone": core_3,
            "core_4_shrink_retest": core_4,
            "core_5_rebound_candle": core_5,
            "guard_1_recent_pump_cap": guard_1,
            "guard_2_recent_turbulence_cap": guard_2,
        }
        triggered = all(core_checks.values())
        metrics = {
            "sideways_range": round(sideways_range, 6),
            "bottom_count": float(bottom_count),
            "bottom_med": round(bottom_med, 6),
            "bottom_spread": round(bottom_spread, 6),
            "close_to_bottom_ratio": round(close_to_bottom_ratio, 6),
            "sma3_sma10prev_ratio": round(shrink_ratio, 6),
            "recent_pump_ratio_14": round(recent_pump_ratio_14, 6),
            "recent_max_abs_return_14": round(recent_max_abs_return_14, 6),
        }
        reason = "S2核心规则全满足" if triggered else "S2核心规则未全满足"
        return StrategyResult(name, triggered, core_checks, metrics, reason)

    def _strategy_3(self, rows: List[sqlite3.Row]) -> StrategyResult:
        name = "S3_VOLUME_3X"
        nz_window = int(self._cfg("s3.non_zero_window", 20))
        if len(rows) < nz_window:
            return StrategyResult(name, False, {"enough_data": False}, {}, f"K线不足{nz_window}根")

        volumes = [float(r["volume"] or 0) for r in rows]
        today_v = volumes[-1]
        yesterday_v = volumes[-2] if len(volumes) >= 2 else 0.0
        vol_ratio = self.safe_ratio(today_v, max(yesterday_v, 1.0))
        core_1 = vol_ratio >= float(self._cfg("s3.volume_multiple", 4.0))

        recent_n = volumes[-nz_window:]
        non_zero_ratio = sum(1 for v in recent_n if v > 0) / float(nz_window)
        core_5 = non_zero_ratio >= float(self._cfg("s3.non_zero_min_ratio", 0.80))

        core_checks = {
            "core_1_volume_3x": core_1,
            "core_5_non_stagnant": core_5,
        }
        triggered = all(core_checks.values())
        metrics = {
            "today_volume": today_v,
            "yesterday_volume": yesterday_v,
            "volume_ratio": round(vol_ratio, 6),
            "non_zero_ratio_20": round(non_zero_ratio, 6),
        }
        reason = "S3核心规则全满足" if triggered else "S3核心规则未全满足"
        return StrategyResult(name, triggered, core_checks, metrics, reason)

    def evaluate_rows(self, rows: List[sqlite3.Row]) -> List[StrategyResult]:
        return [self._strategy_1(rows), self._strategy_2(rows), self._strategy_3(rows)]

    @staticmethod
    def timestamp_to_date(ts_ms: int) -> str:
        return datetime.fromtimestamp(ts_ms / 1000).strftime("%Y-%m-%d")


def format_triplet(variable: str, value: Any) -> str:
    return f"{variable}; {EXPLANATIONS.get(variable, variable)}; {value}"


def build_aux_triplets(snapshot: Dict[str, Any]) -> List[str]:
    ordered = [
        "turnover_number",
        "rank_num",
        "yyyp_lease_annual",
        "buff_sell_price",
        "yyyp_sell_price",
        "steam_sell_price",
        "yyyp_buy_num",
        "yyyp_sell_num",
        "steam_buff_sell_conversion",
        "statistic",
        "sell_price_rate_1",
        "yyyp_sell_price_rate_1",
        "yyyp_sell_price_rate_15",
    ]
    return [format_triplet(k, snapshot.get(k)) for k in ordered]


def build_alert(
    item_id: int,
    item_name: str,
    signal_date: str,
    strategy_result: StrategyResult,
    snapshot: Dict[str, Any],
) -> Dict[str, Any]:
    meta_rows: List[str] = [
        format_triplet("date", signal_date),
        format_triplet("item_id", item_id),
        format_triplet("item_name", item_name),
        format_triplet("strategy", strategy_result.strategy_name),
    ]
    if snapshot.get("date") is not None:
        meta_rows.append(format_triplet("snapshot_date", snapshot.get("date")))
    if snapshot.get("fetch_time") is not None:
        meta_rows.append(format_triplet("snapshot_fetch_time", snapshot.get("fetch_time")))

    core_rule_triplets: List[str] = []
    for k, v in strategy_result.core_checks.items():
        core_rule_triplets.append(format_triplet(k, v))

    metric_triplets = [format_triplet(k, v) for k, v in strategy_result.core_metrics.items()]

    return {
        "triplet_format": "<字段>; <解释>; <数值>",
        "meta": meta_rows,
        "core_rule_results": core_rule_triplets,
        "core_metric_values": metric_triplets,
        "auxiliary_values": build_aux_triplets(snapshot),
        "reason": strategy_result.reason,
    }


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler()],
    )


def run_current_mode(detector: AnomalyDetector, item_ids: List[int]) -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "mode": "current",
        "run_at": datetime.now().isoformat(),
        "scanned_item_count": len(item_ids),
        "triggered_item_count": 0,
        "alert_count": 0,
        "alerts": [],
    }
    triggered_item_ids = set()

    s3_entries: List[str] = []

    for item_id in item_ids:
        item_name = detector.get_item_name(item_id)
        rows = detector.get_klines(item_id)
        snapshot = detector.get_latest_snapshot(item_id)

        if not rows:
            continue

        signal_date = detector.timestamp_to_date(int(rows[-1]["timestamp"]))
        strategy_results = detector.evaluate_rows(rows)
        item_triggered = False
        for res in strategy_results:
            if not res.triggered:
                continue
            item_triggered = True
            if res.strategy_name == "S3_VOLUME_3X":
                s3_entries.append(f"{signal_date}; {item_id}; {item_name}")
            else:
                report["alerts"].append(build_alert(item_id, item_name, signal_date, res, snapshot))

        if item_triggered:
            triggered_item_ids.add(item_id)

    if s3_entries:
        report["alerts"].append(
            {
                "triplet_format": "date; item_id; item_name",
                "meta": [
                    "strategy; 触发策略名称; S3_VOLUME_3X",
                    f"count; S3命中条数; {len(s3_entries)}",
                ],
                "items": s3_entries,
            }
        )

    report["triggered_item_count"] = len(triggered_item_ids)
    report["alert_count"] = len(report["alerts"])

    return report


def run_backtest_mode(detector: AnomalyDetector, item_ids: List[int], lookback_bars: int) -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "mode": "backtest",
        "run_at": datetime.now().isoformat(),
        "item_count": len(item_ids),
        "lookback_bars": lookback_bars,
        "alerts": [],
        "summary": {
            "S1_MAIN_FORCE_ENTRY": 0,
            "S2_MULTI_BOTTOM_RETRACE": 0,
            "S3_VOLUME_3X": 0,
        },
    }

    min_bars = 50
    s3_entries: List[str] = []

    for item_id in item_ids:
        item_name = detector.get_item_name(item_id)
        rows = detector.get_klines(item_id)
        if len(rows) < min_bars:
            continue

        start_idx = max(min_bars - 1, len(rows) - lookback_bars)
        for end_idx in range(start_idx, len(rows)):
            window_rows = rows[: end_idx + 1]
            signal_date = detector.timestamp_to_date(int(window_rows[-1]["timestamp"]))
            snapshot = detector.get_snapshot_on_or_before(item_id, signal_date)
            strategy_results = detector.evaluate_rows(window_rows)

            for res in strategy_results:
                if not res.triggered:
                    continue
                report["summary"][res.strategy_name] += 1
                if res.strategy_name == "S3_VOLUME_3X":
                    s3_entries.append(f"{signal_date}; {item_id}; {item_name}")
                else:
                    report["alerts"].append(build_alert(item_id, item_name, signal_date, res, snapshot))

    if s3_entries:
        report["alerts"].append(
            {
                "triplet_format": "date; item_id; item_name",
                "meta": [
                    "strategy; 触发策略名称; S3_VOLUME_3X",
                    f"count; S3命中条数; {len(s3_entries)}",
                ],
                "items": s3_entries,
            }
        )

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="异动识别工具（当前检测 + 回测）")
    parser.add_argument("--db-path", type=str, default="./csgo_monitor.db", help="SQLite数据库路径")
    parser.add_argument("--config", type=str, default="./config.json", help="策略参数配置文件路径")
    parser.add_argument("--item-id", type=int, default=None, help="仅检测单个item_id")
    parser.add_argument("--output-dir", type=str, default="./signals", help="输出目录")
    parser.add_argument("--mode", type=str, default="current", choices=["current", "backtest"], help="运行模式")
    parser.add_argument("--lookback-bars", type=int, default=120, help="回测模式的回看K线根数")
    args = parser.parse_args()

    setup_logging()
    config = load_config(args.config)
    detector = AnomalyDetector(args.db_path, config=config)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        item_ids = detector.get_item_ids(args.item_id)
        if not item_ids:
            logger.warning("未找到可检测的K线数据")
            return

        if args.mode == "current":
            report = run_current_mode(detector, item_ids)
            filename = f"anomaly_current_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        else:
            report = run_backtest_mode(detector, item_ids, args.lookback_bars)
            filename = f"anomaly_backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        report["db_path"] = str(Path(args.db_path).resolve())
        output_file = output_dir / filename
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        item_metric = int(report.get("item_count", report.get("scanned_item_count", 0)))
        logger.info("模式=%s, item=%d, alerts=%d", report["mode"], item_metric, len(report["alerts"]))
        logger.info("报告已保存: %s", output_file)
    finally:
        detector.close()


if __name__ == "__main__":
    main()
