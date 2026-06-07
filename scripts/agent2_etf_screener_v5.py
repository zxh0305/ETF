#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETF低估筛选器 v5.0 - 真正跑出候选池
==========================================
核心改进：
1. 利用新增的PEG数据（868只，58.5%覆盖率）
2. 三级候选池：核心池 / 价值池 / 观察池
3. 穿透估值作为主要信号源（79.8%覆盖率）
4. 流动性门槛分层：核心≥1亿 / 价值≥3000万 / 观察≥500万

筛选逻辑（v5.0）：
【核心池】满足以下任一条件：
  A) PE%≤30% + PEG<1 + 日均≥1亿
  B) PB%≤30% + PEG<1 + 日均≥1亿
  C) 穿透PE<15 + 穿透PB<1.5 + PEG<1 + 日均≥1亿

【价值池】满足以下任一条件（流动性要求降低）：
  A) PE%≤50% + PEG<1.2 + 日均≥3000万
  B) PB%≤50% + PEG<1.5 + 日均≥3000万
  C) 穿透PE<20 + 日均≥3000万

【观察池】有估值信号但流动性不足，或PEG未知
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).parent.parent.resolve()
INPUT_FILE = BASE_DIR / "data" / "etf_valuation_latest.json"
PEN_FILE = BASE_DIR / "data" / "etf_penetration_valuation_latest.json"
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_JSON = OUTPUT_DIR / "low_valuation_candidates_v5.json"
OUTPUT_MD = OUTPUT_DIR / "low_valuation_report_v5.md"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("etf_screener_v5")


def to_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        v = value.strip()
        if v in ("", "N/A", "-", "nan", "None", "null"):
            return default
        try:
            return float(v)
        except ValueError:
            return default
    return default


class ETFScreenerV5:
    """
    估值穿透分层引擎 v5

    三级池架构：
    - core_pool: 核心池（高置信度 + 高流动性）
    - value_pool: 价值池（中等置信度 + 中等流动性）
    - watch_pool: 观察池（有信号但流动性不足）
    """

    def __init__(self):
        self.pen_map: Dict[str, Dict] = {}
        self.stats = {
            "total": 0,
            "core_pool": 0,
            "value_pool": 0,
            "watch_pool": 0,
            "unavailable": 0,
            "peg_available": 0,
            "pen_available": 0,
        }
        # 加载穿透估值
        self._load_penetration()

    def _load_penetration(self):
        # 优先从估值文件读取（v2.0优化后数据嵌入）
        if INPUT_FILE.exists():
            try:
                with open(INPUT_FILE, "r", encoding="utf-8") as f:
                    val_data = json.load(f)
                records = val_data.get("data", [])
                count = 0
                for rec in records:
                    code = rec.get("code", "")
                    pen_pe = to_float(rec.get("penetration_pe"))
                    pen_pb = to_float(rec.get("penetration_pb"))
                    # 从估值文件提取穿透数据内嵌
                    if pen_pe or pen_pb:
                        self.pen_map[code] = {
                            "code": code,
                            "penetration_pe": pen_pe,
                            "penetration_pb": pen_pb,
                            "penetration_status": rec.get("penetration_status_v2", "fixed"),
                        }
                        count += 1
                self.stats["pen_available"] = count
                logger.info(f"✅ 从估值文件加载穿透估值: {count} 条")
                return
            except Exception as e:
                logger.warning(f"⚠️ 从估值文件加载穿透失败: {e}")
        # fallback: 旧穿透文件
        if PEN_FILE.exists():
            try:
                with open(PEN_FILE, "r", encoding="utf-8") as f:
                    pen_data = json.load(f)
                records = pen_data.get("data", [])
                for rec in records:
                    code = rec.get("code", "")
                    status = rec.get("penetration_status") or rec.get("penetration_status_v2", "")
                    if status in ("success", "fixed") and code:
                        self.pen_map[code] = rec
                self.stats["pen_available"] = len(self.pen_map)
                logger.info(f"✅ 从旧穿透文件加载: {len(self.pen_map)} 条")
            except Exception as e:
                logger.warning(f"⚠️ 穿透估值加载失败: {e}")

    # ── 信号提取 ──────────────────────────────────────────────

    def _get_pe_pct(self, etf: Dict) -> Optional[float]:
        """获取PE分位（优先真实，其次穿透估算）"""
        pe_pct = to_float(etf.get("pe_percentile"))
        if pe_pct is not None:
            return pe_pct
        # fallback: 穿透估值 → 估算分位
        code = etf.get("code", "")
        pen = self.pen_map.get(code, {})
        pen_pe = to_float(pen.get("penetration_pe"))
        if pen_pe and pen_pe > 0:
            # 简单线性估算：PE<12 → 10%，PE<20 → 30%，PE<30 → 50%
            if pen_pe < 12:
                return 10.0
            elif pen_pe < 20:
                return 30.0
            elif pen_pe < 30:
                return 50.0
            else:
                return 80.0
        return None

    def _get_pb_pct(self, etf: Dict) -> Optional[float]:
        """获取PB分位"""
        pb_pct = to_float(etf.get("pb_percentile"))
        if pb_pct is not None:
            return pb_pct
        code = etf.get("code", "")
        pen = self.pen_map.get(code, {})
        pen_pb = to_float(pen.get("penetration_pb"))
        if pen_pb and pen_pb > 0:
            if pen_pb < 1.0:
                return 5.0
            elif pen_pb < 1.5:
                return 20.0
            elif pen_pb < 2.5:
                return 40.0
            else:
                return 70.0
        return None

    def _get_peg(self, etf: Dict) -> Optional[float]:
        """获取PEG（优先持仓加权，其次SW估算）"""
        peg = to_float(etf.get("peg"))
        if peg is not None and peg > 0:
            return peg
        return None

    def _get_liquidity(self, etf: Dict) -> Optional[float]:
        """获取流动性（优先20日均额）"""
        return to_float(etf.get("avg_amount_20d")) or to_float(etf.get("amount"))

    def _get_pen_pe(self, code: str) -> Optional[float]:
        pen = self.pen_map.get(code, {})
        return to_float(pen.get("penetration_pe"))

    def _get_pen_pb(self, code: str) -> Optional[float]:
        pen = self.pen_map.get(code, {})
        return to_float(pen.get("penetration_pb"))

    # ── 三级池判断 ──────────────────────────────────────────────

    def _passes_core(self, etf: Dict) -> Tuple[bool, str]:
        """
        核心池：高置信度 + 高流动性
        满足以下任一条件：
          A) PE%≤30% + PEG<1 + 日均≥1亿
          B) PB%≤30% + PEG<1 + 日均≥1亿
          C) 穿透PE<15 + 穿透PB<1.5 + PEG<1 + 日均≥1亿
        """
        code = etf.get("code", "")
        name = etf.get("name", "")

        # 跳过不可操作品种
        if any(kw in name for kw in ["货币", "债券", "国债", "企业债", "美元债"]):
            return False, "非权益类ETF"

        pe_pct = self._get_pe_pct(etf)
        pb_pct = self._get_pb_pct(etf)
        peg = self._get_peg(etf)
        liq = self._get_liquidity(etf)

        # 流动性门槛
        if liq is None or liq < 1e8:
            return False, f"流动性不足({liq/1e8:.2f}亿 < 1亿)"

        # 条件A：PE低估 + PEG合理
        cond_a = (pe_pct is not None and pe_pct <= 30 and
                   peg is not None and peg < 1.0)

        # 条件B：PB低估 + PEG合理
        cond_b = (pb_pct is not None and pb_pct <= 30 and
                   peg is not None and peg < 1.0)

        # 条件C：穿透估值低估 + PEG合理
        pen_pe = self._get_pen_pe(code)
        pen_pb = self._get_pen_pb(code)
        cond_c = (pen_pe is not None and pen_pe < 15 and
                   pen_pb is not None and pen_pb < 1.5 and
                   peg is not None and peg < 1.0)

        if cond_a or cond_b or cond_c:
            reasons = []
            if cond_a:
                reasons.append(f"PE%={pe_pct:.0f}%")
            if cond_b:
                reasons.append(f"PB%={pb_pct:.0f}%")
            if cond_c:
                reasons.append(f"穿透PE={pen_pe:.1f}")
            reasons.append(f"PEG={peg:.2f}" if peg else "PEG=无")
            reasons.append(f"日均={liq/1e8:.2f}亿")
            return True, "核心池[" + " | ".join(reasons) + "]"

        return False, f"未满足核心条件(PE%={pe_pct}, PB%={pb_pct}, PEG={peg})"

    def _passes_value(self, etf: Dict) -> Tuple[bool, str]:
        """
        价值池：中等置信度 + 中等流动性
        满足以下任一条件：
          A) PE%≤50% + PEG<1.2 + 日均≥3000万
          B) PB%≤50% + PEG<1.5 + 日均≥3000万
          C) 穿透PE<20 + 日均≥3000万
        """
        code = etf.get("code", "")
        name = etf.get("name", "")

        if any(kw in name for kw in ["货币", "债券", "国债", "企业债", "美元债"]):
            return False, "非权益类ETF"

        pe_pct = self._get_pe_pct(etf)
        pb_pct = self._get_pb_pct(etf)
        peg = self._get_peg(etf)
        liq = self._get_liquidity(etf)

        if liq is None or liq < 3e7:
            return False, f"流动性不足({liq/1e8:.2f}亿 < 0.3亿)"

        # 条件A
        cond_a = (pe_pct is not None and pe_pct <= 50 and
                   peg is not None and peg < 1.2)

        # 条件B
        cond_b = (pb_pct is not None and pb_pct <= 50 and
                   peg is not None and peg < 1.5)

        # 条件C（穿透估值，允许PEG未知）
        pen_pe = self._get_pen_pe(code)
        cond_c = (pen_pe is not None and pen_pe < 20 and liq >= 3e7)

        if cond_a or cond_b or cond_c:
            reasons = []
            if cond_a:
                reasons.append(f"PE%={pe_pct:.0f}%")
            if cond_b:
                reasons.append(f"PB%={pb_pct:.0f}%")
            if cond_c:
                reasons.append(f"穿透PE={pen_pe:.1f}")
            if peg is not None:
                reasons.append(f"PEG={peg:.2f}")
            else:
                reasons.append("PEG=估算")
            reasons.append(f"日均={liq/1e8:.2f}亿")
            return True, "价值池[" + " | ".join(reasons) + "]"

        return False, f"未满足价值条件(PE%={pe_pct}, PB%={pb_pct}, PEG={peg})"

    def _passes_watch(self, etf: Dict) -> Tuple[bool, str]:
        """
        观察池：有估值信号但流动性不足，或PEG未知
        """
        code = etf.get("code", "")
        name = etf.get("name", "")

        if any(kw in name for kw in ["货币", "债券", "国债", "企业债", "美元债"]):
            return False, "非权益类ETF"

        pe_pct = self._get_pe_pct(etf)
        pb_pct = self._get_pb_pct(etf)
        peg = self._get_peg(etf)
        liq = self._get_liquidity(etf)

        # 至少要有估值信号
        has_valuation = ((pe_pct is not None and pe_pct <= 60) or
                         (pb_pct is not None and pb_pct <= 60) or
                         self._get_pen_pe(code) is not None)

        if not has_valuation:
            return False, "无估值信号"

        # 流动性≥500万即可进观察池
        if liq is not None and liq >= 5e6:
            reasons = []
            if pe_pct is not None:
                reasons.append(f"PE%={pe_pct:.0f}%")
            if pb_pct is not None:
                reasons.append(f"PB%={pb_pct:.0f}%")
            if peg is not None:
                reasons.append(f"PEG={peg:.2f}")
            else:
                reasons.append("PEG=无")
            return True, "观察池[" + " | ".join(reasons) + "]"

        return False, f"流动性过低({liq/1e8:.2f}亿)"

    # ── 评分 ──────────────────────────────────────────────

    def _calc_score(self, etf: Dict) -> float:
        """
        综合评分（0-100）：
        - 估值分位（50%）：越低越好
        - PEG（30%）：越低越好（<0.5→满分，<1→80分，<1.5→50分）
        - 流动性（20%）：越高越好
        """
        pe_pct = self._get_pe_pct(etf)
        pb_pct = self._get_pb_pct(etf)
        peg = self._get_peg(etf)
        liq = self._get_liquidity(etf)

        score = 0.0

        # 估值分位得分（50%）
        val_pct = None
        if pe_pct is not None and pb_pct is not None:
            val_pct = min(pe_pct, pb_pct)
        elif pe_pct is not None:
            val_pct = pe_pct
        elif pb_pct is not None:
            val_pct = pb_pct

        if val_pct is not None:
            val_score = max(0, 100 - val_pct) / 100 * 50
            score += val_score

        # PEG得分（30%）
        if peg is not None:
            if peg < 0.5:
                peg_score = 30
            elif peg < 1.0:
                peg_score = 24
            elif peg < 1.5:
                peg_score = 15
            else:
                peg_score = max(0, 30 - (peg - 1.5) * 10)
            score += max(0, peg_score)

        # 流动性得分（20%）
        if liq is not None:
            if liq >= 5e8:        # ≥5亿
                liq_score = 20
            elif liq >= 1e8:      # ≥1亿
                liq_score = 16
            elif liq >= 3e7:      # ≥3000万
                liq_score = 10
            elif liq >= 5e6:      # ≥500万
                liq_score = 5
            else:
                liq_score = 0
            score += liq_score

        return round(score, 1)

    # ── 主流程 ──────────────────────────────────────────────

    def screen(self) -> Dict:
        logger.info("=" * 70)
        logger.info("ETF低估筛选 v5.0 - 三级候选池")
        logger.info("=" * 70)

        if not INPUT_FILE.exists():
            logger.error(f"❌ 输入文件不存在: {INPUT_FILE}")
            return {"error": "输入文件不存在"}

        with open(INPUT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        records = data.get("data", [])
        self.stats["total"] = len(records)

        # PEG统计
        peg_count = sum(1 for e in records if to_float(e.get("peg")) and to_float(e.get("peg")) > 0)
        self.stats["peg_available"] = peg_count

        logger.info(f"加载 {len(records)} 条ETF记录")
        logger.info(f"  PEG可用: {peg_count}/{len(records)} ({peg_count/len(records)*100:.1f}%)")
        logger.info(f"  穿透估值可用: {self.stats['pen_available']}/{len(records)}")

        core_pool = []
        value_pool = []
        watch_pool = []
        unavailable = []

        for etf in records:
            passes_core, reason_core = self._passes_core(etf)
            if passes_core:
                score = self._calc_score(etf)
                core_pool.append({**etf, "score": score, "pool": "core", "reason": reason_core})
                self.stats["core_pool"] += 1
                continue

            passes_value, reason_value = self._passes_value(etf)
            if passes_value:
                score = self._calc_score(etf)
                value_pool.append({**etf, "score": score, "pool": "value", "reason": reason_value})
                self.stats["value_pool"] += 1
                continue

            passes_watch, reason_watch = self._passes_watch(etf)
            if passes_watch:
                score = self._calc_score(etf)
                watch_pool.append({**etf, "score": score, "pool": "watch", "reason": reason_watch})
                self.stats["watch_pool"] += 1
                continue

            self.stats["unavailable"] += 1
            unavailable.append(etf)

        # 按评分排序
        core_pool.sort(key=lambda x: x.get("score", 0), reverse=True)
        value_pool.sort(key=lambda x: x.get("score", 0), reverse=True)
        watch_pool.sort(key=lambda x: x.get("score", 0), reverse=True)

        logger.info("=" * 70)
        logger.info(f"核心池: {len(core_pool)} 只")
        logger.info(f"价值池: {len(value_pool)} 只")
        logger.info(f"观察池: {len(watch_pool)} 只")
        logger.info(f"无信号: {self.stats['unavailable']} 只")
        logger.info("=" * 70)

        result = {
            "meta": {
                "generated_at": datetime.now().isoformat(),
                "version": "v5.0-triple-pool",
                "data_coverage": {
                    "peg": f"{peg_count}/{len(records)}",
                    "penetration": f"{self.stats['pen_available']}/{len(records)}",
                },
                "pool_rules": {
                    "core": "PE%≤30%或PB%≤30% + PEG<1 + 日均≥1亿（或穿透PE<15+PB<1.5+PEG<1）",
                    "value": "PE%≤50%或PB%≤50% + PEG<1.2 + 日均≥3000万（或穿透PE<20）",
                    "watch": "有估值信号 + 日均≥500万（流动性不足或PEG未知）",
                },
            },
            "stats": self.stats,
            "core_pool": core_pool,
            "value_pool": value_pool,
            "watch_pool": watch_pool,
        }

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        logger.info(f"✅ 输出: {OUTPUT_JSON}")
        return result

    def generate_report(self, result: Dict) -> str:
        core = result.get("core_pool", [])
        value = result.get("value_pool", [])
        watch = result.get("watch_pool", [])
        stats = result.get("stats", {})
        meta = result.get("meta", {})

        lines = [
            "# ETF低估候选池报告 v5.0",
            "",
            f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"版本: v5.0（三级候选池）",
            "",
            "## 📊 数据覆盖",
            "",
            f"- PEG数据: {meta.get('data_coverage', {}).get('peg', '?')}",
            f"- 穿透估值: {meta.get('data_coverage', {}).get('penetration', '?')}",
            "",
            "## 📈 候选池统计",
            "",
            f"| 池别 | 数量 | 门槛 |",
            f"|------|------|------|",
            f"| **核心池** | **{len(core)}只** | PE%≤30%或PB%≤30% + PEG<1 + 日均≥1亿 |",
            f"| **价值池** | **{len(value)}只** | PE%≤50%或PB%≤50% + PEG<1.2 + 日均≥3000万 |",
            f"| **观察池** | **{len(watch)}只** | 有估值信号 + 日均≥500万 |",
            f"| 无信号 | {stats.get('unavailable', 0)}只 | 无估值信号 |",
            "",
        ]

        # 核心池
        if core:
            lines += [
                "## 🏆 核心池（高置信度，可重点关注）",
                "",
                "| 排名 | 代码 | 名称 | 评分 | PE% | PB% | PEG | 日均(亿) | 信号 |",
                "|------|------|------|------|------|------|-----|---------|------|",
            ]
            for i, etf in enumerate(core[:20]):
                pe_pct = self._get_pe_pct(etf)
                pb_pct = self._get_pb_pct(etf)
                peg = self._get_peg(etf)
                liq = self._get_liquidity(etf)
                pe_str = f"{pe_pct:.0f}%" if pe_pct is not None else "-"
                pb_str = f"{pb_pct:.0f}%" if pb_pct is not None else "-"
                peg_str = f"{peg:.2f}" if peg is not None else "-"
                liq_str = f"{liq/1e8:.2f}" if liq else "-"
                # 投资建议
                score = etf.get("score", 0)
                if score >= 70:
                    advice = "✅ 强烈推荐"
                elif score >= 55:
                    advice = "✅ 值得关注"
                else:
                    advice = "📌 可观察"
                reason_short = etf.get("reason", "")[:40]
                lines.append(
                    f"| {i+1} | {etf['code']} | {etf['name']} | {score} | "
                    f"{pe_str} | {pb_str} | {peg_str} | {liq_str} | {advice} |"
                )
            lines.append("")
        else:
            lines += [
                "## 🏆 核心池",
                "",
                "❌ 当前无ETF同时满足核心条件，市场整体估值偏高。",
                "",
            ]

        # 价值池
        if value:
            lines += [
                "## 💎 价值池（中等置信度，性价比较好）",
                "",
                "| 排名 | 代码 | 名称 | 评分 | PE% | PB% | PEG | 日均(亿) |",
                "|------|------|------|------|------|------|-----|---------|",
            ]
            for i, etf in enumerate(value[:15]):
                pe_pct = self._get_pe_pct(etf)
                pb_pct = self._get_pb_pct(etf)
                peg = self._get_peg(etf)
                liq = self._get_liquidity(etf)
                pe_str = f"{pe_pct:.0f}%" if pe_pct is not None else "-"
                pb_str = f"{pb_pct:.0f}%" if pb_pct is not None else "-"
                peg_str = f"{peg:.2f}" if peg is not None else "-"
                liq_str = f"{liq/1e8:.2f}" if liq else "-"
                lines.append(
                    f"| {i+1} | {etf['code']} | {etf['name']} | {etf.get('score', 0)} | "
                    f"{pe_str} | {pb_str} | {peg_str} | {liq_str} |"
                )
            lines.append("")

        # 观察池摘要
        if watch:
            lines += [
                "## 📡 观察池（有信号，流动性有限）",
                "",
                f"共 {len(watch)} 只，摘选前10只：",
                "",
                "| 代码 | 名称 | 评分 | PE% | PB% | PEG | 日均(亿) |",
                "|------|------|------|------|------|-----|---------|",
            ]
            for etf in watch[:10]:
                pe_pct = self._get_pe_pct(etf)
                pb_pct = self._get_pb_pct(etf)
                peg = self._get_peg(etf)
                liq = self._get_liquidity(etf)
                pe_str = f"{pe_pct:.0f}%" if pe_pct is not None else "-"
                pb_str = f"{pb_pct:.0f}%" if pb_pct is not None else "-"
                peg_str = f"{peg:.2f}" if peg is not None else "-"
                liq_str = f"{liq/1e8:.2f}" if liq else "-"
                lines.append(
                    f"| {etf['code']} | {etf['name']} | {etf.get('score', 0)} | "
                    f"{pe_str} | {pb_str} | {peg_str} | {liq_str} |"
                )
            lines.append("")

        # 使用说明
        lines += [
            "## 📋 使用说明",
            "",
            "1. **核心池**：高置信度信号，可重点关注。建议结合行业趋势判断入场时机。",
            "2. **价值池**：性价比较好，但流动性一般。建议小仓位试探。",
            "3. **观察池**：有低估信号但流动性不足，适合长期定投或小资金。",
            "4. **PEG说明**：基于持仓加权净利润增速计算，每月更新一次。",
            "5. **穿透估值**：基于持仓加权行业PE/PB，覆盖79.8%的ETF。",
            "",
            "---",
            "*数据来源：AkShare + 乐咕乐股 + 申万行业 | 仅供参考，投资有风险*",
        ]

        report = "\n".join(lines)
        with open(OUTPUT_MD, "w", encoding="utf-8") as f:
            f.write(report)
        logger.info(f"✅ 报告: {OUTPUT_MD}")
        return report


def main():
    screener = ETFScreenerV5()
    result = screener.screen()
    if "error" not in result:
        report = screener.generate_report(result)
        print("\n" + "=" * 70)
        print("筛选结果 v5.0")
        print("=" * 70)
        print(f"核心池: {result['stats']['core_pool']} 只")
        print(f"价值池: {result['stats']['value_pool']} 只")
        print(f"观察池: {result['stats']['watch_pool']} 只")
        print(f"PEG可用: {result['stats']['peg_available']} 只")
        print("=" * 70)


if __name__ == "__main__":
    main()
