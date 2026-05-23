# portfolio_engine/engine.py
"""
主引擎（Portfolio Engine）

串联所有模块，提供统一入口。

执行流程：
1. RiskProfiler: 获取风险配置
2. DataQualityFilter: 过滤并分配 max_weight
3. CorrelationAnalyzer: 计算相关性矩阵
4. PortfolioOptimizer: 优化仓位分配
5. RiskController: 应用风控规则
6. OutputGenerator: 生成最终输出

输入：
- input_file: 输入文件路径（low_valuation_candidates_latest.json）
- output_file: 输出文件路径（portfolio_latest.json）
- risk_level: 风险等级（conservative/balanced/aggressive）

输出：
- PortfolioResult 对象（包含 portfolio + meta + risk_config + warnings）
"""

import sys
import os
import logging
from typing import Optional, Dict, Any, List
import json

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

from portfolio_engine.models import (
    ETFData, 
    RiskConfig, 
    PortfolioResult,
    create_etf_data_from_dict,
    create_risk_config
)
from portfolio_engine.risk_profiler import RiskProfiler, get_risk_config
from portfolio_engine.data_quality import DataQualityFilter, filter_etfs_by_data_quality
from portfolio_engine.correlation import CorrelationAnalyzer, compute_etf_correlation
from portfolio_engine.optimizer import PortfolioOptimizer, optimize_portfolio
from portfolio_engine.risk_controller import RiskController, apply_risk_control
from portfolio_engine.output import OutputGenerator, generate_portfolio_output


# ============================================================================
# 配置日志
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# PortfolioEngine 类
# ============================================================================

class PortfolioEngine:
    """
    投资组合引擎
    
    串联所有模块，提供统一入口。
    """
    
    def __init__(
        self, 
        risk_level: str = "balanced",
        input_file: str = "output/low_valuation_candidates_latest.json",
        output_file: str = "output/portfolio_latest.json"
    ):
        """
        初始化投资组合引擎
        
        Args:
            risk_level: 风险等级（"conservative" / "balanced" / "aggressive"）
            input_file: 输入文件路径（相对或绝对）
            output_file: 输出文件路径（相对或绝对）
        
        Raises:
            ValueError: 如果参数无效
        """
        # 校验参数
        if not risk_level or risk_level not in ("conservative", "balanced", "aggressive"):
            error_msg = f"无效的风险等级: {risk_level}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        if not input_file:
            error_msg = "input_file 不能为空"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        if not output_file:
            error_msg = "output_file 不能为空"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # 转换为绝对路径
        self.project_root = os.path.dirname(os.path.abspath(__file__)) + "/.."
        
        if not os.path.isabs(input_file):
            self.input_file = os.path.join(self.project_root, input_file)
        else:
            self.input_file = input_file
        
        if not os.path.isabs(output_file):
            self.output_file = os.path.join(self.project_root, output_file)
        else:
            self.output_file = output_file
        
        self.risk_level = risk_level
        self.result = None
        self.warnings = []
        
        logger.info(f"PortfolioEngine 初始化完成")
        logger.info(f"  - risk_level: {self.risk_level}")
        logger.info(f"  - input_file: {self.input_file}")
        logger.info(f"  - output_file: {self.output_file}")
    
    def run(self) -> Optional[PortfolioResult]:
        """
        执行完整流程
        
        Returns:
            PortfolioResult: 投资组合结果对象
        
        Raises:
            FileNotFoundError: 如果输入文件不存在
            RuntimeError: 如果流程执行失败
            ValueError: 如果输入数据无效
        """
        try:
            logger.info("=" * 80)
            logger.info("开始执行 Portfolio Engine")
            logger.info("=" * 80)
            
            # ------------------------------------------------------------------------
            # Step 1: 加载输入数据
            # ------------------------------------------------------------------------
            
            logger.info("【Step 1/7】加载输入数据...")
            
            etf_data_list = self._load_input()
            
            logger.info(f"✅ Step 1 完成: 加载 {len(etf_data_list)} 只 ETF")
            
            # ------------------------------------------------------------------------
            # Step 2: 风险配置
            # ------------------------------------------------------------------------
            
            logger.info("【Step 2/7】风险配置...")
            
            risk_config = self._run_risk_profiler()
            
            logger.info(f"✅ Step 2 完成: 风险等级 = {risk_config.risk_level}")
            logger.info(f"  - total_position: {risk_config.total_position:.0%}")
            logger.info(f"  - single_etf_cap: {risk_config.single_etf_cap:.0%}")
            
            # ------------------------------------------------------------------------
            # Step 3: 数据质量过滤
            # ------------------------------------------------------------------------
            
            logger.info("【Step 3/7】数据质量过滤...")
            
            filtered_etfs = self._run_data_quality_filter(etf_data_list, risk_config)
            
            logger.info(f"✅ Step 3 完成: 过滤后 {len(filtered_etfs)} 只 ETF")
            
            # ------------------------------------------------------------------------
            # Step 4: 相关性分析
            # ------------------------------------------------------------------------
            
            logger.info("【Step 4/7】相关性分析...")
            
            correlation_matrix = self._run_correlation_analyzer(filtered_etfs)
            
            if correlation_matrix is not None:
                logger.info(f"✅ Step 4 完成: 相关性矩阵 {correlation_matrix.shape}")
            else:
                logger.warning("⚠️ Step 4 跳过: 相关性矩阵计算失败")
            
            # ------------------------------------------------------------------------
            # Step 5: 组合优化
            # ------------------------------------------------------------------------
            
            logger.info("【Step 5/7】组合优化...")
            
            raw_portfolio = self._run_portfolio_optimizer(
                filtered_etfs, 
                correlation_matrix, 
                risk_config
            )
            
            logger.info(f"✅ Step 5 完成: 优化后 {len(raw_portfolio)} 只 ETF")
            
            # ------------------------------------------------------------------------
            # Step 6: 风险控制
            # ------------------------------------------------------------------------
            
            logger.info("【Step 6/7】风险控制...")
            
            final_portfolio, warnings = self._run_risk_controller(
                raw_portfolio, 
                correlation_matrix, 
                risk_config
            )
            
            logger.info(f"✅ Step 6 完成: 风控后 {len(final_portfolio)} 只 ETF")
            logger.info(f"  - 警告数量: {len(warnings)} 条")
            
            # 保存警告
            self.warnings = warnings
            
            # ------------------------------------------------------------------------
            # Step 7: 生成输出
            # ------------------------------------------------------------------------
            
            logger.info("【Step 7/7】生成输出...")
            
            result = self._run_output_generator(
                final_portfolio, 
                risk_config, 
                correlation_matrix, 
                warnings
            )
            
            logger.info(f"✅ Step 7 完成: 输出文件 = {self.output_file}")
            
            # ------------------------------------------------------------------------
            # 完成
            # ------------------------------------------------------------------------
            
            logger.info("=" * 80)
            logger.info("✅ Portfolio Engine 执行完成！")
            logger.info("=" * 80)
            
            self.result = result
            return result
        
        except FileNotFoundError as e:
            error_msg = f"输入文件不存在: {e}"
            logger.error(error_msg)
            raise
        
        except RuntimeError as e:
            error_msg = f"执行失败: {e}"
            logger.error(error_msg)
            raise
        
        except ValueError as e:
            error_msg = f"输入数据无效: {e}"
            logger.error(error_msg)
            raise
        
        except Exception as e:
            error_msg = f"未知错误: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
    
    def _load_input(self) -> List[ETFData]:
        """
        加载输入数据
        
        Returns:
            etf_data_list: ETFData 对象列表
        
        Raises:
            FileNotFoundError: 如果输入文件不存在
            ValueError: 如果输入数据无效
        """
        # 检查文件是否存在
        if not os.path.exists(self.input_file):
            error_msg = f"输入文件不存在: {self.input_file}"
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)
        
        # 加载 JSON
        try:
            with open(self.input_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        
        except json.JSONDecodeError as e:
            error_msg = f"输入文件 JSON 解析失败: {e}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # 提取 formal_pool
        if "formal_pool" not in data:
            error_msg = "输入文件缺少 'formal_pool' 字段"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        formal_pool = data["formal_pool"]
        
        if not formal_pool:
            error_msg = "'formal_pool' 为空"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # 转换为 ETFData 对象
        etf_data_list = []
        for i, item in enumerate(formal_pool):
            try:
                etf = create_etf_data_from_dict(item)
                etf_data_list.append(etf)
            
            except Exception as e:
                logger.warning(f"[{i+1}] 转换 ETFData 失败: {item.get('code', 'unknown')} - {e}")
                continue
        
        logger.info(f"成功加载 {len(etf_data_list)} 只 ETF（来自 {self.input_file}）")
        
        return etf_data_list
    
    def _run_risk_profiler(self) -> RiskConfig:
        """
        执行 RiskProfiler
        
        Returns:
            RiskConfig: 风险配置对象
        """
        profiler = RiskProfiler(self.risk_level)
        return profiler.get_config()
    
    def _run_data_quality_filter(
        self, 
        etfs: List[ETFData], 
        risk_config: RiskConfig
    ) -> List[ETFData]:
        """
        执行 DataQualityFilter
        
        Args:
            etfs: ETFData 对象列表
            risk_config: 风险配置对象
        
        Returns:
            filtered: 带 max_weight 的 ETF 列表
        """
        filter_obj = DataQualityFilter(risk_config)
        return filter_obj.filter(etfs)
    
    def _run_correlation_analyzer(
        self, 
        etfs: List[ETFData]
    ) -> Optional[Any]:
        """
        执行 CorrelationAnalyzer
        
        Args:
            etfs: 带 max_weight 的 ETF 列表
        
        Returns:
            matrix: 相关性矩阵（如果计算成功）
                     None（如果计算失败）
        """
        try:
            analyzer = CorrelationAnalyzer(cache_dir="data")
            
            # 尝试加载缓存
            matrix = analyzer.load_cached_matrix()
            
            if matrix is not None:
                logger.info("使用缓存的相关性矩阵")
                return matrix
            
            # 重新计算
            logger.info("重新计算相关性矩阵（可能需要 1-2 分钟）...")
            matrix = analyzer.compute_correlation(etfs, lookback_days=60)
            
            return matrix
        
        except Exception as e:
            logger.warning(f"相关性分析失败: {e}，跳过")
            return None
    
    def _run_portfolio_optimizer(
        self, 
        etfs: List[ETFData], 
        correlation_matrix: Any, 
        risk_config: RiskConfig
    ) -> List[ETFData]:
        """
        执行 PortfolioOptimizer
        
        Args:
            etfs: 带 max_weight 的 ETF 列表
            correlation_matrix: 相关性矩阵（可选）
            risk_config: 风险配置对象
        
        Returns:
            raw_portfolio: 带 weight 的 ETF 列表
        """
        optimizer = PortfolioOptimizer(risk_config, correlation_matrix)
        return optimizer.optimize(etfs)
    
    def _run_risk_controller(
        self, 
        portfolio: List[ETFData], 
        correlation_matrix: Any, 
        risk_config: RiskConfig
    ) -> tuple:
        """
        执行 RiskController
        
        Args:
            portfolio: 带 weight 的 ETF 列表
            correlation_matrix: 相关性矩阵（可选）
            risk_config: 风险配置对象
        
        Returns:
            tuple: (final_portfolio, warnings)
        """
        controller = RiskController(risk_config, correlation_matrix)
        return controller.apply_rules(portfolio)
    
    def _run_output_generator(
        self, 
        final_portfolio: List[ETFData], 
        risk_config: RiskConfig, 
        correlation_matrix: Any, 
        warnings: List[str]
    ) -> PortfolioResult:
        """
        执行 OutputGenerator
        
        Args:
            final_portfolio: 最终投资组合
            risk_config: 风险配置对象
            correlation_matrix: 相关性矩阵（可选）
            warnings: 警告信息列表
        
        Returns:
            PortfolioResult: 投资组合结果对象
        """
        generator = OutputGenerator(output_dir=os.path.dirname(self.output_file))
        return generator.generate(
            final_portfolio, 
            risk_config, 
            correlation_matrix, 
            warnings
        )
    
    def print_result(self) -> None:
        """
        打印最终结果（人类可读）
        """
        if self.result is None:
            print("⚠️ 结果尚未生成，请先调用 run()")
            return
        
        generator = OutputGenerator()
        generator.print_human_readable(self.result)


# ============================================================================
# 辅助函数（模块级）
# ============================================================================

def run_portfolio_engine(
    risk_level: str = "balanced",
    input_file: str = "output/low_valuation_candidates_latest.json",
    output_file: str = "output/portfolio_latest.json"
) -> Optional[PortfolioResult]:
    """
    快捷函数：运行 Portfolio Engine
    
    Args:
        risk_level: 风险等级
        input_file: 输入文件路径
        output_file: 输出文件路径
    
    Returns:
        PortfolioResult: 投资组合结果对象
    
    Example:
        >>> from portfolio_engine.engine import run_portfolio_engine
        >>> result = run_portfolio_engine(risk_level="balanced")
    """
    engine = PortfolioEngine(
        risk_level=risk_level,
        input_file=input_file,
        output_file=output_file
    )
    return engine.run()


# ============================================================================
# 独立运行测试
# ============================================================================

if __name__ == "__main__":
    """
    独立运行测试
    
    测试内容：
    1. 创建 PortfolioEngine 对象
    2. 执行完整流程（run()）
    3. 打印最终结果
    4. 测试快捷函数
    5. 错误处理（无效的输入文件）
    """
    
    print("=" * 80)
    print("PortfolioEngine 独立测试")
    print("=" * 80)
    print()
    
    # ------------------------------------------------------------------------
    # 测试1: 创建 PortfolioEngine 对象
    # ------------------------------------------------------------------------
    
    print("【测试1】创建 PortfolioEngine 对象")
    print("-" * 80)
    
    try:
        engine = PortfolioEngine(
            risk_level="balanced",
            input_file="output/low_valuation_candidates_latest.json",
            output_file="output/portfolio_latest.json"
        )
        
        print(f"✅ PortfolioEngine 创建成功")
        print(f"  - risk_level: {engine.risk_level}")
        print(f"  - input_file: {engine.input_file}")
        print(f"  - output_file: {engine.output_file}")
    
    except Exception as e:
        print(f"❌ PortfolioEngine 创建失败: {e}")
    
    print()
    
    # ------------------------------------------------------------------------
    # 测试2: 执行完整流程（run()）
    # ------------------------------------------------------------------------
    
    print("【测试2】执行完整流程（run()）")
    print("-" * 80)
    print("（这可能需要 2-3 分钟，请耐心等待...）")
    print()
    
    try:
        result = engine.run()
        
        print(f"✅ 完整流程执行成功！")
        print(f"  - meta['total_etfs']: {result.meta['total_etfs']}")
        print(f"  - meta['total_weight']: {result.meta['total_weight']:.2%}")
        print(f"  - meta['cash_weight']: {result.meta['cash_weight']:.2%}")
        print(f"  - portfolio length: {len(result.portfolio)}")
        print(f"  - warnings count: {len(result.warnings)}")
        print()
    
    except FileNotFoundError as e:
        print(f"⚠️ 输入文件不存在: {e}")
        print("   请先运行 ETF 数据采集流程，生成 low_valuation_candidates_latest.json")
        print()
    
    except Exception as e:
        print(f"❌ 完整流程执行失败: {e}")
        print()
    
    # ------------------------------------------------------------------------
    # 测试3: 打印最终结果
    # ------------------------------------------------------------------------
    
    print("【测试3】打印最终结果")
    print("-" * 80)
    
    try:
        if engine.result is not None:
            engine.print_result()
        else:
            print("⚠️ 结果尚未生成，跳过打印")
    
    except Exception as e:
        print(f"❌ 打印结果失败: {e}")
    
    print()
    
    # ------------------------------------------------------------------------
    # 测试4: 测试快捷函数
    # ------------------------------------------------------------------------
    
    print("【测试4】测试快捷函数")
    print("-" * 80)
    
    try:
        # 注意：如果输入文件不存在，会抛出异常
        print("正在调用 run_portfolio_engine()...")
        
        result_fast = run_portfolio_engine(
            risk_level="balanced",
            input_file="output/low_valuation_candidates_latest.json",
            output_file="output/portfolio_latest.json"
        )
        
        if result_fast is not None:
            print(f"✅ 快捷函数调用成功！")
            print(f"  - meta['risk_level']: {result_fast.meta['risk_level']}")
            print()
        else:
            print(f"⚠️ 快捷函数返回 None")
            print()
    
    except FileNotFoundError:
        print("⚠️ 输入文件不存在，跳过测试4")
        print()
    
    except Exception as e:
        print(f"❌ 快捷函数调用失败: {e}")
        print()
    
    # ------------------------------------------------------------------------
    # 测试5: 错误处理（无效的输入文件）
    # ------------------------------------------------------------------------
    
    print("【测试5】错误处理（无效的输入文件）")
    print("-" * 80)
    
    try:
        invalid_engine = PortfolioEngine(
            risk_level="balanced",
            input_file="invalid_file.json",
            output_file="output/test_output.json"
        )
        
        invalid_engine.run()
        print(f"❌ 应该抛出异常，但没有")
    
    except FileNotFoundError:
        print(f"✅ 正确捕获异常（文件不存在）")
    
    except Exception as e:
        print(f"✅ 捕获异常: {e}")
    
    print()
    
    # ------------------------------------------------------------------------
    # 完成
    # ------------------------------------------------------------------------
    
    print("=" * 80)
    print("✅ 所有测试完成！")
    print("=" * 80)
