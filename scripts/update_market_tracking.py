from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.utils import DATA_DIR, read_csv_safe, write_csv_atomic, write_json  # noqa: E402

BEIJING = ZoneInfo("Asia/Shanghai")
OUTPUT_JSON = DATA_DIR / "market_tracking.json"
OUTPUT_CSV = DATA_DIR / "market_tracking.csv"
STATUS_PATH = DATA_DIR / "status.json"

HISTORY_COLUMNS = [
    "trade_date",
    "market_score",
    "risk_score",
    "suggested_position_pct",
    "risk_level",
    "market_phase",
    "style_signal",
    "source",
]

FRAMEWORK_SECTIONS = [
    {
        "title": "整体投研系统",
        "subtitle": "大盘决定仓位，产业决定方向，个股决定标的，交易决定节奏，风控决定生存。",
        "items": ["大盘模型", "产业模型", "个股模型", "交易模型", "风险控制体系"],
    },
    {
        "title": "总控层",
        "subtitle": "先判断市场环境，再决定是否承担风险。",
        "items": ["绝对收益 + 相对收益兼顾", "最大回撤约束", "多周期结合", "A股为核心，海外市场辅助"],
    },
    {
        "title": "大盘模型",
        "subtitle": "输出大盘评分、市场阶段、总仓位建议、风格判断。",
        "items": ["宏观周期 15%", "流动性环境 20%", "政策环境 15%", "盈利周期 15%", "估值水平 15%", "市场情绪 10%", "风格结构 10%"],
    },
    {
        "title": "风险领先预警模型",
        "subtitle": "提前发现风险，而不是等待指数下跌。",
        "items": ["市场广度恶化 20%", "量价质量恶化 20%", "主线健康度 20%", "杠杆资金拥挤 15%", "外部资产压力 10%", "估值盈利背离 10%", "政策反应钝化 5%"],
    },
    {
        "title": "产业与交易",
        "subtitle": "产业研究确定方向，交易模型决定节奏。",
        "items": ["AI", "光模块", "PCB", "半导体材料", "存储", "HBM", "半导体设备"],
    },
]

PROCESS_STEPS = ["市场环境判断", "产业方向选择", "个股筛选", "交易执行", "风险控制"]

MARKET_MODULES = [
    ("宏观周期", 15),
    ("流动性环境", 20),
    ("政策环境", 15),
    ("盈利周期", 15),
    ("估值水平", 15),
    ("市场情绪", 10),
    ("风格结构", 10),
]

RISK_MODULES = [
    ("市场广度恶化", 20),
    ("量价质量恶化", 20),
    ("主线健康度", 20),
    ("杠杆资金拥挤", 15),
    ("外部资产压力", 10),
    ("估值盈利背离", 10),
    ("政策反应钝化", 5),
]


def clean_number(value: Any) -> float | None:
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(number):
        return None
    return float(number)


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return float(max(low, min(high, value)))


def score_between(value: float | None, low: float, high: float) -> float:
    if value is None or high == low:
        return 50.0
    return clamp((value - low) / (high - low) * 100)


def inverse_score_between(value: float | None, low: float, high: float) -> float:
    return 100.0 - score_between(value, low, high)


def average(values: list[float | None], default: float = 50.0) -> float:
    clean = [float(x) for x in values if x is not None and np.isfinite(float(x))]
    return float(np.mean(clean)) if clean else default


def pct_rank(values: pd.Series, current: float | None) -> float:
    series = pd.to_numeric(values, errors="coerce").dropna()
    if current is None or series.empty:
        return 50.0
    return float((series <= current).mean() * 100)


def latest_row(frame: pd.DataFrame, date_col: str, as_of: str | None = None) -> pd.Series | None:
    if frame.empty or date_col not in frame.columns:
        return None
    current = frame.copy()
    current[date_col] = current[date_col].astype(str)
    if as_of:
        key = as_of[:6] if date_col == "month" else as_of
        current = current[current[date_col] <= key]
    current = current.sort_values(date_col)
    if current.empty:
        return None
    return current.iloc[-1]


def latest_value(frame: pd.DataFrame, column: str, date_col: str, as_of: str | None = None) -> float | None:
    row = latest_row(frame, date_col, as_of)
    return clean_number(row.get(column)) if row is not None and column in row else None


def series_until(frame: pd.DataFrame, date_col: str, as_of: str | None = None) -> pd.DataFrame:
    if frame.empty or date_col not in frame.columns:
        return frame.copy()
    current = frame.copy()
    current[date_col] = current[date_col].astype(str)
    if as_of:
        key = as_of[:6] if date_col == "month" else as_of
        current = current[current[date_col] <= key]
    return current.sort_values(date_col)


def delta(frame: pd.DataFrame, column: str, date_col: str, periods: int = 1, as_of: str | None = None) -> float | None:
    current = series_until(frame, date_col, as_of)
    values = pd.to_numeric(current[column], errors="coerce").dropna() if column in current else pd.Series(dtype=float)
    if len(values) <= periods:
        return None
    return float(values.iloc[-1] - values.iloc[-1 - periods])


def momentum(market: pd.DataFrame, symbol: str, days: int, as_of: str | None = None) -> float | None:
    if market.empty:
        return None
    rows = market[market["symbol"].astype(str) == symbol].copy()
    rows = series_until(rows, "trade_date", as_of)
    rows["close"] = pd.to_numeric(rows.get("close"), errors="coerce")
    rows = rows.dropna(subset=["close"])
    if len(rows) <= days:
        return None
    return float((rows["close"].iloc[-1] / rows["close"].iloc[-1 - days] - 1) * 100)


def ma_gap(market: pd.DataFrame, symbol: str, days: int, as_of: str | None = None) -> float | None:
    rows = market[market["symbol"].astype(str) == symbol].copy()
    rows = series_until(rows, "trade_date", as_of)
    rows["close"] = pd.to_numeric(rows.get("close"), errors="coerce")
    rows = rows.dropna(subset=["close"])
    if len(rows) < days:
        return None
    close = float(rows["close"].iloc[-1])
    ma = float(rows["close"].tail(days).mean())
    if ma == 0:
        return None
    return (close / ma - 1) * 100


def format_pct(value: float | None, digits: int = 2) -> str:
    if value is None or not np.isfinite(value):
        return "暂无"
    return f"{value:.{digits}f}%"


def format_num(value: float | None, digits: int = 2) -> str:
    if value is None or not np.isfinite(value):
        return "暂无"
    return f"{value:.{digits}f}"


def status_label(score: float) -> str:
    if score >= 70:
        return "偏强"
    if score >= 55:
        return "中性偏强"
    if score >= 45:
        return "中性"
    if score >= 30:
        return "偏弱"
    return "弱"


def risk_level(score: float) -> str:
    if score <= 35:
        return "绿色"
    if score <= 55:
        return "黄色"
    if score <= 75:
        return "橙色"
    return "红色"


def risk_label(score: float) -> str:
    if score <= 35:
        return "低"
    if score <= 55:
        return "中"
    if score <= 75:
        return "偏高"
    return "高"


def suggested_position(score: float, risk: float) -> tuple[float, float, float]:
    if score >= 70:
        base = 80.0
    elif score >= 60:
        base = 65.0
    elif score >= 50:
        base = 50.0
    elif score >= 40:
        base = 35.0
    else:
        base = 20.0

    level = risk_level(risk)
    discount = {"绿色": 1.0, "黄色": 0.8, "橙色": 0.6, "红色": 0.4}[level]
    return base, discount, round(base * discount, 1)


def market_phase(score: float, risk: float) -> str:
    if risk >= 75:
        return "风险压缩"
    if score >= 70 and risk <= 45:
        return "风险偏好扩张"
    if score >= 60 and risk <= 55:
        return "震荡偏强"
    if score < 45:
        return "防御观察"
    return "震荡均衡"


def style_signal(market: pd.DataFrame, as_of: str | None = None) -> tuple[str, float, list[str]]:
    growth_symbols = ["399006.SZ", "000688.SH", "931087.CSI"]
    broad_symbols = ["000300.SH", "000001.SH"]
    growth_values = [momentum(market, symbol, 20, as_of) for symbol in growth_symbols]
    broad_values = [momentum(market, symbol, 20, as_of) for symbol in broad_symbols]
    growth = average(growth_values, default=0.0)
    broad = average(broad_values, default=0.0)
    spread = growth - broad
    if spread >= 3:
        label = "成长科技占优"
    elif spread <= -3:
        label = "大盘价值占优"
    else:
        label = "均衡轮动"
    score = clamp(50 + abs(spread) * 5)
    basis = [
        f"成长/科技20日动量均值 {format_pct(growth)}",
        f"宽基20日动量均值 {format_pct(broad)}",
        f"风格差 {format_pct(spread)}",
    ]
    return label, score, basis


def valuation_percentile(valuation: pd.DataFrame, as_of: str | None = None) -> tuple[float, list[str]]:
    if valuation.empty or "pe_ttm" not in valuation.columns:
        return 50.0, ["估值数据暂缺，按中性处理"]
    current = series_until(valuation, "trade_date", as_of)
    percentiles: list[float] = []
    notes: list[str] = []
    for code, group in current.groupby("index_code"):
        values = pd.to_numeric(group["pe_ttm"], errors="coerce").dropna()
        if values.empty:
            continue
        current_value = float(values.iloc[-1])
        rank = float((values <= current_value).mean() * 100)
        percentiles.append(rank)
        name = str(group.iloc[-1].get("index_name", code))
        notes.append(f"{name} PE历史分位 {rank:.0f}%")
    if not percentiles:
        return 50.0, ["估值数据暂缺，按中性处理"]
    return float(np.mean(percentiles)), notes[:4]


def evaluate(as_of: str | None, data: dict[str, pd.DataFrame]) -> dict[str, Any]:
    macro = data["macro"]
    liquidity = data["liquidity"]
    market = data["market"]
    global_macro = data["global_macro"]
    valuation = data["valuation"]
    crowding = data["crowding"]
    breadth = data["breadth"]
    leverage = data["leverage"]

    latest_breadth = latest_row(breadth, "trade_date", as_of)
    up_count = clean_number(latest_breadth.get("up_count")) if latest_breadth is not None else None
    total_count = clean_number(latest_breadth.get("total_count")) if latest_breadth is not None else None
    up_ratio = up_count / total_count * 100 if up_count is not None and total_count else None
    broad_turnover = clean_number(latest_breadth.get("broad_turnover_pct")) if latest_breadth is not None else None
    amount = clean_number(latest_breadth.get("total_amount_trillion")) if latest_breadth is not None else None

    pmi = latest_value(macro, "pmi_manufacturing", "month", as_of)
    m1_m2_gap = latest_value(macro, "m1_m2_gap_pp", "month", as_of)
    sf_yoy = latest_value(macro, "sf_stock_yoy_pct", "month", as_of)
    cpi = latest_value(macro, "cpi_yoy_pct", "month", as_of)
    dr007 = latest_value(liquidity, "dr007_pct", "trade_date", as_of)
    dr007_rank = pct_rank(series_until(liquidity, "trade_date", as_of).get("dr007_pct", pd.Series(dtype=float)), dr007)
    dr007_delta_5 = delta(liquidity, "dr007_pct", "trade_date", 5, as_of)
    crowd = latest_value(crowding, "crowding_pct", "trade_date", as_of)
    crowd_rank = pct_rank(series_until(crowding, "trade_date", as_of).get("crowding_pct", pd.Series(dtype=float)), crowd)
    margin_ratio = latest_value(leverage, "margin_to_market_cap_pct", "trade_date", as_of)
    margin_rank = pct_rank(series_until(leverage, "trade_date", as_of).get("margin_to_market_cap_pct", pd.Series(dtype=float)), margin_ratio)
    val_rank, val_notes = valuation_percentile(valuation, as_of)

    dgs10 = latest_value(global_macro[global_macro["series"].astype(str) == "DGS10"], "value_pct", "trade_date", as_of)
    dgs10_delta_20 = delta(global_macro[global_macro["series"].astype(str) == "DGS10"], "value_pct", "trade_date", 20, as_of)
    usd_liq = latest_value(global_macro[global_macro["series"].astype(str) == "NET_USD_LIQUIDITY_SOMA"], "value_pct", "trade_date", as_of)
    usd_liq_delta = delta(global_macro[global_macro["series"].astype(str) == "NET_USD_LIQUIDITY_SOMA"], "value_pct", "trade_date", 4, as_of)

    sh_comp_20 = momentum(market, "000001.SH", 20, as_of)
    csi300_20 = momentum(market, "000300.SH", 20, as_of)
    chinext_20 = momentum(market, "399006.SZ", 20, as_of)
    star50_20 = momentum(market, "000688.SH", 20, as_of)
    nasdaq_20 = momentum(market, "^IXIC", 20, as_of)
    ma_gaps = [ma_gap(market, symbol, 20, as_of) for symbol in ["000001.SH", "000300.SH", "399006.SZ", "000688.SH"]]
    index_momentum = average([sh_comp_20, csi300_20, chinext_20, star50_20], default=0.0)
    style, style_score, style_basis = style_signal(market, as_of)

    macro_score = average([
        score_between(pmi, 47, 52),
        score_between(m1_m2_gap, -8, 4),
        score_between(sf_yoy, 7, 12),
    ])
    liquidity_score = average([
        100 - dr007_rank,
        60 if dr007_delta_5 is not None and dr007_delta_5 <= 0 else 42,
        score_between(usd_liq_delta, -0.15, 0.15),
    ])
    policy_score = average([
        58 if dr007_delta_5 is not None and dr007_delta_5 <= 0 else 48,
        score_between(sf_yoy, 7, 12),
        55 if pmi is not None and pmi < 50 else 50,
    ])
    earnings_score = average([
        score_between(pmi, 47, 52),
        score_between(sf_yoy, 7, 12),
        score_between(index_momentum, -8, 8),
    ])
    valuation_score = 100 - val_rank
    sentiment_score = average([
        score_between(up_ratio, 35, 65),
        score_between(index_momentum, -8, 8),
        inverse_score_between(abs((crowd or 40) - 42), 0, 22),
    ])

    market_modules = [
        {
            "name": "宏观周期",
            "weight": 15,
            "score": round(macro_score, 1),
            "status": status_label(macro_score),
            "basis": [f"制造业PMI {format_num(pmi)}", f"M1-M2剪刀差 {format_num(m1_m2_gap)}个百分点", f"社融存量同比 {format_pct(sf_yoy)}"],
        },
        {
            "name": "流动性环境",
            "weight": 20,
            "score": round(liquidity_score, 1),
            "status": status_label(liquidity_score),
            "basis": [f"DR007 {format_pct(dr007)}，历史分位 {dr007_rank:.0f}%", f"DR007近5期变化 {format_num(dr007_delta_5)}个百分点", f"美元净流动性近4期变化 {format_num(usd_liq_delta)}万亿美元"],
        },
        {
            "name": "政策环境",
            "weight": 15,
            "score": round(policy_score, 1),
            "status": status_label(policy_score),
            "basis": ["公开高频政策指标暂未接入，当前用流动性、信用扩张和经济动能做代理", f"社融存量同比 {format_pct(sf_yoy)}", f"DR007近5期变化 {format_num(dr007_delta_5)}个百分点"],
        },
        {
            "name": "盈利周期",
            "weight": 15,
            "score": round(earnings_score, 1),
            "status": status_label(earnings_score),
            "basis": [f"制造业PMI {format_num(pmi)}", f"社融存量同比 {format_pct(sf_yoy)}", f"主要A股指数20日动量均值 {format_pct(index_momentum)}"],
        },
        {
            "name": "估值水平",
            "weight": 15,
            "score": round(valuation_score, 1),
            "status": status_label(valuation_score),
            "basis": [f"指数PE历史分位均值 {val_rank:.0f}%", *val_notes[:3]],
        },
        {
            "name": "市场情绪",
            "weight": 10,
            "score": round(sentiment_score, 1),
            "status": status_label(sentiment_score),
            "basis": [f"上涨家数占比 {format_pct(up_ratio)}", f"A股成交额/总市值 {format_pct(broad_turnover)}", f"交易拥挤度 {format_pct(crowd)}"],
        },
        {
            "name": "风格结构",
            "weight": 10,
            "score": round(style_score, 1),
            "status": status_label(style_score),
            "basis": style_basis,
        },
    ]

    market_score = sum(item["score"] * item["weight"] for item in market_modules) / 100

    breadth_health = average([score_between(up_ratio, 35, 65), score_between(delta(breadth, "up_count", "trade_date", 5, as_of), -800, 800)])
    ma_health = average([score_between(value, -6, 6) for value in ma_gaps])
    price_quality_health = average([ma_health, score_between(index_momentum, -8, 8), score_between(delta(breadth, "total_amount_trillion", "trade_date", 5, as_of), -0.5, 0.5)])
    mainline_health = average([score_between(chinext_20, -10, 10), score_between(star50_20, -10, 10), inverse_score_between(abs((crowd or 42) - 42), 0, 25)])
    leverage_risk = average([crowd_rank, margin_rank])
    external_pressure = average([
        score_between(dgs10, 3.3, 5.0),
        score_between(dgs10_delta_20, -0.25, 0.25),
        inverse_score_between(nasdaq_20, -8, 8),
        inverse_score_between(usd_liq_delta, -0.15, 0.15),
    ])
    val_earnings_risk = average([val_rank, 100 - earnings_score if val_rank >= 65 else 45])
    policy_dull_risk = average([55 if policy_score < 50 else 40, 60 if pmi is not None and pmi < 50 and index_momentum < 0 else 40])

    risk_items = [
        {
            "name": "市场广度恶化",
            "weight": 20,
            "risk": round(100 - breadth_health, 1),
            "level": risk_label(100 - breadth_health),
            "basis": [f"上涨家数占比 {format_pct(up_ratio)}", f"近5期上涨家数变化 {format_num(delta(breadth, 'up_count', 'trade_date', 5, as_of), 0)}只"],
        },
        {
            "name": "量价质量恶化",
            "weight": 20,
            "risk": round(100 - price_quality_health, 1),
            "level": risk_label(100 - price_quality_health),
            "basis": [f"主要指数20日动量均值 {format_pct(index_momentum)}", f"主要指数相对20日均线均值 {format_pct(average(ma_gaps, default=0.0))}", f"成交额近5期变化 {format_num(delta(breadth, 'total_amount_trillion', 'trade_date', 5, as_of))}万亿元"],
        },
        {
            "name": "主线健康度",
            "weight": 20,
            "risk": round(100 - mainline_health, 1),
            "level": risk_label(100 - mainline_health),
            "basis": [f"创业板20日动量 {format_pct(chinext_20)}", f"科创50 20日动量 {format_pct(star50_20)}", f"交易拥挤度 {format_pct(crowd)}"],
        },
        {
            "name": "杠杆资金拥挤",
            "weight": 15,
            "risk": round(leverage_risk, 1),
            "level": risk_label(leverage_risk),
            "basis": [f"两融/总市值 {format_pct(margin_ratio)}，历史分位 {margin_rank:.0f}%", f"交易拥挤度历史分位 {crowd_rank:.0f}%"],
        },
        {
            "name": "外部资产压力",
            "weight": 10,
            "risk": round(external_pressure, 1),
            "level": risk_label(external_pressure),
            "basis": [f"美国10年期国债 {format_pct(dgs10)}", f"纳斯达克20日动量 {format_pct(nasdaq_20)}", f"美元净流动性 {format_num(usd_liq)}万亿美元"],
        },
        {
            "name": "估值盈利背离",
            "weight": 10,
            "risk": round(val_earnings_risk, 1),
            "level": risk_label(val_earnings_risk),
            "basis": [f"指数PE历史分位均值 {val_rank:.0f}%", f"盈利周期分数 {earnings_score:.1f}"],
        },
        {
            "name": "政策反应钝化",
            "weight": 5,
            "risk": round(policy_dull_risk, 1),
            "level": risk_label(policy_dull_risk),
            "basis": ["当前尚未接入政策文本事件库，先用政策代理指标与市场反应判断", f"政策环境分数 {policy_score:.1f}"],
        },
    ]
    risk_score = sum(item["risk"] * item["weight"] for item in risk_items) / 100
    base_position, discount, actual_position = suggested_position(market_score, risk_score)
    latest_dates = [
        str(value)
        for value in [
            latest_breadth.get("trade_date") if latest_breadth is not None else None,
            latest_row(market, "trade_date", as_of).get("trade_date") if latest_row(market, "trade_date", as_of) is not None else None,
            latest_row(liquidity, "trade_date", as_of).get("trade_date") if latest_row(liquidity, "trade_date", as_of) is not None else None,
        ]
        if value is not None and str(value) != "nan"
    ]
    latest_date = max(latest_dates) if latest_dates else as_of

    return {
        "trade_date": latest_date,
        "summary": {
            "market_score": round(market_score, 1),
            "risk_score": round(risk_score, 1),
            "risk_level": risk_level(risk_score),
            "market_phase": market_phase(market_score, risk_score),
            "base_position_pct": round(base_position, 1),
            "risk_discount": round(discount, 2),
            "suggested_position_pct": actual_position,
            "style_signal": style,
            "style_reason": "；".join(style_basis),
            "formula": "实际仓位 = 大盘建议仓位 × 风险折扣",
        },
        "modules": market_modules,
        "risk_modules": risk_items,
        "signals": {
            "up_ratio_pct": round(up_ratio, 2) if up_ratio is not None else None,
            "total_amount_trillion": round(amount, 3) if amount is not None else None,
            "broad_turnover_pct": round(broad_turnover, 3) if broad_turnover is not None else None,
            "crowding_pct": round(crowd, 2) if crowd is not None else None,
            "margin_to_market_cap_pct": round(margin_ratio, 3) if margin_ratio is not None else None,
            "index_momentum_20d_pct": round(index_momentum, 2),
            "dgs10_pct": round(dgs10, 3) if dgs10 is not None else None,
        },
    }


def load_data() -> dict[str, pd.DataFrame]:
    return {
        "macro": read_csv_safe(DATA_DIR / "macro.csv"),
        "liquidity": read_csv_safe(DATA_DIR / "liquidity.csv"),
        "market": read_csv_safe(DATA_DIR / "market.csv"),
        "global_macro": read_csv_safe(DATA_DIR / "global_macro.csv"),
        "valuation": read_csv_safe(DATA_DIR / "valuation.csv"),
        "crowding": read_csv_safe(DATA_DIR / "crowding.csv"),
        "breadth": read_csv_safe(DATA_DIR / "breadth.csv"),
        "leverage": read_csv_safe(DATA_DIR / "leverage.csv"),
    }


def history_dates(data: dict[str, pd.DataFrame], lookback: int = 120) -> list[str]:
    breadth = data["breadth"]
    if not breadth.empty and "trade_date" in breadth.columns:
        dates = breadth["trade_date"].dropna().astype(str).sort_values().unique().tolist()
        return dates[-lookback:]
    market = data["market"]
    if not market.empty and "trade_date" in market.columns:
        dates = market["trade_date"].dropna().astype(str).sort_values().unique().tolist()
        return dates[-lookback:]
    return [datetime.now(BEIJING).strftime("%Y%m%d")]


def update_status(row_count: int, latest_date: str | None) -> None:
    if STATUS_PATH.exists():
        try:
            status = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
        except Exception:
            status = {"overall_status": "partial", "datasets": {}}
    else:
        status = {"overall_status": "partial", "datasets": {}}
    status.setdefault("datasets", {})["market_tracking"] = {
        "status": "success" if row_count else "partial",
        "latest_date": latest_date,
        "rows": row_count,
        "cached_rows": row_count,
        "source": "由宏观、流动性、估值、A股情绪、两融、全球市场公开数据自动评分",
        "note": "每日随网站数据更新自动重算；政策环境当前为代理指标，后续可接政策事件库。",
    }
    status["updated_at"] = datetime.now(BEIJING).isoformat(timespec="seconds")
    write_json(STATUS_PATH, status)


def main() -> None:
    data = load_data()
    dates = history_dates(data)
    latest = evaluate(dates[-1] if dates else None, data)
    history_rows = []
    for trade_date in dates:
        result = evaluate(trade_date, data)
        history_rows.append({
            "trade_date": trade_date,
            "market_score": result["summary"]["market_score"],
            "risk_score": result["summary"]["risk_score"],
            "suggested_position_pct": result["summary"]["suggested_position_pct"],
            "risk_level": result["summary"]["risk_level"],
            "market_phase": result["summary"]["market_phase"],
            "style_signal": result["summary"]["style_signal"],
            "source": "二级市场投研框架自动评分",
        })
    history = pd.DataFrame(history_rows, columns=HISTORY_COLUMNS)
    write_csv_atomic(history, OUTPUT_CSV)
    payload = {
        "updated_at": datetime.now(BEIJING).strftime("%Y-%m-%d %H:%M:%S+08:00"),
        "timezone": "Asia/Shanghai",
        "schedule": ["每日随公开数据刷新", "交易日收盘后重点更新A股情绪与仓位信号"],
        "framework_source": "二级框架.rtf",
        "framework_sections": FRAMEWORK_SECTIONS,
        "process_steps": PROCESS_STEPS,
        "tracking": latest,
        "method_note": "分数为0-100，越高代表大盘环境越友好；风险分数越高代表需要降仓。所有结果仅为投研监测，不构成投资建议。",
    }
    write_json(OUTPUT_JSON, payload)
    update_status(len(history), latest.get("trade_date"))
    print(json.dumps({"latest": latest["summary"], "history_rows": len(history)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
