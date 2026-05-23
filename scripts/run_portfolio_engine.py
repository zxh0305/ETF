#!/usr/bin/env python3
"""
Portfolio Engine CLI 入口脚本

功能：
1. 解析命令行参数（risk_level, input_file, output_file, --print）
2. 调用 PortfolioEngine.run()
3. 打印结果（可选）
4. 错误处理

使用方法：
    # 基础用法（默认 balanced，输出到 portfolio_latest.json）
    python3 scripts/run_portfolio_engine.py
    
    # 指定风险等级
    python3 scripts/run_portfolio_engine.py --risk-level aggressive
    
    # 指定输入/输出文件
    python3 scripts/run_portfolio_engine.py \
        --input-file output/low_valuation_candidates_latest.json \
        --output-file output/portfolio_latest.json
    
    # 打印人类可读报告
    python3 scripts/run_portfolio_engine.py --print
    
    # 组合使用
    python3 scripts/run_portfolio_engine.py \
        --risk-level balanced \
        --print \
        --output-file output/portfolio_balanced.json
"""

import sys
import os
import argparse
import logging
from typing import Optional

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from portfolio_engine.engine import PortfolioEngine, run_portfolio_engine
from portfolio_engine.output import load_portfolio_result


# ============================================================================
# 配置日志
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# 主函数
# ============================================================================

def main():
    """
    主函数：解析命令行参数，执行 Portfolio Engine
    """
    # ------------------------------------------------------------------------
    # 1. 解析命令行参数
    # ------------------------------------------------------------------------
    
    parser = argparse.ArgumentParser(
        description="ETF Portfolio Engine - 生成智能投资组合",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 基础用法（默认 balanced）
  python3 %(prog)s
  
  # 激进型配置
  python3 %(prog)s --risk-level aggressive
  
  # 指定输入/输出文件
  python3 %(prog)s --input-file data/input.json --output-file data/output.json
  
  # 打印人类可读报告
  python3 %(prog)s --print
  
  # 静默模式（只输出错误信息）
  python3 %(prog)s --quiet
        """
    )
    
    parser.add_argument(
        "--risk-level",
        type=str,
        choices=["conservative", "balanced", "aggressive"],
        default="balanced",
        help="风险等级（默认: balanced）"
    )
    
    parser.add_argument(
        "--input-file",
        type=str,
        default="output/low_valuation_candidates_latest.json",
        help="输入文件路径（包含正式池+观察池，默认: output/low_valuation_candidates_latest.json）"
    )
    
    parser.add_argument(
        "--output-file",
        type=str,
        default="output/portfolio_latest.json",
        help="输出文件路径（默认: output/portfolio_latest.json）"
    )
    
    parser.add_argument(
        "--print",
        action="store_true",
        help="打印人类可读报告"
    )
    
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="静默模式（只输出错误信息）"
    )
    
    args = parser.parse_args()
    
    # ------------------------------------------------------------------------
    # 2. 配置日志级别
    # ------------------------------------------------------------------------
    
    if args.quiet:
        logging.getLogger().setLevel(logging.WARNING)
    
    # ------------------------------------------------------------------------
    # 3. 执行 Portfolio Engine
    # ------------------------------------------------------------------------
    
    logger.info("=" * 80)
    logger.info("ETF Portfolio Engine CLI")
    logger.info("=" * 80)
    logger.info(f"风险等级: {args.risk_level}")
    logger.info(f"输入文件: {args.input_file}")
    logger.info(f"输出文件: {args.output_file}")
    logger.info("=" * 80)
    
    try:
        # 方法1：使用 PortfolioEngine 类（推荐）
        engine = PortfolioEngine(
            risk_level=args.risk_level,
            input_file=args.input_file,
            output_file=args.output_file
        )
        
        result = engine.run()
        
        # ------------------------------------------------------------------------
        # 4. 打印结果（可选）
        # ------------------------------------------------------------------------
        
        if args.print and result is not None:
            engine.print_result()
        
        # ------------------------------------------------------------------------
        # 5. 输出摘要
        # ------------------------------------------------------------------------
        
        if result is not None:
            logger.info("=" * 80)
            logger.info("✅ 执行完成！")
            logger.info("=" * 80)
            logger.info(f"📊 投资组合: {result.meta['total_etfs']} 只 ETF")
            logger.info(f"💰 总仓位: {result.meta['total_weight']:.2%}")
            logger.info(f"💵 现金比例: {result.meta['cash_weight']:.2%}")
            logger.info(f"⚠️  警告数量: {result.meta['warnings_count']} 条")
            logger.info(f"📄 输出文件: {args.output_file}")
            logger.info("=" * 80)
            
            # 返回成功
            sys.exit(0)
        
        else:
            logger.error("❌ 执行失败：result 为 None")
            sys.exit(1)
    
    # ------------------------------------------------------------------------
    # 6. 错误处理
    # ------------------------------------------------------------------------
    
    except FileNotFoundError as e:
        logger.error(f"❌ 输入文件不存在: {e}")
        logger.error("请先运行 ETF 数据采集流程，生成 low_valuation_candidates_latest.json")
        sys.exit(1)
    
    except ValueError as e:
        logger.error(f"❌ 输入数据无效: {e}")
        sys.exit(1)
    
    except RuntimeError as e:
        logger.error(f"❌ 执行失败: {e}")
        sys.exit(1)
    
    except Exception as e:
        logger.error(f"❌ 未知错误: {e}")
        sys.exit(1)


# ============================================================================
# 快捷函数（模块级）
# ============================================================================

def run_engine_cli(
    risk_level: str = "balanced",
    input_file: str = "output/low_valuation_candidates_latest.json",
    output_file: str = "output/portfolio_latest.json",
    print_result: bool = False
) -> int:
    """
    快捷函数：以编程方式运行 CLI
    
    Args:
        risk_level: 风险等级
        input_file: 输入文件路径
        output_file: 输出文件路径
        print_result: 是否打印结果
    
    Returns:
        int: 退出码（0=成功，1=失败）
    
    Example:
        >>> from scripts.run_portfolio_engine import run_engine_cli
        >>> exit_code = run_engine_cli(risk_level="balanced", print_result=True)
    """
    # 模拟命令行参数
    sys.argv = [
        "run_portfolio_engine.py",
        "--risk-level", risk_level,
        "--input-file", input_file,
        "--output-file", output_file
    ]
    
    if print_result:
        sys.argv.append("--print")
    
    # 调用主函数
    main()
    
    return 0  # 如果执行到这里，说明成功


# ============================================================================
# 独立运行
# ============================================================================

if __name__ == "__main__":
    """
    主入口：解析命令行参数并执行 Portfolio Engine
    """
    main()
