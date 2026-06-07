# portfolio_engine/models.py
"""
数据模型（Data Models）

定义 Portfolio Engine 使用的数据结构：
1. ETFData: ETF 基础数据（来自筛选系统）
2. RiskConfig: 风险配置（3种风险等级）
3. PortfolioItem: 投资组合中的单个 ETF（带权重）
4. PortfolioResult: 完整输出（JSON 可序列化）

所有类都支持 JSON 序列化/反序列化。
"""

import sys
import os
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict, field
import json
import numpy as np

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")


# ============================================================================
# 配置日志
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# ETFData 类
# ============================================================================

@dataclass
class ETFData:
    """
    ETF 基础数据（来自筛选系统）
    
    字段说明：
    - code: ETF 代码（如 "sh512880"）
    - name: ETF 名称（如 "国泰中证全指证券公司ETF"）
    - pe_percentile: PE 历史分位（0-100，None 表示暂无数据）
    - pb_percentile: PB 历史分位（0-100，None 表示暂无数据）
    - avg_amount_20d: 20 日平均成交额（单位：元）
    - percentile_real_flag: 是否真实历史分位（True=乐咕乐股20年数据，False=估算）
    - pe_pb_source: 数据来源（如 "乐咕乐股" / "估算（申万行业）"）
    - data_quality: 数据质量标签（"REAL" / "RELIABLE_EST" / "ESTIMATED"）
    - max_weight: 最大仓位（由 DataQualityFilter 设置）
    - score: 综合评分（由 PortfolioOptimizer 计算）
    - weight: 最终仓位（由 PortfolioOptimizer 分配）
    
    使用示例：
        >>> etf = ETFData(code="sh512880", name="国泰中证全指证券公司ETF")
        >>> etf.pe_percentile = 18.0
        >>> etf.pb_percentile = 26.0
        >>> etf.avg_amount_20d = 3_930_000_000.0
        >>> etf.percentile_real_flag = False
        >>> etf.pe_pb_source = "估算（申万行业）"
    """
    
    # 必填字段
    code: str
    name: str
    
    # 可选字段（估值）
    pe_percentile: Optional[float] = None
    pb_percentile: Optional[float] = None
    
    # 可选字段（流动性）
    avg_amount_20d: Optional[float] = None
    
    # 可选字段（数据质量）
    percentile_real_flag: Optional[bool] = None
    pe_pb_source: Optional[str] = None
    data_quality: Optional[str] = None  # "REAL" / "RELIABLE_EST" / "ESTIMATED"
    
    # 新增字段（由后续模块填充）
    max_weight: Optional[float] = None  # 由 DataQualityFilter 设置
    score: Optional[float] = None         # 由 PortfolioOptimizer 计算
    weight: Optional[float] = None       # 由 PortfolioOptimizer 分配
    
    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典（JSON 可序列化）
        
        Returns:
            dict: 字典表示
        
        Example:
            >>> etf = ETFData(code="sh512880", name="测试ETF")
            >>> d = etf.to_dict()
            >>> print(d['code'])  # "sh512880"
        """
        return {
            "code": self.code,
            "name": self.name,
            "pe_percentile": self.pe_percentile,
            "pb_percentile": self.pb_percentile,
            "avg_amount_20d": self.avg_amount_20d,
            "percentile_real_flag": self.percentile_real_flag,
            "pe_pb_source": self.pe_pb_source,
            "data_quality": self.data_quality,
            "max_weight": self.max_weight,
            "score": self.score,
            "weight": self.weight
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ETFData":
        """
        从字典创建 ETFData 对象
        
        Args:
            data: 字典表示
        
        Returns:
            ETFData: ETF 数据对象
        
        Example:
            >>> data = {"code": "sh512880", "name": "测试ETF"}
            >>> etf = ETFData.from_dict(data)
        """
        return cls(**data)


# ============================================================================
# RiskConfig 类
# ============================================================================

@dataclass
class RiskConfig:
    """
    风险配置（3种风险等级）
    
    字段说明：
    - risk_level: 风险等级（"conservative" / "balanced" / "aggressive"）
    - total_position: 总仓位上限（0.0-1.0）
    - single_etf_cap: 单只 ETF 仓位上限（0.0-1.0）
    - real_data_cap: REAL 数据 ETF 合计仓位上限（0.0-1.0）
    - reliable_est_data_cap: RELIABLE_EST 数据（申万行业加权）ETF 合计仓位上限
    - estimated_data_cap: ESTIMATED 数据 ETF 合计仓位上限（0.0-1.0）
    - correlation_threshold: 相关性阈值（0.0-1.0，高于此值视为高相关）
    - correlation_cap: 高相关 ETF 合计仓位上限（0.0-1.0）
    
    使用示例：
        >>> config = RiskConfig(
        ...     risk_level="balanced",
        ...     total_position=0.80,
        ...     single_etf_cap=0.20,
        ...     real_data_cap=0.40,
        ...     reliable_est_data_cap=0.30,
        ...     estimated_data_cap=0.15
        ... )
    """
    
    # 必填字段
    risk_level: str
    
    # 仓位控制
    total_position: float = 0.80      # 总仓位上限（默认 80%）
    single_etf_cap: float = 0.20      # 单只 ETF 上限（默认 20%）
    real_data_cap: float = 0.40        # REAL 数据 ETF 合计上限（默认 40%）
    reliable_est_data_cap: float = 0.30  # RELIABLE_EST 数据 ETF 合计上限（默认 30%）
    estimated_data_cap: float = 0.15    # ESTIMATED 数据 ETF 合计上限（默认 15%）
    
    # 行业/指数分散控制
    industry_cap: float = 0.25         # 单一申万/穿透行业合计上限（默认 25%）
    index_cap: float = 0.30            # 单一指数合计上限（默认 30%）
    
    # 相关性控制
    correlation_threshold: float = 0.70  # 相关性阈值（默认 0.70）
    correlation_cap: float = 0.30        # 高相关 ETF 合计上限（默认 30%）
    
    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典（JSON 可序列化）
        
        Returns:
            dict: 字典表示
        """
        return {
            "risk_level": self.risk_level,
            "total_position": self.total_position,
            "single_etf_cap": self.single_etf_cap,
            "real_data_cap": self.real_data_cap,
            "reliable_est_data_cap": self.reliable_est_data_cap,
            "estimated_data_cap": self.estimated_data_cap,
            "industry_cap": self.industry_cap,
            "index_cap": self.index_cap,
            "correlation_threshold": self.correlation_threshold,
            "correlation_cap": self.correlation_cap
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RiskConfig":
        """
        从字典创建 RiskConfig 对象
        
        Args:
            data: 字典表示
        
        Returns:
            RiskConfig: 风险配置对象
        """
        # 兼容旧格式：缺的字段用默认值
        defaults = {
            "industry_cap": 0.25,
            "index_cap": 0.30,
        }
        for k, v in defaults.items():
            if k not in data:
                data[k] = v
        return cls(**data)


# ============================================================================
# PortfolioItem 类
# ============================================================================

@dataclass
class PortfolioItem:
    """
    投资组合中的单个 ETF（带权重）
    
    字段说明：
    - code: ETF 代码
    - name: ETF 名称
    - weight: 推荐仓位（0.0-1.0）
    - reason: 推荐理由（人类可读）
    - data_quality: 数据质量（"REAL" / "ESTIMATED"）
    - pe_percentile: PE 历史分位（可选）
    - pb_percentile: PB 历史分位（可选）
    - avg_amount_20d: 20 日平均成交额（可选）
    - score: 综合评分（可选）
    
    使用示例：
        >>> item = PortfolioItem(
        ...     code="sh512880",
        ...     name="国泰中证全指证券公司ETF",
        ...     weight=0.15,
        ...     reason="PE%=18%（低估）；PB%=26%（低估）",
        ...     data_quality="ESTIMATED"
        ... )
    """
    
    # 必填字段
    code: str
    name: str
    weight: float
    reason: str
    data_quality: str  # "REAL" / "RELIABLE_EST" / "ESTIMATED"
    
    # 可选字段（用于生成 reason 和输出）
    pe_percentile: Optional[float] = None
    pb_percentile: Optional[float] = None
    avg_amount_20d: Optional[float] = None
    score: Optional[float] = None
    max_weight: Optional[float] = None  # data_quality.py 设置的单只上限
    
    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典（JSON 可序列化）
        
        Returns:
            dict: 字典表示
        """
        return {
            "code": self.code,
            "name": self.name,
            "weight": self.weight,
            "reason": self.reason,
            "data_quality": self.data_quality,
            "pe_percentile": self.pe_percentile,
            "pb_percentile": self.pb_percentile,
            "avg_amount_20d": self.avg_amount_20d,
            "score": self.score,
            "max_weight": self.max_weight
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PortfolioItem":
        """
        从字典创建 PortfolioItem 对象
        
        Args:
            data: 字典表示
        
        Returns:
            PortfolioItem: 投资组合项目对象
        """
        return cls(**data)


# ============================================================================
# PortfolioResult 类
# ============================================================================

@dataclass
class PortfolioResult:
    """
    完整输出（JSON 可序列化）
    
    字段说明：
    - meta: 生成时间、风险等级、统计信息等
    - portfolio: ETF 列表（List[PortfolioItem]）
    - risk_config: 完整风险配置（RiskConfig）
    - correlation: 高相关 ETF 对（可选）
    - warnings: 警告信息（可选）
    
    使用示例：
        >>> result = PortfolioResult(
        ...     meta={"generate_time": "2026-05-23 17:00:00", "risk_level": "balanced"},
        ...     portfolio=[...],
        ...     risk_config=config,
        ...     correlation=None,
        ...     warnings=[]
        ... )
        >>> result.save("output/portfolio_latest.json")
    """
    
    # 必填字段
    meta: Dict[str, Any]
    portfolio: List[PortfolioItem]
    
    # 可选字段
    risk_config: Optional[RiskConfig] = None
    correlation: Optional[Dict[str, Any]] = None
    warnings: Optional[List[str]] = None
    
    def save(self, file_path: str) -> None:
        """
        保存到 JSON 文件
        
        Args:
            file_path: 文件路径
        
        Raises:
            IOError: 如果文件写入失败
            TypeError: 如果对象不可 JSON 序列化
        
        Example:
            >>> result.save("output/portfolio_latest.json")
        """
        try:
            # 转换为可 JSON 序列化的字典
            data = self.to_dict()
            
            # 写入文件
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"✅ 保存成功: {file_path}")
        
        except IOError as e:
            error_msg = f"文件写入失败: {e}"
            logger.error(error_msg)
            raise
        
        except TypeError as e:
            error_msg = f"JSON 序列化失败: {e}"
            logger.error(error_msg)
            raise
    
    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典（JSON 可序列化）
        
        Returns:
            dict: 字典表示
        """
        return {
            "meta": self.meta,
            "portfolio": [item.to_dict() for item in self.portfolio],
            "risk_config": self.risk_config.to_dict() if self.risk_config else None,
            "correlation": self.correlation,
            "warnings": self.warnings
        }
    
    @classmethod
    def from_json(cls, file_path: str) -> "PortfolioResult":
        """
        从 JSON 文件加载
        
        Args:
            file_path: JSON 文件路径
        
        Returns:
            PortfolioResult: 投资组合结果对象
        
        Raises:
            FileNotFoundError: 如果文件不存在
            JSONDecodeError: 如果 JSON 解析失败
        
        Example:
            >>> result = PortfolioResult.from_json("output/portfolio_latest.json")
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            return cls.from_dict(data)
        
        except FileNotFoundError as e:
            error_msg = f"文件不存在: {file_path}"
            logger.error(error_msg)
            raise
        
        except json.JSONDecodeError as e:
            error_msg = f"JSON 解析失败: {file_path} - {e}"
            logger.error(error_msg)
            raise
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PortfolioResult":
        """
        从字典创建 PortfolioResult 对象
        
        Args:
            data: 字典表示
        
        Returns:
            PortfolioResult: 投资组合结果对象
        """
        # 转换 portfolio
        portfolio = [
            PortfolioItem.from_dict(item) for item in data.get("portfolio", [])
        ]
        
        # 转换 risk_config
        risk_config = None
        if data.get("risk_config"):
            risk_config = RiskConfig.from_dict(data["risk_config"])
        
        return cls(
            meta=data["meta"],
            portfolio=portfolio,
            risk_config=risk_config,
            correlation=data.get("correlation"),
            warnings=data.get("warnings")
        )


# ============================================================================
# 辅助函数（模块级）
# ============================================================================

def create_etf_data_from_dict(data: Dict[str, Any]) -> ETFData:
    """
    从字典创建 ETFData 对象（兼容自动化筛选系统的 JSON 格式）
    
    Args:
        data: 字典（包含 code, name, pe_percentile, pb_percentile 等字段）
    
    Returns:
        ETFData: ETF 数据对象
    
    Example:
        >>> data = {
        ...     "code": "sh512880",
        ...     "name": "国泰中证全指证券公司ETF",
        ...     "pe_percentile": 18.0,
        ...     "pb_percentile": 26.0
        ... }
        >>> etf = create_etf_data_from_dict(data)
    """
    # 字段映射（兼容不同命名）
    field_mapping = {
        "code": ["code", "etf_code"],
        "name": ["name", "etf_name"],
        "pe_percentile": ["pe_percentile", "pe_pct"],
        "pb_percentile": ["pb_percentile", "pb_pct"],
        "avg_amount_20d": ["avg_amount_20d", "avg_amt"],
        "percentile_real_flag": ["percentile_real_flag", "is_real"],
        "pe_pb_source": ["pe_pb_source", "source"]
    }
    
    # 提取字段
    kwargs = {}
    for target_key, source_keys in field_mapping.items():
        for source_key in source_keys:
            if source_key in data:
                kwargs[target_key] = data[source_key]
                break
    
    # 创建对象
    etf = ETFData(**kwargs)
    
    # 设置 data_quality（如果未设置或无效）
    if not etf.data_quality or str(etf.data_quality).upper() == "N/A":
        # 三档分类
        if etf.percentile_real_flag:
            etf.data_quality = "REAL"
        elif etf.pe_pb_source and '申万' in etf.pe_pb_source:
            etf.data_quality = "RELIABLE_EST"
        else:
            etf.data_quality = "ESTIMATED"
    
    return etf


def create_risk_config(risk_level: str) -> RiskConfig:
    """
    创建风险配置（3种预设）
    
    Args:
        risk_level: 风险等级（"conservative" / "balanced" / "aggressive"）
    
    Returns:
        RiskConfig: 风险配置对象
    
    Raises:
        ValueError: 如果 risk_level 无效
    
    Example:
        >>> config = create_risk_config("balanced")
        >>> print(config.total_position)  # 0.80
    """
    # 预设配置
    presets = {
        "conservative": {
            "risk_level": "conservative",
            "total_position": 0.50,      # 总仓位 ≤ 50%
            "single_etf_cap": 0.10,       # 单只 ETF ≤ 10%
            "real_data_cap": 0.30,         # REAL 数据 ETF ≤ 30%
            "reliable_est_data_cap": 0.20,  # RELIABLE_EST 数据 ETF ≤ 20%
            "estimated_data_cap": 0.05,    # ESTIMATED 数据 ETF ≤ 5%
            "industry_cap": 0.15,           # 单一行业 ≤ 15%
            "index_cap": 0.20,              # 单一指数 ≤ 20%
            "correlation_threshold": 0.70,
            "correlation_cap": 0.20
        },
        "balanced": {
            "risk_level": "balanced",
            "total_position": 0.80,         # 总仓位 ≤ 80%
            "single_etf_cap": 0.20,         # 单只 ETF ≤ 20%
            "real_data_cap": 0.40,          # REAL 数据 ETF ≤ 40%
            "reliable_est_data_cap": 0.80,   # RELIABLE_EST 数据 ETF ≤ 80%
            "estimated_data_cap": 0.10,     # ESTIMATED 数据 ETF ≤ 10%
            "industry_cap": 0.25,           # 单一行业 ≤ 25%
            "index_cap": 0.30,              # 单一指数 ≤ 30%
            "correlation_threshold": 0.70,
            "correlation_cap": 0.30
        },
        "aggressive": {
            "risk_level": "aggressive",
            "total_position": 1.00,        # 总仓位 ≤ 100%
            "single_etf_cap": 0.30,        # 单只 ETF ≤ 30%
            "real_data_cap": 0.60,         # REAL 数据 ETF ≤ 60%
            "reliable_est_data_cap": 0.40,   # RELIABLE_EST 数据 ETF ≤ 40%
            "estimated_data_cap": 0.15,     # ESTIMATED 数据 ETF ≤ 15%
            "industry_cap": 0.35,           # 单一行业 ≤ 35%
            "index_cap": 0.40,              # 单一指数 ≤ 40%
            "correlation_threshold": 0.70,
            "correlation_cap": 0.40
        }
    }
    
    # 检查参数
    if risk_level not in presets:
        error_msg = f"无效的风险等级: {risk_level}，可选: {list(presets.keys())}"
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    # 创建配置
    config = RiskConfig.from_dict(presets[risk_level])
    
    logger.info(f"✅ 创建风险配置成功: {risk_level}")
    logger.info(f"  - total_position: {config.total_position:.0%}")
    logger.info(f"  - single_etf_cap: {config.single_etf_cap:.0%}")
    
    return config


# ============================================================================
# 独立运行测试
# ============================================================================

if __name__ == "__main__":
    """
    独立运行测试
    
    测试内容：
    1. 创建 ETFData 对象
    2. 测试 to_dict() / from_dict()
    3. 创建 RiskConfig 对象
    4. 测试 create_risk_config()
    5. 创建 PortfolioItem 对象
    6. 创建 PortfolioResult 对象
    7. 测试 save() / from_json()
    """
    
    print("=" * 80)
    print("models.py 独立测试")
    print("=" * 80)
    print()
    
    # ------------------------------------------------------------------------
    # 测试1: 创建 ETFData 对象
    # ------------------------------------------------------------------------
    
    print("【测试1】创建 ETFData 对象")
    print("-" * 80)
    
    etf = ETFData(
        code="sh512880",
        name="国泰中证全指证券公司ETF",
        pe_percentile=18.0,
        pb_percentile=26.0,
        avg_amount_20d=3_930_000_000.0,
        percentile_real_flag=False,
        pe_pb_source="估算（申万行业）",
        data_quality="ESTIMATED"
    )
    
    print(f"✅ ETFData 创建成功:")
    print(f"  - code: {etf.code}")
    print(f"  - name: {etf.name}")
    print(f"  - pe_percentile: {etf.pe_percentile}")
    print(f"  - data_quality: {etf.data_quality}")
    print()
    
    # ------------------------------------------------------------------------
    # 测试2: 测试 to_dict() / from_dict()
    # ------------------------------------------------------------------------
    
    print("【测试2】测试 to_dict() / from_dict()")
    print("-" * 80)
    
    etf_dict = etf.to_dict()
    etf_restored = ETFData.from_dict(etf_dict)
    
    print(f"✅ to_dict() 成功: {len(etf_dict)} 个字段")
    print(f"✅ from_dict() 成功: {etf_restored.code}")
    print()
    
    # ------------------------------------------------------------------------
    # 测试3: 创建 RiskConfig 对象
    # ------------------------------------------------------------------------
    
    print("【测试3】创建 RiskConfig 对象")
    print("-" * 80)
    
    config = RiskConfig(
        risk_level="balanced",
        total_position=0.80,
        single_etf_cap=0.20
    )
    
    print(f"✅ RiskConfig 创建成功:")
    print(f"  - risk_level: {config.risk_level}")
    print(f"  - total_position: {config.total_position:.0%}")
    print(f"  - single_etf_cap: {config.single_etf_cap:.0%}")
    print()
    
    # ------------------------------------------------------------------------
    # 测试4: 测试 create_risk_config()
    # ------------------------------------------------------------------------
    
    print("【测试4】测试 create_risk_config()")
    print("-" * 80)
    
    for risk_level in ["conservative", "balanced", "aggressive"]:
        config = create_risk_config(risk_level)
        print(f"✅ {risk_level}: total_position={config.total_position:.0%}")
    
    print()
    
    # ------------------------------------------------------------------------
    # 测试5: 创建 PortfolioItem 对象
    # ------------------------------------------------------------------------
    
    print("【测试5】创建 PortfolioItem 对象")
    print("-" * 80)
    
    item = PortfolioItem(
        code="sh512880",
        name="国泰中证全指证券公司ETF",
        weight=0.15,
        reason="PE%=18%（低估）；PB%=26%（低估）",
        data_quality="ESTIMATED"
    )
    
    print(f"✅ PortfolioItem 创建成功:")
    print(f"  - code: {item.code}")
    print(f"  - weight: {item.weight:.2%}")
    print(f"  - reason: {item.reason}")
    print()
    
    # ------------------------------------------------------------------------
    # 测试6: 创建 PortfolioResult 对象
    # ------------------------------------------------------------------------
    
    print("【测试6】创建 PortfolioResult 对象")
    print("-" * 80)
    
    result = PortfolioResult(
        meta={
            "generate_time": "2026-05-23 17:00:00",
            "risk_level": "balanced",
            "total_etfs": 1
        },
        portfolio=[item],
        risk_config=config,
        correlation=None,
        warnings=[]
    )
    
    print(f"✅ PortfolioResult 创建成功:")
    print(f"  - meta['risk_level']: {result.meta['risk_level']}")
    print(f"  - portfolio length: {len(result.portfolio)}")
    print()
    
    # ------------------------------------------------------------------------
    # 测试7: 测试 save() / from_json()
    # ------------------------------------------------------------------------
    
    print("【测试7】测试 save() / from_json()")
    print("-" * 80)
    
    # 保存到文件
    test_file = "output/test_portfolio_result.json"
    os.makedirs(os.path.dirname(test_file), exist_ok=True)
    
    result.save(test_file)
    print(f"✅ save() 成功: {test_file}")
    
    # 从文件加载
    loaded_result = PortfolioResult.from_json(test_file)
    print(f"✅ from_json() 成功: {loaded_result.meta['risk_level']}")
    print()
    
    # ------------------------------------------------------------------------
    # 测试8: 测试 create_etf_data_from_dict()
    # ------------------------------------------------------------------------
    
    print("【测试8】测试 create_etf_data_from_dict()")
    print("-" * 80)
    
    test_data = {
        "code": "sz159905",
        "name": "红利ETF工银",
        "pe_percentile": 20.0,
        "pb_percentile": 20.0,
        "avg_amount_20d": 80000000.0,
        "percentile_real_flag": True,
        "pe_pb_source": "乐咕乐股"
    }
    
    etf_from_dict = create_etf_data_from_dict(test_data)
    
    print(f"✅ create_etf_data_from_dict() 成功:")
    print(f"  - code: {etf_from_dict.code}")
    print(f"  - data_quality: {etf_from_dict.data_quality}")
    print()
    
    # ------------------------------------------------------------------------
    # 完成
    # ------------------------------------------------------------------------
    
    print("=" * 80)
    print("✅ 所有测试通过！")
    print("=" * 80)
