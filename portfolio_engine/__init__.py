# Portfolio Engine 模块初始化文件
# 作者：资深量化系统架构师
# 创建时间：2026-05-23

"""
ETF 投资组合引擎（Portfolio Engine）

智能构建 ETF 投资组合，包含：
1. 风险配置（RiskProfiler）
2. 数据质量过滤（DataQualityFilter）
3. 相关性分析（CorrelationAnalyzer）
4. 组合优化（PortfolioOptimizer）
5. 风险控制（RiskController）
6. 输出生成（OutputGenerator）
7. 主引擎（PortfolioEngine）

使用方法：
    from portfolio_engine.engine import PortfolioEngine, run_portfolio_engine
    
    # 方法1：使用类
    engine = PortfolioEngine(risk_level="balanced")
    result = engine.run()
    
    # 方法2：使用快捷函数
    result = run_portfolio_engine(risk_level="balanced")
"""

# 版本信息
__version__ = "1.0.0"
__author__ = "资深量化系统架构师"
__created__ = "2026-05-23"

# 导入主要类（便于外部调用）
from portfolio_engine.models import (
    ETFData,
    RiskConfig,
    PortfolioItem,
    PortfolioResult,
    create_etf_data_from_dict,
    create_risk_config
)

from portfolio_engine.risk_profiler import (
    RiskProfiler,
    get_risk_config
)

from portfolio_engine.data_quality import (
    DataQualityFilter,
    filter_etfs_by_data_quality
)

from portfolio_engine.correlation import (
    CorrelationAnalyzer,
    compute_etf_correlation
)

from portfolio_engine.optimizer import (
    PortfolioOptimizer,
    optimize_portfolio
)

from portfolio_engine.risk_controller import (
    RiskController,
    apply_risk_control
)

from portfolio_engine.output import (
    OutputGenerator,
    generate_portfolio_output,
    load_portfolio_result
)

from portfolio_engine.engine import (
    PortfolioEngine,
    run_portfolio_engine
)

# 导出列表
__all__ = [
    # Models
    "ETFData",
    "RiskConfig",
    "PortfolioItem",
    "PortfolioResult",
    "create_etf_data_from_dict",
    "create_risk_config",
    # RiskProfiler
    "RiskProfiler",
    "get_risk_config",
    # DataQualityFilter
    "DataQualityFilter",
    "filter_etfs_by_data_quality",
    # CorrelationAnalyzer
    "CorrelationAnalyzer",
    "compute_etf_correlation",
    # PortfolioOptimizer
    "PortfolioOptimizer",
    "optimize_portfolio",
    # RiskController
    "RiskController",
    "apply_risk_control",
    # OutputGenerator
    "OutputGenerator",
    "generate_portfolio_output",
    "load_portfolio_result",
    # PortfolioEngine
    "PortfolioEngine",
    "run_portfolio_engine"
]
