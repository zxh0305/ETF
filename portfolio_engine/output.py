# portfolio_engine/output.py
"""
输出生成器（Output Generator）

生成最终输出（JSON + 人类可读报告）。

输出内容：
1. portfolio_latest.json（机器可读）
2. 人类可读报告（打印到控制台）

输入：
- final_portfolio: List[ETFData]（最终投资组合）
- risk_config: RiskConfig
- correlation_matrix: np.ndarray（可选）
- warnings: List[str]

输出：
- PortfolioResult 对象（可保存为 JSON）
"""

import sys
import os
import logging
from typing import List, Dict, Any, Optional
import json
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

from portfolio_engine.models import (
    ETFData, 
    RiskConfig, 
    PortfolioItem, 
    PortfolioResult
)


# ============================================================================
# 配置日志
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# OutputGenerator 类
# ============================================================================

class OutputGenerator:
    """
    输出生成器
    
    生成最终输出（JSON + 人类可读报告）。
    """
    
    def __init__(self, output_dir: str = "output"):
        """
        初始化输出生成器
        
        Args:
            output_dir: 输出目录（相对于项目根目录）
        
        Raises:
            ValueError: 如果 output_dir 无效
        """
        if not output_dir:
            error_msg = "output_dir 不能为空"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # 转换为绝对路径
        self.output_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), 
            "..", 
            output_dir
        )
        os.makedirs(self.output_dir, exist_ok=True)
        
        logger.info(f"OutputGenerator 初始化完成，输出目录: {self.output_dir}")
    
    def generate(
        self, 
        final_portfolio: List[ETFData], 
        risk_config: RiskConfig, 
        correlation_matrix: Optional[Any] = None, 
        warnings: Optional[List[str]] = None
    ) -> PortfolioResult:
        """
        生成最终输出
        
        Args:
            final_portfolio: 最终投资组合（List[ETFData]）
            risk_config: 风险配置对象
            correlation_matrix: 相关性矩阵（可选）
            warnings: 警告信息列表（可选）
        
        Returns:
            PortfolioResult: 投资组合结果对象
        
        Raises:
            ValueError: 如果 final_portfolio 为空或包含无效数据
        """
        # ------------------------------------------------------------------------
        # 1. 输入校验
        # ------------------------------------------------------------------------
        
        if not final_portfolio:
            error_msg = "final_portfolio 列表不能为空"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        logger.info(f"开始生成输出：{len(final_portfolio)} 只 ETF")
        
        # 校验 ETFData 对象
        valid_portfolio = []
        for i, etf in enumerate(final_portfolio):
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
        # 2. 构建 PortfolioItem 列表
        # ------------------------------------------------------------------------
        
        logger.info("正在构建 PortfolioItem 列表...")
        
        portfolio_items = []
        for etf in valid_portfolio:
            # 生成推荐理由
            reason = self._generate_reason(etf)
            
            # 创建 PortfolioItem 对象
            item = PortfolioItem(
                code=etf.code,
                name=etf.name,
                weight=etf.weight,
                reason=reason,
                data_quality=etf.data_quality,
                pe_percentile=etf.pe_percentile,
                pb_percentile=etf.pb_percentile,
                avg_amount_20d=etf.avg_amount_20d,
                score=etf.score
            )
            
            portfolio_items.append(item)
        
        logger.info(f"✅ PortfolioItem 列表构建完成: {len(portfolio_items)} 只 ETF")
        
        # ------------------------------------------------------------------------
        # 3. 构建 meta 信息
        # ------------------------------------------------------------------------
        
        logger.info("正在构建 meta 信息...")
        
        total_weight = sum([item.weight for item in portfolio_items])
        cash_weight = 1.0 - total_weight
        
        meta = {
            "generate_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "risk_level": risk_config.risk_level,
            "total_etfs": len(portfolio_items),
            "total_weight": total_weight,
            "cash_weight": cash_weight,
            "warnings_count": len(warnings) if warnings else 0
        }
        
        logger.info(f"✅ meta 信息构建完成:")
        logger.info(f"  - generate_time: {meta['generate_time']}")
        logger.info(f"  - total_etfs: {meta['total_etfs']}")
        logger.info(f"  - total_weight: {meta['total_weight']:.2%}")
        logger.info(f"  - cash_weight: {meta['cash_weight']:.2%}")
        
        # ------------------------------------------------------------------------
        # 4. 构建 correlation 信息（可选）
        # ------------------------------------------------------------------------
        
        correlation_info = None
        if correlation_matrix is not None:
            logger.info("正在构建 correlation 信息...")
            
            # 简化：只保存高相关ETF对
            threshold = risk_config.correlation_threshold
            high_corr_pairs = []
            
            n = len(valid_portfolio)
            for i in range(n):
                for j in range(i+1, n):
                    corr = correlation_matrix[i, j]
                    if corr > threshold:
                        high_corr_pairs.append({
                            "etf1": valid_portfolio[i].code,
                            "etf2": valid_portfolio[j].code,
                            "correlation": float(corr)
                        })
            
            correlation_info = {
                "threshold": threshold,
                "high_corr_pairs": high_corr_pairs
            }
            
            logger.info(f"✅ correlation 信息构建完成: {len(high_corr_pairs)} 对高相关ETF")
        
        # ------------------------------------------------------------------------
        # 5. 创建 PortfolioResult 对象
        # ------------------------------------------------------------------------
        
        logger.info("正在创建 PortfolioResult 对象...")
        
        result = PortfolioResult(
            meta=meta,
            portfolio=portfolio_items,
            risk_config=risk_config,
            correlation=correlation_info,
            warnings=warnings if warnings else []
        )
        
        logger.info(f"✅ PortfolioResult 对象创建完成")
        
        # ------------------------------------------------------------------------
        # 6. 保存为 JSON 文件
        # ------------------------------------------------------------------------
        
        logger.info("正在保存 JSON 文件...")
        
        output_file = os.path.join(self.output_dir, "portfolio_latest.json")
        result.save(output_file)
        
        logger.info(f"✅ JSON 文件保存成功: {output_file}")
        
        # ------------------------------------------------------------------------
        # 7. 返回结果
        # ------------------------------------------------------------------------
        
        logger.info(f"✅ 输出生成完成！")
        
        return result
    
    def _generate_reason(self, etf: ETFData) -> str:
        """
        生成推荐理由（人类可读）
        
        Args:
            etf: ETFData 对象
        
        Returns:
            str: 推荐理由
        """
        reasons = []
        
        # PE% 理由
        if etf.pe_percentile is not None:
            pe_status = "低估" if etf.pe_percentile <= 30 else "中等" if etf.pe_percentile <= 70 else "高估"
            reasons.append(f"PE%={etf.pe_percentile:.0f}%（{pe_status}）")
        
        # PB% 理由
        if etf.pb_percentile is not None:
            pb_status = "低估" if etf.pb_percentile <= 30 else "中等" if etf.pb_percentile <= 70 else "高估"
            reasons.append(f"PB%={etf.pb_percentile:.0f}%（{pb_status}）")
        
        # 数据质量理由
        if etf.data_quality == "REAL":
            reasons.append("✅真实历史分位（乐咕乐股20年数据）")
        elif etf.data_quality == "ESTIMATED":
            reasons.append("⚠️估算数据（申万行业）")
        
        # 成交额理由
        if etf.avg_amount_20d is not None:
            if etf.avg_amount_20d >= 1e8:
                reasons.append(f"成交额={etf.avg_amount_20d/1e8:.1f}亿（充足）")
            else:
                reasons.append(f"成交额={etf.avg_amount_20d/1e4:.1f}万（一般）")
        
        return "；".join(reasons)
    
    def print_human_readable(self, result: PortfolioResult) -> None:
        """
        打印人类可读报告
        
        Args:
            result: PortfolioResult 对象
        """
        print("=" * 80)
        print(f"ETF 投资组合建议（{result.meta['risk_level'].upper()}）")
        print("=" * 80)
        print()
        print(f"生成时间: {result.meta['generate_time']}")
        print(f"ETF 数量: {result.meta['total_etfs']} 只")
        print(f"总仓位: {result.meta['total_weight']:.2%}")
        print(f"现金比例: {result.meta['cash_weight']:.2%}")
        print()
        
        print("投资组合:")
        print("-" * 80)
        for i, item in enumerate(result.portfolio):
            print(f"{i+1}. {item.code} {item.name}")
            print(f"   仓位: {item.weight:.2%}")
            print(f"   理由: {item.reason}")
            print()
        
        if result.warnings:
            print("警告信息:")
            print("-" * 80)
            for i, warning in enumerate(result.warnings):
                print(f"{i+1}. {warning}")
            print()
        
        print("=" * 80)


# ============================================================================
# 辅助函数（模块级）
# ============================================================================

def generate_portfolio_output(
    final_portfolio: List[ETFData], 
    risk_config: RiskConfig, 
    correlation_matrix: Optional[Any] = None, 
    warnings: Optional[List[str]] = None,
    output_dir: str = "output"
) -> PortfolioResult:
    """
    快捷函数：生成投资组合输出
    
    Args:
        final_portfolio: 最终投资组合
        risk_config: 风险配置
        correlation_matrix: 相关性矩阵（可选）
        warnings: 警告信息列表（可选）
        output_dir: 输出目录
    
    Returns:
        PortfolioResult: 投资组合结果对象
    
    Example:
        >>> from portfolio_engine.output import generate_portfolio_output
        >>> result = generate_portfolio_output(portfolio, config, matrix, warnings)
    """
    generator = OutputGenerator(output_dir=output_dir)
    return generator.generate(
        final_portfolio, 
        risk_config, 
        correlation_matrix, 
        warnings
    )


def load_portfolio_result(file_path: str) -> PortfolioResult:
    """
    加载投资组合结果（从 JSON 文件）
    
    Args:
        file_path: JSON 文件路径
    
    Returns:
        PortfolioResult: 投资组合结果对象
    
    Example:
        >>> from portfolio_engine.output import load_portfolio_result
        >>> result = load_portfolio_result("output/portfolio_latest.json")
    """
    return PortfolioResult.from_json(file_path)


# ============================================================================
# 独立运行测试
# ============================================================================

if __name__ == "__main__":
    """
    独立运行测试
    
    测试内容：
    1. 创建测试数据（模拟 RiskController 输出）
    2. 创建 RiskConfig（balanced）
    3. 创建 OutputGenerator 对象
    4. 执行 generate()
    5. 验证输出文件
    6. 测试 print_human_readable()
    7. 测试快捷函数
    8. 测试 load_portfolio_result()
    """
    
    print("=" * 80)
    print("OutputGenerator 独立测试")
    print("=" * 80)
    print()
    
    # ------------------------------------------------------------------------
    # 测试1: 创建测试数据（模拟 RiskController 输出）
    # ------------------------------------------------------------------------
    
    print("【测试1】创建测试数据（模拟 RiskController 输出）")
    print("-" * 80)
    
    from portfolio_engine.models import create_etf_data_from_dict
    
    # 模拟 4 只 ETF（2只 REAL，2只 ESTIMATED）
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
            "weight": 0.25
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
            "weight": 0.15
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
            "weight": 0.20
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
    # 测试3: 创建 OutputGenerator 对象
    # ------------------------------------------------------------------------
    
    print("【测试3】创建 OutputGenerator 对象")
    print("-" * 80)
    
    try:
        generator = OutputGenerator(output_dir="output")
        print(f"✅ 创建 OutputGenerator 成功")
        print(f"  - output_dir: {generator.output_dir}")
    
    except ValueError as e:
        print(f"❌ 创建失败: {e}")
    
    print()
    
    # ------------------------------------------------------------------------
    # 测试4: 执行 generate()
    # ------------------------------------------------------------------------
    
    print("【测试4】执行 generate()")
    print("-" * 80)
    
    try:
        result = generator.generate(
            final_portfolio=etf_objects,
            risk_config=config,
            correlation_matrix=None,
            warnings=["总仓位上限触发: 合计 80.00% > 上限 80%"]
        )
        
        print(f"✅ 输出生成成功:")
        print(f"  - meta['total_etfs']: {result.meta['total_etfs']}")
        print(f"  - meta['total_weight']: {result.meta['total_weight']:.2%}")
        print(f"  - portfolio length: {len(result.portfolio)}")
        print(f"  - warnings count: {len(result.warnings)}")
        print()
    
    except Exception as e:
        print(f"❌ 输出生成失败: {e}")
        print()
    
    # ------------------------------------------------------------------------
    # 测试5: 验证输出文件
    # ------------------------------------------------------------------------
    
    print("【测试5】验证输出文件")
    print("-" * 80)
    
    output_file = "output/portfolio_latest.json"
    output_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), 
        "..", 
        output_file
    )
    
    if os.path.exists(output_path):
        print(f"✅ 输出文件存在: {output_path}")
        
        # 验证 JSON 格式
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            print(f"✅ JSON 格式验证通过:")
            print(f"  - meta['risk_level']: {data['meta']['risk_level']}")
            print(f"  - portfolio length: {len(data['portfolio'])}")
            print()
        
        except Exception as e:
            print(f"❌ JSON 格式验证失败: {e}")
            print()
    
    else:
        print(f"❌ 输出文件不存在: {output_path}")
        print()
    
    # ------------------------------------------------------------------------
    # 测试6: 测试 print_human_readable()
    # ------------------------------------------------------------------------
    
    print("【测试6】测试 print_human_readable()")
    print("-" * 80)
    
    try:
        generator.print_human_readable(result)
        print("✅ print_human_readable() 成功")
        print()
    
    except Exception as e:
        print(f"❌ print_human_readable() 失败: {e}")
        print()
    
    # ------------------------------------------------------------------------
    # 测试7: 测试快捷函数
    # ------------------------------------------------------------------------
    
    print("【测试7】测试快捷函数")
    print("-" * 80)
    
    try:
        result_fast = generate_portfolio_output(
            final_portfolio=etf_objects,
            risk_config=config,
            correlation_matrix=None,
            warnings=[],
            output_dir="output"
        )
        
        print(f"✅ 快捷函数调用成功:")
        print(f"  - meta['risk_level']: {result_fast.meta['risk_level']}")
        print()
    
    except Exception as e:
        print(f"❌ 快捷函数调用失败: {e}")
        print()
    
    # ------------------------------------------------------------------------
    # 测试8: 测试 load_portfolio_result()
    # ------------------------------------------------------------------------
    
    print("【测试8】测试 load_portfolio_result()")
    print("-" * 80)
    
    try:
        loaded_result = load_portfolio_result(output_path)
        
        print(f"✅ load_portfolio_result() 成功:")
        print(f"  - meta['risk_level']: {loaded_result.meta['risk_level']}")
        print(f"  - portfolio length: {len(loaded_result.portfolio)}")
        print()
    
    except Exception as e:
        print(f"❌ load_portfolio_result() 失败: {e}")
        print()
    
    # ------------------------------------------------------------------------
    # 完成
    # ------------------------------------------------------------------------
    
    print("=" * 80)
    print("✅ 所有测试完成！")
    print("=" * 80)
