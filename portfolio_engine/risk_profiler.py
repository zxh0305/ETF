# portfolio_engine/risk_profiler.py
"""
风险配置器（Risk Profiler）

提供3种风险等级预设，用户可根据风险偏好选择。

风险等级：
1. conservative（保守型）：总仓位≤50%，单ETF≤10%，REAL数据≤30%
2. balanced（稳健型）：总仓位≤80%，单ETF≤20%，REAL数据≤40%
3. aggressive（激进型）：总仓位≤100%，单ETF≤30%，REAL数据≤60%

使用示例：
    >>> from portfolio_engine.risk_profiler import RiskProfiler, get_risk_config
    >>> profiler = RiskProfiler("balanced")
    >>> config = profiler.get_config()
    >>> print(config.total_position)  # 0.80
"""

import sys
import os
import logging
from typing import Dict, Any, Optional

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

from portfolio_engine.models import RiskConfig, create_risk_config


# ============================================================================
# 配置日志
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# RiskProfiler 类
# ============================================================================

class RiskProfiler:
    """
    风险配置器
    
    根据风险等级返回对应的 RiskConfig 对象。
    """
    
    def __init__(self, risk_level: str = "balanced"):
        """
        初始化风险配置器
        
        Args:
            risk_level: 风险等级（"conservative" / "balanced" / "aggressive"）
        
        Raises:
            ValueError: 如果 risk_level 无效
        """
        # 校验参数
        valid_levels = ["conservative", "balanced", "aggressive"]
        if not risk_level or risk_level not in valid_levels:
            error_msg = f"无效的风险等级: {risk_level}，可选: {valid_levels}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        self.risk_level = risk_level
        logger.info(f"RiskProfiler 初始化完成，risk_level={self.risk_level}")
    
    def get_config(self) -> RiskConfig:
        """
        获取风险配置
        
        Returns:
            RiskConfig: 风险配置对象
        
        Example:
            >>> profiler = RiskProfiler("balanced")
            >>> config = profiler.get_config()
            >>> print(config.total_position)  # 0.80
        """
        logger.info(f"正在获取风险配置: {self.risk_level}")
        
        config = create_risk_config(self.risk_level)
        
        logger.info(f"✅ 风险配置获取成功:")
        logger.info(f"  - total_position: {config.total_position:.0%}")
        logger.info(f"  - single_etf_cap: {config.single_etf_cap:.0%}")
        logger.info(f"  - real_data_cap: {config.real_data_cap:.0%}")
        
        return config
    
    def print_summary(self) -> None:
        """
        打印风险配置摘要（人类可读）
        
        Example:
            >>> profiler = RiskProfiler("balanced")
            >>> profiler.print_summary()
        """
        config = self.get_config()
        
        print("=" * 80)
        print(f"风险等级: {self.risk_level.upper()}")
        print("=" * 80)
        print()
        print(f"📊 仓位控制:")
        print(f"  - 总仓位上限: {config.total_position:.0%}")
        print(f"  - 单ETF仓位上限: {config.single_etf_cap:.0%}")
        print(f"  - REAL数据ETF合计上限: {config.real_data_cap:.0%}")
        print(f"  - ESTIMATED数据ETF合计上限: {config.estimated_data_cap:.0%}")
        print()
        print(f"🔗 相关性控制:")
        print(f"  - 相关性阈值: {config.correlation_threshold:.2f}")
        print(f"  - 高相关ETF合计上限: {config.correlation_cap:.0%}")
        print()
        print("=" * 80)


# ============================================================================
# 辅助函数（模块级）
# ============================================================================

def get_risk_config(risk_level: str) -> RiskConfig:
    """
    快捷函数：获取风险配置
    
    Args:
        risk_level: 风险等级
    
    Returns:
        RiskConfig: 风险配置对象
    
    Example:
        >>> from portfolio_engine.risk_profiler import get_risk_config
        >>> config = get_risk_config("balanced")
    """
    profiler = RiskProfiler(risk_level)
    return profiler.get_config()


def list_risk_levels() -> Dict[str, Dict[str, Any]]:
    """
    列出所有风险等级及其配置
    
    Returns:
        dict: 风险等级 → 配置字典
    
    Example:
        >>> from portfolio_engine.risk_profiler import list_risk_levels
        >>> levels = list_risk_levels()
        >>> print(levels["balanced"]["total_position"])  # 0.80
    """
    levels = {}
    
    for risk_level in ["conservative", "balanced", "aggressive"]:
        config = get_risk_config(risk_level)
        levels[risk_level] = config.to_dict()
    
    return levels


# ============================================================================
# 独立运行测试
# ============================================================================

if __name__ == "__main__":
    """
    独立运行测试
    
    测试内容：
    1. 创建 RiskProfiler 对象（3种风险等级）
    2. 测试 get_config()
    3. 测试 print_summary()
    4. 测试快捷函数
    5. 测试 list_risk_levels()
    6. 错误处理（无效的风险等级）
    """
    
    print("=" * 80)
    print("RiskProfiler 独立测试")
    print("=" * 80)
    print()
    
    # ------------------------------------------------------------------------
    # 测试1: 创建 RiskProfiler 对象（3种风险等级）
    # ------------------------------------------------------------------------
    
    print("【测试1】创建 RiskProfiler 对象（3种风险等级）")
    print("-" * 80)
    
    for risk_level in ["conservative", "balanced", "aggressive"]:
        try:
            profiler = RiskProfiler(risk_level)
            print(f"✅ {risk_level} 创建成功")
        
        except ValueError as e:
            print(f"❌ {risk_level} 创建失败: {e}")
    
    print()
    
    # ------------------------------------------------------------------------
    # 测试2: 测试 get_config()
    # ------------------------------------------------------------------------
    
    print("【测试2】测试 get_config()")
    print("-" * 80)
    
    try:
        profiler = RiskProfiler("balanced")
        config = profiler.get_config()
        
        print(f"✅ get_config() 成功:")
        print(f"  - risk_level: {config.risk_level}")
        print(f"  - total_position: {config.total_position:.0%}")
        print(f"  - single_etf_cap: {config.single_etf_cap:.0%}")
    
    except Exception as e:
        print(f"❌ get_config() 失败: {e}")
    
    print()
    
    # ------------------------------------------------------------------------
    # 测试3: 测试 print_summary()
    # ------------------------------------------------------------------------
    
    print("【测试3】测试 print_summary()")
    print("-" * 80)
    
    try:
        profiler = RiskProfiler("balanced")
        profiler.print_summary()
        print("✅ print_summary() 成功")
    
    except Exception as e:
        print(f"❌ print_summary() 失败: {e}")
    
    print()
    
    # ------------------------------------------------------------------------
    # 测试4: 测试快捷函数
    # ------------------------------------------------------------------------
    
    print("【测试4】测试快捷函数")
    print("-" * 80)
    
    try:
        config = get_risk_config("balanced")
        print(f"✅ get_risk_config() 成功: {config.risk_level}")
        
        levels = list_risk_levels()
        print(f"✅ list_risk_levels() 成功: {len(levels)} 个风险等级")
    
    except Exception as e:
        print(f"❌ 快捷函数失败: {e}")
    
    print()
    
    # ------------------------------------------------------------------------
    # 测试5: 错误处理（无效的风险等级）
    # ------------------------------------------------------------------------
    
    print("【测试5】错误处理（无效的风险等级）")
    print("-" * 80)
    
    try:
        profiler = RiskProfiler("invalid_level")
        print(f"❌ 应该抛出异常，但没有")
    
    except ValueError as e:
        print(f"✅ 正确捕获异常: {e}")
    
    print()
    
    # ------------------------------------------------------------------------
    # 完成
    # ------------------------------------------------------------------------
    
    print("=" * 80)
    print("✅ 所有测试通过！")
    print("=" * 80)
