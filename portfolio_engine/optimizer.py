#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
组合优化器（Portfolio Optimizer）v2.0
======================================
根据估值（PE%、PB%）、行业分散、相关性约束分配仓位。

v2.0 变更：
  - 评分改为非线性分段（越低估越加分，差异更大）
  - 权重分配改为分层（TOP5 10%、TOP6-15 5%、TOP16-25 2%、其余1%）
  - 加入行业分散约束（同行业≤15%，同指数≤20%）
  - 加入相关性约束（高相关对≤30%）
  - 总仓位目标默认80%（之前实际只有30%）

输入：
- etfs: List[ETFData]（带 max_weight）
- correlation_matrix: np.ndarray（可选）
- risk_config: RiskConfig

输出：
- portfolio: List[ETFData]（带 weight）
"""

import sys
import os
import logging
from typing import List, Dict, Any, Optional, Tuple
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

from portfolio_engine.models import ETFData, RiskConfig

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def extract_industry(pe_pb_source: str) -> Optional[str]:
    """从pe_pb_source提取行业/指数名"""
    if not pe_pb_source:
        return None
    if '申万-' in pe_pb_source:
        part = pe_pb_source.split('申万-')[1]
        return part.split('(')[0].strip()
    if '穿透-' in pe_pb_source:
        part = pe_pb_source.split('穿透-')[1]
        return part.split(',')[0].strip()
    if '中证指数官方' in pe_pb_source and '-' in pe_pb_source:
        return pe_pb_source.rsplit('-', 1)[-1].strip()
    return None


class PortfolioOptimizer:
    """投资组合优化器 v2.0"""

    def __init__(self, risk_config: RiskConfig, correlation_matrix: Optional[np.ndarray] = None):
        if risk_config is None:
            raise ValueError("risk_config 不能为 None")
        self.risk_config = risk_config
        self.correlation_matrix = correlation_matrix
        logger.info("PortfolioOptimizer v2.0 初始化完成")

    def optimize(self, etfs: List[ETFData]) -> List[ETFData]:
        """执行组合优化"""
        if not etfs:
            raise ValueError("etfs 列表不能为空")

        logger.info(f"开始组合优化：{len(etfs)} 只 ETF")

        # 1. 过滤有效ETF
        valid_etfs = [e for e in etfs if isinstance(e, ETFData) and e.max_weight is not None]
        if not valid_etfs:
            raise ValueError("没有有效的 ETF 数据")
        logger.info(f"有效 ETF 数量: {len(valid_etfs)}")

        # 2. 计算综合评分（非线性分段）
        for etf in valid_etfs:
            etf.score = self._calculate_score(etf)
        valid_etfs.sort(key=lambda e: e.score, reverse=True)

        logger.info(f"✅ 评分完成，最高分: {valid_etfs[0].code} {valid_etfs[0].name} = {valid_etfs[0].score:.1f}")

        # 3. 分层权重分配
        self._allocate_weights(valid_etfs)
        logger.info(f"✅ 权重分配完成，总仓位: {sum(e.weight or 0 for e in valid_etfs):.2%}")

        # 4. 行业分散约束
        self._apply_industry_cap(valid_etfs)
        logger.info(f"✅ 行业约束完成，总仓位: {sum(e.weight or 0 for e in valid_etfs):.2%}")

        # 5. 相关性约束
        if self.correlation_matrix is not None:
            self._apply_correlation_cap(valid_etfs)
            logger.info(f"✅ 相关性约束完成，总仓位: {sum(e.weight or 0 for e in valid_etfs):.2%}")

        # 6. 最终归一化
        self._normalize_to_target(valid_etfs)
        logger.info(f"✅ 最终归一化完成，总仓位: {sum(e.weight or 0 for e in valid_etfs):.2%}")

        # 过滤掉权重为0的
        result = [e for e in valid_etfs if e.weight and e.weight > 0.001]
        logger.info(f"✅ 组合优化完成: {len(result)} 只 ETF（有效持仓）")
        return result

    def _calculate_score(self, etf: ETFData) -> float:
        """
        非线性分段评分
        
        设计原则：低估ETF得分远高于合理/高估ETF
        """
        score = 0.0

        # PE分位评分（非线性）
        pe = etf.pe_percentile
        if pe is not None:
            if pe <= 5:   score += 45   # 极度低估
            elif pe <= 10: score += 40
            elif pe <= 15: score += 35
            elif pe <= 20: score += 30
            elif pe <= 25: score += 22
            elif pe <= 30: score += 15   # 低估边界
            elif pe <= 40: score += 8
            elif pe <= 50: score += 3    # 中性
            elif pe <= 70: score -= 5
            else:          score -= 15   # 高估
        else:
            score -= 5  # 无PE数据扣分

        # PB分位评分（非线性）
        pb = etf.pb_percentile
        if pb is not None:
            if pb <= 5:   score += 45
            elif pb <= 10: score += 40
            elif pb <= 15: score += 35
            elif pb <= 20: score += 30
            elif pb <= 25: score += 22
            elif pb <= 30: score += 15
            elif pb <= 40: score += 8
            elif pb <= 50: score += 3
            elif pb <= 70: score -= 5
            else:          score -= 15
        else:
            score -= 5

        # 数据质量加分
        if etf.data_quality == "REAL":
            score += 12

        # 极度低估额外奖励（PE+PB都≤15%）
        if pe is not None and pb is not None and pe <= 15 and pb <= 15:
            score += 25

        # 流动性加分
        amt = etf.avg_amount_20d or 0
        if amt >= 5e9:     score += 8    # 50亿+
        elif amt >= 2e9:   score += 6    # 20亿+
        elif amt >= 1e9:   score += 4    # 10亿+
        elif amt >= 5e8:   score += 2    # 5亿+
        elif amt >= 1e8:   score += 1    # 1亿+

        return score

    def _allocate_weights(self, etfs: List[ETFData]):
        """分层权重分配"""
        total_position = self.risk_config.total_position

        # 分层配置：[start_idx, end_idx, single_cap]
        tiers = [
            (0, min(5, len(etfs)),   0.10),   # TOP5: 单只上限10%
            (5, min(15, len(etfs)),  0.05),   # TOP6-15: 单只上限5%
            (15, min(25, len(etfs)), 0.03),   # TOP16-25: 单只上限3%
            (25, len(etfs),          0.01),   # 其余: 单只上限1%
        ]

        # 计算每层预算
        # 策略：每层用满 cap × count，然后按比例缩放到总仓位
        tier_budgets = []
        for start, end, cap in tiers:
            count = max(0, end - start)
            tier_budgets.append(count * cap if count > 0 else 0)
        
        # 按比例缩放到目标总仓位
        raw_total = sum(tier_budgets)
        if raw_total > 0:
            scale_factor = total_position / raw_total
            tier_budgets = [b * scale_factor for b in tier_budgets]

        total_budget = sum(tier_budgets)
        if total_budget <= 0:
            # fallback: 等权
            for etf in etfs:
                etf.weight = total_position / len(etfs)
            return

        # 在每层内按score比例分配
        for i, (start, end, cap) in enumerate(tiers):
            tier = etfs[start:end]
            if not tier:
                continue

            tier_score = sum(e.score for e in tier if e.score and e.score > 0)
            if tier_score <= 0:
                # 层内无正分，等权分配
                for etf in tier:
                    etf.weight = min(tier_budgets[i] / len(tier), cap)
            else:
                for etf in tier:
                    if etf.score and etf.score > 0:
                        etf.weight = min((etf.score / tier_score) * tier_budgets[i], cap)
                    else:
                        etf.weight = 0

    def _apply_industry_cap(self, etfs: List[ETFData]):
        """限制同一行业/指数总仓位，并把节约的仓位重新分配"""
        config = self.risk_config
        industry_cap = getattr(config, 'industry_cap', 0.25)
        index_cap = getattr(config, 'index_cap', 0.30)
        
        # 分类：行业型(申万/穿透) vs 指数型(中证官方等)
        industry_groups: Dict[str, List[ETFData]] = {}
        index_groups: Dict[str, List[ETFData]] = {}
        
        for etf in etfs:
            if not etf.weight or etf.weight <= 0:
                continue
            ind = self._extract_industry(etf.pe_pb_source)
            if not ind:
                continue
            if '申万' in str(etf.pe_pb_source) or '穿透' in str(etf.pe_pb_source):
                industry_groups.setdefault(ind, []).append(etf)
            else:
                index_groups.setdefault(ind, []).append(etf)
        
        freed_weight = 0.0
        capped_industries: List[str] = []  # 记录被约束的行业
        
        # 1. 缩减超限行业/指数
        for ind, members in industry_groups.items():
            total = sum(e.weight or 0 for e in members)
            if total > industry_cap:
                scale = industry_cap / total
                freed = total - industry_cap
                freed_weight += freed
                capped_industries.append(ind)
                logger.info(f"  行业约束: {ind} {total:.2%} > {industry_cap:.0%}，缩至 {industry_cap:.0%}，释放 {freed:.2%}")
                for etf in members:
                    if etf.weight:
                        etf.weight *= scale
        
        for idx, members in index_groups.items():
            total = sum(e.weight or 0 for e in members)
            if total > index_cap:
                scale = index_cap / total
                freed = total - index_cap
                freed_weight += freed
                capped_industries.append(idx)
                logger.info(f"  指数约束: {idx} {total:.2%} > {index_cap:.0%}，缩至 {index_cap:.0%}，释放 {freed:.2%}")
                for etf in members:
                    if etf.weight:
                        etf.weight *= scale
        
        # 2. 重新分配：只分配给未超限的行业
        if freed_weight > 0.001:
            # 找未超限的行业
            uncapped = []
            for ind, members in industry_groups.items():
                if ind in capped_industries:
                    continue
                ind_total = sum(e.weight or 0 for e in members)
                headroom = industry_cap - ind_total
                if headroom > 0.001:
                    uncapped.append((ind, headroom, members))
            for idx, members in index_groups.items():
                if idx in capped_industries:
                    continue
                idx_total = sum(e.weight or 0 for e in members)
                headroom = index_cap - idx_total
                if headroom > 0.001:
                    uncapped.append((idx, headroom, members))
            
            if uncapped:
                # 按剩余空间分配释放的仓位
                total_headroom = sum(h for _, h, _ in uncapped)
                for ind, headroom, members in uncapped:
                    alloc = freed_weight * (headroom / total_headroom)
                    # 在该行业内部按 score 分配
                    score_total = sum(e.score or 0 for e in members if e.score and e.score > 0)
                    if score_total > 0:
                        for etf in members:
                            if etf.score and etf.score > 0:
                                add = alloc * (etf.score / score_total)
                                new_w = (etf.weight or 0) + add
                                cap = etf.max_weight or config.single_etf_cap
                                etf.weight = min(new_w, cap, etf.max_weight or 1.0)
                    else:
                        for etf in members:
                            add = alloc / len(members)
                            new_w = (etf.weight or 0) + add
                            cap = etf.max_weight or config.single_etf_cap
                            etf.weight = min(new_w, cap, etf.max_weight or 1.0)
                logger.info(f"  重新分配 {freed_weight:.2%} 到 {len(uncapped)} 个未超限行业/指数")
            else:
                # 所有行业都满了，按 score 比例分配给所有有 weight 的 ETF（不超单只上限）
                eligible = [e for e in etfs if e.weight and e.weight > 0 and e.score and e.score > 0]
                if eligible:
                    score_total = sum(e.score for e in eligible)
                    for etf in eligible:
                        add = (etf.score / score_total) * freed_weight
                        cap = min(config.single_etf_cap, etf.max_weight or 1.0)
                        etf.weight = min((etf.weight or 0) + add, cap)
                    logger.info(f"  所有行业/指数已达上限，按 score 分配 {freed_weight:.2%}")
    
    def _extract_industry(self, pe_pb_source: str) -> Optional[str]:
        """从pe_pb_source提取行业/指数名称"""
        if not pe_pb_source:
            return None
        if '申万-' in pe_pb_source:
            part = pe_pb_source.split('申万-')[1]
            return part.split('(')[0].strip()
        if '穿透-' in pe_pb_source:
            # 穿透格式: "穿透-电子,石油石化,通信"
            return pe_pb_source.split('-')[1].split(',')[0].strip()
        if '中证指数官方' in pe_pb_source and '-' in pe_pb_source:
            return pe_pb_source.rsplit('-', 1)[-1].strip()
        if 'CNINFO-' in pe_pb_source:
            part = pe_pb_source.split('CNINFO-')[1]
            return part.split('(')[0].strip() if '(' in part else part.strip()
        return None

    def _apply_correlation_cap(self, etfs: List[ETFData]):
        """限制高相关ETF对的合计仓位"""
        if self.correlation_matrix is None:
            return
        
        threshold = self.risk_config.correlation_threshold
        cap = self.risk_config.correlation_cap
        
        # 找出高相关对
        codes = [e.code for e in etfs]
        for i, etf_i in enumerate(etfs):
            for j, etf_j in enumerate(etfs):
                if i >= j:
                    continue
                if not etf_i.weight or not etf_j.weight:
                    continue
                try:
                    idx_i = codes.index(etf_i.code)
                    idx_j = codes.index(etf_j.code)
                    corr = abs(self.correlation_matrix[idx_i, idx_j])
                    if corr > threshold:
                        pair_total = etf_i.weight + etf_j.weight
                        if pair_total > cap:
                            scale = cap / pair_total
                            etf_i.weight *= scale
                            etf_j.weight *= scale
                            logger.info(f"  相关性约束: {etf_i.code}+{etf_j.code} corr={corr:.2f} 缩至{cap:.0%}")
                except (ValueError, IndexError):
                    continue

    def _normalize_to_target(self, etfs: List[ETFData]):
        """归一化到目标总仓位（同时遵守 max_weight 和 single_etf_cap）"""
        current = sum(e.weight or 0 for e in etfs)
        target = self.risk_config.total_position
        cap = self.risk_config.single_etf_cap
        
        if current <= 0:
            return
        
        if abs(current - target) > 0.001:
            scale = target / current
            for etf in etfs:
                if etf.weight:
                    # 同时遵守 single_etf_cap 和 max_weight
                    hard_cap = min(cap, etf.max_weight or 1.0)
                    etf.weight = min(etf.weight * scale, hard_cap)
            
            # 二次检查：如果还超，再缩一次
            current = sum(e.weight or 0 for e in etfs)
            if current > target * 1.01:
                scale = target / current
                for etf in etfs:
                    if etf.weight:
                        hard_cap = min(cap, etf.max_weight or 1.0)
                        etf.weight = min(etf.weight * scale, hard_cap)


def optimize_portfolio(
    etfs: List[ETFData],
    risk_config: RiskConfig,
    correlation_matrix: Optional[np.ndarray] = None
) -> List[ETFData]:
    """快捷函数：执行组合优化"""
    optimizer = PortfolioOptimizer(risk_config, correlation_matrix)
    return optimizer.optimize(etfs)
