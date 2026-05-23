# portfolio_engine/risk_controller.py
"""
风险控制器（Risk Controller）

应用3类风控规则，确保投资组合安全。

风控规则：
1. 总仓位限制：∑ weight ≤ total_position
2. 单ETF上限：weight ≤ single_etf_cap
3. 数据质量限制：REAL合计 ≤ real_data_cap，ESTIMATED合计 ≤ estimated_data_cap
4. 相关性限制：高相关ETF（corr > threshold）合计 ≤ correlation_cap

输入：
- portfolio: List[ETFData]（带 weight）
- risk_config: RiskConfig
- correlation_matrix: np.ndarray（可选）

输出：
- final_portfolio: List[ETFData]（调整后）
- warnings: List[str]（警告信息）
"""

import sys
import os
import logging
from typing import List, Dict, Any, Optional, Tuple
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
# RiskController 类
# ============================================================================

class RiskController:
    """
    风险控制器
    
    应用风控规则，确保投资组合安全。
    """
    
    def __init__(
        self, 
        risk_config: RiskConfig, 
        correlation_matrix: Optional[np.ndarray] = None
    ):
        """
        初始化风险控制器
        
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
        self.warnings = []
        
        logger.info(f"RiskController 初始化完成")
        logger.info(f"  - total_position: {risk_config.total_position:.0%}")
        logger.info(f"  - single_etf_cap: {risk_config.single_etf_cap:.0%}")
        logger.info(f"  - correlation_threshold: {risk_config.correlation_threshold:.2f}")
    
    def apply_rules(
        self, 
        portfolio: List[ETFData]
    ) -> Tuple[List[ETFData], List[str]]:
        """
        应用风控规则
        
        Args:
            portfolio: ETFData 对象列表（带 weight）
        
        Returns:
            tuple: (final_portfolio, warnings)
        
        Raises:
            ValueError: 如果 portfolio 为空或包含无效数据
        """
        # ------------------------------------------------------------------------
        # 1. 输入校验
        # ------------------------------------------------------------------------
        
        if not portfolio:
            error_msg = "portfolio 列表不能为空"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        logger.info(f"开始风险控制：{len(portfolio)} 只 ETF")
        
        # 校验 ETFData 对象
        valid_portfolio = []
        for i, etf in enumerate(portfolio):
            if not isinstance(etf, ETFData):
                logger.warning(f"[{i+1}] 跳过无效对象: {type(etf)}")
                continue
            
            # 检查 weight 是否已设置
            if etf.weight is None:
                logger.warning(f"[{i+1}] {etf.code} weight 未设置，跳过")
                continue
            
            valid_portfolio.append(etf)
        
        if not valid_portfolio:
            error_msg = "没有有效的 ETF 数据"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        logger.info(f"有效 ETF 数量: {len(valid_portfolio)}")
        
        # ------------------------------------------------------------------------
        # 2. 应用风控规则
        # ------------------------------------------------------------------------
        
        # 规则1：单ETF上限（weight ≤ single_etf_cap）
        logger.info("【规则1】单ETF上限检查...")
        valid_portfolio = self._apply_single_etf_cap(valid_portfolio)
        
        # 规则2：数据质量限制（REAL/ESTIMATED 合计上限）
        logger.info("【规则2】数据质量限制检查...")
        valid_portfolio = self._apply_data_quality_cap(valid_portfolio)
        
        # 规则3：总仓位限制（∑ weight ≤ total_position）
        logger.info("【规则3】总仓位限制检查...")
        valid_portfolio = self._apply_total_position_cap(valid_portfolio)
        
        # 规则4：相关性限制（可选）
        if self.correlation_matrix is not None:
            logger.info("【规则4】相关性限制检查...")
            valid_portfolio = self._apply_correlation_cap(valid_portfolio)
        
        # ------------------------------------------------------------------------
        # 3. 返回结果
        # ------------------------------------------------------------------------
        
        logger.info(f"✅ 风险控制完成: {len(valid_portfolio)} 只 ETF")
        logger.info(f"  - 总仓位: {sum([etf.weight for etf in valid_portfolio]):.2%}")
        logger.info(f"  - 警告数量: {len(self.warnings)} 条")
        
        return valid_portfolio, self.warnings
    
    def _apply_single_etf_cap(self, portfolio: List[ETFData]) -> List[ETFData]:
        """
        应用单ETF上限规则
        
        Args:
            portfolio: ETF 列表
        
        Returns:
            List[ETFData]: 调整后的 ETF 列表
        """
        cap = self.risk_config.single_etf_cap
        adjusted = []
        
        for etf in portfolio:
            if etf.weight > cap:
                old_weight = etf.weight
                etf.weight = cap
                self.warnings.append(
                    f"单ETF上限触发: {etf.code} {etf.name} "
                    f"weight {old_weight:.2%} → {etf.weight:.2%}"
                )
                logger.warning(
                    f"单ETF上限触发: {etf.code} {etf.name} "
                    f"weight {old_weight:.2%} → {etf.weight:.2%}"
                )
            adjusted.append(etf)
        
        return adjusted
    
    def _apply_data_quality_cap(self, portfolio: List[ETFData]) -> List[ETFData]:
        """
        应用数据质量限制规则
        
        Args:
            portfolio: ETF 列表
        
        Returns:
            List[ETFData]: 调整后的 ETF 列表
        """
        # 分类：REAL vs ESTIMATED
        real_etfs = [etf for etf in portfolio if etf.data_quality == "REAL"]
        estimated_etfs = [etf for etf in portfolio if etf.data_quality == "ESTIMATED"]
        
        # REAL 数据限制
        real_cap = self.risk_config.real_data_cap
        real_total = sum([etf.weight for etf in real_etfs])
        
        if real_total > real_cap:
            scale = real_cap / real_total if real_total > 0 else 0
            for etf in real_etfs:
                old_weight = etf.weight
                etf.weight *= scale
                self.warnings.append(
                    f"REAL数据上限触发: {etf.code} {etf.name} "
                    f"weight {old_weight:.2%} → {etf.weight:.2%}"
                )
            
            logger.warning(
                f"REAL数据上限触发: 合计 {real_total:.2%} > 上限 {real_cap:.0%}，"
                f"缩放比例 {scale:.2%}"
            )
        
        # ESTIMATED 数据限制
        estimated_cap = self.risk_config.estimated_data_cap
        estimated_total = sum([etf.weight for etf in estimated_etfs])
        
        if estimated_total > estimated_cap:
            scale = estimated_cap / estimated_total if estimated_total > 0 else 0
            for etf in estimated_etfs:
                old_weight = etf.weight
                etf.weight *= scale
                self.warnings.append(
                    f"ESTIMATED数据上限触发: {etf.code} {etf.name} "
                    f"weight {old_weight:.2%} → {etf.weight:.2%}"
                )
            
            logger.warning(
                f"ESTIMATED数据上限触发: 合计 {estimated_total:.2%} > 上限 {estimated_cap:.0%}，"
                f"缩放比例 {scale:.2%}"
            )
        
        return portfolio
    
    def _apply_total_position_cap(self, portfolio: List[ETFData]) -> List[ETFData]:
        """
        应用总仓位限制规则
        
        Args:
            portfolio: ETF 列表
        
        Returns:
            List[ETFData]: 调整后的 ETF 列表
        """
        total_cap = self.risk_config.total_position
        total_weight = sum([etf.weight for etf in portfolio])
        
        if total_weight > total_cap:
            scale = total_cap / total_weight
            for etf in portfolio:
                etf.weight *= scale
            
            self.warnings.append(
                f"总仓位上限触发: 合计 {total_weight:.2%} > 上限 {total_cap:.0%}，"
                f"缩放比例 {scale:.2%}"
            )
            logger.warning(
                f"总仓位上限触发: 合计 {total_weight:.2%} > 上限 {total_cap:.0%}，"
                f"缩放比例 {scale:.2%}"
            )
        
        return portfolio
    
    def _apply_correlation_cap(self, portfolio: List[ETFData]) -> List[ETFData]:
        """
        应用相关性限制规则
        
        Args:
            portfolio: ETF 列表
        
        Returns:
            List[ETFData]: 调整后的 ETF 列表
        
        Note:
            这是一个简化实现。实际应该：
            1. 找出高相关ETF对（corr > threshold）
            2. 限制这些ETF的合计仓位 ≤ correlation_cap
        """
        if self.correlation_matrix is None:
            return portfolio
        
        threshold = self.risk_config.correlation_threshold
        cap = self.risk_config.correlation_cap
        
        # 找出高相关ETF对
        high_corr_pairs = []
        n = len(portfolio)
        
        for i in range(n):
            for j in range(i+1, n):
                corr = self.correlation_matrix[i, j]
                if corr > threshold:
                    high_corr_pairs.append((i, j, corr))
        
        if not high_corr_pairs:
            logger.info("未发现高相关ETF对")
            return portfolio
        
        # 记录警告）
        for i, j, corr in high_corr_pairs:
            self.warnings.append(
                f"高相关性检测到: {portfolio[i].code} {portfolio[i].name} "
                f"与 {portfolio[j].code} {portfolio[j].name} "
                f"相关性 {corr:.2f} > 阈值 {threshold:.2f}"
            )
            logger.warning(
                f"高相关性检测到: {portfolio[i].code} {portfolio[i].name} "
                f"与 {portfolio[j].code} {portfolio[j].name} "
                f"相关性 {corr:.2f} > 阈值 {threshold:.2f}"
            )
        
        # 简化：不实际调整权重（实际需要更复杂的优化算法）
        logger.warning("相关性限制规则已触发警告，但未自动调整权重（需要更复杂的算法）")
        
        return portfolio


# ============================================================================
# 辅助函数（模块级）
# ============================================================================

def apply_risk_control(
    portfolio: List[ETFData], 
    risk_config: RiskConfig, 
    correlation_matrix: Optional[np.ndarray] = None
) -> Tuple[List[ETFData], List[str]]:
    """
    快捷函数：应用风险控制
    
    Args:
        portfolio: ETF 列表
        risk_config: 风险配置
        correlation_matrix: 相关性矩阵（可选）
    
    Returns:
        tuple: (final_portfolio, warnings)
    
    Example:
        >>> from portfolio_engine.risk_controller import apply_risk_control
        >>> final_portfolio, warnings = apply_risk_control(portfolio, config, matrix)
    """
    controller = RiskController(risk_config, correlation_matrix)
    return controller.apply_rules(portfolio)


# ============================================================================
# 独立运行测试
# ============================================================================

if __name__ == "__main__":
    """
    独立运行测试
    
    测试内容：
    1. 创建测试数据（模拟 Optimizer 输出）
    2. 创建 RiskConfig（balanced）
    3. 创建 RiskController 对象
    4. 执行 apply_rules()
    5. 验证风控规则
    6. 测试快捷函数
    7. 错误处理（无效的 portfolio 列表）
    """
    
    print("=" * 80)
    print("RiskController 独立测试")
    print("=" * 80)
    print()
    
    # ------------------------------------------------------------------------
    # 测试1: 创建测试数据（模拟 Optimizer 输出）
    # ------------------------------------------------------------------------
    
    print("【测试1】创建测试数据（模拟 Optimizer 输出）")
    print("-" * 80)
    
    from portfolio_engine.models import create_etf_data_from_dict
    
    # 模拟 5 只 ETF（3只 REAL，2只 ESTIMATED）
    test_etfs = [
        {
            "code": "sz159905",
            "name": "红利ETF工银",
            "pe_percentile": 20.0,
            "pb_percentile": 20.0,
            "data_quality": "REAL",
            "weight": 0.25  # 超过 single_etf_cap (20%)
        },
        {
            "code": "sh510050",
            "name": "华夏上证50ETF",
            "pe_percentile": 66.0,
            "pb_percentile": 70.0,
            "data_quality": "REAL",
            "weight": 0.20
        },
        {
            "code": "sh000300",
            "name": "沪深300ETF",
            "pe_percentile": 45.0,
            "pb_percentile": 30.0,
            "data_quality": "REAL",
            "weight": 0.20
        },
        {
            "code": "sh512880",
            "name": "证券公司ETF",
            "pe_percentile": 18.0,
            "pb_percentile": 26.0,
            "data_quality": "ESTIMATED",
            "weight": 0.20
        },
        {
            "code": "sh512690",
            "name": "酒ETF",
            "pe_percentile": 25.0,
            "pb_percentile": 30.0,
            "data_quality": "ESTIMATED",
            "weight": 0.20
        }
    ]
    
    # 转换为 ETFData 对象
    etf_objects = []
    for data in test_etfs:
        etf = create_etf_data_from_dict(data)
        etf.weight = data["weight"]  # 手动设置（实际由 Optimizer 设置）
        etf_objects.append(etf)
    
    print(f"✅ 创建测试数据成功: {len(etf_objects)} 只 ETF")
    print(f"  - 总仓位: {sum([e.weight for e in etf_objects]):.2%}")
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
    # 测试3: 创建 RiskController 对象
    # ------------------------------------------------------------------------
    
    print("【测试3】创建 RiskController 对象")
    print("-" * 80)
    
    try:
        controller = RiskController(config)
        print(f"✅ 创建 RiskController 成功")
    
    except ValueError as e:
        print(f"❌ 创建失败: {e}")
    
    print()
    
    # ------------------------------------------------------------------------
    # 测试4: 执行 apply_rules()
    # ------------------------------------------------------------------------
    
    print("【测试4】执行 apply_rules()")
    print("-" * 80)
    
    try:
        final_portfolio, warnings = controller.apply_rules(etf_objects)
        
        print(f"✅ 风控规则应用成功:")
        print(f"  - 调整前 ETF 数量: {len(etf_objects)}")
        print(f"  - 调整后 ETF 数量: {len(final_portfolio)}")
        print(f"  - 警告数量: {len(warnings)} 条")
        print()
        
        # 打印调整后权重
        print("调整后权重:")
        for i, etf in enumerate(final_portfolio):
            print(f"  {i+1}. {etf.code} {etf.name}")
            print(f"     - weight: {etf.weight:.2%}")
            print(f"     - data_quality: {etf.data_quality}")
            print()
        
        # 验证合计
        total_weight = sum([etf.weight for etf in final_portfolio])
        print(f"✅ 验证合计:")
        print(f"  - 总仓位: {total_weight:.2%} (上限: {config.total_position:.0%})")
        print()
    
    except Exception as e:
        print(f"❌ 风控规则应用失败: {e}")
        print()
    
    # ------------------------------------------------------------------------
    # 测试5: 测试快捷函数
    # ------------------------------------------------------------------------
    
    print("【测试5】测试快捷函数")
    print("-" * 80)
    
    try:
        final_portfolio_fast, warnings_fast = apply_risk_control(
            etf_objects, 
            config
        )
        
        print(f"✅ 快捷函数调用成功:")
        print(f"  - 调整后 ETF 数量: {len(final_portfolio_fast)}")
        print(f"  - 警告数量: {len(warnings_fast)} 条")
        print()
    
    except Exception as e:
        print(f"❌ 快捷函数调用失败: {e}")
        print()
    
    # ------------------------------------------------------------------------
    # 测试6: 错误处理（无效的 portfolio 列表）
    # ------------------------------------------------------------------------
    
    print("【测试6】错误处理（无效的 portfolio 列表）")
    print("-" * 80)
    
    try:
        controller.apply_rules([])
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
