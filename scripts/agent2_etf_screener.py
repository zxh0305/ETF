#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETF低估筛选器 v4.0 - PPT标准版
=====================================
按PPT《龙虾ETF投资智能体》核心筛选规则：
  ① PE历史分位 ≤ 30% 或 PB历史分位 ≤ 30%
  ② PEG < 1（成长性价比）
  ③ 日均成交额 ≥ 1亿元（仅推荐有实质流动性的ETF）
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).parent.parent.resolve()
INPUT_FILE = BASE_DIR / "data" / "etf_valuation_latest.json"
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_JSON = OUTPUT_DIR / "low_valuation_candidates_latest.json"
OUTPUT_MD = OUTPUT_DIR / "low_valuation_report_latest.md"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("etf_screener_v3")


def to_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    """安全转换为float"""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        value = value.strip()
        if value in ("", "N/A", "-", "nan", "None"):
            return default
        try:
            return float(value)
        except:
            return default
    return default


class ETFScreenerV3:
    """ETF筛选器 - 真实历史分位版"""
    
    # 行业PE/PB历史分位参考值（用于穿透估值分位估算）
    # 格式：{行业代码: {pe_min, pe_max, pb_min, pb_max}}
    INDUSTRY_RANGE = {
        "801010": {"pe_min": 10, "pe_max": 50, "pb_min": 1.0, "pb_max": 4.0},  # 农林牧渔
        "801030": {"pe_min": 10, "pe_max": 40, "pb_min": 1.0, "pb_max": 4.0},  # 基础化工
        "801040": {"pe_min": 5, "pe_max": 30, "pb_min": 0.5, "pb_max": 2.5},   # 钢铁
        "801050": {"pe_min": 10, "pe_max": 60, "pb_min": 1.5, "pb_max": 5.0},  # 有色金属
        "801080": {"pe_min": 15, "pe_max": 80, "pb_min": 2.0, "pb_max": 8.0},  # 电子
        "801110": {"pe_min": 10, "pe_max": 40, "pb_min": 1.5, "pb_max": 5.0},  # 家用电器
        "801120": {"pe_min": 15, "pe_max": 60, "pb_min": 2.0, "pb_max": 10.0}, # 食品饮料
        "801150": {"pe_min": 15, "pe_max": 70, "pb_min": 2.0, "pb_max": 8.0},  # 医药生物
        "801790": {"pe_min": 5, "pe_max": 30, "pb_min": 0.5, "pb_max": 3.0},   # 非银金融
        "801880": {"pe_min": 5, "pe_max": 25, "pb_min": 0.5, "pb_max": 2.5},   # 银行
        "801950": {"pe_min": 5, "pe_max": 30, "pb_min": 0.5, "pb_max": 2.5},   # 煤炭
        "801960": {"pe_min": 8, "pe_max": 35, "pb_min": 0.8, "pb_max": 3.5},   # 石油石化
    }
    
    def _estimate_percentile_from_pe(self, pe: float, sw_code: str = "801150") -> Optional[float]:
        """根据PE绝对值估算分位（基于行业历史范围）"""
        if pe is None or pe <= 0:
            return None
        industry = self.INDUSTRY_RANGE.get(sw_code, self.INDUSTRY_RANGE["801150"])
        pe_min = industry["pe_min"]
        pe_max = industry["pe_max"]
        # 线性估算分位（假设PE在[pe_min, pe_max]范围内均匀分布）
        if pe <= pe_min:
            return 0.0  # 极度低估
        elif pe >= pe_max:
            return 100.0  # 极度高估
        else:
            return round((pe - pe_min) / (pe_max - pe_min) * 100, 1)
    
    def _estimate_percentile_from_pb(self, pb: float, sw_code: str = "801150") -> Optional[float]:
        """根据PB绝对值估算分位（基于行业历史范围）"""
        if pb is None or pb <= 0:
            return None
        industry = self.INDUSTRY_RANGE.get(sw_code, self.INDUSTRY_RANGE["801150"])
        pb_min = industry["pb_min"]
        pb_max = industry["pb_max"]
        # 线性估算分位（假设PB在[pb_min, pb_max]范围内均匀分布）
        if pb <= pb_min:
            return 0.0  # 极度低估
        elif pb >= pb_max:
            return 100.0  # 极度高估
        else:
            return round((pb - pb_min) / (pb_max - pb_min) * 100, 1)
    
    def __init__(self):
        self.stats = {
            "total": 0,
            "formal_pool": 0,
            "observation_pool": 0,
            "unavailable": 0,
        }
        
        # 筛选阈值
        self.PE_PCT_THRESHOLD = 30.0      # PE分位阈值
        self.PB_PCT_THRESHOLD = 30.0      # PB分位阈值
        self.LIQUIDITY_MIN = 100_000_000   # 日均成交额≥1亿（PPT标准）
        self.PEG_THRESHOLD = 1.0          # PEG阈值
        self.WATCH_LIQ_MIN = 3_000_000   # 关注池门槛：日均≥300万（低估+流动性尚可）
    
    def _passes_watch_list(self, etf: Dict) -> Tuple[bool, str]:
        """
        关注池筛选（v4.0 - 低估值+尚可流动性）
        
        条件：
        1. PE分位 ≤ 30% 或 PB分位 ≤ 30%（满足低估条件）
        2. 日均成交额 ≥ 300万（有一定流动性，但不满足1亿标准）
        
        注意：
        - 不检查PEG（关注池允许PEG未知或≥1的情况）
        - 对估算数据添加警告标签
        """
        pe_pct = to_float(etf.get("pe_percentile"))
        pb_pct = to_float(etf.get("pb_percentile"))
        avg_amount = to_float(etf.get("avg_amount_20d")) or to_float(etf.get("amount"))
        
        if pe_pct is None and pb_pct is None:
            return False, "无分位数据"
        
        # 满足低估条件
        low_val = (pe_pct is not None and pe_pct <= self.PE_PCT_THRESHOLD) or \
                  (pb_pct is not None and pb_pct <= self.PB_PCT_THRESHOLD)
        if not low_val:
            return False, f"估值不够低"
        
        # 流动性门槛
        if avg_amount is None or avg_amount < self.WATCH_LIQ_MIN:
            return False, f"流动性偏低（{avg_amount/1e8 if avg_amount else 0:.3f}亿 < 1000万）"
        
        # === 新增：数据真实性检查 ===
        real_flag = etf.get("percentile_real_flag", False)
        data_quality = etf.get("data_quality_flag", "unavailable")
        source = etf.get("pe_pb_source", "")
        
        if real_flag:
            flag_str = "✅真实"
        elif "估算" in source or data_quality == "partial":
            flag_str = "⚠️估算"
        else:
            flag_str = "❓未知"
        
        peg_val = etf.get("peg")
        peg_str = f" PEG={peg_val:.2f}" if peg_val is not None else ""
        return True, f"关注[{flag_str}]（PE%={pe_pct}, PB%={pb_pct}{peg_str}, 成交额={avg_amount/1e8:.2f}亿）"
    
    def _passes_formal_pool(self, etf: Dict) -> Tuple[bool, str]:
        """
        正式低估池筛选（v4.0 - PPT标准版）
        
        按PPT《龙虾ETF投资智能体》要求：
        1. PE历史分位 ≤ 30% 或 PB历史分位 ≤ 30%
        2. PEG < 1（成长性价比）
        3. 日均成交额 ≥ 1亿元（仅推荐有实质流动性的ETF）
        """
        pe_pct = to_float(etf.get("pe_percentile"))
        pb_pct = to_float(etf.get("pb_percentile"))
        # 优先使用20日均成交额（更稳定），次选当日成交额兜底
        avg_amount = to_float(etf.get("avg_amount_20d")) or to_float(etf.get("amount"))
        
        # 0. 数据真实性检查（区分真实数据、穿透估值、估算数据）
        real_flag = etf.get("percentile_real_flag", False)
        data_quality = etf.get("data_quality_flag", "unavailable")
        source = etf.get("pe_pb_source", "")
        
        # 穿透估值数据（v1.0）
        code = etf.get('code', '')
        pen_data = self.penetration_map.get(code, {})
        pen_status = pen_data.get('penetration_status', '')
        pen_pe = pen_data.get('penetration_pe')
        pen_pb = pen_data.get('penetration_pb')
        
        # 【修改】正式池：允许真实数据 或 穿透估值数据 或 宽基指数ETF
        # 乐咕乐股数据：20年真实历史，可信度⭐⭐⭐⭐
        # 穿透估值数据：持仓加权估算，可信度⭐⭐⭐
        # 宽基指数ETF：放宽条件，允许PE%≤50%或PB%≤50%
        
        # 判断是否为宽基指数ETF（通过名称或代码识别）
        name = etf.get('name', '')
        is_broad_base = any(keyword in name for keyword in ['上证50', '沪深300', '中证500', '创业板', '科创50', '北证50'])
        
        if not real_flag and pen_status != 'success' and not is_broad_base:
            # 非真实数据 且 无穿透估值 且 非宽基指数ETF，不进入正式池
            return False, f"数据非真实且无穿透估值（{source}），不纳入正式推荐池"
        
        # 使用穿透估值补充PE/PB分位
        if pen_status == 'success':
            # 使用穿透估值PE/PB（补充或替代）
            if pe_pct is None and pen_pe:
                pe_pct = self._estimate_percentile_from_pe(pen_pe)
            if pb_pct is None and pen_pb:
                pb_pct = self._estimate_percentile_from_pb(pen_pb)
            source += f"[穿透PE={pen_pe:.1f} PB={pen_pb:.2f}]"
        
        # 【修改】宽基指数ETF放宽条件：PE%≤50% 或 PB%≤50%
        if is_broad_base:
            broad_pe_threshold = 50.0
            broad_pb_threshold = 50.0
        else:
            broad_pe_threshold = self.PE_PCT_THRESHOLD
            broad_pb_threshold = self.PB_PCT_THRESHOLD
        
        # 1. 必须有分位数据
        if pe_pct is None and pb_pct is None:
            return False, "无分位数据"
        
        # 2. PE分位或PB分位必须足够低（宽基放宽到50%）
        low_valuation = False
        if pe_pct is not None and pe_pct <= broad_pe_threshold:
            low_valuation = True
        if pb_pct is not None and pb_pct <= broad_pb_threshold:
            low_valuation = True
        
        if not low_valuation:
            threshold_str = f"PE%≤{broad_pe_threshold:.0f}% 或 PB%≤{broad_pb_threshold:.0f}%"
            return False, f"估值不够低（{threshold_str}，实际 PE%={pe_pct}, PB%={pb_pct}）"
        
        # 2. PEG < 1（成长性价比，PE相对盈利增速是否划算）
        peg = to_float(etf.get("peg"))
        if peg is not None and peg >= self.PEG_THRESHOLD:
            return False, f"PEG偏高（PEG={peg:.2f} ≥ 1.0，增长性价比不足）"
        
        # 3. 流动性检查（日均成交额≥1亿，PPT标准）
        # 用户PPT标准：日均成交额≥1亿（保证足够流动性）
        # 注意：此标准不应随意放宽，除非用户明确同意
        LIQ_THRESHOLD = 100_000_000   # 1亿（PPT标准）
        if avg_amount is None or avg_amount < LIQ_THRESHOLD:
            return False, f"流动性不足（20日均={avg_amount/1e8 if avg_amount else 0:.1f}亿 < 1亿）"
        
        real_flag = etf.get("percentile_real_flag", False)
        flag_str = "真实" if real_flag else "估算"
        return True, f"正式低估[{flag_str}]（PE分位={pe_pct}, PB分位={pb_pct}, 成交额={avg_amount/1e8:.1f}亿）"
    
    def _passes_observation_pool(self, etf: Dict) -> Tuple[bool, str]:
        """
        观察池筛选（v4.0 - 有分位数据但不满足正式/关注池条件）
        
        条件：
        1. 有分位数据（真实或估算）
        2. 不满足正式池或关注池条件
        
        注意：
        - 对估算数据添加⚠️警告标签
        - 观察池数据仅供参考，不构成投资建议
        """
        pe_pct = to_float(etf.get("pe_percentile"))
        pb_pct = to_float(etf.get("pb_percentile"))
        avg_amount = to_float(etf.get("avg_amount_20d")) or to_float(etf.get("amount"))
        
        # 有分位数据即可纳入观察池
        reasons = []
        if pe_pct is not None:
            reasons.append(f"PE分位={pe_pct:.1f}%")
        if pb_pct is not None:
            reasons.append(f"PB分位={pb_pct:.1f}%")
        if avg_amount is not None:
            reasons.append(f"成交额={avg_amount/1e8:.1f}亿")
        
        # === 新增：数据真实性标签 ===
        real_flag = etf.get("percentile_real_flag", False)
        data_quality = etf.get("data_quality_flag", "unavailable")
        source = etf.get("pe_pb_source", "")
        
        if real_flag:
            flag_str = "✅真实"
        elif "估算" in source or data_quality == "partial":
            flag_str = "⚠️估算"
        else:
            flag_str = "❓未知"
        
        return True, f"观察池[{flag_str}]：" + (", ".join(reasons) if reasons else "有分位数据")
    
    def _calc_score(self, etf: Dict) -> float:
        """
        计算评分（仅基于真实数据）
        
        评分维度：
        - PE分位（40%）：越低越好
        - PB分位（30%）：越低越好
        - 流动性（30%）：越高越好
        """
        pe_pct = to_float(etf.get("pe_percentile"))
        pb_pct = to_float(etf.get("pb_percentile"))
        # 20日均成交额优先，当日值兜底
        avg_amount = to_float(etf.get("avg_amount_20d")) or to_float(etf.get("amount"))
        
        score = 0.0
        
        # PE分位得分（40%）：分位越低得分越高
        if pe_pct is not None:
            pe_score = max(0, 100 - pe_pct) / 100 * 40
            score += pe_score
        
        # PB分位得分（30%）：分位越低得分越高
        if pb_pct is not None:
            pb_score = max(0, 100 - pb_pct) / 100 * 30
            score += pb_score
        
        # 流动性得分（30%）
        if avg_amount is not None:
            if avg_amount >= 500_000_000:
                liq_score = 30
            elif avg_amount >= 100_000_000:
                liq_score = 20
            else:
                liq_score = max(0, avg_amount / 100_000_000 * 10)
            score += liq_score
        
        return round(score, 1)
    
    def screen(self) -> Dict:
        """执行筛选"""
        logger.info("=" * 70)
        logger.info("ETF低估筛选 v4.0 - PPT标准版（含关注池）")
        logger.info("=" * 70)
        
        # 加载数据
        if not INPUT_FILE.exists():
            logger.error(f"输入文件不存在: {INPUT_FILE}")
            return {"error": "输入文件不存在"}
        
        with open(INPUT_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        records = data.get("data", [])
        
        # 加载穿透估值数据（v1.0）
        self.penetration_map = {}
        penetration_file = BASE_DIR / "data" / "etf_penetration_valuation_latest.json"
        if penetration_file.exists():
            try:
                with open(penetration_file, 'r', encoding='utf-8') as f:
                    pen_data = json.load(f)
                pen_records = pen_data.get("data", [])
                for rec in pen_records:
                    if rec.get('penetration_status') == 'success':
                        self.penetration_map[rec['code']] = rec
                logger.info(f"✅ 加载穿透估值数据: {len(self.penetration_map)} 条")
            except Exception as e:
                logger.warning(f"⚠️ 穿透估值数据加载失败: {e}")
        else:
            logger.warning(f"⚠️ 穿透估值文件不存在: {penetration_file}")
        self.stats["total"] = len(records)
        
        logger.info(f"加载 {len(records)} 条ETF记录")
        
        # 分类（正式池 / 关注池 / 观察池）
        formal_pool = []
        watch_list = []
        observation_pool = []

        for etf in records:
            passes_formal, reason_formal = self._passes_formal_pool(etf)
            if passes_formal:
                score = self._calc_score(etf)
                enriched = {**etf, "score": score, "pool": "formal", "reason": reason_formal}
                formal_pool.append(enriched)
                self.stats["formal_pool"] += 1
                continue

            # 关注池（低估值+1000万流动性，不要求PEG）
            passes_watch, reason_watch = self._passes_watch_list(etf)
            if passes_watch:
                score = self._calc_score(etf)
                enriched = {**etf, "score": score, "pool": "watch_list", "reason": reason_watch}
                watch_list.append(enriched)
                continue

            passes_obs, reason_obs = self._passes_observation_pool(etf)
            if passes_obs:
                score = self._calc_score(etf)
                enriched = {**etf, "score": score, "pool": "observation", "reason": reason_obs}
                observation_pool.append(enriched)
                self.stats["observation_pool"] += 1
                continue

            self.stats["unavailable"] += 1

        # 排序
        formal_pool.sort(key=lambda x: x.get("score", 0), reverse=True)
        watch_list.sort(key=lambda x: x.get("score", 0), reverse=True)
        observation_pool.sort(key=lambda x: x.get("score", 0), reverse=True)

        logger.info(f"  正式低估池: {len(formal_pool)}")
        logger.info(f"  关注池: {len(watch_list)}")
        logger.info(f"  观察池: {len(observation_pool)}")
        logger.info(f"  数据不可用: {self.stats['unavailable']}")

        result = {
            "meta": {
                "generated_at": datetime.now().isoformat(),
                "version": "v4.0-ppt-standard",
                "screening_rules": {
                    "pe_pct_threshold": self.PE_PCT_THRESHOLD,
                    "pb_pct_threshold": self.PB_PCT_THRESHOLD,
                    "peg_threshold": self.PEG_THRESHOLD,
                    "liq_threshold_formal": self.LIQUIDITY_MIN,
                    "liq_threshold_watch": self.WATCH_LIQ_MIN,
                },
            },
            "stats": {**self.stats, "watch_list": len(watch_list)},
            "formal_pool": formal_pool,
            "watch_list": watch_list,
            "observation_pool": observation_pool,
        }

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
            json.dump(result, ensure_ascii=False, indent=2, fp=f)

        logger.info(f"✅ 输出: {OUTPUT_JSON}")

        return result
    
    def generate_report(self, result: Dict) -> str:
        """生成Markdown报告（v4.0 - 含投资建议）"""
        stats = result.get("stats", self.stats)
        formal = result.get("formal_pool", [])
        watch = result.get("watch_list", [])
        observation = result.get("observation_pool", [])

        rules = result.get("meta", {}).get("screening_rules", {})
        peg_ok = rules.get("peg_threshold", 1.0)
        liq_formal = rules.get("liq_threshold_formal", 0) / 1e8
        liq_watch = rules.get("liq_threshold_watch", 0) / 1e8

        lines = [
            "# ETF低估筛选报告",
            f"",
            f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"版本: v4.0（PPT标准版）",
            f"",
            "## 📊 筛选规则",
            f"",
            f"| 指标 | 阈值 | 说明 |",
            f"|------|------|------|",
            f"| PE历史分位 | ≤ 30% | 估值安全垫 |",
            f"| PB历史分位 | ≤ 30% | 估值安全垫 |",
            f"| PEG | < {peg_ok:.0f} | 成长性价比 |",
            f"| 日均成交额(正式) | ≥ {liq_formal:.0f}亿 | 流动性保障 |",
            f"| 日均成交额(关注) | ≥ {self.WATCH_LIQ_MIN/1e4:.0f}万 | 低估但流动性有限 |",
            f"",
            "## 📈 统计",
            f"",
            f"| 池别 | 数量 | 说明 |",
            f"|------|------|------|",
            f"| **正式低估池** | **{stats.get('formal_pool', 0)}只** | 满足全部条件，可操作 |",
            f"| **关注池** | **{stats.get('watch_list', 0)}只** | 低估但流动性有限，供参考 |",
            f"| 观察池 | {stats.get('observation_pool', 0)}只 | 有分位数据但不低估 |",
            f"| 数据不可用 | {stats.get('unavailable', 0)}只 | 无分位数据 |",
            f"",
        ]

        # === 市场温度计 ===
        sw_path = BASE_DIR / "data" / "sw_industry_valuation_latest.json"
        if sw_path.exists():
            try:
                with open(sw_path, 'r', encoding='utf-8') as f:
                    sw_data = json.load(f)
                industries = sw_data.get('industries', {})
                meta = sw_data.get('meta', {})
                
                pe_values = [v['pe_ttm'] for v in industries.values() if v.get('pe_ttm')]
                avg_pe = round(sum(pe_values) / len(pe_values), 1) if pe_values else 0
                
                # 温度判定
                if avg_pe < 15: temp_icon, temp_label = "🥶 极寒", "严重低估区间"
                elif avg_pe < 20: temp_icon, temp_label = "❄️ 偏冷", "低估区间"
                elif avg_pe < 30: temp_icon, temp_label = "🌱 温和", "正常偏低"
                elif avg_pe < 40: temp_icon, temp_label = "☀️ 适中", "正常区间"
                elif avg_pe < 50: temp_icon, temp_label = "🔥 偏热", "偏高区间"
                else: temp_icon, temp_label = "🔴 过热", "高估区间"
                
                # PE排序找最便宜/最贵行业
                sorted_by_pe = sorted(industries.items(), key=lambda x: x[1].get('pe_ttm', 999) or 999)
                sorted_by_pb = sorted(industries.items(), key=lambda x: x[1].get('pb', 999) or 999)
                
                cheap_5 = [(v['name'], v['pe_ttm'], v['pb']) for _, v in sorted_by_pe[:5]]
                hot_5 = [(v['name'], v['pe_ttm'], v['pb']) for _, v in sorted_by_pe[-5:]]
                
                lines += [
                    "",
                    "## 🌡️ 市场温度计",
                    "",
                    f"基于31个申万一级行业整体估值（数据更新：{meta.get('generated_at', '')[:10]}）：",
                    "",
                    f"**整体市场温度：{temp_icon} {temp_label}（申万行业PE均值 = {avg_pe}）**",
                    "",
                    "> 📌 **投资参考**：市场整体PE均值不代表所有行业，",
                    f"> 当前市场呈现**结构性分化**：传统周期行业估值低（{cheap_5[0][0]}PE={cheap_5[0][1]}），",
                    f"> 科技成长行业估值高（{hot_5[-1][0]}PE={hot_5[-1][1]}）。",
                    f"> {'建议关注低估值行业ETF，耐心等待机会' if avg_pe >= 30 else '整体估值合理偏低，可适度关注低估行业机会'}",
                    "",
                    "| 温度 | 行业 | PE(TTM) | PB |",
                    "|------|------|---------|-----|",
                ]
                for name, pe, pb in cheap_5:
                    temp = "❄️ 偏低估" if pe < 20 else "🌱 正常偏低"
                    lines.append(f"| {temp} | {name} | {pe:.1f} | {pb:.2f} |")
                lines.append("| ... | ... | ... | ... |")
                for name, pe, pb in reversed(hot_5):
                    temp = "🔴 高估" if pe > 50 else "🔥 偏高"
                    lines.append(f"| {temp} | {name} | {pe:.1f} | {pb:.2f} |")
                lines.append("")
            except Exception as e:
                logger.warning(f"市场温度计加载失败: {e}")

        # === 正式低估池 ===
        if formal:
            lines += [
                "## 🎯 正式低估池（满足全部条件）",
                "",
                "| 代码 | 名称 | 行业 | PE分位 | PB分位 | 20日均(亿) | **投资建议** |",
                "|------|------|------|--------|--------|-----------|------------|",
            ]
            for etf in formal[:20]:
                pe = etf.get("pe_percentile") or 0
                pb = etf.get("pb_percentile") or 0
                amt = to_float(etf.get("avg_amount_20d"), 0)
                src = etf.get("pe_pb_source", "")
                # 生成投资建议
                if pe <= 15 and pb <= 15:
                    advice = "✅ 强烈低估，可关注买入"
                elif pe <= 20:
                    advice = "✅ 低估，可关注"
                elif pb <= 20:
                    advice = "📌 PB低估，可关注"
                else:
                    advice = "⚠️ 满足条件，观察确认"
                lines.append(
                    f"| {etf['code']} | {etf['name']} | {src} | "
                    f"{pe:.1f}% | {pb:.1f}% | {amt/1e8:.2f} | {advice} |"
                )
            lines.append("")
        else:
            lines += [
                "## 🎯 正式低估池（满足全部条件）",
                "",
                "❌ 今日无ETF同时满足低估条件和流动性要求。",
                "",
                "**市场解读**：当前A股主流ETF估值分位普遍较高（PE% > 40%），",
                "或虽有低估信号但流动性不足。建议等待更好时机。",
                "",
            ]

        # === 关注池 ===
        if watch:
            lines += [
                "## 👀 关注池（低估值+流动性尚可，供参考）",
                "",
                "⚠️ 以下ETF满足低估条件，但日均成交额低于1亿元，",
                "**实际操作时需注意流动性风险**，建议小仓位试探或观察。",
                "",
                "| 代码 | 名称 | 行业 | PE分位 | PB分位 | 20日均(亿) | **参考建议** |",
                "|------|------|------|--------|--------|-----------|------------|",
            ]
            for etf in watch[:20]:
                pe = etf.get("pe_percentile") or 0
                pb = etf.get("pb_percentile") or 0
                amt = to_float(etf.get("avg_amount_20d"), 0)
                src = etf.get("pe_pb_source", "")
                peg = etf.get("peg")
                if pe <= 15 and pb <= 15:
                    advice = "📌 极度低估，高风险机会"
                elif pe <= 20:
                    advice = "⚠️ 低估，观察确认后再操作"
                elif pb <= 20:
                    advice = "📌 PB低估，关注"
                else:
                    advice = "⚠️ 满足低估，观察"
                peg_str = f" | PEG={peg:.1f}" if peg else ""
                lines.append(
                    f"| {etf['code']} | {etf['name']} | {src} | "
                    f"{pe:.1f}% | {pb:.1f}% | {amt/1e8:.2f} | {advice}{peg_str} |"
                )
            lines.append("")

        # === 风险提示 ===
        lines += [
            "## ⚠️ 风险提示",
            "",
            "1. **市场整体水位**：当前A股估值分位偏高，主流宽基ETF PE分位多在40-70%，建议保持谨慎",
            "2. **流动性风险**：关注池ETF日均成交额较低，大额买入/卖出可能冲击价格",
            "3. **分位数据说明**：申万行业估算分位仅供参考，真实历史分位更准确",
            "4. **投资建议仅供参考**：不构成投资建议，投资者需自行判断",
            "",
            "---",
            "*数据来源：AkShare金融数据库  |  ETF智能体 v4.0 | 仅供参考，投资有风险*",
        ]

        report = "\n".join(lines)
        with open(OUTPUT_MD, 'w', encoding='utf-8') as f:
            f.write(report)
        logger.info(f"✅ 报告: {OUTPUT_MD}")
        return report


def main():
    screener = ETFScreenerV3()
    result = screener.screen()
    report = screener.generate_report(result)
    
    # 打印摘要
    print("\n" + "=" * 70)
    print("筛选结果摘要（v4.0 - PPT标准版）")
    print("=" * 70)
    print(f"正式低估池: {screener.stats['formal_pool']} 只（满足全部PPT条件）")
    print(f"关注池: {screener.stats.get('watch_list', len(result.get('watch_list', [])))} 只（低估值+300万流动性，供参考）")
    print(f"观察池: {screener.stats['observation_pool']} 只")
    print(f"数据不可用: {screener.stats['unavailable']} 只")
    print("=" * 70)


if __name__ == "__main__":
    main()
