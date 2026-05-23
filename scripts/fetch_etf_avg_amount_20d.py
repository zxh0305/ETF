#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETF 20日平均成交额计算器
=========================
获取所有ETF近20个交易日平均成交额，用于流动性筛选
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import akshare as ak

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("etf_avg_amount")

BASE_DIR = Path(__file__).parent.parent.resolve()
INPUT_FILE = BASE_DIR / "data" / "etf_spot_latest.json"
OUTPUT_FILE = BASE_DIR / "data" / "etf_avg_amount_20d.json"


def get_etf_avg_amount_20d(code: str, max_retries: int = 3) -> Optional[float]:
    """
    获取单个ETF近20日平均成交额
    
    Args:
        code: ETF代码（不带前缀）
        max_retries: 最大重试次数
    
    Returns:
        20日平均成交额（元），失败返回None
    """
    for attempt in range(max_retries):
        try:
            # 去掉代码前缀（如sz/sh）
            clean_code = code.replace("sz", "").replace("sh", "")
            
            # 获取历史数据
            df = ak.fund_etf_hist_em(symbol=clean_code, period="daily", adjust="")
            
            if df is None or len(df) == 0:
                return None
            
            # 取最近20个交易日
            recent_20 = df.tail(20)
            
            # 计算平均成交额
            avg_amount = recent_20['成交额'].mean()
            
            return avg_amount
            
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(0.5)
                continue
            else:
                logger.warning(f"获取 {code} 失败: {e}")
                return None
    
    return None


def main():
    """主函数"""
    logger.info("=" * 70)
    logger.info("ETF 20日平均成交额计算器")
    logger.info("=" * 70)
    
    start_time = datetime.now()
    
    # 读取ETF列表
    if not INPUT_FILE.exists():
        logger.error(f"输入文件不存在: {INPUT_FILE}")
        return
    
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        spot_data = json.load(f)
    
    etf_list = spot_data.get('data', [])
    logger.info(f"共 {len(etf_list)} 只ETF需要处理")
    
    # 计算每只ETF的20日平均成交额
    results = {}
    success_count = 0
    fail_count = 0
    
    for i, etf in enumerate(etf_list, 1):
        code = etf.get('code', '')
        name = etf.get('name', '')
        
        if i % 50 == 0:
            logger.info(f"进度: {i}/{len(etf_list)}")
        
        avg_amount = get_etf_avg_amount_20d(code)
        
        if avg_amount is not None:
            results[code] = {
                "name": name,
                "avg_amount_20d": avg_amount,
                "avg_amount_20d_yi": round(avg_amount / 1e8, 2),
            }
            success_count += 1
        else:
            results[code] = {
                "name": name,
                "avg_amount_20d": None,
                "avg_amount_20d_yi": None,
            }
            fail_count += 1
        
        # 避免请求过快
        time.sleep(0.1)
    
    # 保存结果
    output = {
        "meta": {
            "generated_at": datetime.now().isoformat(),
            "total_count": len(etf_list),
            "success_count": success_count,
            "fail_count": fail_count,
            "period_days": 20,
        },
        "data": results,
    }
    
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, ensure_ascii=False, indent=2, fp=f)
    
    duration = (datetime.now() - start_time).total_seconds()
    
    logger.info("=" * 70)
    logger.info(f"✅ 完成！耗时: {duration:.1f}秒")
    logger.info(f"   成功: {success_count}只")
    logger.info(f"   失败: {fail_count}只")
    logger.info(f"   输出: {OUTPUT_FILE}")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
