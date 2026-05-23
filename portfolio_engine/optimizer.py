# portfolio_engine/optimizer.py
"""
组合优化器（Portfolio Optimizer）

根据估值（PE%、PB%）和风险（相关性）分配仓位。

核心逻辑：
1. 计算综合评分：score = w1 * (1 - PE%) + w2 * (1 - PB%) + w3 * quality_score
2. 按 score 分配仓位（高分多配，低分少配）
3. 限制单 ETF 不超过 max_weight

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
from typing import List, Dict, Any, Optional
import numpy as np

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

from portfolio_engine.models import ETFData, RiskConfig


# ============================================================================
# 配置日志
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# PortfolioOptimizer 类
# ============================================================================

class PortfolioOptimizer:
    """
    投资组合优化器
    
    根据估值和风险分配仓位。
    """
    
    def __init__(
        self, 
        risk_config: RiskConfig, 
        correlation_matrix: Optional[np.ndarray] = None
    ):
        """
        初始化组合优化器
        
        Args:
            risk_config: 风险配置对象
            correlation_matrix: 相关性矩阵（可选）
        
        Raises:
            ValueError: 如果 risk_config 无效
        """
        if risk_config is None:
            error_msg = "risk_config 不能为 None"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        self.risk_config = risk_config
        self.correlation_matrix = correlation_matrix
        
        # 评分权重（可调整）
        self.w1 = 0.40  # PE% 权重
        self.w2 = 0.40  # PB% 权重
        self.w3 = 0.20  # 数据质量权重（REAL=1.0, ESTIMATED=0.5）
        
        logger.info(f"PortfolioOptimizer 初始化完成")
        logger.info(f"  - w1 (PE%): {self.w1}")
        logger.info(f"  - w2 (PB%): {self.w2}")
        logger.info(f"  - w3 (quality): {self.w3}")
    
    def optimize(self, etfs: List[ETFData]) -> List[ETFData]:
        """
        执行组合优化
        
        Args:
            etfs: ETFData 对象列表（带 max_weight）
        
        Returns:
            List[ETFData]: 带 weight 字段的 ETF 列表
        
        Raises:
            ValueError: 如果 etfs 为空或包含无效数据
        """
        # ------------------------------------------------------------------------
        # 1. 输入校验
        # ------------------------------------------------------------------------
        
        if not etfs:
            error_msg = "etfs 列表不能为空"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        logger.info(f"开始组合优化：{len(etfs)} 只 ETF")
        
        # 校验 ETFData 对象
        valid_etfs = []
        for i, etf in enumerate(etfs):
            if not isinstance(etf, ETFData):
                logger.warning(f"[{i+1}] 跳过无效对象: {type(etf)}")
                continue
            
            # 检查 max_weight 是否已设置
            if etf.max_weight is None:
                logger.warning(f"[{i+1}] {etf.code} max_weight 未设置，跳过")
                continue
            
            valid_etfs.append(etf)
        
        if not valid_etfs:
            error_msg = "没有有效的 ETF 数据"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        logger.info(f"有效 ETF 数量: {len(valid_etfs)}")
        
        # ------------------------------------------------------------------------
        # 2. 计算综合评分
        # ------------------------------------------------------------------------
        
        logger.info("正在计算综合评分...")
        
        for etf in valid_etfs:
            etf.score = self._calculate_score(etf)
        
        # 按评分排序（高分在前）
        valid_etfs.sort(key=lambda e: e.score, reverse=True)
        
        logger.info(f"✅ 综合评分计算完成")
        logger.info(f"  最高分: {valid_etfs[0].code} {valid_etfs[0].name} = {valid_etfs[0].score:.4f}")
        
        # ------------------------------------------------------------------------
        # 3. 分配仓位
        # ------------------------------------------------------------------------
        
        logger.info("正在分配仓位...")
        
        # 方法：按评分比例分配，但不超过 max_weight
        total_score = sum([etf.score for etf in valid_etfs])
        
        for etf in valid_etfs:
            # 理论权重 = (score / total_score) * total_position
            theoretical_weight = (etf.score / total_score) * self.risk_config.total_position
            
            # 实际权重 = min(理论权重, max_weight)
            etf.weight = min(theoretical_weight, etf.max_weight)
        
        # 归一化（确保合计 = total_position）
        total_weight = sum([etf.weight for etf in valid_etfs])
        if total_weight > 0:
            scale = self.risk_config.total_position / total_weight
            for etf in valid_etfs:
                etf.weight *= scale
        
        logger.info(f"✅ 仓位分配完成")
        logger.info(f"  总仓位: {sum([etf.weight for etf in valid_etfs]):.2%}")
        
        # ------------------------------------------------------------------------
        # 4. 返回结果
        # ------------------------------------------------------------------------
        
        logger.info(f"✅ 组合优化完成: {len(valid_etfs)} 只 ETF")
        
        return valid_etfs
    
    def _calculate_score(self, etf: ETFData) -> float:
        """
        计算单只 ETF 的综合评分
        
        Args:
            etf: ETFData 对象
        
        Returns:
            float: 综合评分（越高越好）
        
        Note:
            评分公式：score = w1 * (1 - PE%) + w2 * (1 - PB%) + w3 * quality_score
            PE% 和 PB% 需要转换为 0-1 的小数。
        """
        # 初始化评分
        score = 0.0
        
        # PE% 评分（越低越好，所以取 1 - PE%）
        if etf.pe_percentile is not None:
            pe_pct = etf.pe_percentile / 100.0  # 转换为 0-1
            score += self.w1 * (1.0 - pe_pct)
        
        # PB% 评分（越低越好，所以取 1 - PB%）
        if etf.pb_percentile is not None:
            pb_pct = etf.pb_percentile / 100.0  # 转换为 0-1
            score += self.w2 * (1.0 - pb_pct)
        
        # 数据质量评分（REAL=1.0, ESTIMATED=0.5）
        quality_score = 1.0 if etf.data_quality == "REAL" else 0.5
        score += self.w3 * quality_score
        
        # 流动性评分（可选：成交额越高越好）
        if etf.avg_amount_20d is not None:
            # 归一化到 0-0.1（避免主导评分）
            log_amount = np.log10(etf.avg_amount_20d + 1)
            liquidity_score = min(log_amount / 10.0, 0.1)  # 上限 0.1
            score += liquidity_score
        
        return score


# ============================================================================
# 辅助函数（模块级）
# ============================================================================

def optimize_portfolio(
    etfs: List[ETFData], 
    risk_config: RiskConfig, 
    correlation_matrix: Optional[np.ndarray] = None
) -> List[ETFData]:
    """
    快捷函数：执行组合优化
    
    Args:
        etfs: ETF 列表
        risk_config: 风险配置
        correlation_matrix: 相关性矩阵（可选）
    
    Returns:
        List[ETFData]: 带 weight 的 ETF 列表
    
    Example:
        >>> from portfolio_engine.optimizer import optimize_portfolio
        >>> portfolio = optimize_portfolio(etfs, config, matrix)
    """
    optimizer = PortfolioOptimizer(risk_config, correlation_matrix)
    return optimizer.optimize(etfs)


# ============================================================================
# 独立运行测试
# ============================================================================

if __name__ == "__main__":
    """
    独立运行测试
    
    测试内容：
    1. 创建测试数据（模拟 DataQualityFilter 输出）
    2. 创建 RiskConfig（balanced）
    3. 创建 PortfolioOptimizer 对象
    4. 执行 optimize()
    5. 验证权重分配
    6. 测试快捷函数
    7. 错误处理（无效的 ETF 列表）
    """
    
    print("=" * 80)
    print("PortfolioOptimizer 独立测试")
    print("=" * 80)
    print()
    
    # ------------------------------------------------------------------------
    # 测试1: 创建测试数据（模拟 DataQualityFilter 输出）
    # ------------------------------------------------------------------------
    
    print("【测试1】创建测试数据（模拟 DataQualityFilter 输出）")
    print("-" * 80)
    
    from portfolio_engine.models import create_etf_data_from_dict
    
    # 模拟 5 只 ETF（3只 REAL，2只 ESTIMATED）
    test_etfs = [
        {
            "code": "sz159905",
            "name": "红利ETF工银",
            "pe_percentile": 20.0,
            "pb_percentile": 20.0,
            "avg_amount_20d": 80000000.0,
            "percentile_real_flag": True,
            "pe_pb_source": "乐咕乐股",
            "data_quality": "REAL",
            "max_weight": 0.133  # 40% / 3
        },
        {
            "code": "sh510050",
            "name": "华夏上证50ETF",
            "pe_percentile": 66.0,
            "pb_percentile": 70.0,
            "avg_amount_20d": 2000000000.0,
            "percentile_real_flag": True,
            "pe_pb_source": "乐咕乐股",
            "data_quality": "REAL",
            "max_weight": 0.133
        },
        {
            "code": "sh000300",
            "name": "沪深300ETF",
            "pe_percentile": 45.0,
            "pb_percentile": 30.0,
            "avg_amount_20d": 1500000000.0,
            "percentile_real_flag": True,
            "pe_pb_source": "乐咕乐股",
            "data_quality": "REAL",
            "max_weight": 0.133
        },
        {
            "code": "sh512880",
            "name": "证券公司ETF",
            "pe_percentile": 18.0,
            "pb_percentile": 26.0,
            "avg_amount_20d": 3930000000.0,
            "percentile_real_flag": False,
            "pe_pb_source": "估算（申万行业）",
            "data_quality": "ESTIMATED",
            "max_weight": 0.075  # 15% / 2
        },
        {
            "code": "sh512690",
            "name": "酒ETF",
            "pe_percentile": 25.0,
            "pb_percentile": 30.0,
            "avg_amount_20d": 1500000000.0,
            "percentile_real_flag": False,
            "pe_pb_source": "估算（申万行业）",
            "data_quality": "ESTIMATED",
            "max_weight": 0.075
        }
    ]
    
    # 转换为 ETFData 对象
    etf_objects = []
    for data in test_etfs:
        etf = create_etf_data_from_dict(data)
        etf.max_weight = data["max_weight"]  # 手动设置（实际由 DataQualityFilter 设置）
        etf_objects.append(etf)
    
    print(f"✅ 创建测试数据成功: {len(etf_objects)} 只 ETF")
    print()
    
    # ------------------------------------------------------------------------
    # 测试2: 创建 RiskConfig（balanced）
    # ------------------------------------------------------------------------
    
    print("【测试2】创建 RiskConfig（balanced）")
    print("-" * 80)
    
    from portfolio_engine.models import create_risk_config
    
    config = create_risk_config("balanced")
    
    print(f"✅ 创建 RiskConfig 成功")
    print(f"  - total_position: {config.total_position:.0%}")
    print(f"  - single_etf_cap: {config.single_etf_cap:.0%}")
    print()
    
    # ------------------------------------------------------------------------
    # 测试3: 创建 PortfolioOptimizer 对象
    # ------------------------------------------------------------------------
    
    print("【测试3】创建 PortfolioOptimizer 对象")
    print("-" * 80)
    
    try:
        optimizer = PortfolioOptimizer(config)
        print(f"✅ 创建 PortfolioOptimizer 成功")
        print(f"  - w1 (PE%): {optimizer.w1}")
        print(f"  - w2 (PB%): {optimizer.w2}")
        print(f"  - w3 (quality): {optimizer.w3}")
    
    except ValueError as e:
        print(f"❌ 创建失败: {e}")
    
    print()
    
    # ------------------------------------------------------------------------
    # 测试4: 执行 optimize()
    # ------------------------------------------------------------------------
    
    print("【测试4】执行 optimize()")
    print("-" * 80)
    
    try:
        portfolio = optimizer.optimize(etf_objects)
        
        print(f"✅ 优化成功: {len(portfolio)} 只 ETF")
        print()
        
        # 打印权重分配结果
        print("权重分配结果:")
        for i, etf in enumerate(portfolio):
            print(f"  {i+1}. {etf.code} {etf.name}")
            print(f"     - score: {etf.score:.4f}")
            print(f"     - weight: {etf.weight:.2%}")
            print(f"     - max_weight: {etf.max_weight:.2%}")
            print()
        
        # 验证合计
        total_weight = sum([etf.weight for etf in portfolio])
        print(f"✅ 验证合计:")
        print(f"  - 总仓位: {total_weight:.2%} (目标: {config.total_position:.0%})")
        print()
    
    except Exception as e:
        print(f"❌ 优化失败: {e}")
        print()
    
    # ------------------------------------------------------------------------
    # 测试5: 测试快捷函数
    # ------------------------------------------------------------------------
    
    print("【测试5】测试快捷函数")
    print("-" * 80)
    
    try:
        portfolio_fast = optimize_portfolio(etf_objects, config)
        
        print(f"✅ 快捷函数调用成功: {len(portfolio_fast)} 只 ETF")
        print()
    
    except Exception as e:
        print(f"❌ 快捷函数调用失败: {e}")
        print()
    
    # ------------------------------------------------------------------------
    # 测试6: 错误处理（无效的 ETF 列表）
    # ------------------------------------------------------------------------
    
    print("【测试6】错误处理（无效的 ETF 列表）")
    print("-" * 80)
    
    try:
        optimizer.optimize([])
        print(f"❌ 应该抛出异常，但没有")
    
    except ValueError as e:
        print(f"✅ 正确捕获异常: {e}")
    
    print()
    
    # ------------------------------------------------------------------------
    # 完成
    # ------------------------------------------------------------------------
    
    print("=" * 80)
    print("✅ 所有测试完成！")
    print("=" * 80)
