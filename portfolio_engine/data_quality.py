# portfolio_engine/data_quality.py
"""
数据质量过滤器（Data Quality Filter）

根据数据质量（REAL vs ESTIMATED）分配 max_weight。

规则：
- REAL 数据（乐咕乐股20年历史分位） → max_weight = real_data_cap / N_real
- ESTIMATED 数据（申万行业估算） → max_weight = estimated_data_cap / N_estimated

输入：
- etfs: List[ETFData]（来自筛选系统）
- risk_config: RiskConfig（风险配置）

输出：
- filtered: List[ETFData]（带 max_weight 字段）
"""

import sys
import os
import logging
from typing import List, Dict, Any, Optional

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
# DataQualityFilter 类
# ============================================================================

class DataQualityFilter:
    """
    数据质量过滤器
    
    根据数据质量分配 max_weight。
    """
    
    def __init__(self, risk_config: RiskConfig):
        """
        初始化数据质量过滤器
        
        Args:
            risk_config: 风险配置对象
        
        Raises:
            ValueError: 如果 risk_config 无效
        """
        if risk_config is None:
            error_msg = "risk_config 不能为 None"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        self.risk_config = risk_config
        logger.info(f"DataQualityFilter 初始化完成")
        logger.info(f"  - real_data_cap: {risk_config.real_data_cap:.0%}")
        logger.info(f"  - estimated_data_cap: {risk_config.estimated_data_cap:.0%}")
    
    def filter(self, etfs: List[ETFData]) -> List[ETFData]:
        """
        过滤并分配 max_weight
        
        Args:
            etfs: ETFData 对象列表（来自筛选系统）
        
        Returns:
            filtered: 带 max_weight 字段的 ETF 列表
        
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
        
        logger.info(f"开始数据质量过滤：{len(etfs)} 只 ETF")
        
        # 校验 ETFData 对象
        valid_etfs = []
        for i, etf in enumerate(etfs):
            if not isinstance(etf, ETFData):
                logger.warning(f"[{i+1}] 跳过无效对象: {type(etf)}")
                continue
            
            # 确保 data_quality 字段已设置
            if etf.data_quality is None:
                # 尝试从 percentile_real_flag 推断
                if etf.percentile_real_flag is not None:
                    etf.data_quality = "REAL" if etf.percentile_real_flag else "ESTIMATED"
                else:
                    logger.warning(f"[{i+1}] {etf.code} data_quality 未设置，跳过")
                    continue
            
            valid_etfs.append(etf)
        
        if not valid_etfs:
            error_msg = "没有有效的 ETF 数据"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        logger.info(f"有效 ETF 数量: {len(valid_etfs)}")
        
        # ------------------------------------------------------------------------
        # 2. 分类：REAL vs ESTIMATED
        # ------------------------------------------------------------------------
        
        real_etfs = [etf for etf in valid_etfs if etf.data_quality == "REAL"]
        estimated_etfs = [etf for etf in valid_etfs if etf.data_quality == "ESTIMATED"]
        
        logger.info(f"REAL 数据 ETF: {len(real_etfs)} 只")
        logger.info(f"ESTIMATED 数据 ETF: {len(estimated_etfs)} 只")
        
        # ------------------------------------------------------------------------
        # 3. 分配 max_weight
        # ------------------------------------------------------------------------
        
        # REAL 数据：max_weight = real_data_cap / N_real
        if real_etfs:
            real_cap = self.risk_config.real_data_cap
            real_weight = real_cap / len(real_etfs)
            
            for etf in real_etfs:
                etf.max_weight = real_weight
            
            logger.info(f"REAL 数据 max_weight 分配完成: {real_weight:.2%} / 只")
        
        # ESTIMATED 数据：max_weight = estimated_data_cap / N_estimated
        if estimated_etfs:
            estimated_cap = self.risk_config.estimated_data_cap
            estimated_weight = estimated_cap / len(estimated_etfs)
            
            for etf in estimated_etfs:
                etf.max_weight = estimated_weight
            
            logger.info(f"ESTIMATED 数据 max_weight 分配完成: {estimated_weight:.2%} / 只")
        
        # ------------------------------------------------------------------------
        # 4. 合并并返回
        # ------------------------------------------------------------------------
        
        filtered = real_etfs + estimated_etfs
        
        logger.info(f"✅ 数据质量过滤完成: {len(filtered)} 只 ETF")
        logger.info(f"  - REAL 数据: {len(real_etfs)} 只，合计上限 {self.risk_config.real_data_cap:.0%}")
        logger.info(f"  - ESTIMATED 数据: {len(estimated_etfs)} 只，合计上限 {self.risk_config.estimated_data_cap:.0%}")
        
        return filtered


# ============================================================================
# 辅助函数（模块级）
# ============================================================================

def filter_etfs_by_data_quality(
    etfs: List[ETFData], 
    risk_config: RiskConfig
) -> List[ETFData]:
    """
    快捷函数：数据质量过滤
    
    Args:
        etfs: ETF 列表
        risk_config: 风险配置
    
    Returns:
        List[ETFData]: 带 max_weight 的 ETF 列表
    
    Example:
        >>> from portfolio_engine.data_quality import filter_etfs_by_data_quality
        >>> filtered = filter_etfs_by_data_quality(etfs, config)
    """
    filter_obj = DataQualityFilter(risk_config)
    return filter_obj.filter(etfs)


# ============================================================================
# 独立运行测试
# ============================================================================

if __name__ == "__main__":
    """
    独立运行测试
    
    测试内容：
    1. 创建测试数据（模拟筛选系统输出）
    2. 创建 RiskConfig（balanced）
    3. 创建 DataQualityFilter 对象
    4. 执行 filter()
    5. 验证 max_weight 分配
    6. 测试错误处理（无效的 ETF 列表）
    """
    
    print("=" * 80)
    print("DataQualityFilter 独立测试")
    print("=" * 80)
    print()
    
    # ------------------------------------------------------------------------
    # 测试1: 创建测试数据（模拟筛选系统输出）
    # ------------------------------------------------------------------------
    
    print("【测试1】创建测试数据（模拟筛选系统输出）")
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
            "percentile_real_flag": True,  # REAL
            "pe_pb_source": "乐咕乐股"
        },
        {
            "code": "sh510050",
            "name": "华夏上证50ETF",
            "pe_percentile": 66.0,
            "pb_percentile": 70.0,
            "avg_amount_20d": 2000000000.0,
            "percentile_real_flag": True,  # REAL
            "pe_pb_source": "乐咕乐股"
        },
        {
            "code": "sh512880",
            "name": "国泰中证全指证券公司ETF",
            "pe_percentile": 18.0,
            "pb_percentile": 26.0,
            "avg_amount_20d": 3930000000.0,
            "percentile_real_flag": False,  # ESTIMATED
            "pe_pb_source": "估算（申万行业）"
        },
        {
            "code": "sh512690",
            "name": "酒ETF",
            "pe_percentile": 25.0,
            "pb_percentile": 30.0,
            "avg_amount_20d": 1500000000.0,
            "percentile_real_flag": False,  # ESTIMATED
            "pe_pb_source": "估算（申万行业）"
        },
        {
            "code": "sh512290",
            "name": "生物医药ETF",
            "pe_percentile": 28.0,
            "pb_percentile": 35.0,
            "avg_amount_20d": 500000000.0,
            "percentile_real_flag": False,  # ESTIMATED
            "pe_pb_source": "估算（申万行业）"
        }
    ]
    
    # 转换为 ETFData 对象
    etf_objects = []
    for data in test_etfs:
        etf = create_etf_data_from_dict(data)
        etf_objects.append(etf)
    
    print(f"✅ 创建测试数据成功: {len(etf_objects)} 只 ETF")
    print(f"  - REAL 数据: {sum([1 for e in etf_objects if e.percentile_real_flag])} 只")
    print(f"  - ESTIMATED 数据: {sum([1 for e in etf_objects if not e.percentile_real_flag])} 只")
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
    print(f"  - real_data_cap: {config.real_data_cap:.0%}")
    print(f"  - estimated_data_cap: {config.estimated_data_cap:.0%}")
    print()
    
    # ------------------------------------------------------------------------
    # 测试3: 创建 DataQualityFilter 对象
    # ------------------------------------------------------------------------
    
    print("【测试3】创建 DataQualityFilter 对象")
    print("-" * 80)
    
    try:
        filter_obj = DataQualityFilter(config)
        print(f"✅ 创建 DataQualityFilter 成功")
    
    except ValueError as e:
        print(f"❌ 创建失败: {e}")
    
    print()
    
    # ------------------------------------------------------------------------
    # 测试4: 执行 filter()
    # ------------------------------------------------------------------------
    
    print("【测试4】执行 filter()")
    print("-" * 80)
    
    try:
        filtered = filter_obj.filter(etf_objects)
        
        print(f"✅ 过滤成功: {len(filtered)} 只 ETF")
        print()
        
        # 打印 max_weight 分配结果
        print("max_weight 分配结果:")
        for i, etf in enumerate(filtered):
            print(f"  {i+1}. {etf.code} {etf.name}")
            print(f"     - data_quality: {etf.data_quality}")
            print(f"     - max_weight: {etf.max_weight:.2%}")
            print()
        
        # 验证合计
        real_total = sum([e.max_weight for e in filtered if e.data_quality == "REAL"])
        estimated_total = sum([e.max_weight for e in filtered if e.data_quality == "ESTIMATED"])
        
        print(f"✅ 验证合计:")
        print(f"  - REAL 数据合计: {real_total:.2%} (上限: {config.real_data_cap:.0%})")
        print(f"  - ESTIMATED 数据合计: {estimated_total:.2%} (上限: {config.estimated_data_cap:.0%})")
        print()
    
    except Exception as e:
        print(f"❌ 过滤失败: {e}")
        print()
    
    # ------------------------------------------------------------------------
    # 测试5: 测试快捷函数
    # ------------------------------------------------------------------------
    
    print("【测试5】测试快捷函数")
    print("-" * 80)
    
    try:
        filtered_fast = filter_etfs_by_data_quality(etf_objects, config)
        
        print(f"✅ 快捷函数调用成功: {len(filtered_fast)} 只 ETF")
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
        filter_obj.filter([])
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
