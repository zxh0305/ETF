# portfolio_engine/correlation.py
"""
相关性分析器（Correlation Analyzer）

计算 ETF 净值历史相关性，提供缓存机制（7天有效期）。

核心逻辑：
1. 获取 ETF 过去 60 日净值历史
2. 计算日收益率：（今日净值 - 昨日净值）/ 昨日净值
3. 计算收益率相关系数矩阵（N x N）
4. 缓存结果（避免重复计算）

输入：
- etfs: List[ETFData]（带 code 字段）
- lookback_days: 回溯天数（默认 60）

输出：
- correlation_matrix: np.ndarray（N x N 相关性矩阵）
"""

import sys
import os
import logging
from typing import List, Dict, Any, Optional
import numpy as np
import json
from datetime import datetime, timedelta
import time

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

from portfolio_engine.models import ETFData


# ============================================================================
# 配置日志
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# CorrelationAnalyzer 类
# ============================================================================

class CorrelationAnalyzer:
    """
    相关性分析器
    
    计算 ETF 净值历史相关性，提供缓存机制。
    """
    
    def __init__(self, cache_dir: str = "data"):
        """
        初始化相关性分析器
        
        Args:
            cache_dir: 缓存目录（相对于项目根目录）
        
        Raises:
            ValueError: 如果 cache_dir 无效
        """
        if not cache_dir:
            error_msg = "cache_dir 不能为空"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # 转换为绝对路径
        self.cache_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), 
            "..", 
            cache_dir
        )
        os.makedirs(self.cache_dir, exist_ok=True)
        
        self.cache_file = os.path.join(
            self.cache_dir, 
            "etf_correlation_cache.json"
        )
        
        logger.info(f"CorrelationAnalyzer 初始化完成，缓存目录: {self.cache_dir}")
    
    def compute_correlation(
        self, 
        etfs: List[ETFData], 
        lookback_days: int = 60
    ) -> Optional[np.ndarray]:
        """
        计算 ETF 相关性矩阵
        
        Args:
            etfs: ETFData 对象列表
            lookback_days: 回溯天数（默认 60）
        
        Returns:
            np.ndarray: 相关性矩阵（N x N），如果计算失败返回 None
        
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
        
        logger.info(f"开始计算 {len(etfs)} 只 ETF 的相关性矩阵（回溯 {lookback_days} 天）")
        
        # 校验 ETFData 对象
        valid_etfs = []
        for i, etf in enumerate(etfs):
            if not isinstance(etf, ETFData):
                logger.warning(f"[{i+1}] 跳过无效对象: {type(etf)}")
                continue
            
            if not etf.code:
                logger.warning(f"[{i+1}] ETF code 未设置，跳过")
                continue
            
            valid_etfs.append(etf)
        
        if len(valid_etfs) < 2:
            error_msg = f"有效 ETF 数量不足（需要 ≥2，实际 {len(valid_etfs)}）"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        logger.info(f"有效 ETF 数量: {len(valid_etfs)}")
        
        # ------------------------------------------------------------------------
        # 2. 获取历史净值数据
        # ------------------------------------------------------------------------
        
        logger.info("正在获取历史净值数据...")
        
        nav_data = {}  # code -> [nav1, nav2, ...]
        
        for etf in valid_etfs:
            try:
                navs = self._fetch_nav_history(etf.code, lookback_days)
                if navs and len(navs) >= 20:  # 至少 20 个交易日
                    nav_data[etf.code] = navs
                    logger.debug(f"  {etf.code} {etf.name}: {len(navs)} 条数据")
                else:
                    logger.warning(f"  {etf.code} {etf.name}: 数据不足（{len(navs) if navs else 0} 条）")
            
            except Exception as e:
                logger.warning(f"  {etf.code} {etf.name}: 获取失败 - {e}")
                continue
        
        # 检查是否有足够的数据
        if len(nav_data) < 2:
            error_msg = f"有效数据不足（需要 ≥2，实际 {len(nav_data)}）"
            logger.error(error_msg)
            return None
        
        logger.info(f"成功获取 {len(nav_data)} 只 ETF 的历史数据")
        
        # ------------------------------------------------------------------------
        # 3. 计算日收益率
        # ------------------------------------------------------------------------
        
        logger.info("正在计算日收益率...")
        
        return_rates = {}
        for code, navs in nav_data.items():
            returns = self._calculate_returns(navs)
            if returns is not None and len(returns) >= 20:
                return_rates[code] = returns
        
        if len(return_rates) < 2:
            error_msg = f"有效收益率数据不足（需要 ≥2，实际 {len(return_rates)}）"
            logger.error(error_msg)
            return None
        
        logger.info(f"成功计算 {len(return_rates)} 只 ETF 的收益率")
        
        # ------------------------------------------------------------------------
        # 4. 计算相关性矩阵
        # ------------------------------------------------------------------------
        
        logger.info("正在计算相关性矩阵...")
        
        codes = list(return_rates.keys())
        n = len(codes)
        
        # 构建收益率矩阵（每行一只 ETF，每列一个交易日）
        min_len = min([len(return_rates[code]) for code in codes])
        
        return_matrix = np.zeros((n, min_len))
        for i, code in enumerate(codes):
            return_matrix[i, :] = return_rates[code][-min_len:]  # 取最近的数据
        
        # 计算相关性矩阵
        correlation_matrix = np.corrcoef(return_matrix)
        
        # 保存缓存
        self._save_cache(correlation_matrix, codes)
        
        logger.info(f"✅ 相关性矩阵计算完成: {n} x {n}")
        
        return correlation_matrix
    
    def load_cached_matrix(self) -> Optional[np.ndarray]:
        """
        加载缓存的相关性矩阵
        
        Returns:
            np.ndarray: 相关性矩阵（如果缓存有效），否则返回 None
        """
        if not os.path.exists(self.cache_file):
            logger.info("缓存文件不存在")
            return None
        
        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                cache = json.load(f)
            
            # 检查缓存是否过期（7天）
            timestamp = cache.get("timestamp", 0)
            if time.time() - timestamp > 7 * 24 * 3600:
                logger.info("缓存已过期（>7天）")
                return None
            
            matrix = np.array(cache["matrix"])
            codes = cache["codes"]
            
            logger.info(f"✅ 加载缓存成功: {len(codes)} x {len(codes)} 矩阵")
            
            return matrix
        
        except Exception as e:
            logger.warning(f"加载缓存失败: {e}")
            return None
    
    def _fetch_nav_history(self, code: str, lookback_days: int) -> List[float]:
        """
        获取 ETF 历史净值数据
        
        Args:
            code: ETF 代码（如 "sh512880"）
            lookback_days: 回溯天数
        
        Returns:
            List[float]: 净值列表（按时间升序）
        
        Note:
            这是一个占位实现，实际需要调用 AkShare 或其他数据源。
            示例数据用于测试。
        """
        # TODO: 实际实现需要调用 akshare 的 fund_etf_hist_em() 或类似接口
        # 这里返回模拟数据用于测试
        
        logger.debug(f"正在获取 {code} 的历史净值（模拟数据）")
        
        # 模拟数据：生成 lookback_days 个净值（随机游走）
        np.random.seed(hash(code) % 2**32)  # 保证同一 code 生成相同数据
        
        navs = [1.0]  # 初始净值
        for _ in range(lookback_days):
            change = np.random.normal(0, 0.01)  # 日收益率均值0，标准差1%
            nav = navs[-1] * (1 + change)
            navs.append(nav)
        
        return navs[1:]  # 去掉初始值
    
    def _calculate_returns(self, navs: List[float]) -> Optional[np.ndarray]:
        """
        计算日收益率
        
        Args:
            navs: 净值列表（按时间升序）
        
        Returns:
            np.ndarray: 收益率数组
        """
        if not navs or len(navs) < 2:
            return None
        
        navs_array = np.array(navs)
        returns = (navs_array[1:] - navs_array[:-1]) / navs_array[:-1]
        
        return returns
    
    def _save_cache(self, matrix: np.ndarray, codes: List[str]) -> None:
        """
        保存相关性矩阵到缓存
        
        Args:
            matrix: 相关性矩阵
            codes: ETF 代码列表
        """
        try:
            cache = {
                "timestamp": time.time(),
                "codes": codes,
                "matrix": matrix.tolist()
            }
            
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
            
            logger.info(f"✅ 缓存保存成功: {self.cache_file}")
        
        except Exception as e:
            logger.warning(f"缓存保存失败: {e}")


# ============================================================================
# 辅助函数（模块级）
# ============================================================================

def compute_etf_correlation(
    etfs: List[ETFData], 
    lookback_days: int = 60,
    cache_dir: str = "data"
) -> Optional[np.ndarray]:
    """
    快捷函数：计算 ETF 相关性矩阵
    
    Args:
        etfs: ETF 列表
        lookback_days: 回溯天数
        cache_dir: 缓存目录
    
    Returns:
        np.ndarray: 相关性矩阵
    
    Example:
        >>> from portfolio_engine.correlation import compute_etf_correlation
        >>> matrix = compute_etf_correlation(etfs, lookback_days=60)
    """
    analyzer = CorrelationAnalyzer(cache_dir=cache_dir)
    
    # 尝试加载缓存
    matrix = analyzer.load_cached_matrix()
    if matrix is not None:
        return matrix
    
    # 重新计算
    return analyzer.compute_correlation(etfs, lookback_days)


# ============================================================================
# 独立运行测试
# ============================================================================

if __name__ == "__main__":
    """
    独立运行测试
    
    测试内容：
    1. 创建测试数据（模拟筛选系统输出）
    2. 创建 CorrelationAnalyzer 对象
    3. 计算相关性矩阵
    4. 测试缓存加载
    5. 测试错误处理
    """
    
    print("=" * 80)
    print("CorrelationAnalyzer 独立测试")
    print("=" * 80)
    print()
    
    # ------------------------------------------------------------------------
    # 测试1: 创建测试数据
    # ------------------------------------------------------------------------
    
    print("【测试1】创建测试数据")
    print("-" * 80)
    
    from portfolio_engine.models import create_etf_data_from_dict
    
    test_etfs = [
        {"code": "sh512880", "name": "证券公司ETF"},
        {"code": "sh512690", "name": "酒ETF"},
        {"code": "sh512290", "name": "生物医药ETF"},
        {"code": "sz159915", "name": "创业板ETF"},
        {"code": "sh510300", "name": "沪深300ETF"}
    ]
    
    etf_objects = [create_etf_data_from_dict(data) for data in test_etfs]
    
    print(f"✅ 创建测试数据成功: {len(etf_objects)} 只 ETF")
    print()
    
    # ------------------------------------------------------------------------
    # 测试2: 创建 CorrelationAnalyzer 对象
    # ------------------------------------------------------------------------
    
    print("【测试2】创建 CorrelationAnalyzer 对象")
    print("-" * 80)
    
    try:
        analyzer = CorrelationAnalyzer(cache_dir="data")
        print(f"✅ 创建 CorrelationAnalyzer 成功")
        print(f"  - cache_dir: {analyzer.cache_dir}")
        print(f"  - cache_file: {analyzer.cache_file}")
    
    except Exception as e:
        print(f"❌ 创建失败: {e}")
    
    print()
    
    # ------------------------------------------------------------------------
    # 测试3: 计算相关性矩阵
    # ------------------------------------------------------------------------
    
    print("【测试3】计算相关性矩阵")
    print("-" * 80)
    print("（这可能需要 1-2 分钟，请耐心等待...）")
    print()
    
    try:
        matrix = analyzer.compute_correlation(etf_objects, lookback_days=60)
        
        if matrix is not None:
            print(f"✅ 相关性矩阵计算成功:")
            print(f"  - shape: {matrix.shape}")
            print(f"  - dtype: {matrix.dtype}")
            print()
            print("相关性矩阵（前5x5）:")
            print(matrix[:5, :5])
            print()
        
        else:
            print(f"❌ 相关性矩阵计算失败: 返回 None")
            print()
    
    except Exception as e:
        print(f"❌ 计算失败: {e}")
        print()
    
    # ------------------------------------------------------------------------
    # 测试4: 测试缓存加载
    # ------------------------------------------------------------------------
    
    print("【测试4】测试缓存加载")
    print("-" * 80)
    
    try:
        cached_matrix = analyzer.load_cached_matrix()
        
        if cached_matrix is not None:
            print(f"✅ 缓存加载成功: {cached_matrix.shape}")
        
        else:
            print(f"⚠️  缓存不存在或已过期")
        
        print()
    
    except Exception as e:
        print(f"❌ 缓存加载失败: {e}")
        print()
    
    # ------------------------------------------------------------------------
    # 测试5: 测试快捷函数
    # ------------------------------------------------------------------------
    
    print("【测试5】测试快捷函数")
    print("-" * 80)
    
    try:
        matrix_fast = compute_etf_correlation(
            etf_objects, 
            lookback_days=60, 
            cache_dir="data"
        )
        
        if matrix_fast is not None:
            print(f"✅ 快捷函数调用成功: {matrix_fast.shape}")
        
        else:
            print(f"⚠️  快捷函数返回 None（可能是数据不足）")
        
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
        analyzer.compute_correlation([])
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
