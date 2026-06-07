#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETF低估策略回测引擎 v1.0
========================
基于历史快照数据验证"低估买入"策略的表现。

支持策略：
  1. low_valuation: 从正式池选PE%+PB%最低的N只ETF等权买入
  2. top_n: 选PE%最低的N只ETF等权买入

回测指标：累计收益率、最大回撤、夏普比率、胜率、日均收益

使用：
  python3 scripts/backtest_engine.py --start 2026-04-18 --end 2026-05-29 --top 10 --hold 5
"""

import argparse
import json
import logging
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).parent.parent.resolve()
ARCHIVE_DIR = BASE_DIR / "archive"
INDEX_ARCHIVE_DIR = BASE_DIR / "archive" / "index_valuation_history"
OUTPUT_DIR = BASE_DIR / "output"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backtest_v1")


def to_float(val, default=None):
    if val is None:
        return default
    if isinstance(val, (int, float)):
        return float(val) if not math.isnan(val) else default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


class BacktestEngine:
    def __init__(self, start_date: str, end_date: str):
        self.start_date = start_date
        self.end_date = end_date
        self.daily_snapshots: Dict[str, Dict] = {}

    def load_data(self):
        """加载回测区间的所有快照数据"""
        if not ARCHIVE_DIR.exists():
            logger.error(f"归档目录不存在: {ARCHIVE_DIR}")
            return 0

        dates = sorted([
            d.name for d in ARCHIVE_DIR.iterdir()
            if d.is_dir() and self.start_date <= d.name <= self.end_date
            and not d.name.startswith('backup')
            and not d.name.startswith('index')
        ])

        loaded = 0
        for date in dates:
            date_dir = ARCHIVE_DIR / date
            snapshot = {}

            # 加载低估池
            candidates_file = date_dir / "low_valuation_candidates_latest.json"
            if candidates_file.exists():
                try:
                    with open(candidates_file, "r", encoding="utf-8") as f:
                        snapshot["candidates"] = json.load(f)
                except Exception as e:
                    logger.warning(f"  {date} 候选池读取失败: {e}")

            # 加载行情
            spot_file = date_dir / "etf_spot_latest.json"
            if spot_file.exists():
                try:
                    with open(spot_file, "r", encoding="utf-8") as f:
                        snapshot["spot"] = json.load(f)
                except Exception as e:
                    logger.warning(f"  {date} 行情读取失败: {e}")

            if snapshot:
                self.daily_snapshots[date] = snapshot
                loaded += 1

        logger.info(f"加载完成: {loaded}个交易日 ({dates[0] if dates else 'N/A'} ~ {dates[-1] if dates else 'N/A'})")
        return loaded

    def run_strategy(self, strategy_name: str = "low_valuation", top_n: int = 10,
                     hold_days: int = 5) -> Dict:
        """运行回测策略"""
        if strategy_name == "low_valuation":
            return self._strategy_low_valuation(top_n, hold_days)
        elif strategy_name == "top_n":
            return self._strategy_top_n(top_n, hold_days)
        else:
            raise ValueError(f"未知策略: {strategy_name}")

    def _strategy_low_valuation(self, top_n: int, hold_days: int) -> Dict:
        """
        低估策略：从正式池选PE%+PB%最低的top_n只，等权买入，持有hold_days天
        """
        dates = sorted(self.daily_snapshots.keys())
        if not dates:
            return {"error": "无数据"}

        results = {"strategy": "low_valuation", "daily_pnl": [], "trades": [], "top_n": top_n, "hold_days": hold_days}
        portfolio: Dict[str, Dict] = {}  # code -> {entry_price, weight, entry_date}
        cumulative = 1.0
        next_rebalance = 0

        for i, date in enumerate(dates):
            snapshot = self.daily_snapshots[date]
            prices = self._get_prices(snapshot.get("spot", {}))

            if not prices:
                continue

            # 调仓日
            if i >= next_rebalance or not portfolio:
                # 先结算旧组合
                if portfolio:
                    day_return = self._calc_portfolio_return(portfolio, prices)
                    cumulative *= (1 + day_return)
                    results["trades"].append({
                        "date": date,
                        "action": "rebalance",
                        "return": day_return,
                        "cumulative": cumulative,
                    })

                # 选新组合
                candidates = snapshot.get("candidates", {})
                formal_pool = candidates.get("formal_pool", [])

                if formal_pool:
                    # 按PE%+PB%排序（双低优先）
                    sorted_pool = sorted(
                        formal_pool,
                        key=lambda e: (to_float(e.get("pe_percentile"), 100) or 100) +
                                      (to_float(e.get("pb_percentile"), 100) or 100)
                    )
                    selected = sorted_pool[:top_n]
                    
                    portfolio = {}
                    valid_count = 0
                    for etf in selected:
                        code = etf.get("code", "")
                        if code in prices and prices[code] > 0:
                            portfolio[code] = {
                                "entry_price": prices[code],
                                "weight": 1.0 / top_n,
                                "entry_date": date,
                                "pe_pct": to_float(etf.get("pe_percentile")),
                                "pb_pct": to_float(etf.get("pb_percentile")),
                                "name": etf.get("name", ""),
                            }
                            valid_count += 1
                    
                    if valid_count > 0:
                        # 重新归一化权重
                        for code in portfolio:
                            portfolio[code]["weight"] = 1.0 / valid_count

                    next_rebalance = i + hold_days
                else:
                    # 正式池为空，清仓
                    portfolio = {}
                    next_rebalance = i + hold_days

            # 记录当日收益
            if portfolio:
                day_return = self._calc_portfolio_return(portfolio, prices)
                cumulative *= (1 + day_return)
                results["daily_pnl"].append({
                    "date": date,
                    "return": round(day_return, 6),
                    "cumulative": round(cumulative, 6),
                    "positions": len(portfolio),
                })

        return results

    def _strategy_top_n(self, top_n: int, hold_days: int) -> Dict:
        """
        TOP-N策略：选PE%最低的N只ETF，等权买入，定期调仓
        """
        dates = sorted(self.daily_snapshots.keys())
        if not dates:
            return {"error": "无数据"}

        results = {"strategy": "top_n", "daily_pnl": [], "trades": [], "top_n": top_n, "hold_days": hold_days}
        portfolio: Dict[str, Dict] = {}
        cumulative = 1.0
        next_rebalance = 0

        for i, date in enumerate(dates):
            snapshot = self.daily_snapshots[date]
            prices = self._get_prices(snapshot.get("spot", {}))
            if not prices:
                continue

            if i >= next_rebalance or not portfolio:
                if portfolio:
                    day_return = self._calc_portfolio_return(portfolio, prices)
                    cumulative *= (1 + day_return)

                # 从所有ETF中选PE%最低的
                candidates = snapshot.get("candidates", {})
                all_etfs = candidates.get("formal_pool", []) + candidates.get("watch_pool", []) + candidates.get("observe_pool", [])

                if not all_etfs:
                    # 直接从spot中获取
                    spot_data = snapshot.get("spot", {})
                    if isinstance(spot_data, dict):
                        all_etfs = spot_data.get("data", [])

                if all_etfs:
                    sorted_etfs = sorted(
                        all_etfs,
                        key=lambda e: to_float(e.get("pe_percentile"), 100) or 100
                    )
                    selected = sorted_etfs[:top_n]

                    portfolio = {}
                    valid_count = 0
                    for etf in selected:
                        code = etf.get("code", "")
                        if code in prices and prices[code] > 0:
                            portfolio[code] = {
                                "entry_price": prices[code],
                                "weight": 1.0 / top_n,
                                "entry_date": date,
                            }
                            valid_count += 1

                    if valid_count > 0:
                        for code in portfolio:
                            portfolio[code]["weight"] = 1.0 / valid_count

                next_rebalance = i + hold_days

            if portfolio:
                day_return = self._calc_portfolio_return(portfolio, prices)
                cumulative *= (1 + day_return)
                results["daily_pnl"].append({
                    "date": date,
                    "return": round(day_return, 6),
                    "cumulative": round(cumulative, 6),
                    "positions": len(portfolio),
                })

        return results

    def _get_prices(self, spot_data: Any) -> Dict[str, float]:
        """从行情数据提取价格"""
        prices = {}
        if isinstance(spot_data, dict):
            data = spot_data.get("data", [])
        elif isinstance(spot_data, list):
            data = spot_data
        else:
            return prices

        for etf in data:
            if isinstance(etf, dict):
                code = etf.get("code", "")
                price = to_float(etf.get("price")) or to_float(etf.get("收盘")) or to_float(etf.get("current"))
                if code and price and price > 0:
                    prices[code] = price
        return prices

    def _calc_portfolio_return(self, portfolio: Dict, current_prices: Dict[str, float]) -> float:
        """计算组合收益率（相对entry_price）"""
        total_return = 0.0
        for code, info in portfolio.items():
            if code in current_prices:
                entry = info["entry_price"]
                current = current_prices[code]
                if entry > 0:
                    ret = (current - entry) / entry
                    total_return += info["weight"] * ret
        return total_return

    @staticmethod
    def calculate_metrics(daily_pnl: List[Dict]) -> Dict:
        """计算回测指标"""
        if not daily_pnl:
            return {"error": "无交易数据"}

        returns = [d["return"] for d in daily_pnl]
        cumulatives = [d["cumulative"] for d in daily_pnl]

        # 累计收益率
        final_cumulative = cumulatives[-1]
        total_return = (final_cumulative - 1) * 100

        # 最大回撤
        peak = cumulatives[0]
        max_dd = 0
        for c in cumulatives:
            if c > peak:
                peak = c
            dd = (peak - c) / peak
            if dd > max_dd:
                max_dd = dd
        max_drawdown = max_dd * 100

        # 夏普比率（假设无风险利率2%）
        if len(returns) > 1:
            avg_return = sum(returns) / len(returns)
            std_return = (sum((r - avg_return) ** 2 for r in returns) / (len(returns) - 1)) ** 0.5
            risk_free_daily = 0.02 / 252
            sharpe = ((avg_return - risk_free_daily) / std_return * (252 ** 0.5)) if std_return > 0 else 0
        else:
            sharpe = 0

        # 胜率
        win_days = sum(1 for r in returns if r > 0)
        total_days = len(returns)
        win_rate = (win_days / total_days * 100) if total_days > 0 else 0

        # 日均收益
        avg_daily = (sum(returns) / len(returns) * 100) if returns else 0

        # 年化收益
        trading_days = len(returns)
        if trading_days > 0 and final_cumulative > 0:
            annual_return = (final_cumulative ** (252 / trading_days) - 1) * 100
        else:
            annual_return = 0

        return {
            "total_return_pct": round(total_return, 2),
            "annual_return_pct": round(annual_return, 2),
            "max_drawdown_pct": round(max_drawdown, 2),
            "sharpe_ratio": round(sharpe, 2),
            "win_rate_pct": round(win_rate, 1),
            "avg_daily_return_pct": round(avg_daily, 4),
            "trading_days": trading_days,
            "final_cumulative": round(final_cumulative, 4),
        }

    def generate_report(self, results: Dict) -> Dict:
        """生成回测报告"""
        metrics = self.calculate_metrics(results.get("daily_pnl", []))
        
        report = {
            "meta": {
                "strategy": results.get("strategy", "unknown"),
                "period": f"{self.start_date} ~ {self.end_date}",
                "top_n": results.get("top_n"),
                "hold_days": results.get("hold_days"),
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "version": "v1.0",
            },
            "metrics": metrics,
            "daily_pnl_count": len(results.get("daily_pnl", [])),
            "trades_count": len(results.get("trades", [])),
        }

        return report


def main():
    parser = argparse.ArgumentParser(description="ETF低估策略回测")
    parser.add_argument("--start", default="2026-04-18", help="回测开始日期")
    parser.add_argument("--end", default=datetime.now().strftime("%Y-%m-%d"), help="回测结束日期")
    parser.add_argument("--top", type=int, default=10, help="选股数量")
    parser.add_argument("--hold", type=int, default=5, help="持有天数")
    parser.add_argument("--strategy", default="low_valuation", choices=["low_valuation", "top_n"])
    args = parser.parse_args()

    logger.info("=" * 70)
    logger.info(f"ETF低估策略回测 v1.0")
    logger.info(f"  区间: {args.start} ~ {args.end}")
    logger.info(f"  策略: {args.strategy} | TOP={args.top} | 持有={args.hold}天")
    logger.info("=" * 70)

    engine = BacktestEngine(args.start, args.end)
    loaded = engine.load_data()
    if loaded == 0:
        logger.error("无可用数据")
        sys.exit(1)

    # 运行回测
    results = engine.run_strategy(args.strategy, args.top, args.hold)
    report = engine.generate_report(results)

    # 保存报告
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report_file = OUTPUT_DIR / "backtest_report_latest.json"
    
    # 保存完整结果（含daily_pnl）
    full_output = {
        **report,
        "daily_pnl": results.get("daily_pnl", [])[-50:],  # 只保留最近50天
        "trades": results.get("trades", [])[-20:],         # 只保留最近20笔
    }
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(full_output, f, ensure_ascii=False, indent=2)

    # 打印摘要
    metrics = report["metrics"]
    print("\n" + "=" * 70)
    print(f"回测报告 — {args.strategy}")
    print("=" * 70)
    print(f"  区间: {args.start} ~ {args.end}")
    print(f"  交易天数: {metrics.get('trading_days', 0)}")
    print(f"  累计收益率: {metrics.get('total_return_pct', 0):.2f}%")
    print(f"  年化收益率: {metrics.get('annual_return_pct', 0):.2f}%")
    print(f"  最大回撤:   {metrics.get('max_drawdown_pct', 0):.2f}%")
    print(f"  夏普比率:   {metrics.get('sharpe_ratio', 0):.2f}")
    print(f"  胜率:       {metrics.get('win_rate_pct', 0):.1f}%")
    print(f"  日均收益:   {metrics.get('avg_daily_return_pct', 0):.4f}%")
    print("=" * 70)
    print(f"报告已保存: {report_file}")

    return report


if __name__ == "__main__":
    main()
