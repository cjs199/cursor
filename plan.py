"""BTC 阶梯定投 + 分档抄底 购买方案生成器.

读取 data/btc_prices.json (短期 30 分钟级) 和
data/btc_prices_monthly.json (中期日级) 两份 Google Finance
抓下来的价格序列, 输出一个具体的、可执行的分档买入方案.

策略 (illustrative, 非投资建议):
  1. 用月线序列计算 30 日区间百分位, 判断"现价相对估值".
  2. 按现价在区间中的位置 (低/中/高) 分配总预算的核心比例:
        - 处于近月低 25% 分位以下 -> 重仓核心 60% + 阶梯 40%
        - 处于近月中 25%-75% 分位  -> 平衡 40%/60%
        - 处于近月高 25% 分位以上 -> 轻核心 25% + 阶梯 75%
  3. 阶梯抄底单按现价向下打 5 档 (-1%, -2%, -3.5%, -5%, -7%),
     单档金额随跌幅增大递增 (1x / 1.25x / 1.5x / 2x / 2.5x).
  4. 设置一个保护性止盈位 = 月内最高价的 102%, 触发后清掉
     最先建仓的 30% 头寸 (供参考).
  5. 用短期 30m 序列做最终时点提示: 若最近 1h 收益率 < -0.5%,
     建议立即下首张阶梯单; > +0.5% 则等待回踩.

仅用 Python 标准库, 无外部依赖.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import List, Tuple

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DEFAULT_BUDGET_USD = 10_000.0


@dataclass
class Stats:
    current: float
    period_low: float
    period_high: float
    period_mean: float
    pct_in_range: float
    short_high: float
    short_low: float
    last_1h_return_pct: float
    last_24p_return_pct: float


def _load_json(name: str) -> dict:
    with open(os.path.join(DATA_DIR, name), "r", encoding="utf-8") as f:
        return json.load(f)


def load_series() -> Tuple[List[float], List[float]]:
    short = _load_json("btc_prices.json")["prices"]
    monthly = [s["price"] for s in _load_json("btc_prices_monthly.json")["samples"]]
    return short, monthly


def compute_stats(short: List[float], monthly: List[float]) -> Stats:
    current = short[-1]
    lo, hi = min(monthly), max(monthly)
    mean = sum(monthly) / len(monthly)
    pct = 0.0 if hi == lo else (current - lo) / (hi - lo) * 100.0

    last_1h = (short[-1] / short[-3] - 1.0) * 100.0 if len(short) >= 3 else 0.0
    last_24p = (short[-1] / short[-25] - 1.0) * 100.0 if len(short) >= 25 else 0.0

    return Stats(
        current=current,
        period_low=lo,
        period_high=hi,
        period_mean=mean,
        pct_in_range=pct,
        short_high=max(short),
        short_low=min(short),
        last_1h_return_pct=last_1h,
        last_24p_return_pct=last_24p,
    )


def allocation_split(pct_in_range: float) -> Tuple[float, float, str]:
    """返回 (核心仓占比, 阶梯抄底占比, 区间档位描述)."""
    if pct_in_range < 25.0:
        return 0.60, 0.40, "近月低位 (<25%)"
    if pct_in_range < 75.0:
        return 0.40, 0.60, "近月中位 (25%-75%)"
    return 0.25, 0.75, "近月高位 (>75%)"


def ladder_orders(current: float, ladder_budget: float) -> List[dict]:
    drops = [-1.0, -2.0, -3.5, -5.0, -7.0]
    weights = [1.0, 1.25, 1.5, 2.0, 2.5]
    total_w = sum(weights)
    orders = []
    for d, w in zip(drops, weights):
        price = current * (1.0 + d / 100.0)
        amount = ladder_budget * (w / total_w)
        qty = amount / price
        orders.append(
            {
                "trigger_drop_pct": d,
                "limit_price": round(price, 2),
                "alloc_usd": round(amount, 2),
                "alloc_btc": round(qty, 6),
            }
        )
    return orders


def timing_hint(s: Stats) -> str:
    if s.last_1h_return_pct < -0.5:
        return ("最近 1h 已回落 {:+.2f}%, 建议**立即**下首张阶梯单 "
                "(-1% 档已可挂;若已成交则按计划执行下一档).").format(s.last_1h_return_pct)
    if s.last_1h_return_pct > 0.5:
        return ("最近 1h 上涨 {:+.2f}%, 价格仍在反弹.建议**等待回踩**, "
                "先挂限价单不主动追价.").format(s.last_1h_return_pct)
    return ("最近 1h 震荡 ({:+.2f}%), 可按计划下首张限价单, "
            "其余阶梯单全部挂出.").format(s.last_1h_return_pct)


def take_profit(monthly_high: float) -> dict:
    target = monthly_high * 1.02
    return {
        "trigger_price": round(target, 2),
        "action": "在该价位上方挂限价卖单, 卖出最先建仓的 30% 头寸",
        "rationale": "月内高点 +2% 处通常会遇到前高阻力, 部分止盈以锁定收益",
    }


def build_plan(budget: float = DEFAULT_BUDGET_USD) -> dict:
    short, monthly = load_series()
    s = compute_stats(short, monthly)
    core_pct, ladder_pct, regime = allocation_split(s.pct_in_range)

    core_budget = budget * core_pct
    ladder_budget = budget * ladder_pct

    plan = {
        "budget_usd": budget,
        "regime": regime,
        "stats": {
            "current_price": round(s.current, 2),
            "monthly_low": round(s.period_low, 2),
            "monthly_high": round(s.period_high, 2),
            "monthly_mean": round(s.period_mean, 2),
            "position_in_range_pct": round(s.pct_in_range, 1),
            "last_1h_return_pct": round(s.last_1h_return_pct, 2),
            "last_24p_return_pct": round(s.last_24p_return_pct, 2),
        },
        "core_position": {
            "alloc_usd": round(core_budget, 2),
            "execution": "市价/接近市价限价立即建仓 (一次性吃满核心仓)",
            "limit_price": round(s.current * 1.001, 2),
            "alloc_btc": round(core_budget / s.current, 6),
        },
        "ladder_buys": ladder_orders(s.current, ladder_budget),
        "ladder_total_usd": round(ladder_budget, 2),
        "take_profit": take_profit(s.period_high),
        "stop_loss": {
            "trigger_price": round(s.period_low * 0.97, 2),
            "action": "跌破月内低点 -3% 视为趋势破坏, 暂停剩余未触发阶梯单",
        },
        "timing_hint": timing_hint(s),
        "disclaimer": (
            "本方案为基于历史价格序列的算法化输出, 仅作技术演示, 不构成任何投资建议. "
            "加密资产波动剧烈, 请自行评估风险并控制仓位."
        ),
    }
    return plan


def render(plan: dict) -> str:
    lines: List[str] = []
    lines.append("================ BTC 购买方案 ================")
    lines.append(f"总预算: ${plan['budget_usd']:,.2f}    估值区间: {plan['regime']}")
    st = plan["stats"]
    lines.append(
        f"现价: ${st['current_price']:,.2f}   月内: "
        f"${st['monthly_low']:,.2f} ~ ${st['monthly_high']:,.2f} "
        f"(均价 ${st['monthly_mean']:,.2f})"
    )
    lines.append(
        f"现价处于近月区间 {st['position_in_range_pct']}% 位; "
        f"近 1h {st['last_1h_return_pct']:+.2f}%, "
        f"近 ~12h {st['last_24p_return_pct']:+.2f}%"
    )
    lines.append("")
    lines.append("--- 1. 核心仓 (立即建仓) ---")
    c = plan["core_position"]
    lines.append(
        f"  挂限价 ${c['limit_price']:,.2f}  投入 ${c['alloc_usd']:,.2f}  "
        f"≈ {c['alloc_btc']} BTC"
    )
    lines.append("")
    lines.append(
        f"--- 2. 阶梯抄底单 (合计 ${plan['ladder_total_usd']:,.2f}) ---"
    )
    lines.append(f"  {'档位':<8}{'限价':>14}{'金额(USD)':>14}{'数量(BTC)':>14}")
    for o in plan["ladder_buys"]:
        lines.append(
            f"  {o['trigger_drop_pct']:>+5.1f}%  "
            f"  ${o['limit_price']:>11,.2f}"
            f"  ${o['alloc_usd']:>11,.2f}"
            f"  {o['alloc_btc']:>13.6f}"
        )
    lines.append("")
    lines.append("--- 3. 风险控制 ---")
    tp = plan["take_profit"]
    sl = plan["stop_loss"]
    lines.append(f"  止盈触发 ${tp['trigger_price']:,.2f} -> {tp['action']}")
    lines.append(f"  止损触发 ${sl['trigger_price']:,.2f} -> {sl['action']}")
    lines.append("")
    lines.append("--- 4. 时点提示 ---")
    lines.append(f"  {plan['timing_hint']}")
    lines.append("")
    lines.append(plan["disclaimer"])
    lines.append("=" * 46)
    return "\n".join(lines)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="生成 BTC 分档购买方案")
    parser.add_argument(
        "--budget", type=float, default=DEFAULT_BUDGET_USD,
        help="总预算 (美元), 默认 10000"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="输出原始 JSON 而非渲染文本"
    )
    args = parser.parse_args()

    plan = build_plan(args.budget)
    if args.json:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
    else:
        print(render(plan))


if __name__ == "__main__":
    main()
